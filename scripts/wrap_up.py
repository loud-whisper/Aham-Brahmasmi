#!/usr/bin/env python3
"""M3 project-aware wrapper around the canonical revisioned wrap-up engine."""

from __future__ import annotations

import io
import json
import sys
from recovery_commands import recovery_command
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from typing import Any, Iterator

import wrap_up_core as core
from operation_receipt import operation_record, pending_receipt, print_json_receipt, print_text_receipt, receipt_from_record
from project_state import (
    ensure_project,
    git_snapshot_strong,
    reconcile_latest_checkpoint,
    reconcile_project_heads,
    resolve_project_id,
)
from session_authority import advance_session_revision, load_session, require_operation_authority
from state_io import StateError, git_contains_ancestor, read_json, require_workspace, resolve_workspace, workspace_fingerprint


def _extract_option(name: str) -> str | None:
    """Consume one wrapper-only CLI option before wrap_up_core parses argv."""
    prefix = name + "="
    for index, argument in enumerate(list(sys.argv[1:]), start=1):
        if argument.startswith(prefix):
            value = argument[len(prefix):]
            del sys.argv[index]
            return value
        if argument == name:
            if index + 1 >= len(sys.argv):
                return ""
            value = sys.argv[index + 1]
            del sys.argv[index:index + 2]
            return value
    return None


def _extract_flag(name: str) -> bool:
    found = False
    for index in range(len(sys.argv) - 1, 0, -1):
        if sys.argv[index] == name:
            del sys.argv[index]
            found = True
    return found


def _peek_option(name: str) -> str | None:
    prefix = name + "="
    for index, argument in enumerate(sys.argv[1:], start=1):
        if argument.startswith(prefix):
            return argument[len(prefix):]
        if argument == name:
            return sys.argv[index + 1] if index + 1 < len(sys.argv) else ""
    return None


_PRESENTED_SESSION_ID = _extract_option("--session-id")
_PRESENTED_PROJECT_ID = _extract_option("--project-id")
_JSON_OUTPUT = _extract_flag("--json")

core.REPOSITORY_FIELDS = set(core.REPOSITORY_FIELDS) | {
    "identity", "root", "git_common_dir", "remote_url", "tracked_dirty", "untracked_present", "status_digest"
}
core.git_snapshot = git_snapshot_strong

_original_commit_operation = core.commit_operation
_original_advance_store_head = core.advance_store_head
_original_writer_lock = core.writer_lock


def _project_names(bundle: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for update in bundle.get("project_updates", []):
        if isinstance(update, dict) and isinstance(update.get("project"), str):
            names.append(update["project"])
    checkpoint = bundle.get("checkpoint")
    if isinstance(checkpoint, dict) and isinstance(checkpoint.get("project"), str):
        names.append(checkpoint["project"])
    return list(dict.fromkeys(names))


def _project_bindings(workspace: Path, transaction: dict[str, Any]) -> dict[str, str]:
    return {
        name: resolve_project_id(workspace, name, operation_id=transaction["operation_id"], slot=f"project-{index}")
        for index, name in enumerate(_project_names(transaction["bundle"]))
    }


def _ensure_bundle_projects(workspace: Path, transaction: dict[str, Any]) -> list[str]:
    repository = transaction.get("repository")
    location = repository.get("root") if isinstance(repository, dict) and isinstance(repository.get("root"), str) else None
    bindings = _project_bindings(workspace, transaction)
    ids: list[str] = []
    for name in _project_names(transaction["bundle"]):
        project_id, _ = ensure_project(workspace, name, project_id=bindings[name], location=location)
        ids.append(project_id)
    return list(dict.fromkeys(ids))


@contextmanager
def coordinated_writer_lock(workspace: Path) -> Iterator[dict[str, Any]]:
    with _original_writer_lock(workspace) as head:
        reconcile_project_heads(workspace)
        reconcile_latest_checkpoint(workspace)
        if "--status" not in sys.argv:
            operation = "recover_wrap_up" if "--recover-pending" in sys.argv else "wrap_up"
            require_operation_authority(
                workspace,
                operation,
                session_id=_PRESENTED_SESSION_ID,
                project_id=_PRESENTED_PROJECT_ID,
                committed_revision=head["revision"],
            )
        yield head


def verify_repository(transaction: dict[str, Any], repo: str | None) -> None:
    expected = transaction.get("repository")
    if not expected:
        return
    if not repo:
        raise StateError("pending wrap-up recorded repository state; --repo is required to verify it")
    current = git_snapshot_strong(repo)
    if expected.get("identity") != current.get("identity"):
        raise StateError("repository identity mismatch; this is not the repository location recorded by the operation")
    if expected.get("branch") != current.get("branch"):
        raise StateError(f"repository branch mismatch; transaction={expected.get('branch')} current={current.get('branch')}")
    head = expected.get("head")
    if not isinstance(head, str) or not head:
        raise StateError("pending wrap-up repository state has no valid commit")
    if not git_contains_ancestor(repo, head):
        raise StateError("recorded wrap-up commit is not an ancestor of the current repository state")


def expected_committed_items(workspace: Path, transaction: dict[str, Any]) -> list[dict[str, Any]]:
    bundle = transaction["bundle"]
    items: list[dict[str, Any]] = []
    for kind, field, destination in (
        ("memory", "durable_facts", "MEMORY.md"),
        ("todo", "unfinished_work", "TODO.md"),
        ("lesson", "reusable_lessons", "LESSONS.md"),
    ):
        for index, item in enumerate(bundle[field]):
            items.append(core.descriptor(kind, index, destination, item))
    bindings = _project_bindings(workspace, transaction)
    for index, item in enumerate(bundle["project_updates"]):
        items.append(core.descriptor("project", index, f"projects/{bindings[item['project']]}.md", item["content"]))
    history_date = str(transaction["created_at"])[:10]
    for index, item in enumerate(bundle["history"]):
        items.append(core.descriptor("history", index, f"history/{history_date}.md", item))
    return items


def apply_transaction(
    workspace: Path,
    transaction: dict[str, Any],
    *,
    progress: core.ProgressCallback | None = None,
) -> tuple[Path, list[dict[str, Any]]]:
    def mark(step: str, detail: str | None = None) -> None:
        if progress:
            progress(step, detail)

    core.validate_transaction(transaction, expected_status="pending")
    if transaction["workspace_fingerprint"] != workspace_fingerprint(require_workspace(workspace)):
        raise StateError("pending wrap-up belongs to a different workspace identity")
    bundle = transaction["bundle"]
    operation_id = transaction["operation_id"]
    bindings = _project_bindings(workspace, transaction)
    committed_items = expected_committed_items(workspace, transaction)
    for field, path, kind, step in (
        ("durable_facts", workspace / "MEMORY.md", "memory", "route_memory"),
        ("unfinished_work", workspace / "TODO.md", "todo", "route_todo"),
        ("reusable_lessons", workspace / "LESSONS.md", "lesson", "route_lessons"),
    ):
        values = bundle[field]
        for index, value in enumerate(values):
            mark(step, f"{field} item {index + 1} of {len(values)}")
            core.append_operation_block(path, operation_id, f"{kind}-{index}", value, f"- {value}")

    repository = transaction.get("repository")
    location = repository.get("root") if isinstance(repository, dict) and isinstance(repository.get("root"), str) else None
    updates = bundle["project_updates"]
    for index, item in enumerate(updates):
        project_id = bindings[item["project"]]
        mark("route_projects", f"project update {index + 1} of {len(updates)}: {item['project']} ({project_id})")
        project_id, _ = ensure_project(workspace, item["project"], project_id=project_id, location=location)
        path = workspace / "projects" / f"{project_id}.md"
        core.ensure_heading(path, item["project"])
        core.append_operation_block(path, operation_id, f"project-{index}", item["content"], item["content"])

    history = bundle["history"]
    history_date = str(transaction["created_at"])[:10]
    history_path = workspace / "history" / f"{history_date}.md"
    if history:
        mark("route_history", f"prepare history file for {history_date}")
        core.ensure_heading(history_path, history_date)
    for index, item in enumerate(history):
        mark("route_history", f"history item {index + 1} of {len(history)}")
        core.append_operation_block(history_path, operation_id, f"history-{index}", item, f"- {item}")

    mark("verify_routed_state", f"verify {len(committed_items)} routed item(s) by content")
    for item in committed_items:
        core.verify_projection_item(workspace, transaction, item)

    checkpoint = bundle["checkpoint"]
    if isinstance(checkpoint.get("project"), str):
        name = checkpoint["project"]
        ensure_project(workspace, name, project_id=bindings[name], location=location)
    mark("write_final_checkpoint", f"checkpoint wrap-{operation_id}")
    checkpoint_path, _ = core.write_checkpoint(
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
    core.sync_directory(checkpoint_path.parent)
    core.sync_directory(workspace / "state")
    if not checkpoint_path.is_file():
        raise StateError("final wrap-up checkpoint was not persisted")
    return checkpoint_path, committed_items


def commit_operation(
    workspace: Path, *, operation_id: str, kind: str, payload_digest: str, details: dict[str, Any], target_revision: int
):
    enriched = dict(details)
    if kind == "wrap_up":
        receipt = enriched.get("receipt")
        if isinstance(receipt, dict) and isinstance(receipt.get("bundle"), dict):
            enriched["project_ids"] = _ensure_bundle_projects(workspace, receipt)
            enriched["project_display_names"] = _project_names(receipt["bundle"])
            if isinstance(receipt.get("checkpoint_file"), str):
                enriched["checkpoint_file"] = receipt["checkpoint_file"]
    record_path, record = _original_commit_operation(
        workspace, operation_id=operation_id, kind=kind, payload_digest=payload_digest,
        details=enriched, target_revision=target_revision
    )
    session = load_session(workspace)
    advance_session_revision(workspace, session, int(record["revision"]))
    return record_path, record


def advance_store_head(workspace: Path, record_path: Path, record: dict[str, Any]):
    result = _original_advance_store_head(workspace, record_path, record)
    reconcile_project_heads(workspace)
    reconcile_latest_checkpoint(workspace)
    session = load_session(workspace)
    advance_session_revision(workspace, session, int(record["revision"]))
    return result


core.writer_lock = coordinated_writer_lock
core.verify_repository = verify_repository
core.expected_committed_items = expected_committed_items
core.apply_transaction = apply_transaction
core.commit_operation = commit_operation
core.advance_store_head = advance_store_head


def _operation_id_from_output(output: str) -> str:
    for line in output.splitlines():
        if line.startswith("Operation: "):
            operation_id = line.split(":", 1)[1].strip()
            if operation_id:
                return operation_id
    raise StateError("successful wrap-up did not report its operation identity")


def _verified_structured_receipt(workspace: Path, operation_id: str) -> dict[str, Any]:
    record = operation_record(workspace, operation_id, expected_kind="wrap_up")
    completed = core.completed_from_record(record)
    core.verify_completed_state(workspace, completed)
    return receipt_from_record(workspace, record)


def _structured_status_receipt(workspace: Path, operation_id: str) -> dict[str, Any]:
    try:
        return _verified_structured_receipt(workspace, operation_id)
    except StateError as committed_error:
        pending_path = workspace / "state" / "pending_wrap_up.json"
        if not pending_path.is_file():
            raise committed_error
        pending = read_json(pending_path)
        core.validate_transaction(pending, expected_status="pending")
        if pending.get("operation_id") != operation_id:
            raise committed_error
        return pending_receipt(
            "wrap_up",
            pending,
            recovery_action=recovery_command("wrap-up"),
        )


def _emit_receipt(receipt: dict[str, Any]) -> None:
    if _JSON_OUTPUT:
        print_json_receipt(receipt)
    else:
        print_text_receipt(receipt)


def _run() -> int:
    workspace_arg = _peek_option("--workspace")
    status_operation = _peek_option("--status")
    if status_operation is not None:
        if not workspace_arg or not status_operation:
            print("WRAP UP FAILED: --workspace and a non-empty --status operation ID are required", file=sys.stderr)
            return 1
        if _peek_option("--repo") is not None or _peek_option("--expected-revision") is not None:
            print("WRAP UP FAILED: --repo/--expected-revision cannot be combined with --status", file=sys.stderr)
            return 1
        try:
            _emit_receipt(_structured_status_receipt(resolve_workspace(workspace_arg), status_operation))
            return 0
        except (StateError, OSError, KeyError, TypeError, ValueError) as exc:
            print(f"WRAP UP FAILED: {exc}", file=sys.stderr)
            return 1

    captured = io.StringIO()
    try:
        with redirect_stdout(captured):
            result = core.main()
    except SystemExit:
        # argparse exits inside the capture for --help; surface its text and the wrapper-only options.
        sys.stdout.write(captured.getvalue())
        if captured.getvalue():
            print("\nwrapper options:\n  --session-id ID   session from aham.py start; required for writes\n"
                  "  --project-id ID   project scope checked against the session's authority\n"
                  "  --json            print the receipt as JSON")
        raise
    if result != 0:
        sys.stdout.write(captured.getvalue())
        return result
    if not workspace_arg:
        print("WRAP UP FAILED: committed state exists but --workspace could not be resolved for its receipt", file=sys.stderr)
        return 1
    try:
        operation_id = _operation_id_from_output(captured.getvalue())
        receipt = _verified_structured_receipt(resolve_workspace(workspace_arg), operation_id)
        _emit_receipt(receipt)
        if not _JSON_OUTPUT and "EXISTING RECEIPT REUSED" in captured.getvalue():
            print("EXISTING RECEIPT REUSED")
        if "EXISTING RECEIPT REUSED" not in captured.getvalue():
            # The receipt is already committed. Optional recall cannot invalidate it.
            try:
                from memory_connection import maybe_index_after_wrapup
                outcomes = maybe_index_after_wrapup(resolve_workspace(workspace_arg), operation_id,
                                                    session_id=_PRESENTED_SESSION_ID)
                for outcome in outcomes:
                    if outcome["status"] == "failed":
                        print("OPTIONAL RECALL INDEX FAILED: " + json.dumps(outcome, ensure_ascii=True), file=sys.stderr)
            except (StateError, OSError, KeyError, TypeError, ValueError) as exc:
                print("OPTIONAL RECALL INDEX FAILED: " + json.dumps(str(exc), ensure_ascii=True), file=sys.stderr)
        return 0
    except (StateError, OSError, KeyError, TypeError, ValueError) as exc:
        print(f"WRAP UP FAILED: committed operation could not be reconstructed as a receipt: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(_run())
