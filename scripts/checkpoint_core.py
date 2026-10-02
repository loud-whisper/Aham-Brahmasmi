#!/usr/bin/env python3
"""Create and verify a revisioned durable recovery checkpoint."""

from __future__ import annotations

import argparse
import json
import sys
from recovery_commands import recovery_command
import uuid
from pathlib import Path
from typing import Any

from session_authority import advance_session_revision, require_operation_authority
from state_io import (
    StateError,
    build_checkpoint,
    git_snapshot,
    persist_checkpoint,
    read_json,
    require_workspace,
    resolve_workspace,
    validate_checkpoint,
    workspace_fingerprint,
)
from state_store import (
    advance_store_head,
    assert_expected_revision,
    commit_operation,
    digest_json,
    durable_write_json,
    find_operation,
    reconcile_store,
    sync_directory,
    test_crash_point,
    writer_lock,
)


PENDING_FORMAT = "aham-brahmasmi-checkpoint-operation"
PENDING_VERSION = 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create an Aham Brahmasmi recovery checkpoint.")
    parser.add_argument("--workspace", required=True, help="Path to the private workspace")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--summary", help="Short verified summary of the completed milestone")
    mode.add_argument("--recover-pending", action="store_true", help="Recover an interrupted checkpoint operation")
    parser.add_argument("--completed", action="append", default=[], help="Verified completed item; repeat as needed")
    parser.add_argument("--next-step", action="append", default=[], help="Next verified step; repeat as needed")
    parser.add_argument("--artifact", action="append", default=[], help="Relevant file, commit, PR or artifact reference")
    parser.add_argument("--project", help="Optional project name")
    parser.add_argument("--repo", help="Optional Git repository whose branch and commit should be recorded")
    parser.add_argument("--expected-revision", type=int, help="Fail unless the committed workspace revision matches")
    return parser.parse_args()


def pending_path(workspace: Path) -> Path:
    return workspace / "state" / "pending_checkpoint.json"


def validate_pending(workspace: Path, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise StateError("pending checkpoint transaction must be an object")
    required = {
        "format",
        "version",
        "status",
        "operation_id",
        "workspace_fingerprint",
        "base_revision",
        "target_revision",
        "payload_digest",
        "checkpoint",
    }
    unknown = set(value) - required
    missing = required - set(value)
    if unknown:
        raise StateError("pending checkpoint contains unknown fields: " + ", ".join(sorted(unknown)))
    if missing:
        raise StateError("pending checkpoint is missing fields: " + ", ".join(sorted(missing)))
    if value.get("format") != PENDING_FORMAT or value.get("version") != PENDING_VERSION or value.get("status") != "pending":
        raise StateError("pending checkpoint format/version/status is not recognized")
    if value.get("workspace_fingerprint") != workspace_fingerprint(require_workspace(workspace)):
        raise StateError("pending checkpoint belongs to a different workspace identity")
    if not isinstance(value.get("operation_id"), str) or not value["operation_id"]:
        raise StateError("pending checkpoint has no valid operation_id")
    base_revision = value.get("base_revision")
    target_revision = value.get("target_revision")
    if not isinstance(base_revision, int) or base_revision < 0 or target_revision != base_revision + 1:
        raise StateError("pending checkpoint revision transition is invalid")
    checkpoint = value.get("checkpoint")
    if not isinstance(checkpoint, dict) or validate_checkpoint(checkpoint):
        raise StateError("pending checkpoint payload is invalid")
    if checkpoint.get("revision") != target_revision:
        raise StateError("pending checkpoint revision does not match its target revision")
    if value.get("payload_digest") != digest_json(checkpoint):
        raise StateError("pending checkpoint payload digest does not match its canonical payload")
    return value


def verify_persisted_checkpoint(workspace: Path, path: Path, checkpoint: dict[str, Any]) -> None:
    persisted = read_json(path)
    errors = validate_checkpoint(persisted)
    if errors:
        raise StateError("persisted checkpoint failed validation: " + "; ".join(errors))
    if persisted != checkpoint:
        raise StateError("persisted checkpoint does not match the checkpoint payload")
    latest = read_json(workspace / "state" / "latest_checkpoint.json")
    expected_file = f"state/checkpoints/{path.name}"
    if latest.get("id") != checkpoint.get("id") or latest.get("file") != expected_file:
        raise StateError("latest checkpoint pointer does not reference the persisted checkpoint")
    if latest.get("revision") != checkpoint.get("revision"):
        raise StateError("latest checkpoint pointer does not reference the committed revision")


def make_pending(workspace: Path, args: argparse.Namespace, current_revision: int) -> dict[str, Any]:
    repository = git_snapshot(args.repo) if args.repo else None
    target_revision = current_revision + 1
    checkpoint = build_checkpoint(
        workspace,
        summary=args.summary,
        completed=args.completed,
        next_steps=args.next_step,
        project=args.project,
        artifacts=args.artifact,
        repository=repository,
        revision=target_revision,
    )
    return {
        "format": PENDING_FORMAT,
        "version": PENDING_VERSION,
        "status": "pending",
        "operation_id": f"checkpoint-{uuid.uuid4().hex}",
        "workspace_fingerprint": workspace_fingerprint(require_workspace(workspace)),
        "base_revision": current_revision,
        "target_revision": target_revision,
        "payload_digest": digest_json(checkpoint),
        "checkpoint": checkpoint,
    }


def finish_pending(workspace: Path, pending: dict[str, Any]) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    pending = validate_pending(workspace, pending)
    operation_id = pending["operation_id"]
    existing = find_operation(workspace, operation_id)
    checkpoint = pending["checkpoint"]
    path = persist_checkpoint(workspace, checkpoint)
    sync_directory(path.parent)
    sync_directory((workspace / "state"))
    test_crash_point("checkpoint_after_projection")

    if existing:
        record_path, record = existing
        if record["kind"] != "checkpoint" or record["payload_digest"] != pending["payload_digest"]:
            raise StateError("committed checkpoint operation conflicts with pending state")
        if record["revision"] != pending["target_revision"]:
            raise StateError("committed checkpoint revision conflicts with pending state")
    else:
        current = reconcile_store(workspace)
        if current["revision"] != pending["base_revision"]:
            raise StateError(
                f"checkpoint recovery revision conflict; pending base {pending['base_revision']}, current {current['revision']}"
            )
        record_path, record = commit_operation(
            workspace,
            operation_id=operation_id,
            kind="checkpoint",
            payload_digest=pending["payload_digest"],
            details={"checkpoint": checkpoint, "checkpoint_file": f"state/checkpoints/{path.name}"},
            target_revision=pending["target_revision"],
        )
        test_crash_point("checkpoint_after_commit_record")

    advance_store_head(workspace, record_path, record)
    test_crash_point("checkpoint_after_head")
    verify_persisted_checkpoint(workspace, path, checkpoint)
    pending_file = pending_path(workspace)
    if pending_file.exists():
        pending_file.unlink()
        sync_directory(pending_file.parent)
    return path, checkpoint, record


def main() -> int:
    args = parse_args()
    workspace = resolve_workspace(args.workspace)
    path: Path | None = None
    checkpoint: dict[str, Any] | None = None
    record: dict[str, Any] | None = None
    try:
        require_workspace(workspace)
        with writer_lock(workspace) as head:
            operation = "recover_checkpoint" if args.recover_pending else "checkpoint"
            session = require_operation_authority(workspace, operation, committed_revision=head["revision"])
            pending_file = pending_path(workspace)
            if args.recover_pending:
                if not pending_file.is_file():
                    raise StateError("there is no pending checkpoint operation to recover")
                pending = validate_pending(workspace, read_json(pending_file))
            else:
                if pending_file.exists():
                    raise StateError("an unfinished checkpoint operation exists; recover it first")
                assert_expected_revision(head["revision"], args.expected_revision)
                pending = make_pending(workspace, args, head["revision"])
                durable_write_json(pending_file, pending)
                test_crash_point("checkpoint_after_pending")
            path, checkpoint, record = finish_pending(workspace, pending)
            advance_session_revision(workspace, session, record["revision"])
    except (StateError, OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"CHECKPOINT FAILED: {exc}", file=sys.stderr)
        if pending_path(workspace).exists():
            print(f"Pending checkpoint preserved: {pending_path(workspace)}", file=sys.stderr)
            print("Recovery command: " + recovery_command("save"), file=sys.stderr)
        return 1

    if path is None or checkpoint is None or record is None:
        print("CHECKPOINT FAILED: committed state is unavailable", file=sys.stderr)
        return 1
    print("CHECKPOINT SAVED")
    print("CHECKPOINT VERIFIED")
    print(f"ID: {checkpoint['id']}")
    print(f"Revision: {record['revision']}")
    print(f"File: {path}")
    repository = checkpoint.get("repository")
    if repository:
        print(f"Repository: {repository['name']}")
        print(f"Branch: {repository['branch'] or '(detached)'}")
        print(f"Head: {repository['head']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
