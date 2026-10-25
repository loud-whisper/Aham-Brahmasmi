#!/usr/bin/env python3
"""Route durable session state through canonical, revisioned wrap-up operations."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from recovery_commands import recovery_command
import uuid
from pathlib import Path
from typing import Any, Callable

from state_io import (
    StateError,
    atomic_write_text,
    git_contains_ancestor,
    git_snapshot,
    read_json,
    require_workspace,
    resolve_workspace,
    safe_slug,
    utc_now,
    validate_checkpoint,
    workspace_fingerprint,
    write_checkpoint,
)
from state_store import (
    advance_store_head,
    assert_expected_revision,
    commit_operation,
    durable_write_json,
    find_operation,
    reconcile_store,
    sync_directory,
    test_crash_point,
    writer_lock,
)


WRAP_FORMAT = "aham-brahmasmi-wrap-up"
WRAP_VERSION = 3
CONTROL_VERSION = 1
OPERATION_ID = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
ProgressCallback = Callable[[str, str | None], None]

REQUEST_CANONICAL_FIELDS = {
    "operation_id",
    "durable_facts",
    "unfinished_work",
    "reusable_lessons",
    "project_updates",
    "history",
    "checkpoint",
}
REQUEST_ALIASES = {"session_id", "facts", "lessons", "projects"}
PERSISTED_BUNDLE_FIELDS = {
    "durable_facts",
    "unfinished_work",
    "reusable_lessons",
    "project_updates",
    "history",
    "checkpoint",
}
CHECKPOINT_FIELDS = {"summary", "completed", "next_steps", "artifacts", "project"}
CHECKPOINT_ALIASES = {"next", "next_step"}
PROJECT_UPDATE_FIELDS = {"project", "content"}
REPOSITORY_FIELDS = {"name", "branch", "head"}
PROGRESS_FIELDS = {"step", "updated_at", "detail"}
PENDING_FIELDS = {
    "format",
    "version",
    "status",
    "operation_id",
    "created_at",
    "workspace_fingerprint",
    "repository",
    "payload_digest",
    "bundle",
    "base_revision",
    "target_revision",
    "progress",
}
COMPLETED_FIELDS = PENDING_FIELDS | {"completed_at", "checkpoint_file", "committed_items", "revision"}
COMMITTED_ITEM_FIELDS = {"item_id", "kind", "index", "destination", "content_digest"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Persist an Aham Brahmasmi session safely.")
    parser.add_argument("--workspace", required=True, help="Path to the private workspace")
    parser.add_argument("--bundle", help="JSON bundle containing durable session items")
    parser.add_argument("--repo", help="Optional Git repository whose state should be captured and verified")
    parser.add_argument("--recover-pending", action="store_true", help="Replay an unfinished wrap-up transaction")
    parser.add_argument("--status", metavar="OPERATION_ID", help="Report a persisted operation without mutating state")
    parser.add_argument("--expected-revision", type=int, help="Fail unless the committed workspace revision matches")
    return parser.parse_args()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def payload_digest(bundle: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(bundle).encode("utf-8")).hexdigest()


def content_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def validate_operation_id(value: Any) -> str:
    if not isinstance(value, str) or not OPERATION_ID.fullmatch(value):
        raise StateError("operation_id must contain only letters, digits, '.', '_' or '-' and be at most 80 characters")
    return value


def string_list(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise StateError(f"bundle field '{field}' must be a list of non-empty strings")
    return [item.strip() for item in value]


def reject_unknown_fields(raw: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise StateError(f"{label} contains unknown field(s): {', '.join(unknown)}")


def require_exact_fields(raw: dict[str, Any], required: set[str], label: str) -> None:
    missing = sorted(required - set(raw))
    if missing:
        raise StateError(f"{label} missing field(s): {', '.join(missing)}")


def aliased_value(raw: dict[str, Any], canonical: str, alias: str) -> Any:
    if canonical in raw and alias in raw:
        raise StateError(f"bundle cannot contain both '{canonical}' and alias '{alias}'")
    return raw.get(canonical, raw.get(alias))


def normalize_project_updates(raw: dict[str, Any]) -> list[dict[str, str]]:
    if "project_updates" in raw and "projects" in raw:
        raise StateError("bundle cannot contain both 'project_updates' and alias 'projects'")
    if "projects" in raw:
        projects = raw["projects"]
        if not isinstance(projects, list):
            raise StateError("bundle field 'projects' must be a list")
        normalized_aliases: list[dict[str, str]] = []
        for index, item in enumerate(projects, start=1):
            if not isinstance(item, dict):
                raise StateError(f"project alias #{index} must be an object")
            reject_unknown_fields(item, {"name", "update"}, f"project alias #{index}")
            project = item.get("name")
            content = item.get("update")
            if not isinstance(project, str) or not project.strip():
                raise StateError(f"project alias #{index} has no name")
            if not isinstance(content, str) or not content.strip():
                raise StateError(f"project alias #{index} has no update")
            normalized_aliases.append({"project": project.strip(), "content": content.strip()})
        return normalized_aliases
    project_updates = raw.get("project_updates", [])
    if not isinstance(project_updates, list):
        raise StateError("bundle field 'project_updates' must be a list")
    normalized_updates: list[dict[str, str]] = []
    for index, item in enumerate(project_updates, start=1):
        if not isinstance(item, dict):
            raise StateError(f"project update #{index} must be an object")
        reject_unknown_fields(item, PROJECT_UPDATE_FIELDS, f"project update #{index}")
        project = item.get("project")
        content = item.get("content")
        if not isinstance(project, str) or not project.strip():
            raise StateError(f"project update #{index} has no project name")
        if not isinstance(content, str) or not content.strip():
            raise StateError(f"project update #{index} has no content")
        normalized_updates.append({"project": project.strip(), "content": content.strip()})
    return normalized_updates


def normalize_checkpoint(raw: dict[str, Any]) -> dict[str, Any]:
    reject_unknown_fields(raw, CHECKPOINT_FIELDS | CHECKPOINT_ALIASES, "bundle checkpoint")
    if "next_steps" in raw and ("next" in raw or "next_step" in raw):
        raise StateError("bundle checkpoint cannot combine 'next_steps' with a next-step alias")
    if "next" in raw and "next_step" in raw:
        raise StateError("bundle checkpoint cannot contain both 'next' and 'next_step'")
    summary = raw.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise StateError("bundle checkpoint.summary must be a non-empty string")
    project = raw.get("project")
    if project is not None and (not isinstance(project, str) or not project.strip()):
        raise StateError("bundle checkpoint.project must be a non-empty string when present")
    next_steps_value: Any = raw.get("next_steps")
    if next_steps_value is None:
        alias_value = raw.get("next", raw.get("next_step"))
        if alias_value is not None:
            if not isinstance(alias_value, str) or not alias_value.strip():
                raise StateError("bundle checkpoint next-step alias must be a non-empty string")
            next_steps_value = [alias_value.strip()]
    return {
        "summary": summary.strip(),
        "completed": string_list(raw.get("completed"), "checkpoint.completed"),
        "next_steps": string_list(next_steps_value, "checkpoint.next_steps"),
        "artifacts": string_list(raw.get("artifacts"), "checkpoint.artifacts"),
        "project": project.strip() if isinstance(project, str) else None,
    }


def normalize_request(raw: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    reject_unknown_fields(raw, REQUEST_CANONICAL_FIELDS | REQUEST_ALIASES, "bundle")
    if "operation_id" in raw and "session_id" in raw:
        raise StateError("bundle cannot contain both 'operation_id' and alias 'session_id'")
    checkpoint = raw.get("checkpoint")
    if not isinstance(checkpoint, dict):
        raise StateError("bundle field 'checkpoint' must be an object")
    operation_id = raw.get("operation_id", raw.get("session_id"))
    if operation_id is None:
        operation_id = uuid.uuid4().hex
    operation_id = validate_operation_id(operation_id)
    bundle = {
        "durable_facts": string_list(aliased_value(raw, "durable_facts", "facts"), "durable_facts"),
        "unfinished_work": string_list(raw.get("unfinished_work"), "unfinished_work"),
        "reusable_lessons": string_list(aliased_value(raw, "reusable_lessons", "lessons"), "reusable_lessons"),
        "project_updates": normalize_project_updates(raw),
        "history": string_list(raw.get("history"), "history"),
        "checkpoint": normalize_checkpoint(checkpoint),
    }
    return operation_id, bundle


def validate_canonical_bundle(bundle: Any) -> dict[str, Any]:
    if not isinstance(bundle, dict):
        raise StateError("persisted wrap-up bundle must be an object")
    reject_unknown_fields(bundle, PERSISTED_BUNDLE_FIELDS, "persisted bundle")
    require_exact_fields(bundle, PERSISTED_BUNDLE_FIELDS, "persisted bundle")
    normalized: dict[str, Any] = {
        "durable_facts": string_list(bundle.get("durable_facts"), "durable_facts"),
        "unfinished_work": string_list(bundle.get("unfinished_work"), "unfinished_work"),
        "reusable_lessons": string_list(bundle.get("reusable_lessons"), "reusable_lessons"),
        "history": string_list(bundle.get("history"), "history"),
    }
    updates = bundle.get("project_updates")
    if not isinstance(updates, list):
        raise StateError("persisted bundle field 'project_updates' must be a list")
    normalized_updates: list[dict[str, str]] = []
    for index, item in enumerate(updates, start=1):
        if not isinstance(item, dict):
            raise StateError(f"persisted project update #{index} must be an object")
        reject_unknown_fields(item, PROJECT_UPDATE_FIELDS, f"persisted project update #{index}")
        require_exact_fields(item, PROJECT_UPDATE_FIELDS, f"persisted project update #{index}")
        project = item.get("project")
        content = item.get("content")
        if not isinstance(project, str) or not project.strip() or project != project.strip():
            raise StateError(f"persisted project update #{index} has a non-canonical project name")
        if not isinstance(content, str) or not content.strip() or content != content.strip():
            raise StateError(f"persisted project update #{index} has non-canonical content")
        normalized_updates.append({"project": project, "content": content})
    normalized["project_updates"] = normalized_updates
    checkpoint = bundle.get("checkpoint")
    if not isinstance(checkpoint, dict):
        raise StateError("persisted bundle checkpoint must be an object")
    reject_unknown_fields(checkpoint, CHECKPOINT_FIELDS, "persisted bundle checkpoint")
    require_exact_fields(checkpoint, CHECKPOINT_FIELDS, "persisted bundle checkpoint")
    summary = checkpoint.get("summary")
    project = checkpoint.get("project")
    if not isinstance(summary, str) or not summary.strip() or summary != summary.strip():
        raise StateError("persisted checkpoint summary is not canonical")
    if project is not None and (not isinstance(project, str) or not project.strip() or project != project.strip()):
        raise StateError("persisted checkpoint project is not canonical")
    normalized["checkpoint"] = {
        "summary": summary,
        "completed": string_list(checkpoint.get("completed"), "checkpoint.completed"),
        "next_steps": string_list(checkpoint.get("next_steps"), "checkpoint.next_steps"),
        "artifacts": string_list(checkpoint.get("artifacts"), "checkpoint.artifacts"),
        "project": project,
    }
    if normalized != bundle:
        raise StateError("persisted wrap-up bundle is not in canonical form")
    return normalized


def validate_repository(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise StateError("persisted repository state must be an object or null")
    reject_unknown_fields(value, REPOSITORY_FIELDS, "persisted repository state")
    require_exact_fields(value, REPOSITORY_FIELDS, "persisted repository state")
    if not isinstance(value.get("name"), str) or not value["name"]:
        raise StateError("persisted repository state has no valid name")
    branch = value.get("branch")
    if branch is not None and not isinstance(branch, str):
        raise StateError("persisted repository branch must be a string or null")
    head = value.get("head")
    if not isinstance(head, str) or not head:
        raise StateError("persisted repository state has no valid commit")
    return value


def validate_progress(value: Any) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        raise StateError("persisted progress must be an object")
    reject_unknown_fields(value, PROGRESS_FIELDS, "persisted progress")
    require_exact_fields(value, {"step", "updated_at"}, "persisted progress")
    if not isinstance(value.get("step"), str) or not value["step"]:
        raise StateError("persisted progress has no valid step")
    if not isinstance(value.get("updated_at"), str) or not value["updated_at"]:
        raise StateError("persisted progress has no valid timestamp")
    if "detail" in value and (not isinstance(value["detail"], str) or not value["detail"]):
        raise StateError("persisted progress detail must be a non-empty string")


def validate_committed_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise StateError("completed wrap-up committed_items must be a list")
    items: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise StateError(f"committed item #{index} must be an object")
        reject_unknown_fields(item, COMMITTED_ITEM_FIELDS, f"committed item #{index}")
        require_exact_fields(item, COMMITTED_ITEM_FIELDS, f"committed item #{index}")
        if not isinstance(item.get("item_id"), str) or not item["item_id"]:
            raise StateError(f"committed item #{index} has no item_id")
        if not isinstance(item.get("kind"), str) or not item["kind"]:
            raise StateError(f"committed item #{index} has no kind")
        if not isinstance(item.get("index"), int) or item["index"] < 0:
            raise StateError(f"committed item #{index} has invalid index")
        if not isinstance(item.get("destination"), str) or not item["destination"]:
            raise StateError(f"committed item #{index} has no destination")
        digest = item.get("content_digest")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise StateError(f"committed item #{index} has invalid content digest")
        items.append(item)
    return items


def validate_transaction(transaction: Any, *, expected_status: str | None = None) -> dict[str, Any]:
    if not isinstance(transaction, dict):
        raise StateError("persisted wrap-up transaction must be an object")
    status = transaction.get("status")
    if status not in {"pending", "complete"}:
        raise StateError("persisted wrap-up status is not recognized")
    if expected_status is not None and status != expected_status:
        raise StateError(f"persisted wrap-up is {status}, expected {expected_status}")
    allowed = PENDING_FIELDS if status == "pending" else COMPLETED_FIELDS
    required = PENDING_FIELDS - {"progress"}
    if status == "complete":
        required |= {"completed_at", "checkpoint_file", "committed_items", "revision"}
    reject_unknown_fields(transaction, allowed, "persisted wrap-up transaction")
    require_exact_fields(transaction, required, "persisted wrap-up transaction")
    if transaction.get("format") != WRAP_FORMAT or transaction.get("version") != WRAP_VERSION:
        raise StateError("persisted wrap-up format/version is not recognized")
    operation_id = validate_operation_id(transaction.get("operation_id"))
    for field in ("created_at", "workspace_fingerprint", "payload_digest"):
        if not isinstance(transaction.get(field), str) or not transaction[field]:
            raise StateError(f"persisted wrap-up has no valid {field}")
    if not re.fullmatch(r"[0-9a-f]{64}", transaction["workspace_fingerprint"]):
        raise StateError("persisted workspace fingerprint is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", transaction["payload_digest"]):
        raise StateError("persisted payload digest is invalid")
    base_revision = transaction.get("base_revision")
    target_revision = transaction.get("target_revision")
    if not isinstance(base_revision, int) or base_revision < 0 or target_revision != base_revision + 1:
        raise StateError("persisted wrap-up revision transition is invalid")
    bundle = validate_canonical_bundle(transaction.get("bundle"))
    if payload_digest(bundle) != transaction["payload_digest"]:
        raise StateError("persisted payload digest does not match the canonical bundle")
    validate_repository(transaction.get("repository"))
    validate_progress(transaction.get("progress"))
    if status == "complete":
        if transaction.get("revision") != target_revision:
            raise StateError("completed wrap-up revision does not match its target revision")
        if not isinstance(transaction.get("completed_at"), str) or not transaction["completed_at"]:
            raise StateError("completed wrap-up has no completion timestamp")
        checkpoint_file = transaction.get("checkpoint_file")
        if not isinstance(checkpoint_file, str) or not checkpoint_file.startswith("state/checkpoints/"):
            raise StateError("completed wrap-up has no valid checkpoint file")
        validate_committed_items(transaction.get("committed_items"))
    if operation_id != transaction["operation_id"]:
        raise StateError("persisted operation identity is not canonical")
    return transaction


def load_new_transaction(workspace: Path, bundle_path: Path, repo: str | None, base_revision: int) -> dict[str, Any]:
    raw = read_json(bundle_path)
    operation_id, bundle = normalize_request(raw)
    repository = git_snapshot(repo) if repo else None
    return {
        "format": WRAP_FORMAT,
        "version": WRAP_VERSION,
        "status": "pending",
        "operation_id": operation_id,
        "created_at": utc_now(),
        "workspace_fingerprint": workspace_fingerprint(require_workspace(workspace)),
        "repository": repository,
        "payload_digest": payload_digest(bundle),
        "bundle": bundle,
        "base_revision": base_revision,
        "target_revision": base_revision + 1,
    }


def record_progress(pending_path: Path, transaction: dict[str, Any], step: str, detail: str | None = None) -> None:
    progress: dict[str, Any] = {"step": step, "updated_at": utc_now()}
    if detail:
        progress["detail"] = detail
    transaction["progress"] = progress
    validate_transaction(transaction, expected_status="pending")
    durable_write_json(pending_path, transaction)


def verify_repository(transaction: dict[str, Any], repo: str | None) -> None:
    expected = transaction.get("repository")
    if not expected:
        return
    if not repo:
        raise StateError("pending wrap-up recorded repository state; --repo is required to verify it")
    current = git_snapshot(repo)
    if expected.get("branch") != current.get("branch"):
        raise StateError(f"repository branch mismatch; transaction={expected.get('branch')} current={current.get('branch')}")
    head = expected.get("head")
    if not isinstance(head, str) or not head:
        raise StateError("pending wrap-up repository state has no valid commit")
    if not git_contains_ancestor(repo, head):
        raise StateError("recorded wrap-up commit is not an ancestor of the current repository state")


def ensure_heading(path: Path, heading: str) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, f"# {heading}\n")
    sync_directory(path.parent)


def escape_projection_content(value: str) -> str:
    return value.replace("<!-- aham-op:", "&lt;!-- aham-op:").replace("<!-- /aham-op:", "&lt;!-- /aham-op:")


def render_operation_block(operation_id: str, item_id: str, digest: str, body: str) -> str:
    header = f"<!-- aham-op:v{CONTROL_VERSION} id={operation_id} item={item_id} sha256={digest} -->"
    footer = f"<!-- /aham-op:v{CONTROL_VERSION} id={operation_id} item={item_id} -->"
    return f"{header}\n{escape_projection_content(body).rstrip()}\n{footer}\n"


def append_operation_block(path: Path, operation_id: str, item_id: str, raw_content: str, display_body: str) -> bool:
    digest = content_digest(raw_content)
    block = render_operation_block(operation_id, item_id, digest, display_body)
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    header = block.splitlines()[0]
    if block in current:
        return False
    if header in current:
        raise StateError(f"projection control record for {item_id} exists but its verified content does not match")
    separator = "" if not current or current.endswith("\n\n") else "\n" if current.endswith("\n") else "\n\n"
    atomic_write_text(path, current + separator + block)
    sync_directory(path.parent)
    if block not in path.read_text(encoding="utf-8"):
        raise StateError(f"projection verification failed for {path.name} item {item_id}")
    return True


def descriptor(kind: str, index: int, destination: str, raw_content: str) -> dict[str, Any]:
    return {"item_id": f"{kind}-{index}", "kind": kind, "index": index, "destination": destination, "content_digest": content_digest(raw_content)}


def expected_committed_items(workspace: Path, transaction: dict[str, Any]) -> list[dict[str, Any]]:
    bundle = transaction["bundle"]
    items: list[dict[str, Any]] = []
    for kind, field, destination in (
        ("memory", "durable_facts", "MEMORY.md"),
        ("todo", "unfinished_work", "TODO.md"),
        ("lesson", "reusable_lessons", "LESSONS.md"),
    ):
        for index, item in enumerate(bundle[field]):
            items.append(descriptor(kind, index, destination, item))
    for index, item in enumerate(bundle["project_updates"]):
        items.append(descriptor("project", index, f"projects/{safe_slug(item['project'])}.md", item["content"]))
    history_date = str(transaction["created_at"])[:10]
    for index, item in enumerate(bundle["history"]):
        items.append(descriptor("history", index, f"history/{history_date}.md", item))
    return items


def verify_projection_item(workspace: Path, transaction: dict[str, Any], item: dict[str, Any]) -> None:
    operation_id = transaction["operation_id"]
    bundle = transaction["bundle"]
    kind = item["kind"]
    index = item["index"]
    if kind == "memory":
        raw, body = bundle["durable_facts"][index], f"- {bundle['durable_facts'][index]}"
    elif kind == "todo":
        raw, body = bundle["unfinished_work"][index], f"- {bundle['unfinished_work'][index]}"
    elif kind == "lesson":
        raw, body = bundle["reusable_lessons"][index], f"- {bundle['reusable_lessons'][index]}"
    elif kind == "project":
        raw = bundle["project_updates"][index]["content"]
        body = raw
    elif kind == "history":
        raw, body = bundle["history"][index], f"- {bundle['history'][index]}"
    else:
        raise StateError(f"completed receipt contains unknown projection kind: {kind}")
    expected = render_operation_block(operation_id, item["item_id"], content_digest(raw), body)
    path = workspace / item["destination"]
    if not path.is_file() or expected not in path.read_text(encoding="utf-8"):
        raise StateError(f"committed projection content is missing or changed: {item['destination']} {item['item_id']}")


def apply_transaction(workspace: Path, transaction: dict[str, Any], *, progress: ProgressCallback | None = None) -> tuple[Path, list[dict[str, Any]]]:
    def mark(step: str, detail: str | None = None) -> None:
        if progress:
            progress(step, detail)
    validate_transaction(transaction, expected_status="pending")
    if transaction["workspace_fingerprint"] != workspace_fingerprint(require_workspace(workspace)):
        raise StateError("pending wrap-up belongs to a different workspace identity")
    bundle = transaction["bundle"]
    operation_id = transaction["operation_id"]
    committed_items = expected_committed_items(workspace, transaction)
    routes = (
        ("durable_facts", workspace / "MEMORY.md", "memory", "route_memory"),
        ("unfinished_work", workspace / "TODO.md", "todo", "route_todo"),
        ("reusable_lessons", workspace / "LESSONS.md", "lesson", "route_lessons"),
    )
    for field, path, kind, step in routes:
        items = bundle[field]
        for index, item in enumerate(items):
            mark(step, f"{field} item {index + 1} of {len(items)}")
            append_operation_block(path, operation_id, f"{kind}-{index}", item, f"- {item}")
    updates = bundle["project_updates"]
    for index, item in enumerate(updates):
        project = item["project"]
        mark("route_projects", f"project update {index + 1} of {len(updates)}: {project}")
        path = workspace / "projects" / f"{safe_slug(project)}.md"
        ensure_heading(path, project)
        append_operation_block(path, operation_id, f"project-{index}", item["content"], item["content"])
    history = bundle["history"]
    history_date = str(transaction["created_at"])[:10]
    history_path = workspace / "history" / f"{history_date}.md"
    if history:
        mark("route_history", f"prepare history file for {history_date}")
        ensure_heading(history_path, history_date)
    for index, item in enumerate(history):
        mark("route_history", f"history item {index + 1} of {len(history)}")
        append_operation_block(history_path, operation_id, f"history-{index}", item, f"- {item}")
    mark("verify_routed_state", f"verify {len(committed_items)} routed item(s) by content")
    for item in committed_items:
        verify_projection_item(workspace, transaction, item)
    checkpoint = bundle["checkpoint"]
    mark("write_final_checkpoint", f"checkpoint wrap-{operation_id}")
    checkpoint_path, _ = write_checkpoint(
        workspace,
        summary=checkpoint["summary"],
        completed=list(checkpoint["completed"]),
        next_steps=list(checkpoint["next_steps"]),
        project=checkpoint["project"],
        artifacts=list(checkpoint["artifacts"]),
        repository=transaction.get("repository"),
        checkpoint_id=f"wrap-{operation_id}",
        revision=transaction["target_revision"],
    )
    sync_directory(checkpoint_path.parent)
    sync_directory(workspace / "state")
    if not checkpoint_path.is_file():
        raise StateError("final wrap-up checkpoint was not persisted")
    return checkpoint_path, committed_items


def completed_from_pending(transaction: dict[str, Any], checkpoint_path: Path, committed_items: list[dict[str, Any]]) -> dict[str, Any]:
    completed = dict(transaction)
    completed["status"] = "complete"
    completed["completed_at"] = utc_now()
    completed["checkpoint_file"] = f"state/checkpoints/{checkpoint_path.name}"
    completed["committed_items"] = committed_items
    completed["revision"] = transaction["target_revision"]
    validate_transaction(completed, expected_status="complete")
    return completed


def verify_completed_state(workspace: Path, completed: dict[str, Any]) -> Path:
    validate_transaction(completed, expected_status="complete")
    if completed["workspace_fingerprint"] != workspace_fingerprint(require_workspace(workspace)):
        raise StateError("completed wrap-up belongs to a different workspace identity")
    operation_id = completed["operation_id"]
    checkpoint_path = workspace / completed["checkpoint_file"]
    checkpoint = read_json(checkpoint_path)
    checkpoint_errors = validate_checkpoint(checkpoint)
    if checkpoint_errors:
        raise StateError("final wrap-up checkpoint failed validation: " + "; ".join(checkpoint_errors))
    expected_checkpoint = completed["bundle"]["checkpoint"]
    if checkpoint.get("id") != f"wrap-{operation_id}":
        raise StateError("final wrap-up checkpoint ID does not match the operation")
    if checkpoint.get("revision") != completed["revision"]:
        raise StateError("final wrap-up checkpoint revision does not match the operation")
    for field in ("summary", "completed", "next_steps", "artifacts", "project"):
        actual = checkpoint.get(field)
        expected = expected_checkpoint.get(field)
        if field == "project" and expected is None:
            if actual is not None:
                raise StateError("final wrap-up checkpoint project does not match the accepted payload")
        elif actual != expected:
            raise StateError(f"final wrap-up checkpoint {field} does not match the accepted payload")
    if checkpoint.get("repository") != completed.get("repository"):
        raise StateError("final wrap-up checkpoint repository state does not match the operation")
    expected_items = expected_committed_items(workspace, completed)
    if completed["committed_items"] != expected_items:
        raise StateError("completed receipt does not enumerate the accepted routed content exactly")
    for item in expected_items:
        verify_projection_item(workspace, completed, item)
    return checkpoint_path


def pending_progress(pending_path: Path) -> tuple[str | None, str | None]:
    if not pending_path.is_file():
        return None, None
    try:
        pending = read_json(pending_path)
    except StateError:
        return None, None
    progress = pending.get("progress")
    if not isinstance(progress, dict):
        return None, None
    step = progress.get("step") if isinstance(progress.get("step"), str) else None
    detail = progress.get("detail") if isinstance(progress.get("detail"), str) else None
    return step, detail


def archive_path(workspace: Path, operation_id: str) -> Path:
    return workspace / "state" / "wrapups" / f"{safe_slug(operation_id)}.json"


def print_receipt(completed: dict[str, Any], checkpoint_path: Path, archive: Path, *, reused: bool = False) -> None:
    print("WRAP UP COMPLETE")
    print("WRAP UP VERIFIED")
    if reused:
        print("EXISTING RECEIPT REUSED")
    print(f"Operation: {completed['operation_id']}")
    print(f"Revision: {completed['revision']}")
    print(f"Payload digest: {completed['payload_digest']}")
    print(f"Committed items: {len(completed['committed_items'])}")
    print(f"Checkpoint: {checkpoint_path}")
    print(f"Receipt: {archive}")


def completed_from_record(record: dict[str, Any]) -> dict[str, Any]:
    if record.get("kind") != "wrap_up":
        raise StateError("operation exists but is not a wrap-up")
    details = record.get("details")
    if not isinstance(details, dict) or not isinstance(details.get("receipt"), dict):
        raise StateError("committed wrap-up record has no canonical receipt payload")
    completed = details["receipt"]
    validate_transaction(completed, expected_status="complete")
    if completed["revision"] != record["revision"] or completed["payload_digest"] != record["payload_digest"]:
        raise StateError("committed operation record conflicts with its receipt payload")
    return completed


def materialize_committed_record(workspace: Path, record_path: Path, record: dict[str, Any]) -> tuple[dict[str, Any], Path, Path]:
    completed = completed_from_record(record)
    pending_shape = dict(completed)
    for field in ("completed_at", "checkpoint_file", "committed_items", "revision"):
        pending_shape.pop(field, None)
    pending_shape["status"] = "pending"
    validate_transaction(pending_shape, expected_status="pending")
    checkpoint_path, committed_items = apply_transaction(workspace, pending_shape)
    if committed_items != completed["committed_items"] or f"state/checkpoints/{checkpoint_path.name}" != completed["checkpoint_file"]:
        raise StateError("committed operation projections do not match the immutable record")
    advance_store_head(workspace, record_path, record)
    archive = archive_path(workspace, completed["operation_id"])
    if archive.exists():
        existing = read_json(archive)
        validate_transaction(existing, expected_status="complete")
        if existing != completed:
            raise StateError("existing wrap-up receipt conflicts with the immutable operation record")
    else:
        durable_write_json(archive, completed)
    verify_completed_state(workspace, completed)
    return completed, checkpoint_path, archive


def status_operation(workspace: Path, operation_id: str) -> int:
    operation_id = validate_operation_id(operation_id)
    committed = find_operation(workspace, operation_id)
    if committed:
        _, record = committed
        if record["kind"] != "wrap_up":
            raise StateError("operation exists but is not a wrap-up")
        completed = completed_from_record(record)
        print("OPERATION STATUS")
        print(f"Operation: {operation_id}")
        print("Status: complete")
        print(f"Revision: {record['revision']}")
        print(f"Payload digest: {record['payload_digest']}")
        print(f"Committed items: {len(completed['committed_items'])}")
        return 0
    pending_path = workspace / "state" / "pending_wrap_up.json"
    if pending_path.is_file():
        pending = read_json(pending_path)
        validate_transaction(pending, expected_status="pending")
        if pending["operation_id"] == operation_id:
            print("OPERATION STATUS")
            print(f"Operation: {operation_id}")
            print("Status: pending")
            print(f"Target revision: {pending['target_revision']}")
            print(f"Payload digest: {pending['payload_digest']}")
            step, detail = pending_progress(pending_path)
            if step:
                print(f"Current step: {step}")
            if detail:
                print(f"Step detail: {detail}")
            return 0
    archive = archive_path(workspace, operation_id)
    if archive.is_file():
        legacy = read_json(archive)
        if legacy.get("operation_id") == operation_id:
            print("OPERATION STATUS")
            print(f"Operation: {operation_id}")
            print("Status: complete (legacy receipt; no revision ledger)")
            print(f"Payload digest: {legacy.get('payload_digest', '(unknown)')}")
            return 0
    raise StateError(f"no persisted operation found for {operation_id}")


def finish_transaction(workspace: Path, pending_path: Path, transaction: dict[str, Any], repo: str | None) -> tuple[dict[str, Any], Path, Path]:
    transaction = validate_transaction(transaction, expected_status="pending")
    existing_committed = find_operation(workspace, transaction["operation_id"])
    if existing_committed:
        record_path, record = existing_committed
        if record["payload_digest"] != transaction["payload_digest"] or record["revision"] != transaction["target_revision"]:
            raise StateError("pending transaction conflicts with its committed operation record")
        completed, checkpoint_path, archive = materialize_committed_record(workspace, record_path, record)
        if pending_path.exists():
            pending_path.unlink()
            sync_directory(pending_path.parent)
        return completed, checkpoint_path, archive

    head = reconcile_store(workspace)
    if head["revision"] != transaction["base_revision"]:
        raise StateError(
            f"pending wrap-up revision conflict; base {transaction['base_revision']}, current committed revision {head['revision']}"
        )

    def progress(step: str, detail: str | None = None) -> None:
        record_progress(pending_path, transaction, step, detail)

    progress("verify_repository", "verify recorded repository state when present")
    verify_repository(transaction, repo)
    progress("validate_transaction", "validate canonical pending transaction and workspace identity")
    validate_transaction(transaction, expected_status="pending")
    checkpoint_path, committed_items = apply_transaction(workspace, transaction, progress=progress)
    test_crash_point("wrap_up_after_projection")
    progress("archive_transaction", "prepare immutable committed operation record")
    completed = completed_from_pending(transaction, checkpoint_path, committed_items)
    record_path, record = commit_operation(
        workspace,
        operation_id=transaction["operation_id"],
        kind="wrap_up",
        payload_digest=transaction["payload_digest"],
        details={"receipt": completed},
        target_revision=transaction["target_revision"],
    )
    test_crash_point("wrap_up_after_commit_record")
    advance_store_head(workspace, record_path, record)
    test_crash_point("wrap_up_after_head")
    archive = archive_path(workspace, completed["operation_id"])
    durable_write_json(archive, completed)
    verify_completed_state(workspace, completed)
    test_crash_point("wrap_up_after_receipt")
    pending_path.unlink()
    sync_directory(pending_path.parent)
    return completed, checkpoint_path, archive


def main() -> int:
    args = parse_args()
    workspace = resolve_workspace(args.workspace)
    pending_path = workspace / "state" / "pending_wrap_up.json"
    transaction: dict[str, Any] | None = None
    try:
        require_workspace(workspace)
        selected = int(bool(args.bundle)) + int(bool(args.recover_pending)) + int(bool(args.status))
        if selected != 1:
            raise StateError("choose exactly one of --bundle, --recover-pending, or --status")
        if args.status and (args.repo or args.expected_revision is not None):
            raise StateError("--repo/--expected-revision cannot be combined with --status")

        with writer_lock(workspace) as head:
            if args.status:
                return status_operation(workspace, args.status)

            if args.recover_pending:
                if args.expected_revision is not None:
                    raise StateError("--expected-revision cannot be combined with --recover-pending")
                if not pending_path.is_file():
                    raise StateError("there is no pending wrap-up transaction to recover")
                transaction = read_json(pending_path)
                validate_transaction(transaction, expected_status="pending")
            else:
                candidate = load_new_transaction(workspace, Path(args.bundle).expanduser().resolve(), args.repo, head["revision"])
                committed = find_operation(workspace, candidate["operation_id"])
                if committed:
                    record_path, record = committed
                    if record["kind"] != "wrap_up" or record["payload_digest"] != candidate["payload_digest"]:
                        raise StateError("operation_id is already bound to a different payload")
                    completed, checkpoint_path, archive = materialize_committed_record(workspace, record_path, record)
                    print_receipt(completed, checkpoint_path, archive, reused=True)
                    return 0

                archive = archive_path(workspace, candidate["operation_id"])
                if archive.exists():
                    existing = read_json(archive)
                    if existing.get("payload_digest") != candidate["payload_digest"]:
                        raise StateError("operation_id is already bound to a different legacy payload")
                    raise StateError("operation_id exists only as a legacy unrevisioned receipt; migrate it before reuse")

                if pending_path.exists():
                    existing_pending = read_json(pending_path)
                    validate_transaction(existing_pending, expected_status="pending")
                    if existing_pending["operation_id"] != candidate["operation_id"]:
                        raise StateError("an unfinished wrap-up transaction already exists for a different operation; recover it first")
                    if existing_pending["payload_digest"] != candidate["payload_digest"]:
                        raise StateError("operation_id is already bound to a different pending payload")
                    transaction = existing_pending
                else:
                    assert_expected_revision(head["revision"], args.expected_revision)
                    transaction = candidate
                    durable_write_json(pending_path, transaction)
                    test_crash_point("wrap_up_after_pending")

            if transaction is None:
                raise StateError("wrap-up transaction is unavailable")
            completed, checkpoint_path, archive = finish_transaction(workspace, pending_path, transaction, args.repo)
            print_receipt(completed, checkpoint_path, archive)
            return 0
    except (StateError, OSError, KeyError, TypeError, ValueError) as exc:
        print(f"WRAP UP FAILED: {exc}", file=sys.stderr)
        if pending_path.exists():
            print(f"Pending transaction preserved: {pending_path}", file=sys.stderr)
            step, detail = pending_progress(pending_path)
            if step:
                print(f"Remaining step: {step}", file=sys.stderr)
            if detail:
                print(f"Step detail: {detail}", file=sys.stderr)
            recovery = recovery_command("wrap-up")
            if transaction and transaction.get("repository"):
                recovery += " --repo <same-repository>"
            print(f"Recovery command: {recovery}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
