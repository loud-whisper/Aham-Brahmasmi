#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from project_state import checkpoint_file_from_record, project_by_id, project_ids_from_record
from record_lifecycle import replay
from state_io import (
    StateError,
    read_json,
    require_workspace,
    resolve_workspace,
    validate_checkpoint,
    workspace_fingerprint,
)
from state_store import list_operation_records

FORMAT = "aham-brahmasmi-context-packet"
VERSION = 1


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def packet_digest(packet: dict[str, Any]) -> str:
    material = dict(packet)
    material.pop("packet_sha256", None)
    return hashlib.sha256(canonical_json(material).encode("utf-8")).hexdigest()


def encoded_size(packet: dict[str, Any]) -> int:
    return len((canonical_json(packet) + "\n").encode("utf-8"))


def operation_projects(workspace: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for _, record in list_operation_records(workspace):
        out[record["operation_id"]] = project_ids_from_record(workspace, record)
    return out


def record_scopes(
    state: dict[str, Any], op_projects: dict[str, list[str]]
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    fact_scopes: dict[str, set[str]] = {}
    task_scopes: dict[str, set[str]] = {}
    facts_by_id = {item["fact_id"]: item for item in state["facts"]}

    # Legacy wrap-up facts/tasks do not carry per-item project identity. They may be
    # projected into a packet only when the authoritative operation names exactly one
    # project; otherwise they remain intentionally unscoped rather than leaking across
    # every project mentioned by the operation.
    for fact in state["facts"]:
        provenance = fact.get("provenance", {})
        if provenance.get("source_type") == "wrap_up":
            projects = op_projects.get(provenance.get("operation_id"), [])
            if len(projects) == 1:
                fact_scopes[fact["fact_id"]] = {projects[0]}
    for task in state["tasks"]:
        provenance = task.get("provenance", {})
        if provenance.get("source_type") == "wrap_up":
            projects = op_projects.get(provenance.get("operation_id"), [])
            if len(projects) == 1:
                task_scopes[task["task_id"]] = {projects[0]}

    # A superseding fact inherits the scope of the fact it replaces. Explicit assertions
    # with no project binding remain global/unscoped and are not injected into a project packet.
    changed = True
    while changed:
        changed = False
        for fact_id, fact in facts_by_id.items():
            if fact_id in fact_scopes:
                continue
            parent = fact.get("supersedes")
            if isinstance(parent, str) and parent in fact_scopes:
                fact_scopes[fact_id] = set(fact_scopes[parent])
                changed = True
    return fact_scopes, task_scopes


def validated_checkpoint(workspace: Path, reference: str, record: dict[str, Any]) -> dict[str, Any]:
    checkpoint = read_json(workspace / reference)
    errors = validate_checkpoint(checkpoint)
    if errors:
        raise StateError("checkpoint failed validation: " + "; ".join(errors))
    brain = require_workspace(workspace)
    if checkpoint.get("workspace_fingerprint") != workspace_fingerprint(brain):
        raise StateError("checkpoint belongs to a different workspace identity")
    if checkpoint.get("revision") != record["revision"]:
        raise StateError("project checkpoint revision does not match authoritative operation")
    return checkpoint


def latest_checkpoint(workspace: Path, project_id: str) -> dict[str, Any]:
    display_name = project_by_id(workspace, project_id)["display_name"]
    candidates: list[tuple[dict[str, Any], str, dict[str, Any]]] = []
    for _, record in list_operation_records(workspace):
        reference = checkpoint_file_from_record(record)
        if not reference or project_id not in project_ids_from_record(workspace, record):
            continue
        checkpoint = validated_checkpoint(workspace, reference, record)
        if checkpoint.get("project") == display_name:
            candidates.append((record, reference, checkpoint))
    if not candidates:
        raise StateError("no committed checkpoint exists for requested project")
    record, reference, checkpoint = candidates[-1]
    return {
        "id": checkpoint.get("id"),
        "revision": record["revision"],
        "summary": checkpoint.get("summary"),
        "completed": list(checkpoint.get("completed", [])),
        "next_steps": list(checkpoint.get("next_steps", [])),
        "source": reference,
    }


def project_updates(workspace: Path, project_id: str, display_name: str) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []
    for _, record in list_operation_records(workspace):
        if record.get("kind") != "wrap_up" or project_id not in project_ids_from_record(workspace, record):
            continue
        details = record.get("details") if isinstance(record.get("details"), dict) else {}
        receipt = details.get("receipt") if isinstance(details, dict) else None
        bundle = receipt.get("bundle") if isinstance(receipt, dict) else None
        if not isinstance(bundle, dict):
            continue
        for item in bundle.get("project_updates", []):
            if isinstance(item, dict) and item.get("project") == display_name and isinstance(item.get("content"), str):
                updates.append(
                    {
                        "revision": record["revision"],
                        "operation_id": record["operation_id"],
                        "content": item["content"],
                    }
                )
    return updates


def finalize(packet: dict[str, Any]) -> dict[str, Any]:
    packet["packet_sha256"] = packet_digest(packet)
    return packet


def build_packet(workspace: Path, project_id: str, max_bytes: int) -> dict[str, Any]:
    if max_bytes < 1:
        raise StateError("context budget must be a positive byte count")
    require_workspace(workspace)
    project = project_by_id(workspace, project_id)
    state = replay(workspace)
    fact_scopes, task_scopes = record_scopes(state, operation_projects(workspace))

    facts = [
        item
        for item in state["facts"]
        if item.get("status") == "active" and project_id in fact_scopes.get(item["fact_id"], set())
    ]
    tasks = [
        item
        for item in state["tasks"]
        if item.get("status") == "open" and project_id in task_scopes.get(item["task_id"], set())
    ]
    facts.sort(key=lambda item: (item.get("provenance", {}).get("revision", 0), item["fact_id"]))
    tasks.sort(key=lambda item: (item.get("provenance", {}).get("revision", 0), item["task_id"]))
    updates = project_updates(workspace, project_id, project["display_name"])
    from skills_index import list_skills
    try:
        index = list_skills(workspace, project_id=project_id)
        if index["revision"] != state["revision"]:
            raise StateError("skill snapshot revision differs from the project context snapshot")
        skills = [{"name": item["display_name"], "description": item["description"][:160]}
                  for item in index["skills"]]
        skills_status = "review_required" if index["excluded_sources"] or index["unsupported_skills"] else "available"
    except (StateError, OSError):
        skills, skills_status = [], "unavailable"

    packet: dict[str, Any] = {
        "format": FORMAT,
        "version": VERSION,
        "source_revision": state["revision"],
        "project": {
            "project_id": project_id,
            "display_name": project["display_name"],
            "location": project.get("location"),
        },
        "checkpoint": latest_checkpoint(workspace, project_id),
        "facts": [],
        "tasks": [],
        "project_updates": [],
        "skills": [],
        "skills_status": skills_status,
        "budget": {
            "max_bytes": max_bytes,
            "truncated": False,
            "omitted": {"facts": 0, "tasks": 0, "project_updates": 0, "skills": 0},
            "token_equivalence_claimed": False,
        },
        "packet_sha256": "0" * 64,
    }

    if encoded_size(finalize(packet)) > max_bytes:
        raise StateError("context budget is too small for required project/checkpoint core")

    groups = (("project_updates", updates), ("facts", facts), ("tasks", tasks), ("skills", skills))
    for key, items in groups:
        for index, item in enumerate(items):
            packet[key].append(item)
            finalize(packet)
            if encoded_size(packet) > max_bytes:
                packet[key].pop()
                packet["budget"]["omitted"][key] += len(items) - index
                packet["budget"]["truncated"] = True
                finalize(packet)
                break

    finalize(packet)
    if encoded_size(packet) > max_bytes:
        raise StateError("context budget could not contain deterministic packet metadata")
    return packet


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a bounded project-scoped Aham context packet.")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--max-bytes", required=True, type=int)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        packet = build_packet(resolve_workspace(args.workspace), args.project_id, args.max_bytes)
    except StateError as exc:
        print(f"CONTEXT PACKET FAILED: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(canonical_json(packet))
    else:
        print(json.dumps(packet, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
