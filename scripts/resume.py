#!/usr/bin/env python3
"""Deterministically recover the newest committed checkpoint, with project-scoped heads."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from project_state import (
    checkpoint_file_from_record,
    git_snapshot_strong,
    project_by_id,
    project_ids_from_record,
    reconcile_latest_checkpoint,
    reconcile_project_heads,
)
from state_io import (
    StateError,
    git_contains_ancestor,
    read_json,
    require_workspace,
    resolve_workspace,
    validate_checkpoint,
    workspace_fingerprint,
)
from state_store import list_operation_records, writer_lock


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify and report the latest committed Aham Brahmasmi checkpoint.")
    parser.add_argument("--workspace", required=True, help="Path to the private workspace")
    parser.add_argument("--repo", help="Git repository to verify when the checkpoint recorded repository state")
    parser.add_argument("--project-id", help="Recover the latest committed checkpoint for one stable project ID")
    return parser.parse_args()


def load_checkpoint_for_record(workspace: Path, record: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    relative = checkpoint_file_from_record(record)
    if not relative:
        raise StateError("committed operation has no checkpoint reference")
    path = workspace / relative
    checkpoint = read_json(path)
    errors = validate_checkpoint(checkpoint)
    if errors:
        raise StateError("checkpoint failed validation: " + "; ".join(errors))
    if checkpoint.get("workspace_fingerprint") != workspace_fingerprint(require_workspace(workspace)):
        raise StateError("checkpoint belongs to a different workspace identity")
    if checkpoint.get("revision") != record.get("revision"):
        raise StateError("checkpoint revision does not match its authoritative committed operation")
    return path, checkpoint


def verify_repository(checkpoint: dict[str, Any], repo: str | None) -> list[str]:
    expected = checkpoint.get("repository")
    if not expected:
        if repo:
            return ["a repository was supplied, but this checkpoint did not bind repository state"]
        return []
    if not isinstance(expected, dict):
        raise StateError("checkpoint repository state is malformed")
    if not repo:
        raise StateError("checkpoint recorded repository state; --repo is required to verify it")

    current = git_snapshot_strong(repo)
    expected_identity = expected.get("identity")
    if not isinstance(expected_identity, str) or not expected_identity:
        raise StateError("repository identity is absent from this checkpoint; full continuation cannot be verified")
    if current.get("identity") != expected_identity:
        raise StateError("repository identity mismatch; this clone/location is not the repository recorded by the checkpoint")
    if expected.get("branch") != current.get("branch"):
        raise StateError(f"branch mismatch; checkpoint={expected.get('branch')} current={current.get('branch')}")
    expected_head = expected.get("head")
    if not isinstance(expected_head, str) or not expected_head:
        raise StateError("checkpoint repository state has no valid commit")
    if not git_contains_ancestor(repo, expected_head):
        raise StateError("checkpoint commit is not an ancestor of the current repository state")

    warnings: list[str] = []
    if expected.get("tracked_dirty"):
        warnings.append("checkpoint was created with tracked working-tree changes that were not preserved by the checkpoint")
    if expected.get("untracked_present"):
        warnings.append("checkpoint was created with untracked files that were not preserved by the checkpoint")
    if current.get("tracked_dirty"):
        warnings.append("current repository has tracked working-tree changes outside checkpoint verification")
    if current.get("untracked_present"):
        warnings.append("current repository has untracked files outside checkpoint verification")
    return warnings


def candidate_records(workspace: Path, project_id: str | None) -> list[dict[str, Any]]:
    records = [record for _, record in list_operation_records(workspace) if checkpoint_file_from_record(record)]
    if project_id is not None:
        project_by_id(workspace, project_id)
        records = [record for record in records if project_id in project_ids_from_record(workspace, record)]
    return records


def main() -> int:
    args = parse_args()
    workspace = resolve_workspace(args.workspace)
    try:
        require_workspace(workspace)
    except StateError as exc:
        print(f"RESUME FAILED: {exc}", file=sys.stderr)
        return 1

    pending_wrap = workspace / "state" / "pending_wrap_up.json"
    pending_checkpoint = workspace / "state" / "pending_checkpoint.json"
    if pending_wrap.exists() or pending_checkpoint.exists():
        if pending_wrap.exists():
            print("RESUME BLOCKED: an unfinished wrap-up transaction exists.", file=sys.stderr)
            print("Recover it with scripts/wrap_up.py --workspace <path> --recover-pending before resuming.", file=sys.stderr)
        if pending_checkpoint.exists():
            print("RESUME BLOCKED: an unfinished checkpoint transaction exists.", file=sys.stderr)
            print("Recover it with scripts/checkpoint.py --workspace <path> --recover-pending before resuming.", file=sys.stderr)
        return 2

    try:
        with writer_lock(workspace) as head:
            reconcile_project_heads(workspace)
            reconcile_latest_checkpoint(workspace)
            committed_revision = head["revision"]
            records = candidate_records(workspace, args.project_id)
            if not records:
                raise StateError("no committed checkpoint exists for the requested scope")

            target = records[-1]
            target_revision = target["revision"]
            try:
                path, checkpoint = load_checkpoint_for_record(workspace, target)
            except StateError as newest_error:
                recovered: tuple[Path, dict[str, Any], int] | None = None
                for older in reversed(records[:-1]):
                    try:
                        old_path, old_checkpoint = load_checkpoint_for_record(workspace, older)
                    except StateError:
                        continue
                    recovered = (old_path, old_checkpoint, older["revision"])
                    break
                print("RESUME DEGRADED: newest committed checkpoint cannot be verified.", file=sys.stderr)
                print(f"Committed revision: {target_revision if args.project_id else committed_revision}", file=sys.stderr)
                if recovered:
                    print(f"Recovered revision: {recovered[2]}", file=sys.stderr)
                    print(f"Recovered checkpoint: {recovered[0]}", file=sys.stderr)
                else:
                    print("Recovered revision: none", file=sys.stderr)
                print(f"Continuity gap: {newest_error}", file=sys.stderr)
                print(
                    "Recovery action: repair or restore the newest committed checkpoint before continuing.",
                    file=sys.stderr,
                )
                return 10

            warnings = verify_repository(checkpoint, args.repo)
            if warnings:
                print("RESUME DEGRADED: checkpoint excludes working-tree state from its verification scope.", file=sys.stderr)
                print(f"Committed revision: {target_revision}", file=sys.stderr)
                print(f"Recovered revision: {target_revision}", file=sys.stderr)
                print("Continuity gap: excluded working-tree state was not preserved by the checkpoint.", file=sys.stderr)
                for warning in warnings:
                    print(f"Warning: {warning}", file=sys.stderr)
                print("Verification scope: committed checkpoint data and committed Git history only; unsaved editor buffers are never included.", file=sys.stderr)
                print(
                    "Recovery action: preserve excluded working-tree/editor state separately, then rerun resume with a clean verified repository if full continuation is required.",
                    file=sys.stderr,
                )
                return 11

            print("RESUME STATE VERIFIED: durable checkpoint continuation")
            print(f"Revision: {target_revision}")
            if args.project_id:
                entry = project_by_id(workspace, args.project_id)
                print(f"Project ID: {args.project_id}")
                print(f"Project: {entry['display_name']}")
            print(f"Checkpoint: {checkpoint['id']}")
            print(f"Created: {checkpoint['created_at']}")
            print(f"Summary: {checkpoint['summary']}")
            if checkpoint.get("completed"):
                print("Completed:")
                for item in checkpoint["completed"]:
                    print(f"- {item}")
            if checkpoint.get("next_steps"):
                print("Next steps:")
                for item in checkpoint["next_steps"]:
                    print(f"- {item}")
            print(f"Source: {path}")
            if checkpoint.get("repository"):
                print("Verification scope: committed checkpoint data and committed Git history only.")
                print("Excluded scope: repository working-tree contents, unsaved editor buffers, replicated backup, runtime instruction compliance, end-to-end recovery")
            else:
                print("Verification scope: durable workspace checkpoint data only.")
                print("Excluded scope: repository state, unsaved editor buffers, replicated backup, runtime instruction compliance, end-to-end recovery")
            return 0
    except StateError as exc:
        print(f"RESUME FAILED: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
