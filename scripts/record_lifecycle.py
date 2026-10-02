#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from session_authority import advance_session_revision, require_operation_authority
from state_io import StateError, read_json, require_workspace, resolve_workspace
from state_store import advance_store_head, commit_operation, digest_json, find_operation, list_operation_records, writer_lock

KIND = "record_lifecycle"
FMT = "aham-brahmasmi-record-lifecycle-view"
VERSION = 1
OPID = re.compile(r"^[A-Za-z0-9._-]{1,80}$")


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StateError(f"{name} must be a non-empty string")
    return value.strip()


def _id(prefix: str, operation_id: str, revision: int, index: int, content: str) -> str:
    raw = f"{prefix}\0{operation_id}\0{revision}\0{index}\0{content}".encode()
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()[:32]}"


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _prov(operation_id: str, revision: int, source_type: str, content: str, source: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"operation_id": operation_id, "revision": revision, "source_type": source_type, "content_digest": _digest(content)}
    if source is not None:
        out["source"] = source
    return out


def _event(action: str, operation_id: str, revision: int, reason: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"action": action, "operation_id": operation_id, "revision": revision}
    if reason is not None:
        out["reason"] = reason
    return out


def validate_request(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise StateError("record lifecycle request must be an object")
    operation_id = _text(value.get("operation_id"), "operation_id")
    if not OPID.fullmatch(operation_id):
        raise StateError("operation_id contains unsupported characters")
    action = _text(value.get("action"), "action")
    required = {
        "fact_assert": {"operation_id", "action", "statement", "source"},
        "fact_supersede": {"operation_id", "action", "fact_id", "statement", "source", "reason"},
        "fact_retract": {"operation_id", "action", "fact_id", "reason"},
        "task_complete": {"operation_id", "action", "task_id", "reason"},
        "task_cancel": {"operation_id", "action", "task_id", "reason"},
    }
    if action not in required:
        raise StateError(f"unsupported record lifecycle action: {action}")
    optional = {"conflicts_with"} if action == "fact_assert" else set()
    unknown = set(value) - required[action] - optional
    missing = required[action] - set(value)
    if unknown or missing:
        detail = ", ".join(sorted(unknown or missing))
        raise StateError(("unknown" if unknown else "missing") + f" record lifecycle fields: {detail}")
    out = dict(value)
    out["operation_id"] = operation_id
    out["action"] = action
    for field in ("statement", "source", "reason", "fact_id", "task_id"):
        if field in out:
            out[field] = _text(out[field], field)
    if action == "fact_assert":
        conflicts = out.get("conflicts_with", [])
        if not isinstance(conflicts, list) or any(not isinstance(x, str) or not x for x in conflicts) or len(set(conflicts)) != len(conflicts):
            raise StateError("conflicts_with must be a unique list of fact IDs")
        out["conflicts_with"] = list(conflicts)
    return out


def _wrap_records(record: dict[str, Any], facts: list[dict[str, Any]], tasks: list[dict[str, Any]]) -> None:
    details = record.get("details")
    receipt = details.get("receipt") if isinstance(details, dict) else None
    bundle = receipt.get("bundle") if isinstance(receipt, dict) else None
    if not isinstance(bundle, dict):
        raise StateError("wrap-up record has no canonical bundle")
    for index, statement in enumerate(bundle.get("durable_facts", [])):
        fid = _id("fact", record["operation_id"], record["revision"], index, statement)
        facts.append({"fact_id": fid, "statement": statement, "status": "active", "provenance": _prov(record["operation_id"], record["revision"], "wrap_up", statement), "conflicts_with": [], "superseded_by": None, "supersedes": None, "events": [_event("asserted", record["operation_id"], record["revision"])]})
    for index, description in enumerate(bundle.get("unfinished_work", [])):
        tid = _id("task", record["operation_id"], record["revision"], index, description)
        tasks.append({"task_id": tid, "description": description, "status": "open", "provenance": _prov(record["operation_id"], record["revision"], "wrap_up", description), "events": [_event("opened", record["operation_id"], record["revision"])]})


def _apply(request: dict[str, Any], revision: int, facts: list[dict[str, Any]], tasks: list[dict[str, Any]]) -> dict[str, Any]:
    action = request["action"]
    operation_id = request["operation_id"]
    by_fact = {x["fact_id"]: x for x in facts}
    by_task = {x["task_id"]: x for x in tasks}
    if action == "fact_assert":
        for cid in request["conflicts_with"]:
            if cid not in by_fact:
                raise StateError(f"conflicting fact does not exist: {cid}")
        fid = _id("fact", operation_id, revision, 0, request["statement"])
        item = {"fact_id": fid, "statement": request["statement"], "status": "active", "provenance": _prov(operation_id, revision, KIND, request["statement"], request["source"]), "conflicts_with": list(request["conflicts_with"]), "superseded_by": None, "supersedes": None, "events": [_event("asserted", operation_id, revision)]}
        for cid in request["conflicts_with"]:
            if fid not in by_fact[cid]["conflicts_with"]:
                by_fact[cid]["conflicts_with"].append(fid)
        facts.append(item)
        return {"target_id": fid, "result_id": fid}
    if action == "fact_supersede":
        old = by_fact.get(request["fact_id"])
        if old is None or old["status"] != "active":
            raise StateError("fact supersede requires an existing active fact")
        fid = _id("fact", operation_id, revision, 0, request["statement"])
        old["status"] = "superseded"
        old["superseded_by"] = fid
        old["events"].append(_event("superseded", operation_id, revision, request["reason"]))
        facts.append({"fact_id": fid, "statement": request["statement"], "status": "active", "provenance": _prov(operation_id, revision, KIND, request["statement"], request["source"]), "conflicts_with": [], "superseded_by": None, "supersedes": old["fact_id"], "events": [_event("asserted", operation_id, revision, request["reason"])]})
        return {"target_id": old["fact_id"], "result_id": fid}
    if action == "fact_retract":
        old = by_fact.get(request["fact_id"])
        if old is None or old["status"] != "active":
            raise StateError("fact retract requires an existing active fact")
        old["status"] = "retracted"
        old["events"].append(_event("retracted", operation_id, revision, request["reason"]))
        return {"target_id": old["fact_id"], "result_id": None}
    task = by_task.get(request["task_id"])
    if task is None or task["status"] != "open":
        raise StateError("task transition requires an existing open task")
    if action == "task_complete":
        task["status"] = "completed"
        task["events"].append(_event("completed", operation_id, revision, request["reason"]))
    else:
        task["status"] = "cancelled"
        task["events"].append(_event("cancelled", operation_id, revision, request["reason"]))
    return {"target_id": task["task_id"], "result_id": None}


def replay(workspace: Path) -> dict[str, Any]:
    require_workspace(workspace)
    return replay_records(list_operation_records(workspace))


def replay_records(records: list) -> dict[str, Any]:
    """Replay one validated immutable ledger snapshot, as returned by the store."""
    facts: list[dict[str, Any]] = []
    tasks: list[dict[str, Any]] = []
    revision = 0
    for _, record in records:
        revision = record["revision"]
        if record["kind"] == "wrap_up":
            _wrap_records(record, facts, tasks)
        elif record["kind"] == KIND:
            details = record.get("details")
            request = validate_request(details.get("request") if isinstance(details, dict) else None)
            if digest_json(request) != record["payload_digest"]:
                raise StateError("record lifecycle digest mismatch")
            _apply(request, revision, facts, tasks)
    return {"format": FMT, "version": VERSION, "revision": revision, "facts": facts, "tasks": tasks}


def _verified_receipt(workspace: Path, record: dict[str, Any]) -> dict[str, Any]:
    if record.get("kind") != KIND:
        raise StateError("operation is not record_lifecycle")
    details = record.get("details")
    request = validate_request(details.get("request") if isinstance(details, dict) else None)
    receipt = dict(details.get("receipt", {})) if isinstance(details, dict) else {}
    if digest_json(request) != record["payload_digest"] or receipt.get("revision") != record["revision"] or receipt.get("operation_id") != record["operation_id"]:
        raise StateError("record lifecycle receipt conflicts with immutable operation")
    state = replay(workspace)
    facts = {x["fact_id"]: x for x in state["facts"]}
    tasks = {x["task_id"]: x for x in state["tasks"]}
    target = receipt.get("target_id")
    expected = {"fact_retract": "retracted", "task_complete": "completed", "task_cancel": "cancelled"}.get(request["action"])
    if expected is not None:
        current = facts.get(target) if request["action"].startswith("fact_") else tasks.get(target)
        if current is None or current["status"] != expected:
            raise StateError("replayed lifecycle state does not verify receipt")
    elif request["action"] == "fact_supersede":
        if target not in facts or facts[target]["status"] != "superseded" or receipt.get("result_id") not in facts:
            raise StateError("replayed supersede state does not verify receipt")
    elif target not in facts:
        raise StateError("replayed asserted fact does not verify receipt")
    receipt["independently_verified"] = True
    return receipt


def apply_request(workspace: Path, request: dict[str, Any], session_id: str | None) -> tuple[dict[str, Any], bool]:
    digest = digest_json(request)
    with writer_lock(workspace) as head:
        found = find_operation(workspace, request["operation_id"])
        if found:
            _, record = found
            if record["kind"] != KIND or record["payload_digest"] != digest:
                raise StateError("operation_id is already committed with different content")
            return _verified_receipt(workspace, record), True
        session = require_operation_authority(workspace, "wrap_up", session_id=session_id, committed_revision=head["revision"])
        state = replay(workspace)
        outcome = _apply(request, head["revision"] + 1, copy.deepcopy(state["facts"]), copy.deepcopy(state["tasks"]))
        receipt = {"status": "complete", "kind": KIND, "operation_id": request["operation_id"], "revision": head["revision"] + 1, "action": request["action"], "target_id": outcome["target_id"], "result_id": outcome["result_id"], "payload_digest": digest}
        path, record = commit_operation(workspace, operation_id=request["operation_id"], kind=KIND, payload_digest=digest, details={"request": request, "receipt": receipt}, target_revision=head["revision"] + 1)
        advance_store_head(workspace, path, record)
        advance_session_revision(workspace, session, record["revision"])
        return _verified_receipt(workspace, record), False


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("list"); a.add_argument("--workspace", required=True); a.add_argument("--json", action="store_true")
    a = sub.add_parser("apply"); a.add_argument("--workspace", required=True); a.add_argument("--request", required=True); a.add_argument("--session-id"); a.add_argument("--json", action="store_true")
    a = sub.add_parser("status"); a.add_argument("--workspace", required=True); a.add_argument("--operation-id", required=True); a.add_argument("--json", action="store_true")
    return p


def emit(value: dict[str, Any], as_json: bool) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":")) if as_json else json.dumps(value, indent=2, sort_keys=True))


def main() -> int:
    args = parser().parse_args()
    workspace = resolve_workspace(args.workspace)
    if args.command == "list":
        emit(replay(workspace), args.json); return 0
    if args.command == "apply":
        request = validate_request(read_json(Path(args.request)))
        receipt, reused = apply_request(workspace, request, args.session_id)
        if reused:
            print("EXISTING RECEIPT REUSED")
        emit(receipt, args.json); return 0
    found = find_operation(workspace, _text(args.operation_id, "operation_id"))
    if not found:
        raise StateError("no committed record lifecycle operation found")
    emit(_verified_receipt(workspace, found[1]), args.json); return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except StateError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
