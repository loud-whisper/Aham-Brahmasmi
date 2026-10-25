#!/usr/bin/env python3
"""Validate runtime/harness evidence and reconcile its documentation status."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


REGISTER_FORMAT = "aham-brahmasmi-runtime-evidence-register"
REGISTER_VERSION = 1
ENTRY_TYPES = {"live_runtime_rehearsal", "framework_profile_test", "runtime_switch_recovery"}
RESULTS = {"pass", "fail", "incomplete", "blocked"}
CLAIM_SCOPES = {
    "live_runtime_rehearsal": "single_run_smoke_test",
    "framework_profile_test": "framework_profile_only",
    "runtime_switch_recovery": "single_switch_recovery",
}
ENTRY_FIELDS = {
    "entry_id",
    "evidence_type",
    "runtime_profile",
    "model",
    "harness",
    "harness_version",
    "os_platform",
    "framework_commit",
    "rehearsal_id",
    "permission_mode",
    "result",
    "human_intervention",
    "context_tokens",
    "quantization",
    "verified_at",
    "independently_verified",
    "claim_scope",
    "source",
    "limitations",
}
SWITCH_ENTRY_FIELDS = {
    "entry_id",
    "evidence_type",
    "switch_id",
    "framework_commit",
    "from_runtime_profile",
    "from_model",
    "from_harness",
    "from_harness_version",
    "from_context_tokens",
    "from_quantization",
    "from_os_platform",
    "from_permission_mode",
    "from_human_intervention",
    "from_runtime_command_sha256",
    "to_runtime_profile",
    "to_model",
    "to_harness",
    "to_harness_version",
    "to_context_tokens",
    "to_quantization",
    "to_os_platform",
    "to_permission_mode",
    "to_human_intervention",
    "to_runtime_command_sha256",
    "source_operation_id",
    "source_revision",
    "recovered_revision",
    "source_checkpoint_id",
    "recovered_checkpoint_id",
    "state_digest",
    "fresh_target_session",
    "result",
    "verified_at",
    "independently_verified",
    "claim_scope",
    "source",
    "limitations",
}
HEX40 = re.compile(r"^[0-9a-fA-F]{40}$")
HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
STATUS_START = "<!-- runtime-evidence-status:start -->"
STATUS_END = "<!-- runtime-evidence-status:end -->"
LIVE_PROFILE_LABELS = (
    ("claude", "Claude"),
    ("gemini", "Gemini"),
    ("codex", "Codex"),
    ("local", "Local/open-model"),
)


class EvidenceError(ValueError):
    """Raised when runtime evidence is malformed or overclaims its scope."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Aham Brahmasmi runtime/harness evidence.")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="Validate one versioned runtime evidence register")
    validate.add_argument("--register", required=True, help="Path to the JSON evidence register")

    render = sub.add_parser("render-status", help="Render the canonical Markdown runtime evidence block")
    render.add_argument("--register", required=True, help="Path to the JSON evidence register")

    check_docs = sub.add_parser("check-docs", help="Verify documentation against the canonical evidence register")
    check_docs.add_argument("--register", required=True, help="Path to the JSON evidence register")
    check_docs.add_argument(
        "--document",
        action="append",
        required=True,
        help="Generated evidence document (docs/STATUS.md or PROJECT_CHECKLIST.md); repeat as needed",
    )

    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"could not read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceError("runtime evidence register must be a JSON object")
    return value


def require_string(entry: dict[str, Any], field: str) -> str:
    value = entry[field]
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"{field} must be a non-empty string")
    return value.strip()


def require_optional_string(entry: dict[str, Any], field: str) -> None:
    value = entry[field]
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise EvidenceError(f"{field} must be null or a non-empty string")


def require_optional_positive_int(entry: dict[str, Any], field: str) -> None:
    value = entry[field]
    if value is not None and (
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
    ):
        raise EvidenceError(f"{field} must be null or a positive integer")


def require_positive_int(entry: dict[str, Any], field: str) -> int:
    value = entry[field]
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise EvidenceError(f"{field} must be a positive integer")
    return value


def require_optional_bool(entry: dict[str, Any], field: str) -> None:
    value = entry[field]
    if value is not None and not isinstance(value, bool):
        raise EvidenceError(f"{field} must be true, false, or null")


def require_digest(entry: dict[str, Any], field: str) -> str:
    value = entry[field]
    if not isinstance(value, str) or HEX64.fullmatch(value) is None:
        raise EvidenceError(f"{field} must be an exact 64-character SHA-256 digest")
    return value.lower()


def validate_timestamp(value: Any) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not value.endswith("Z"):
        raise EvidenceError("verified_at must be null or an RFC3339 UTC timestamp ending in Z")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise EvidenceError("verified_at must use YYYY-MM-DDTHH:MM:SSZ") from exc


def validate_common_entry(entry: dict[str, Any], evidence_type: str) -> None:
    require_string(entry, "entry_id")
    result = entry["result"]
    if result not in RESULTS:
        raise EvidenceError(f"unsupported evidence result: {result!r}")
    validate_timestamp(entry["verified_at"])
    if not isinstance(entry["independently_verified"], bool):
        raise EvidenceError("independently_verified must be true or false")
    expected_scope = CLAIM_SCOPES[evidence_type]
    if entry["claim_scope"] != expected_scope:
        raise EvidenceError(
            f"claim_scope for {evidence_type} must be {expected_scope!r}; one run is not a reliability estimate"
        )
    require_string(entry, "source")
    limitations = entry["limitations"]
    if not isinstance(limitations, list) or any(
        not isinstance(item, str) or not item.strip() for item in limitations
    ):
        raise EvidenceError("limitations must be a list of non-empty strings")


def validate_standard_entry(entry: dict[str, Any], evidence_type: str) -> None:
    runtime_profile = entry["runtime_profile"]
    if not isinstance(runtime_profile, str) or not runtime_profile.strip():
        raise EvidenceError("runtime_profile must be a non-empty string")

    for field in (
        "model",
        "harness",
        "harness_version",
        "os_platform",
        "rehearsal_id",
        "permission_mode",
        "quantization",
    ):
        require_optional_string(entry, field)

    framework_commit = entry["framework_commit"]
    if framework_commit is not None and (
        not isinstance(framework_commit, str) or HEX40.fullmatch(framework_commit) is None
    ):
        raise EvidenceError("framework_commit must be null or an exact 40-character Git commit SHA")

    require_optional_bool(entry, "human_intervention")
    require_optional_positive_int(entry, "context_tokens")


def validate_switch_entry(entry: dict[str, Any]) -> None:
    require_string(entry, "switch_id")
    framework_commit = entry["framework_commit"]
    if not isinstance(framework_commit, str) or HEX40.fullmatch(framework_commit) is None:
        raise EvidenceError("framework_commit must be an exact 40-character Git commit SHA")

    for prefix in ("from", "to"):
        require_string(entry, f"{prefix}_runtime_profile")
        for field in ("model", "harness", "harness_version", "quantization"):
            require_optional_string(entry, f"{prefix}_{field}")
        require_string(entry, f"{prefix}_os_platform")
        require_string(entry, f"{prefix}_permission_mode")
        require_optional_bool(entry, f"{prefix}_human_intervention")
        require_optional_positive_int(entry, f"{prefix}_context_tokens")
        require_digest(entry, f"{prefix}_runtime_command_sha256")

    require_string(entry, "source_operation_id")
    source_revision = require_positive_int(entry, "source_revision")
    recovered_revision = require_positive_int(entry, "recovered_revision")
    source_checkpoint_id = require_string(entry, "source_checkpoint_id")
    recovered_checkpoint_id = require_string(entry, "recovered_checkpoint_id")
    require_digest(entry, "state_digest")
    if not isinstance(entry["fresh_target_session"], bool):
        raise EvidenceError("fresh_target_session must be true or false")

    if entry["result"] == "pass":
        if entry["independently_verified"] is not True:
            raise EvidenceError("passing switch recovery must be independently verified")
        if entry["fresh_target_session"] is not True:
            raise EvidenceError("passing switch recovery requires fresh_target_session=true")
        if source_revision != recovered_revision:
            raise EvidenceError("passing switch recovery recovered_revision must equal source_revision")
        if source_checkpoint_id != recovered_checkpoint_id:
            raise EvidenceError("passing switch recovery recovered_checkpoint_id must equal source_checkpoint_id")


def validate_entry(entry: Any) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise EvidenceError("each runtime evidence entry must be an object")

    reliability_fields = [key for key in entry if "reliability" in str(key).lower()]
    if reliability_fields:
        raise EvidenceError(
            "single-run evidence may not contain a reliability percentage or reliability score"
        )

    evidence_type = entry.get("evidence_type")
    if evidence_type not in ENTRY_TYPES:
        raise EvidenceError(f"unsupported evidence_type: {evidence_type!r}")
    fields = SWITCH_ENTRY_FIELDS if evidence_type == "runtime_switch_recovery" else ENTRY_FIELDS
    unknown = set(entry) - fields
    missing = fields - set(entry)
    if unknown:
        raise EvidenceError("runtime evidence entry contains unknown fields: " + ", ".join(sorted(unknown)))
    if missing:
        raise EvidenceError("runtime evidence entry is missing fields: " + ", ".join(sorted(missing)))

    validate_common_entry(entry, evidence_type)
    if evidence_type == "runtime_switch_recovery":
        validate_switch_entry(entry)
    else:
        validate_standard_entry(entry, evidence_type)
    return entry


def validate_register(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceError("runtime evidence register must be an object")
    expected_top = {"format", "version", "entries"}
    unknown = set(value) - expected_top
    missing = expected_top - set(value)
    if unknown:
        raise EvidenceError("runtime evidence register contains unknown fields: " + ", ".join(sorted(unknown)))
    if missing:
        raise EvidenceError("runtime evidence register is missing fields: " + ", ".join(sorted(missing)))
    if value.get("format") != REGISTER_FORMAT or value.get("version") != REGISTER_VERSION:
        raise EvidenceError("runtime evidence register format/version is not recognized")

    entries = value.get("entries")
    if not isinstance(entries, list):
        raise EvidenceError("runtime evidence register entries must be a list")

    seen_entry_ids: set[str] = set()
    seen_live_rehearsals: set[tuple[str, str]] = set()
    seen_switch_ids: set[str] = set()
    for raw_entry in entries:
        entry = validate_entry(raw_entry)
        entry_id = entry["entry_id"]
        if entry_id in seen_entry_ids:
            raise EvidenceError(f"duplicate runtime evidence entry_id: {entry_id}")
        seen_entry_ids.add(entry_id)

        if entry["evidence_type"] == "live_runtime_rehearsal" and entry["rehearsal_id"] is not None:
            identity = (entry["runtime_profile"], entry["rehearsal_id"])
            if identity in seen_live_rehearsals:
                raise EvidenceError(
                    "duplicate live rehearsal identity: "
                    f"runtime_profile={identity[0]} rehearsal_id={identity[1]}"
                )
            seen_live_rehearsals.add(identity)
        if entry["evidence_type"] == "runtime_switch_recovery":
            switch_id = entry["switch_id"]
            if switch_id in seen_switch_ids:
                raise EvidenceError(f"duplicate runtime switch recovery identity: switch_id={switch_id}")
            seen_switch_ids.add(switch_id)

    return value


def live_entries(register: dict[str, Any], profile: str) -> list[dict[str, Any]]:
    return [
        entry
        for entry in register["entries"]
        if entry["evidence_type"] == "live_runtime_rehearsal" and entry["runtime_profile"] == profile
    ]


def has_verified_live_pass(register: dict[str, Any], profile: str) -> bool:
    return any(
        entry["result"] == "pass" and entry["independently_verified"] is True
        for entry in live_entries(register, profile)
    )


def live_status_cells(register: dict[str, Any], profile: str) -> tuple[str, str]:
    entries = live_entries(register, profile)
    passes = [
        entry
        for entry in entries
        if entry["result"] == "pass" and entry["independently_verified"] is True
    ]
    if passes:
        rehearsal_ids = [entry["rehearsal_id"] for entry in passes if entry["rehearsal_id"]]
        rendered_ids = ", ".join(f"`{value}`" for value in rehearsal_ids)
        status = "Independently verified live pass"
        if rendered_ids:
            status += f": {rendered_ids}"
        return status, "Single-run smoke test only, not a reliability estimate"
    if entries:
        return (
            "No independently verified live pass; historical unsuccessful observations are recorded",
            "Live release gate remains open",
        )
    return "No live rehearsal evidence recorded", "Live release gate remains open"


def framework_profile_status(register: dict[str, Any]) -> tuple[str, str]:
    entries = [entry for entry in register["entries"] if entry["evidence_type"] == "framework_profile_test"]
    if any(entry["result"] == "pass" for entry in entries):
        return "Automated framework/profile pass recorded", "Framework/profile only, not live-runtime evidence"
    if entries:
        return "Framework/profile evidence recorded without a pass", "Framework/profile only"
    return "No framework/profile evidence recorded", "Framework/profile only"


def render_status_markdown(register: dict[str, Any]) -> str:
    validate_register(register)
    lines = [
        STATUS_START,
        "Runtime evidence source of truth: `evidence/runtime_harness_register.json`.",
        "",
        "| Runtime/profile | Current evidence | Scope |",
        "| --- | --- | --- |",
    ]
    for profile, label in LIVE_PROFILE_LABELS:
        status, scope = live_status_cells(register, profile)
        lines.append(f"| {label} | {status} | {scope} |")
    framework_status, framework_scope = framework_profile_status(register)
    lines.append(f"| Framework/profile tests | {framework_status} | {framework_scope} |")
    lines.extend(
        [
            "",
            "A live pass records one independently verified rehearsal in one tested environment. It does not establish a reliability percentage or prove other runtime/model/harness configurations.",
            STATUS_END,
        ]
    )
    return "\n".join(lines)


def extract_status_block(text: str, document: Path) -> str:
    start_count = text.count(STATUS_START)
    end_count = text.count(STATUS_END)
    if start_count != 1 or end_count != 1:
        raise EvidenceError(
            f"{document} must contain exactly one {STATUS_START!r} and one {STATUS_END!r} marker"
        )
    start = text.index(STATUS_START)
    end = text.index(STATUS_END, start) + len(STATUS_END)
    return text[start:end]


def verify_checklist_live_boxes(text: str, register: dict[str, Any]) -> None:
    expected = {
        "claude": "Claude-compatible live runtime path tested.",
        "gemini": "Gemini-compatible live runtime path tested.",
        "codex": "Codex-compatible live runtime path tested.",
        "local": "At least one local/open-model live runtime path tested.",
    }
    for profile, label in expected.items():
        checked = "x" if has_verified_live_pass(register, profile) else " "
        line = f"- [{checked}] {label}"
        if line not in text:
            raise EvidenceError(
                f"PROJECT_CHECKLIST.md live-runtime checkbox for {profile} does not match the evidence register; expected {line!r}"
            )


def check_documents(register: dict[str, Any], paths: list[Path]) -> None:
    expected_block = render_status_markdown(register)
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise EvidenceError(f"could not read documentation file {path}: {exc}") from exc
        actual = extract_status_block(text, path)
        if actual != expected_block:
            raise EvidenceError(f"runtime evidence status block is stale in {path}")
        if path.name == "PROJECT_CHECKLIST.md":
            verify_checklist_live_boxes(text, register)


def build_live_rehearsal_entry(
    *,
    entry_id: str,
    runtime_profile: str,
    rehearsal_id: str,
    framework_commit: str | None,
    verified_at: str,
    source: str,
    model: str | None = None,
    harness: str | None = None,
    harness_version: str | None = None,
    os_platform: str | None = None,
    permission_mode: str | None = None,
    human_intervention: bool | None = None,
    context_tokens: int | None = None,
    quantization: str | None = None,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    entry = {
        "entry_id": entry_id,
        "evidence_type": "live_runtime_rehearsal",
        "runtime_profile": runtime_profile,
        "model": model,
        "harness": harness,
        "harness_version": harness_version,
        "os_platform": os_platform,
        "framework_commit": framework_commit,
        "rehearsal_id": rehearsal_id,
        "permission_mode": permission_mode,
        "result": "pass",
        "human_intervention": human_intervention,
        "context_tokens": context_tokens,
        "quantization": quantization,
        "verified_at": verified_at,
        "independently_verified": True,
        "claim_scope": "single_run_smoke_test",
        "source": source,
        "limitations": list(limitations or []),
    }
    return validate_entry(entry)


def build_switch_recovery_entry(
    *,
    switch_id: str,
    framework_commit: str,
    source_execution: dict[str, Any],
    target_execution: dict[str, Any],
    source_operation_id: str,
    source_revision: int,
    recovered_revision: int,
    source_checkpoint_id: str,
    recovered_checkpoint_id: str,
    state_digest: str,
    fresh_target_session: bool,
    verified_at: str,
    source: str,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    entry = {
        "entry_id": f"switch-{switch_id}",
        "evidence_type": "runtime_switch_recovery",
        "switch_id": switch_id,
        "framework_commit": framework_commit,
        "from_runtime_profile": source_execution["runtime_profile"],
        "from_model": source_execution.get("model"),
        "from_harness": source_execution.get("harness"),
        "from_harness_version": source_execution.get("harness_version"),
        "from_context_tokens": source_execution.get("context_tokens"),
        "from_quantization": source_execution.get("quantization"),
        "from_os_platform": source_execution["os_platform"],
        "from_permission_mode": source_execution["permission_mode"],
        "from_human_intervention": source_execution.get("human_intervention"),
        "from_runtime_command_sha256": source_execution["runtime_command_sha256"],
        "to_runtime_profile": target_execution["runtime_profile"],
        "to_model": target_execution.get("model"),
        "to_harness": target_execution.get("harness"),
        "to_harness_version": target_execution.get("harness_version"),
        "to_context_tokens": target_execution.get("context_tokens"),
        "to_quantization": target_execution.get("quantization"),
        "to_os_platform": target_execution["os_platform"],
        "to_permission_mode": target_execution["permission_mode"],
        "to_human_intervention": target_execution.get("human_intervention"),
        "to_runtime_command_sha256": target_execution["runtime_command_sha256"],
        "source_operation_id": source_operation_id,
        "source_revision": source_revision,
        "recovered_revision": recovered_revision,
        "source_checkpoint_id": source_checkpoint_id,
        "recovered_checkpoint_id": recovered_checkpoint_id,
        "state_digest": state_digest,
        "fresh_target_session": fresh_target_session,
        "result": "pass",
        "verified_at": verified_at,
        "independently_verified": True,
        "claim_scope": "single_switch_recovery",
        "source": source,
        "limitations": list(limitations or []),
    }
    return validate_entry(entry)


def main() -> int:
    args = parse_args()
    try:
        register = validate_register(read_json(Path(args.register)))
        if args.command == "validate":
            print("RUNTIME EVIDENCE REGISTER VERIFIED")
            print(f"Entries: {len(register['entries'])}")
            return 0
        if args.command == "render-status":
            print(render_status_markdown(register))
            return 0
        if args.command == "check-docs":
            check_documents(register, [Path(value) for value in args.document])
            print("RUNTIME EVIDENCE DOCUMENTATION VERIFIED")
            print(f"Documents: {len(args.document)}")
            return 0
        return 1
    except EvidenceError as exc:
        print(f"RUNTIME EVIDENCE FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
