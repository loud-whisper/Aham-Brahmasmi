#!/usr/bin/env python3
"""Validate runtime/harness evidence, including negative-path rehearsals."""

from __future__ import annotations

from typing import Any

import runtime_evidence_core as _core
from runtime_evidence_core import *  # noqa: F401,F403


FAILURE_ENTRY_FIELDS = {
    "entry_id",
    "evidence_type",
    "rehearsal_id",
    "framework_commit",
    "malformed_exit_code",
    "malformed_stderr_sha256",
    "malformed_zero_mutation",
    "denied_exit_code",
    "denied_stderr_sha256",
    "denied_zero_mutation",
    "interrupted_operation_id",
    "crash_point",
    "writer_crash_exit_code",
    "source_revision",
    "recovered_revision",
    "source_checkpoint_id",
    "recovered_checkpoint_id",
    "state_digest",
    "target_runtime_profile",
    "target_model",
    "target_harness",
    "target_harness_version",
    "target_context_tokens",
    "target_quantization",
    "target_os_platform",
    "target_permission_mode",
    "target_human_intervention",
    "target_runtime_command_sha256",
    "fresh_target_session",
    "result",
    "verified_at",
    "independently_verified",
    "claim_scope",
    "source",
    "limitations",
}

_core.ENTRY_TYPES.add("runtime_failure_paths")
_core.CLAIM_SCOPES["runtime_failure_paths"] = "single_failure_path_rehearsal"
ENTRY_TYPES = _core.ENTRY_TYPES
CLAIM_SCOPES = _core.CLAIM_SCOPES

_original_validate_entry = _core.validate_entry
_original_validate_register = _core.validate_register


def require_nonzero_int(entry: dict[str, Any], field: str) -> int:
    value = entry[field]
    if isinstance(value, bool) or not isinstance(value, int) or value == 0:
        raise EvidenceError(f"{field} must be a non-zero integer")
    return value


def validate_failure_entry(entry: dict[str, Any]) -> None:
    require_string(entry, "rehearsal_id")
    framework_commit = entry["framework_commit"]
    if not isinstance(framework_commit, str) or _core.HEX40.fullmatch(framework_commit) is None:
        raise EvidenceError("framework_commit must be an exact 40-character Git commit SHA")

    malformed_exit = require_nonzero_int(entry, "malformed_exit_code")
    require_digest(entry, "malformed_stderr_sha256")
    if not isinstance(entry["malformed_zero_mutation"], bool):
        raise EvidenceError("malformed_zero_mutation must be true or false")

    denied_exit = require_nonzero_int(entry, "denied_exit_code")
    require_digest(entry, "denied_stderr_sha256")
    if not isinstance(entry["denied_zero_mutation"], bool):
        raise EvidenceError("denied_zero_mutation must be true or false")

    require_string(entry, "interrupted_operation_id")
    crash_point = require_string(entry, "crash_point")
    writer_crash_exit = require_nonzero_int(entry, "writer_crash_exit_code")
    source_revision = require_positive_int(entry, "source_revision")
    recovered_revision = require_positive_int(entry, "recovered_revision")
    source_checkpoint_id = require_string(entry, "source_checkpoint_id")
    recovered_checkpoint_id = require_string(entry, "recovered_checkpoint_id")
    require_digest(entry, "state_digest")

    require_string(entry, "target_runtime_profile")
    for field in ("target_model", "target_harness", "target_harness_version", "target_quantization"):
        require_optional_string(entry, field)
    require_optional_positive_int(entry, "target_context_tokens")
    require_string(entry, "target_os_platform")
    require_string(entry, "target_permission_mode")
    require_optional_bool(entry, "target_human_intervention")
    require_digest(entry, "target_runtime_command_sha256")
    if not isinstance(entry["fresh_target_session"], bool):
        raise EvidenceError("fresh_target_session must be true or false")

    if entry["result"] == "pass":
        if entry["independently_verified"] is not True:
            raise EvidenceError("passing failure-path rehearsal must be independently verified")
        if malformed_exit == 0 or entry["malformed_zero_mutation"] is not True:
            raise EvidenceError("passing failure-path rehearsal requires malformed request rejection with zero mutation")
        if denied_exit == 0 or entry["denied_zero_mutation"] is not True:
            raise EvidenceError("passing failure-path rehearsal requires denied operation rejection with zero mutation")
        if crash_point != "wrap_up_after_commit_record":
            raise EvidenceError("passing failure-path rehearsal crash_point must be 'wrap_up_after_commit_record'")
        if writer_crash_exit != 86:
            raise EvidenceError("passing failure-path rehearsal writer_crash_exit_code must equal 86")
        if source_revision != recovered_revision:
            raise EvidenceError("passing failure-path rehearsal recovered_revision must equal source_revision")
        if source_checkpoint_id != recovered_checkpoint_id:
            raise EvidenceError(
                "passing failure-path rehearsal recovered_checkpoint_id must equal source_checkpoint_id"
            )
        if entry["fresh_target_session"] is not True:
            raise EvidenceError("passing failure-path rehearsal requires fresh_target_session=true")
        if entry["target_human_intervention"] is not False:
            raise EvidenceError("passing failure-path rehearsal requires target_human_intervention=false")


def validate_entry(entry: Any) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise EvidenceError("each runtime evidence entry must be an object")

    if entry.get("evidence_type") != "runtime_failure_paths":
        return _original_validate_entry(entry)

    reliability_fields = [key for key in entry if "reliability" in str(key).lower()]
    if reliability_fields:
        raise EvidenceError(
            "single-run evidence may not contain a reliability percentage or reliability score"
        )

    unknown = set(entry) - FAILURE_ENTRY_FIELDS
    missing = FAILURE_ENTRY_FIELDS - set(entry)
    if unknown:
        raise EvidenceError("runtime evidence entry contains unknown fields: " + ", ".join(sorted(unknown)))
    if missing:
        raise EvidenceError("runtime evidence entry is missing fields: " + ", ".join(sorted(missing)))

    _core.validate_common_entry(entry, "runtime_failure_paths")
    validate_failure_entry(entry)
    return entry


_core.validate_entry = validate_entry


def validate_register(value: Any) -> dict[str, Any]:
    register = _original_validate_register(value)
    seen_failure_rehearsals: set[str] = set()
    for entry in register["entries"]:
        if entry["evidence_type"] != "runtime_failure_paths":
            continue
        rehearsal_id = entry["rehearsal_id"]
        if rehearsal_id in seen_failure_rehearsals:
            raise EvidenceError(
                f"duplicate runtime failure-path identity: rehearsal_id={rehearsal_id}"
            )
        seen_failure_rehearsals.add(rehearsal_id)
    return register


_core.validate_register = validate_register


if __name__ == "__main__":
    raise SystemExit(_core.main())
