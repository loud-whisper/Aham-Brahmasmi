#!/usr/bin/env python3
"""Explain the current Aham Brahmasmi state in plain language."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from state_io import StateError, newest_valid_checkpoint, read_json, require_managed_path, resolve_workspace, workspace_errors
from onboarding import default_workspace, permission_issue, preflight, sync_root_warning
from recovery_commands import recovery_command
from session_authority import load_session
from state_store import list_operation_records, validate_store


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FRAMEWORK = (
    "START_HERE.md",
    "core/brain.json",
    "core/startup.json",
    "core/lifecycle.json",
    "scripts/startup.py",
    "scripts/checkpoint.py",
    "scripts/resume.py",
    "scripts/wrap_up.py",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check Aham Brahmasmi setup and explain what needs attention.")
    parser.add_argument("--workspace", help="Private Brain workspace to check")
    parser.add_argument("--project", help="Project folder whose runtime bridge should be checked")
    parser.add_argument("--json", action="store_true", help="Print a machine-readable report")
    return parser.parse_args()


def item(level: str, name: str, status: str, detail: str, action: str | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {
        "level": level,
        "name": name,
        "status": status,
        "detail": detail,
    }
    if action:
        value["action"] = action
    return value


def check_framework() -> dict[str, Any]:
    missing = [relative for relative in REQUIRED_FRAMEWORK if not (ROOT / relative).is_file()]
    if missing:
        return item(
            "required",
            "Public framework",
            "action_needed",
            "Some required framework files are missing: " + ", ".join(missing),
            "Use a complete Aham Brahmasmi checkout before continuing.",
        )
    return item("required", "Public framework", "ok", "Required framework files are present.")


def read_optional_semantic(brain: dict[str, Any]) -> tuple[bool, str | None]:
    optional = brain.get("optional_integrations")
    if not isinstance(optional, dict):
        return False, None
    value = optional.get("semantic_memory")
    if not isinstance(value, dict):
        return False, None
    provider = value.get("provider")
    return True, provider if isinstance(provider, str) else None


def check_workspace(path_value: str) -> tuple[list[dict[str, Any]], bool]:
    workspace = resolve_workspace(path_value)
    findings: list[dict[str, Any]] = []
    errors = workspace_errors(workspace)
    if errors:
        findings.append(
            item(
                "required",
                "Private Brain workspace",
                "action_needed",
                "; ".join(errors),
                "Run scripts/verify_workspace.py with the intended private workspace, or create a new one from START_HERE.md.",
            )
        )
        return findings, False

    findings.append(item("required", "Private Brain workspace", "ok", f"Workspace verified: {workspace}"))
    brain = read_json(workspace / "BRAIN.json")
    issue = permission_issue(workspace)
    if sys.platform not in {"linux", "darwin"} and os.name != "nt":
        findings.append(item("optional", "Workspace permissions", "not_checked",
                             "Owner-only directory access has not been verified on this platform.",
                             "Have the workspace owner verify this folder's access permissions. Native access validation is unavailable on this platform; see docs/PLATFORM_SUPPORT.md."))
    elif issue:
        findings.append(item("required", "Workspace permissions", "action_needed", issue,
                             "Ask the owner to repair this selected folder's Windows access permissions and run aham.py check again. Do not change unrelated parent folders." if os.name == "nt" else
                             "Set this workspace directory to owner-only mode 0700 (chmod 700 on POSIX), then run aham.py check again. Do not change unrelated parent folders."))
    else:
        findings.append(item("required", "Workspace permissions", "ok", "Private workspace directory access check passed."))
    warning = sync_root_warning(workspace)
    if warning:
        findings.append(item("optional", "Workspace location", "check_recommended", warning,
                             "Ask the owner to choose a local folder, such as the suggested location from aham.py check without --workspace. See docs/BEFORE_YOU_START.md."))
    try:
        store = require_managed_path(workspace, "state/store.json", label="state store")
        cached = validate_store(read_json(store)) if store.exists() else None
        records = list_operation_records(workspace)
        revision = records[-1][1]["revision"] if records else 0
        if cached is not None and cached["revision"] > revision:
            raise StateError("state store revision is ahead of the immutable operation ledger")
        if cached is not None and cached["revision"] == revision and records:
            path, record = records[-1]
            if cached["last_operation_id"] != record["operation_id"] or cached["last_record"] != "state/operations/" + path.name:
                raise StateError("state store head conflicts with the immutable operation ledger")
        from runtime_trust import trusted_runtimes
        trusted_runtimes(workspace)
        if revision and (cached is None or cached["revision"] < revision):
            findings.append(item("recovery", "Committed head", "action_needed", "A committed operation is newer than the cached head.",
                                 "Recover any pending operation first. Otherwise run aham.py start to reconcile the committed head before new work; do not edit state/store.json."))
    except (StateError, OSError, ValueError) as exc:
        findings.append(item("required", "Committed state", "action_needed", str(exc),
                             "Preserve this workspace and restore a verified backup into a separate empty folder with aham.py restore. Do not edit operation records to make checks pass."))
        return findings, False

    from third_party import installed_source_status
    from skills_lifecycle import summary as skill_summary
    skills = skill_summary(workspace)
    findings.append(item("optional", "Skills", "action_needed" if skills["status"] != "available" else "ok",
                         f"Skills: {skills['active']} active, {skills['reviewed_updates']} reviewed update available ({skills['status']})"))
    external = installed_source_status(workspace)
    if external["status"] == "unreadable":
        findings.append(item("optional", "Reviewed external sources", "action_needed",
                             "External source review manifest is unreadable; no source is counted usable.",
                             "Restore a valid manifest or review fresh source candidates."))
    for source_id, reason in external["excluded"].items():
        findings.append(item("optional", "Reviewed external source: " + source_id, "action_needed", reason,
                             "Use external_sources.py install <source-id> --workspace <workspace> --replace to review a fresh candidate."))

    for relative, label, verb in (("state/pending_wrap_up.json", "Interrupted wrap up", "wrap-up"),
                                  ("state/pending_checkpoint.json", "Interrupted checkpoint", "save")):
        pending = require_managed_path(workspace, relative, label="pending writer operation")
        if pending.exists():
            try:
                session = load_session(workspace)
                can_recover = ("recover_wrap_up" if verb == "wrap-up" else "recover_checkpoint") in session["allowed_operations"]
                can_recover = can_recover and session["current_revision"] == revision
                if session["source"] not in {"workspace_setup", "workspace_owner"}:
                    from runtime_trust import runtime_name, trusted_runtimes
                    can_recover = can_recover and runtime_name(session["requested_runtime"]) in trusted_runtimes(workspace)
            except (StateError, OSError, ValueError):
                can_recover = False
            action = "Use the current writer session to recover before unrelated work: " + recovery_command(verb)
            if not can_recover:
                action = ("Ask the workspace owner to run aham.py recover-access --workspace WORKSPACE --confirm WORKSPACE_ID "
                          "using the workspace_id from BRAIN.json. It permits recovery only. Then run: " + recovery_command(verb))
            findings.append(item("recovery", label, "action_needed", "A replay-safe operation is still pending.", action))
        else:
            findings.append(item("recovery", label, "ok", "No unfinished operation was found."))

    latest = newest_valid_checkpoint(workspace)
    if latest is None:
        findings.append(item("recovery", "Latest checkpoint", "not_configured", "No durable checkpoint exists yet."))
    else:
        _, checkpoint = latest
        findings.append(
            item(
                "recovery",
                "Latest checkpoint",
                "ok",
                f"{checkpoint.get('id')}: {checkpoint.get('summary')}",
            )
        )

    semantic_configured, provider = read_optional_semantic(brain)
    if not semantic_configured:
        findings.append(
            item(
                "optional",
                "Semantic memory",
                "not_configured",
                "No semantic-memory provider is configured. The Brain still works from its durable files.",
            )
        )
    elif provider == "mempalace":
        if shutil.which("mempalace"):
            findings.append(
                item(
                    "optional",
                    "Semantic memory",
                    "check_recommended",
                    "MemPalace is configured and its command is available.",
                    "Run scripts/semantic_memory.py status --workspace <workspace> before relying on recall.",
                )
            )
        else:
            findings.append(
                item(
                    "optional",
                    "Semantic memory",
                    "unavailable",
                    "MemPalace is configured but its command is not currently available. Core Brain operation is unaffected.",
                    "Use offline lite recall, or run scripts/semantic_memory.py setup --workspace <workspace> for upstream install choices.",
                )
            )
    elif provider == "lite":
        findings.append(item("optional", "Semantic memory", "ok",
                             "Offline keyword recall uses committed records without an external provider."))
    else:
        findings.append(
            item(
                "optional",
                "Semantic memory",
                "unavailable",
                f"A semantic-memory provider is configured but is not recognized here: {provider!r}.",
            )
        )

    git_dir = workspace / ".git"
    if git_dir.exists():
        findings.append(item("optional", "Local Git history", "ok", "The private workspace has local Git version history."))
    elif shutil.which("git"):
        findings.append(
            item(
                "optional",
                "Local Git history",
                "not_configured",
                "Git is available but optional Brain history has not been initialized.",
            )
        )
    else:
        findings.append(
            item(
                "optional",
                "Local Git history",
                "unavailable",
                "Git is not available. The local Brain files remain the required durable state.",
            )
        )

    return findings, issue is None


def check_project(path_value: str) -> dict[str, Any]:
    from runtime_bridge import load_status, resolve_project
    try:
        project = resolve_project(path_value)
        status = load_status(project)
    except (StateError, OSError, ValueError) as exc:
        return item("required", "Project bridge", "action_needed", str(exc),
                    "Choose the intended project and use aham.py connect to reinstall its managed bridge. Preserve unrelated instructions.")
    if not status["installed"]:
        return item("required", "Project bridge", "action_needed",
                    "The selected project's bridge is absent or its private configuration is not safely ignored by Git.",
                    "Use aham.py connect for this project. If runtime.json is tracked, remove it from the Git index while keeping your local file, then commit that change before reinstalling.")
    config = status["configuration"]
    return item("required", "Project bridge", "ok", "Project bridge is installed for runtime profile: " + config["runtime"])


def build_report(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    findings: list[dict[str, Any]] = [check_framework()]
    required_ok = findings[0]["status"] == "ok"
    platform = preflight()
    findings.append(item("required", "Platform and Python", "ok" if platform["supported"] else "action_needed",
                         f"Platform: {sys.platform}; Python: {sys.version_info.major}.{sys.version_info.minor}", platform["action"]))
    required_ok = required_ok and platform["supported"]
    recovery_blocked = False

    if args.workspace:
        workspace_findings, workspace_ok = check_workspace(args.workspace)
        findings.extend(workspace_findings)
        required_ok = required_ok and workspace_ok
        recovery_blocked = any(
            finding["level"] == "recovery" and finding["status"] == "action_needed"
            for finding in workspace_findings
        )
    else:
        required_ok = False
        findings.append(
            item(
                "required",
                "Private Brain workspace",
                "not_checked",
                "No workspace was supplied, so private state was not checked.",
                f"Choose a private local folder, then pass --workspace <path>. Suggested location (owner approval required): {default_workspace()}",
            )
        )

    if args.project:
        project_finding = check_project(args.project)
        findings.append(project_finding)
        required_ok = required_ok and project_finding["status"] == "ok"

    if not required_ok:
        ready = False
        exit_code = 1
    elif recovery_blocked:
        ready = False
        exit_code = 2
    else:
        ready = True
        exit_code = 0

    return {
        "format": "aham-brahmasmi-doctor-report",
        "version": 1,
        "ready_for_new_work": ready,
        "readiness_scope": "Selected durable workspace checks; runtime write authority is issued separately by aham.py start.",
        "findings": findings,
    }, exit_code


def print_human(report: dict[str, Any]) -> None:
    print("AHAM BRAHMASMI CHECK")
    print("Ready for new work: " + ("yes" if report["ready_for_new_work"] else "no"))
    print()
    for finding in report["findings"]:
        status = str(finding["status"]).replace("_", " ").upper()
        print(f"[{status}] {finding['name']}")
        print(f"  {finding['detail']}")
        if finding.get("action"):
            print(f"  Next: {finding['action']}")


def main() -> int:
    args = parse_args()
    try:
        report, exit_code = build_report(args)
    except (StateError, OSError, ValueError) as exc:
        report = {"format": "aham-brahmasmi-doctor-report", "version": 1, "ready_for_new_work": False,
                  "findings": [item("required", "Workspace inspection", "action_needed", str(exc),
                                    "Preserve the failing command and output. Select the intended workspace and use docs/TROUBLESHOOTING.md; do not repair framework code during setup.")]}
        exit_code = 1
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_human(report)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
