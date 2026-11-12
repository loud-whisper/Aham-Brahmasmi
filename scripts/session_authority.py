#!/usr/bin/env python3
"""Controller-issued session authority for supported Brain mutations."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any, Iterable

from state_io import StateError, read_json, require_managed_path, require_workspace, utc_now
from state_store import durable_write_json, validate_store

SESSION_FORMAT = "aham-brahmasmi-session-authority"
SESSION_VERSION = 1
SESSION_ID = re.compile(r"^ses_[0-9a-f]{32}$")
AUTHORITY_PATH = "state/session_authority.json"
KNOWN_OPERATIONS = {"checkpoint", "recover_checkpoint", "wrap_up", "recover_wrap_up"}
# New durable work needs confirmed reading; recovery of interrupted work does not.
CONTEXT_GATED_OPERATIONS = {"checkpoint", "wrap_up"}
CONTEXT_FIELDS = {"mode", "source_revision", "packet_sha256", "status", "confirmed_parts", "method"}
CONTEXT_METHODS = {None, "packet_parts", "chat_packet"}
PACKET_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def validate_context(value: Any) -> None:
    """Reading state of a startup-issued session. Absent on owner and setup sessions."""
    if value is None:
        return
    if not isinstance(value, dict) or set(value) != CONTEXT_FIELDS:
        raise StateError("session authority context has unknown or missing fields")
    if value["mode"] not in {"quick", "regular"} or value["status"] not in {"pending", "confirmed"}:
        raise StateError("session authority context mode or status is not recognized")
    if type(value["source_revision"]) is not int or value["source_revision"] < 0:
        raise StateError("session authority context source_revision must be a non-negative integer")
    if not isinstance(value["packet_sha256"], str) or not PACKET_DIGEST.fullmatch(value["packet_sha256"]):
        raise StateError("session authority context packet_sha256 is invalid")
    parts = value["confirmed_parts"]
    if (not isinstance(parts, list) or any(type(item) is not int or item < 1 for item in parts)
            or parts != sorted(set(parts))):
        raise StateError("session authority context confirmed_parts must be ascending part indexes")
    if value["method"] not in CONTEXT_METHODS or (value["method"] is None) != (value["status"] == "pending"):
        raise StateError("session authority context method does not match its status")


def authority_path(workspace: Path) -> Path:
    return require_managed_path(workspace, AUTHORITY_PATH, label="session authority record")


def current_revision_readonly(workspace: Path) -> int:
    """Read the cached committed revision without creating writer state."""
    path = require_managed_path(workspace, "state/store.json", label="state store")
    if not path.exists():
        return 0
    return int(validate_store(read_json(path))["revision"])


def validate_session(value: Any, workspace: Path | None = None) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise StateError("session authority must be a JSON object")
    required = {
        "format",
        "version",
        "session_id",
        "issued_at",
        "source",
        "workspace_id",
        "project_id",
        "requested_runtime",
        "runtime",
        "harness",
        "mode",
        "capabilities",
        "authority",
        "allowed_operations",
        "current_revision",
    }
    # "context" is optional so that records written before reading confirmation
    # existed, and owner or setup sessions that never carry it, remain valid.
    unknown = set(value) - required - {"context"}
    missing = required - set(value)
    if unknown:
        raise StateError("session authority contains unknown fields: " + ", ".join(sorted(unknown)))
    if missing:
        raise StateError("session authority is missing fields: " + ", ".join(sorted(missing)))
    if value.get("format") != SESSION_FORMAT or value.get("version") != SESSION_VERSION:
        raise StateError("session authority format/version is not recognized")
    session_id = value.get("session_id")
    if not isinstance(session_id, str) or not SESSION_ID.fullmatch(session_id):
        raise StateError("session authority has an invalid session_id")
    for field in ("issued_at", "source", "workspace_id", "requested_runtime", "runtime", "mode", "authority"):
        if not isinstance(value.get(field), str) or not value[field]:
            raise StateError(f"session authority field '{field}' must be a non-empty string")
    project_id = value.get("project_id")
    if project_id is not None and (not isinstance(project_id, str) or not project_id):
        raise StateError("session authority project_id must be null or a non-empty stable project ID")
    harness = value.get("harness")
    if harness is not None and (not isinstance(harness, str) or not harness.strip()):
        raise StateError("session authority harness must be null or a non-empty string")
    capabilities = value.get("capabilities")
    if not isinstance(capabilities, list) or any(not isinstance(item, str) or not item for item in capabilities):
        raise StateError("session authority capabilities must be a list of strings")
    operations = value.get("allowed_operations")
    if not isinstance(operations, list) or any(item not in KNOWN_OPERATIONS for item in operations):
        raise StateError("session authority contains an unknown allowed operation")
    if len(set(operations)) != len(operations):
        raise StateError("session authority contains duplicate allowed operations")
    if value["authority"] not in {"read_only", "read_write"}:
        raise StateError("session authority mode is not recognized")
    if value["authority"] == "read_only" and operations:
        raise StateError("read-only session authority cannot allow mutation operations")
    if value["authority"] == "read_write" and not operations:
        raise StateError("read-write session authority must allow at least one mutation operation")
    revision = value.get("current_revision")
    if not isinstance(revision, int) or revision < 0:
        raise StateError("session authority current_revision must be a non-negative integer")
    validate_context(value.get("context"))
    if workspace is not None:
        brain = require_workspace(workspace)
        if value["workspace_id"] != brain["workspace_id"]:
            raise StateError("session authority belongs to a different workspace identity")
    return value


def issue_session(
    workspace: Path,
    *,
    source: str,
    requested_runtime: str,
    runtime: str,
    mode: str,
    capabilities: Iterable[str],
    allowed_operations: Iterable[str],
    project_id: str | None = None,
    harness: str | None = None,
    current_revision: int | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    brain = require_workspace(workspace)
    operations = list(dict.fromkeys(allowed_operations))
    unknown = sorted(set(operations) - KNOWN_OPERATIONS)
    if unknown:
        raise StateError("cannot issue authority for unknown operation(s): " + ", ".join(unknown))
    authority = "read_write" if operations else "read_only"
    record = {
        "format": SESSION_FORMAT,
        "version": SESSION_VERSION,
        "session_id": f"ses_{uuid.uuid4().hex}",
        "issued_at": utc_now(),
        "source": source,
        "workspace_id": brain["workspace_id"],
        "project_id": project_id,
        "requested_runtime": requested_runtime,
        "runtime": runtime,
        "harness": harness,
        "mode": mode,
        "capabilities": sorted(set(capabilities)),
        "authority": authority,
        "allowed_operations": operations,
        "current_revision": current_revision if current_revision is not None else current_revision_readonly(workspace),
    }
    if context is not None:
        record["context"] = context
    validate_session(record, workspace)
    durable_write_json(authority_path(workspace), record)
    return record


def issue_bootstrap_session(workspace: Path) -> dict[str, Any]:
    """Establish trusted direct-CLI authority created by explicit workspace setup."""
    return issue_session(
        workspace,
        source="workspace_setup",
        requested_runtime="direct_cli",
        runtime="direct_cli",
        harness=None,
        mode="bootstrap",
        capabilities=("read_files", "write_files", "run_commands"),
        allowed_operations=("checkpoint", "recover_checkpoint", "wrap_up", "recover_wrap_up"),
        current_revision=0,
    )


def load_session(workspace: Path) -> dict[str, Any]:
    path = authority_path(workspace)
    if not path.is_file():
        raise StateError("session authority is not established; run startup before runtime mutation")
    return validate_session(read_json(path), workspace)


def require_operation_authority(
    workspace: Path,
    operation: str,
    *,
    session_id: str | None = None,
    project_id: str | None = None,
    committed_revision: int | None = None,
    context_verified: bool = False,
) -> dict[str, Any]:
    """Return the active session when it may run the operation.

    ``context_verified`` is for a caller that has itself verified what the assistant
    read, such as the chat import checking the echoed packet digest. It replaces only
    the reading check; trust, mode, project and revision checks still apply.
    """
    if operation not in KNOWN_OPERATIONS:
        raise StateError(f"unknown authority operation: {operation}")
    session = load_session(workspace)

    is_bootstrap_direct_cli = session["source"] in {"workspace_setup", "workspace_owner"} and session["runtime"] == "direct_cli"
    if is_bootstrap_direct_cli:
        if session["mode"] == "owner_recovery" and session_id is None:
            raise StateError("owner recovery requires its exact --session-id")
        if session_id is not None and session_id != session["session_id"]:
            raise StateError("presented session ID does not match the active bootstrap session authority")
    else:
        if session_id is None:
            raise StateError("the active runtime session authority requires its exact --session-id for mutation")
        if session_id != session["session_id"]:
            raise StateError("presented session ID does not match the active session authority")

    if operation not in session["allowed_operations"]:
        if session["mode"] == "quick":
            raise StateError(
                f"Quick sessions are read-only and cannot run '{operation}'; "
                "run start --mode regular for a new session ID, then retry")
        raise StateError(
            f"session authority denies operation '{operation}' in mode '{session['mode']}' for runtime '{session['runtime']}'"
        )
    if not is_bootstrap_direct_cli and operation in CONTEXT_GATED_OPERATIONS and not context_verified:
        context = session.get("context")
        if context is None or context["status"] != "confirmed":
            raise StateError(
                f"session authority refuses '{operation}' until the startup context is confirmed as read; "
                "read each part with context --startup --part N, then run confirm-context with every part_sha256")
    if not is_bootstrap_direct_cli:
        from runtime_trust import runtime_name, trusted_runtimes
        if runtime_name(session["requested_runtime"]) not in trusted_runtimes(workspace):
            raise StateError("runtime trust is absent or revoked; ask the workspace owner to confirm trust, then run startup")
    bound_project = session.get("project_id")
    if bound_project is not None:
        if project_id is None:
            raise StateError("session authority is project-bound but the mutation did not present a project identity")
        if bound_project != project_id:
            raise StateError("session authority is bound to a different project identity")
    if committed_revision is not None and session["current_revision"] != committed_revision:
        raise StateError(
            f"session authority revision {session['current_revision']} does not match committed revision {committed_revision}; run startup again"
        )
    return session


def mark_context_confirmed(workspace: Path, session_id: str, method: str) -> None:
    """Record verified reading on the active startup-issued session, if it is pending."""
    session = load_session(workspace)
    context = session.get("context")
    if session["session_id"] != session_id or context is None or context["status"] == "confirmed":
        return
    updated = dict(session)
    updated["context"] = dict(context, status="confirmed", method=method)
    validate_session(updated, workspace)
    durable_write_json(authority_path(workspace), updated)


def advance_session_revision(workspace: Path, session: dict[str, Any], revision: int) -> dict[str, Any]:
    validated = validate_session(session, workspace)
    current = load_session(workspace)
    if current["session_id"] != validated["session_id"]:
        raise StateError("active session authority changed before the committed revision could be acknowledged")
    if revision < validated["current_revision"]:
        raise StateError("cannot move session authority revision backwards")
    updated = dict(validated)
    updated["current_revision"] = revision
    validate_session(updated, workspace)
    durable_write_json(authority_path(workspace), updated)
    return updated
