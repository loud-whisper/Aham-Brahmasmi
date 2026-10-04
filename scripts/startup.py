#!/usr/bin/env python3
"""Produce a verified model-neutral startup report for a private Brain workspace."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from project_state import project_by_id
from session_authority import issue_session
from state_io import StateError, newest_valid_checkpoint, read_json, require_workspace, resolve_workspace
from state_store import writer_lock
from third_party import installed_source_status
from skills_lifecycle import summary as skill_summary
from semantic_memory import scope_payload
import owner_phrases
import runtime_trust


ROOT = Path(__file__).resolve().parents[1]
STARTUP_CONTRACT = ROOT / "core" / "startup.json"
RUNTIME_PROFILES = ROOT / "runtime_profiles"
PROFILE_REQUIRED_FIELDS = {
    "version",
    "id",
    "display_name",
    "kind",
    "capabilities_must_be_verified",
    "requires_native_skill_loader",
    "requires_semantic_memory",
    "notes",
}


class StartupError(StateError):
    """Raised when startup state cannot be reported safely."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a Brain workspace and report startup state.")
    parser.add_argument("--workspace", required=True, help="Path to the private workspace")
    parser.add_argument(
        "--runtime",
        default="unknown",
        help="Runtime profile to use: claude, gemini, codex, local, unknown, or another name for safe fallback",
    )
    parser.add_argument(
        "--mode",
        default="regular",
        choices=("quick", "regular", "degraded_offline", "wrap_up"),
        help="Startup mode defined by the core contract",
    )
    parser.add_argument(
        "--capability",
        action="append",
        default=[],
        help="Capability this runtime has actually verified; repeat as needed",
    )
    parser.add_argument(
        "--project-id",
        help="Optional stable project ID to bind into the controller session; it must already exist in the Brain registry",
    )
    parser.add_argument(
        "--harness",
        help="Optional explicit harness/controller identity, for example live-runtime-rehearsal:<id>",
    )
    parser.add_argument(
        "--context-loaded",
        action="store_true",
        help="Confirm that Quick mode already has verified current context loaded",
    )
    parser.add_argument("--json", action="store_true", help="Emit the ready report as JSON")
    return parser.parse_args()


def allowed_capabilities() -> set[str]:
    contract = read_json(STARTUP_CONTRACT)
    for phase in contract.get("phases", []):
        if phase.get("id") == "detect_capabilities":
            values = phase.get("capabilities")
            if isinstance(values, list) and all(isinstance(item, str) for item in values):
                return set(values)
    raise StartupError("startup contract does not define capability detection")


def validate_profile(profile: dict[str, Any], path: Path) -> None:
    missing = PROFILE_REQUIRED_FIELDS - set(profile)
    if missing:
        raise StartupError(f"runtime profile {path.name} is missing fields: {', '.join(sorted(missing))}")
    if profile.get("version") != 1:
        raise StartupError(f"runtime profile {path.name} has an unsupported version")
    if not isinstance(profile.get("id"), str) or not profile["id"].strip():
        raise StartupError(f"runtime profile {path.name} has an invalid id")
    if profile.get("kind") not in {"named", "local_open", "unknown"}:
        raise StartupError(f"runtime profile {path.name} has an unsupported kind")
    for field in (
        "capabilities_must_be_verified",
        "requires_native_skill_loader",
        "requires_semantic_memory",
    ):
        if not isinstance(profile.get(field), bool):
            raise StartupError(f"runtime profile {path.name} field '{field}' must be boolean")
    if not isinstance(profile.get("display_name"), str) or not profile["display_name"].strip():
        raise StartupError(f"runtime profile {path.name} display_name must be non-empty")
    if not isinstance(profile.get("notes"), str):
        raise StartupError(f"runtime profile {path.name} notes must be a string")


def load_runtime_profile(requested: str) -> tuple[dict[str, Any], Path, bool]:
    normalized = requested.strip().lower()
    known = normalized if normalized in {"claude", "gemini", "codex", "local", "unknown"} else "unknown"
    path = RUNTIME_PROFILES / f"{known}.json"
    profile = read_json(path)
    validate_profile(profile, path)
    return profile, path, known == normalized


def semantic_memory_status(brain: dict[str, Any], capabilities: set[str]) -> str:
    optional = brain.get("optional_integrations")
    configured = optional.get("semantic_memory") if isinstance(optional, dict) else None
    if configured is None:
        return "not_configured"
    if isinstance(configured, dict) and configured.get("provider") == "lite":
        return "offline_available"
    if "semantic_memory" in capabilities:
        return "reported_available"
    return "configured_not_verified"


def latest_checkpoint_summary(workspace: Path) -> dict[str, Any] | None:
    latest = newest_valid_checkpoint(workspace)
    if latest is None:
        return None
    path, checkpoint = latest
    return {
        "id": checkpoint.get("id"),
        "created_at": checkpoint.get("created_at"),
        "summary": checkpoint.get("summary"),
        "project": checkpoint.get("project"),
        "file": str(path.relative_to(workspace)),
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    workspace = resolve_workspace(args.workspace)
    brain = require_workspace(workspace)
    normalized_runtime = runtime_trust.runtime_name(args.runtime)
    profile, profile_path, exact_profile = load_runtime_profile(args.runtime)

    allowed = allowed_capabilities()
    capabilities = set(args.capability)
    unknown_caps = sorted(capabilities - allowed)
    if unknown_caps:
        raise StartupError(f"unrecognized capability name(s): {', '.join(unknown_caps)}")

    project_id = args.project_id
    if project_id is not None:
        project_by_id(workspace, project_id)

    harness = args.harness.strip() if isinstance(args.harness, str) and args.harness.strip() else None

    blockers: list[str] = []
    if args.mode == "quick" and not args.context_loaded:
        blockers.append("Quick mode requires already-loaded verified context; use Regular mode or confirm --context-loaded.")

    pending_path = workspace / "state" / "pending_wrap_up.json"
    pending_wrap_up = pending_path.exists()

    if args.mode == "degraded_offline":
        state_freshness = "stale_by_mode"
        core_allows_writes = False
    elif args.mode == "quick":
        state_freshness = "verified_loaded_context" if args.context_loaded else "unverified"
        core_allows_writes = True
    else:
        state_freshness = "verified_local"
        core_allows_writes = True

    runtime_reports_write_files = "write_files" in capabilities

    # Startup and mutation share the same writer lock. A runtime session is
    # therefore bound to an authoritative committed revision, not a racy cached read.
    with writer_lock(workspace) as head:
        pending_wrap_up = pending_path.exists()
        pending_checkpoint = (workspace / "state/pending_checkpoint.json").exists()
        if args.mode != "wrap_up":
            if pending_wrap_up:
                blockers.append("An unfinished wrap-up transaction exists and must be recovered before new task work.")
            if pending_checkpoint:
                blockers.append("An unfinished checkpoint exists; start in wrap_up mode and recover it before new work.")
        runtime_is_trusted = normalized_runtime in runtime_trust.trusted_runtimes(workspace)
        phrases = owner_phrases.owner_phrases(workspace)
        self_test = {"status": "not_run"}
        candidate = not blockers and core_allows_writes and runtime_reports_write_files and runtime_is_trusted
        if candidate:
            try:
                self_test = runtime_trust.probe_writer(workspace, head=head)
                if self_test.get("status") != "passed":
                    raise StateError("writer self-test did not pass")
            except (StateError, OSError, ValueError) as exc:
                self_test = {"status": "failed", "reason": str(exc)}
        effective_runtime_write_ready = candidate and self_test["status"] == "passed"
        allowed_operations = (["checkpoint", "recover_checkpoint", "wrap_up", "recover_wrap_up"]
                              if effective_runtime_write_ready else [])
        session = issue_session(
            workspace,
            source="startup_controller",
            requested_runtime=args.runtime,
            runtime=profile["id"],
            harness=harness,
            mode=args.mode,
            capabilities=capabilities,
            allowed_operations=allowed_operations,
            project_id=project_id,
            current_revision=head["revision"],
        )

    report = {
        "format": "aham-brahmasmi-ready-report",
        "version": 1,
        "ready": not blockers,
        "requested_runtime": args.runtime,
        "runtime": profile["id"],
        "harness": harness,
        "runtime_profile_exact_match": exact_profile,
        "runtime_profile": str(profile_path.relative_to(ROOT)),
        "mode": args.mode,
        "capabilities": sorted(capabilities),
        "capability_source": "explicit_runtime_report",
        "workspace_status": "verified",
        "state_freshness": state_freshness,
        "semantic_memory_status": semantic_memory_status(brain, capabilities),
        "semantic_memory_scope": scope_payload(workspace, brain, project_id),
        "latest_checkpoint": latest_checkpoint_summary(workspace),
        "pending_wrap_up": pending_wrap_up,
        "external_sources": installed_source_status(workspace),
        "skills": skill_summary(workspace),
        "native_skill_loader_required": profile["requires_native_skill_loader"],
        "semantic_memory_required": profile["requires_semantic_memory"],
        "write_policy": {
            "core_allows_writes": core_allows_writes,
            "runtime_reports_write_files": runtime_reports_write_files,
            "runtime_profile_trusted_for_writes": False,
            "runtime_trusted_for_writes": runtime_is_trusted,
            "effective_runtime_write_ready": effective_runtime_write_ready,
        },
        "writer_self_test": self_test,
        "owner_phrases": phrases,
        "session_authority": {
            "session_id": session["session_id"],
            "authority": session["authority"],
            "allowed_operations": session["allowed_operations"],
            "project_id": session["project_id"],
            "harness": session["harness"],
            "current_revision": session["current_revision"],
            "record": "state/session_authority.json",
        },
        "blockers": blockers,
    }
    return report


def print_human(report: dict[str, Any]) -> None:
    print("BRAIN READY" if report["ready"] else "BRAIN STARTUP BLOCKED")
    requested = report["requested_runtime"]
    runtime = report["runtime"]
    runtime_text = runtime if requested == runtime else f"{runtime} (safe fallback for requested '{requested}')"
    print(f"Runtime: {runtime_text}")
    if report.get("harness"):
        print(f"Harness: {report['harness']}")
    print(f"Mode: {report['mode']}")
    print(f"Workspace: {report['workspace_status']}")
    print(f"State freshness: {report['state_freshness']}")
    capabilities = ", ".join(report["capabilities"]) if report["capabilities"] else "none reported"
    print(f"Runtime capabilities: {capabilities}")
    print(f"Semantic memory: {report['semantic_memory_status']}")
    scope = report["semantic_memory_scope"]
    print("Semantic scope: " + json.dumps(scope, sort_keys=True, ensure_ascii=True))
    latest = report["latest_checkpoint"]
    print(f"Latest checkpoint: {latest['id']} - {latest['summary']}" if latest else "Latest checkpoint: none")
    print(f"Pending wrap-up: {'yes' if report['pending_wrap_up'] else 'no'}")
    external = report["external_sources"]
    skills = report["skills"]
    print(f"Skills: {skills['active']} active, {skills['reviewed_updates']} reviewed update available ({skills['status']})")
    print(f"External sources: {external['status']}" + (f" ({external['count']})" if external["count"] is not None else ""))
    for source_id, reason in external.get("excluded", {}).items():
        print("Excluded external source: " + json.dumps({"source_id": source_id, "reason": reason}, ensure_ascii=True))
    writes = report["write_policy"]["effective_runtime_write_ready"]
    print(f"Validated runtime writes: {'available' if writes else 'not established'}")
    authority = report["session_authority"]
    print(f"Session authority: {authority['authority']} ({authority['session_id']})")
    if authority["project_id"]:
        print(f"Bound project: {authority['project_id']}")
    for blocker in report["blockers"]:
        print(f"Blocker: {blocker}")


def main() -> int:
    args = parse_args()
    try:
        report = build_report(args)
    except (StateError, StartupError) as exc:
        print(f"STARTUP FAILED: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_human(report)
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
