"""Explicit workspace-owner runtime trust and transient writer self-tests."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import uuid

from session_authority import (advance_session_revision, issue_session,
                               require_operation_authority)
from state_io import StateError, read_json, require_managed_path, require_workspace, resolve_workspace
from state_store import (advance_store_head, commit_operation, digest_json, durable_write_json,
                         list_operation_records, sync_directory, writer_lock)

KIND = "runtime_control"
NAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,79}")


def runtime_name(value: object) -> str:
    if not isinstance(value, str):
        raise StateError("runtime name must be text")
    normalized = value.strip().lower()
    if not NAME.fullmatch(normalized):
        raise StateError("runtime name must contain 1-80 letters, digits, dots, underscores or hyphens")
    return normalized


def _request(value: object) -> dict:
    if (not isinstance(value, dict) or set(value) != {"action", "runtime", "human_confirmation"}
            or not isinstance(value["action"], str) or value["action"] not in {"trust", "revoke"}):
        raise StateError("runtime trust request is invalid")
    name = runtime_name(value["runtime"])
    if value["runtime"] != name or value["human_confirmation"] != name:
        raise StateError("runtime trust requires the exact normalized runtime confirmation")
    return value


def trusted_runtimes(workspace: Path) -> set[str]:
    require_workspace(workspace)
    trusted = set()
    for _, record in list_operation_records(workspace):
        if record["kind"] != KIND:
            continue
        if set(record["details"]) != {"request"}:
            raise StateError("runtime trust record details are invalid")
        request = _request(record["details"]["request"])
        if digest_json(request) != record["payload_digest"]:
            raise StateError("runtime trust record conflicts with its immutable digest")
        if request["action"] == "trust":
            trusted.add(request["runtime"])
        else:
            trusted.discard(request["runtime"])
    return trusted


def _materialize(workspace: Path, revision: int) -> None:
    value = {"format": "aham-runtime-trust-view", "version": 1, "revision": revision,
             "trusted": sorted(trusted_runtimes(workspace))}
    durable_write_json(require_managed_path(workspace, "state/runtime_trust.json", label="runtime trust view"), value)


def change_trust(workspace: Path, runtime: str, *, trusted: bool, human_confirmation: str,
                 session_id=None, owner_control=False) -> dict:
    workspace = workspace.resolve()
    require_workspace(workspace)
    name = runtime_name(runtime)
    if type(trusted) is not bool or type(owner_control) is not bool:
        raise StateError("runtime trust control flags must be booleans")
    request = _request({"action": "trust" if trusted else "revoke", "runtime": name,
                        "human_confirmation": human_confirmation})
    with writer_lock(workspace) as head:
        for path in ("state/pending_wrap_up.json", "state/pending_checkpoint.json"):
            if require_managed_path(workspace, path, label="pending writer operation").exists():
                raise StateError("recover the pending operation before changing runtime trust")
        trusted_runtimes(workspace)  # Refuse corrupt history before issuing owner control.
        if owner_control:
            # Explicit local owner command, never inferred from a model's name or report.
            # Confirmation records intent; it does not authenticate human identity.
            session = issue_session(workspace, source="workspace_owner", requested_runtime="direct_cli",
                                    runtime="direct_cli", mode="owner_control",
                                    capabilities=("read_files", "write_files", "run_commands"),
                                    allowed_operations=("checkpoint", "recover_checkpoint", "wrap_up", "recover_wrap_up"),
                                    current_revision=head["revision"])
            session_id = session["session_id"]
        session = require_operation_authority(workspace, "wrap_up", session_id=session_id,
                                              committed_revision=head["revision"])
        operation_id = "runtime-control-" + uuid.uuid4().hex
        path, record = commit_operation(workspace, operation_id=operation_id, kind=KIND,
                                        payload_digest=digest_json(request), details={"request": request},
                                        target_revision=head["revision"] + 1)
        advance_store_head(workspace, path, record)
        advance_session_revision(workspace, session, record["revision"])
        _materialize(workspace, record["revision"])
        from operation_receipt import receipt_for_operation
        return receipt_for_operation(workspace, operation_id, expected_kind=KIND)


def repair_trust_view(workspace: Path, *, session_id=None) -> dict:
    workspace = workspace.resolve()
    require_workspace(workspace)
    with writer_lock(workspace) as head:
        for relative in ("state/pending_wrap_up.json", "state/pending_checkpoint.json"):
            if require_managed_path(workspace, relative, label="pending writer operation").exists():
                raise StateError("recover the pending operation before repairing runtime trust")
        require_operation_authority(workspace, "wrap_up", session_id=session_id,
                                    committed_revision=head["revision"])
        _materialize(workspace, head["revision"])
        return {"status": "repaired", "revision": head["revision"]}


def owner_recovery_session(workspace: Path, *, human_confirmation: str) -> dict:
    """Explicit owner access to finish legacy pending work before trust changes."""
    workspace = workspace.resolve()
    brain = require_workspace(workspace)
    if human_confirmation != brain["workspace_id"]:
        raise StateError("owner recovery requires --confirm with the exact workspace_id from BRAIN.json")
    pending = [require_managed_path(workspace, relative, label="pending writer operation")
               for relative in ("state/pending_checkpoint.json", "state/pending_wrap_up.json")]
    if not any(path.exists() for path in pending):
        raise StateError("no pending checkpoint or wrap-up needs owner recovery access; use normal startup")
    with writer_lock(workspace) as head:
        if not any(path.exists() for path in pending):
            raise StateError("pending work was already recovered; use normal startup")
        trusted_runtimes(workspace)
        return issue_session(workspace, source="workspace_owner", requested_runtime="direct_cli", runtime="direct_cli",
                             mode="owner_recovery", capabilities=("read_files", "write_files", "run_commands"),
                             allowed_operations=("recover_checkpoint", "recover_wrap_up"), current_revision=head["revision"])


def probe_writer(workspace: Path, *, head=None) -> dict:
    workspace = workspace.resolve()
    require_workspace(workspace)
    if head is None:
        with writer_lock(workspace) as locked_head:
            return probe_writer(workspace, head=locked_head)
    payload = {"format": "aham-writer-probe", "workspace_id": require_workspace(workspace)["workspace_id"],
               "nonce": uuid.uuid4().hex, "revision": head["revision"]}
    directory = require_managed_path(workspace, "state/runtime_probes", label="writer probe directory")
    path = require_managed_path(workspace, directory / (payload["nonce"] + ".json"), label="writer probe")
    try:
        durable_write_json(path, payload)
        if read_json(path) != payload:
            raise StateError("writer self-test readback did not match")
    finally:
        path.unlink(missing_ok=True)
        if directory.exists():
            sync_directory(directory)
    return {"status": "passed", "verified": ["writer_write", "exact_readback", "probe_cleanup"]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Record a workspace owner's explicit runtime trust choice.")
    parser.add_argument("action", choices=("trust", "revoke", "list", "repair", "owner-recovery"))
    parser.add_argument("runtime", nargs="?")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--confirm", help="Owner confirmation: runtime name for trust/revoke, workspace_id for recovery")
    parser.add_argument("--session-id")
    args = parser.parse_args()
    try:
        workspace = resolve_workspace(args.workspace)
        if args.action == "list":
            result = {"trusted": sorted(trusted_runtimes(workspace))}
        elif args.action == "repair":
            result = repair_trust_view(workspace, session_id=args.session_id)
        elif args.action == "owner-recovery":
            result = owner_recovery_session(workspace, human_confirmation=args.confirm)
        else:
            result = change_trust(workspace, args.runtime, trusted=args.action == "trust",
                                  human_confirmation=args.confirm, owner_control=True)
        print(json.dumps(result, sort_keys=True, ensure_ascii=True))
        return 0
    except (StateError, OSError, ValueError) as exc:
        print("RUNTIME TRUST FAILED: " + json.dumps(str(exc), ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
