#!/usr/bin/env python3
"""M3 project-aware wrapper around the canonical revisioned checkpoint engine."""

from __future__ import annotations

import io
import sys
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from typing import Any, Iterator

import checkpoint_core as core
from operation_receipt import latest_receipt, pending_receipt, print_json_receipt, print_text_receipt, receipt_for_operation
from project_state import (
    ensure_project,
    git_snapshot_strong,
    project_id_by_name,
    reconcile_latest_checkpoint,
    reconcile_project_heads,
    resolve_project_id,
)
from session_authority import advance_session_revision, load_session
from state_io import StateError, read_json, resolve_workspace


def _extract_option(name: str) -> str | None:
    """Consume one wrapper-only CLI option before checkpoint_core parses argv."""
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
_STATUS_OPERATION_ID = _extract_option("--status")
_JSON_OUTPUT = _extract_flag("--json")

core.git_snapshot = git_snapshot_strong
_original_commit_operation = core.commit_operation
_original_advance_store_head = core.advance_store_head
_original_writer_lock = core.writer_lock
_original_require_operation_authority = core.require_operation_authority


def _checkpoint_project_id(workspace: Path) -> str | None:
    try:
        index = sys.argv.index("--project")
    except ValueError:
        for argument in sys.argv[1:]:
            if argument.startswith("--project="):
                name = argument.split("=", 1)[1]
                return project_id_by_name(workspace, name)
        return None
    if index + 1 >= len(sys.argv):
        return None
    return project_id_by_name(workspace, sys.argv[index + 1])


def require_operation_authority(
    workspace: Path,
    operation: str,
    *,
    project_id: str | None = None,
    committed_revision: int | None = None,
):
    return _original_require_operation_authority(
        workspace,
        operation,
        session_id=_PRESENTED_SESSION_ID,
        project_id=project_id if project_id is not None else _checkpoint_project_id(workspace),
        committed_revision=committed_revision,
    )


@contextmanager
def coordinated_writer_lock(workspace: Path) -> Iterator[dict[str, Any]]:
    with _original_writer_lock(workspace) as head:
        reconcile_project_heads(workspace)
        reconcile_latest_checkpoint(workspace)
        yield head


def commit_operation(
    workspace: Path,
    *,
    operation_id: str,
    kind: str,
    payload_digest: str,
    details: dict[str, Any],
    target_revision: int,
):
    enriched = dict(details)
    if kind == "checkpoint":
        checkpoint = enriched.get("checkpoint")
        if isinstance(checkpoint, dict) and isinstance(checkpoint.get("project"), str):
            repository = checkpoint.get("repository")
            location = repository.get("root") if isinstance(repository, dict) and isinstance(repository.get("root"), str) else None
            name = checkpoint["project"]
            project_id = resolve_project_id(workspace, name, operation_id=operation_id, slot="project-0")
            project_id, _ = ensure_project(workspace, name, project_id=project_id, location=location)
            enriched["project_ids"] = [project_id]
            enriched["project_display_names"] = [name]
    record_path, record = _original_commit_operation(
        workspace,
        operation_id=operation_id,
        kind=kind,
        payload_digest=payload_digest,
        details=enriched,
        target_revision=target_revision,
    )
    session = load_session(workspace)
    advance_session_revision(workspace, session, int(record["revision"]))
    return record_path, record


def advance_store_head(workspace: Path, record_path: Path, record: dict[str, Any]):
    result = _original_advance_store_head(workspace, record_path, record)
    reconcile_project_heads(workspace)
    reconcile_latest_checkpoint(workspace)
    return result


core.writer_lock = coordinated_writer_lock
core.require_operation_authority = require_operation_authority
core.commit_operation = commit_operation
core.advance_store_head = advance_store_head


def _status_receipt(workspace: Path, operation_id: str) -> dict[str, Any]:
    try:
        return receipt_for_operation(workspace, operation_id, expected_kind="checkpoint")
    except StateError as committed_error:
        pending_file = core.pending_path(workspace)
        if not pending_file.is_file():
            raise committed_error
        pending = core.validate_pending(workspace, read_json(pending_file))
        if pending.get("operation_id") != operation_id:
            raise committed_error
        return pending_receipt(
            "checkpoint",
            pending,
            recovery_action="python3 scripts/checkpoint.py --workspace <same-workspace> --recover-pending",
        )


def _emit_receipt(receipt: dict[str, Any]) -> None:
    if _JSON_OUTPUT:
        print_json_receipt(receipt)
    else:
        print_text_receipt(receipt)


def _run() -> int:
    workspace_arg = _peek_option("--workspace")
    if _STATUS_OPERATION_ID is not None:
        if not workspace_arg or not _STATUS_OPERATION_ID:
            print("CHECKPOINT FAILED: --workspace and a non-empty --status operation ID are required", file=sys.stderr)
            return 1
        try:
            workspace = resolve_workspace(workspace_arg)
            _emit_receipt(_status_receipt(workspace, _STATUS_OPERATION_ID))
            return 0
        except (StateError, OSError, KeyError, TypeError, ValueError) as exc:
            print(f"CHECKPOINT FAILED: {exc}", file=sys.stderr)
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
                  "  --status OPERATION_ID  report a persisted checkpoint without mutating state\n"
                  "  --json            print the receipt as JSON")
        raise
    if result != 0:
        sys.stdout.write(captured.getvalue())
        return result
    if not workspace_arg:
        print("CHECKPOINT FAILED: committed state exists but --workspace could not be resolved for its receipt", file=sys.stderr)
        return 1
    try:
        receipt = latest_receipt(resolve_workspace(workspace_arg), expected_kind="checkpoint")
        _emit_receipt(receipt)
        return 0
    except (StateError, OSError, KeyError, TypeError, ValueError) as exc:
        print(f"CHECKPOINT FAILED: committed operation could not be reconstructed as a receipt: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(_run())
