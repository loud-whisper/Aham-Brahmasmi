#!/usr/bin/env python3
"""Explicit project-local installation/check of the optional command guard.

No core startup, native trust settings or user-home configuration is changed.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sqlite3
import subprocess
import sys
from pathlib import Path

from command_guard_policy import Limits
from command_guard_store import STATE, database, read_policy, state_path
from runtime_bridge import (
    ROOT, git_path_effectively_ignored, git_path_tracked, project_git_root,
    require_regular_or_missing, resolve_project,
)
from state_io import StateError, atomic_write_json, atomic_write_text, require_managed_path

TARGETS = {
    "claude": (".claude/settings.local.json", "PreToolUse", "^(Bash|PowerShell)$"),
    "codex": (".codex/hooks.json", "PreToolUse", "^Bash$"),
    "gemini": (".gemini/settings.json", "BeforeTool", "^run_shell_command$"),
}
MARKER = "aham-brahmasmi-command-guard"


def hook_group(project, runtime):
    relative, event, matcher = TARGETS[runtime]
    command = shlex.join([sys.executable, str(ROOT / "scripts" / "command_guard.py"), "hook",
                          "--runtime", runtime, "--project", str(project)]) + " || exit 2"
    handler = {"type": "command", "command": command, "timeout": 10000 if runtime == "gemini" else 10}
    if runtime == "claude":
        handler["onFailure"] = "block"
    return relative, event, {"matcher": matcher, "hooks": [handler]}


def load_settings(path):
    require_regular_or_missing(path, "native hook settings")
    value = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(value, dict) or not isinstance(value.get("hooks", {}), dict):
        raise ValueError("native settings must have an object-shaped hooks field")
    if not isinstance(value.get("hooksConfig", {}), dict):
        raise ValueError("hooksConfig must be an object")
    return value


def managed(group):
    if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
        raise ValueError("malformed native hook matcher group")
    return any(isinstance(handler, dict) and "command_guard.py" in str(handler.get("command", ""))
               for handler in group["hooks"])


def private_paths(project, runtime):
    paths = [f"{STATE}/config.json", f"{STATE}/audit.sqlite3", f"{STATE}/audit.sqlite3-journal"]
    if runtime in TARGETS:
        paths.append(TARGETS[runtime][0])
    for relative in paths:
        path = require_managed_path(project, relative, label="private command guard path")
        require_regular_or_missing(path, "private command guard path")
        if path.exists() and path.stat().st_nlink != 1:
            raise ValueError("private command guard path has a hard-link alias")
        if git_path_tracked(project, relative):
            raise ValueError("private guard configuration is tracked by Git; remove it from the index before installation")
    # Refuse arbitrary tracked files already inside the private state tree too.
    if project_git_root(project) is not None:
        result = subprocess.run(["git", "-C", str(project), "ls-files", "--", STATE],
                                text=True, capture_output=True, timeout=10, check=True)
        if result.stdout.strip():
            raise ValueError("private guard state directory contains Git-tracked data")
    return paths


def add_ignore(project, directory, filename):
    ignore = require_managed_path(project, directory / ".gitignore", label="guard ignore file")
    require_regular_or_missing(ignore, "guard ignore file")
    if ignore.exists() and ignore.stat().st_nlink != 1:
        raise ValueError("guard ignore file has a hard-link alias")
    text = ignore.read_text(encoding="utf-8") if ignore.exists() else ""
    line = "/" + filename
    if line not in text.splitlines():
        atomic_write_text(ignore, text + ("\n" if text and not text.endswith("\n") else "")
                          + f"# {MARKER}: private local installation\n{line}\n")


def check_install(project, runtime):
    issues = []
    try:
        paths = private_paths(project, runtime)
        read_policy(project)
        db_path = state_path(project, "audit.sqlite3")
        if not db_path.is_file():
            issues.append("audit database is missing")
        else:
            # URI mode=ro prevents --check from creating or updating any state.
            connection = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)
            try:
                if connection.execute("PRAGMA quick_check").fetchone() != ("ok",):
                    issues.append("audit database integrity check failed")
                for name in ("approvals", "audit"):
                    connection.execute(f"SELECT * FROM {name} LIMIT 0")
            finally:
                connection.close()
        if runtime in TARGETS:
            relative, event, expected = hook_group(project, runtime)
            value = load_settings(project / relative)
            groups = value.get("hooks", {}).get(event, [])
            if not isinstance(groups, list) or [group for group in groups if managed(group)] != [expected]:
                issues.append("exact native hook configuration is missing or changed")
            if value.get("disableAllHooks") is True:
                issues.append("native settings disable all hooks")
            if runtime == "gemini" and value.get("hooksConfig", {}).get("enabled") is False:
                issues.append("Gemini settings disable hooks")
        if project_git_root(project) is not None:
            for relative in paths:
                if not git_path_effectively_ignored(project, relative):
                    issues.append("private path is not effectively ignored: " + relative)
    except (OSError, ValueError, RuntimeError, sqlite3.Error, subprocess.SubprocessError, StateError) as exc:
        issues.append(str(exc))
    return {"configured": not issues, "runtime": runtime, "issues": issues,
            "runtime_trust_checked": False,
            "next_action": "Review/trust native hooks and test an actual blocked call in your runtime; configuration checks do not prove hook activation."}


def install(project, runtime, *, max_bytes=None, max_files=None, check=False):
    project = resolve_project(project)
    if runtime not in {*TARGETS, "wrapper"}:
        raise ValueError("unverified native hook format; use the wrapper")
    if os.name != "posix":
        raise ValueError("native installation is currently supported only on POSIX; no Windows execution claim")
    if check:
        return check_install(project, runtime)
    private_paths(project, runtime)
    try:
        prior = read_policy(project)
    except FileNotFoundError:
        prior = Limits()
    limits = Limits(prior.max_bytes if max_bytes is None else max_bytes,
                    prior.max_files if max_files is None else max_files)
    settings = None
    if runtime in TARGETS:
        relative, event, group = hook_group(project, runtime)
        settings_path = require_managed_path(project, relative, label="native hook settings")
        settings = load_settings(settings_path)
        groups = settings.get("hooks", {}).get(event, [])
        if not isinstance(groups, list):
            raise ValueError("native hook event must be an array")
        existing = [item for item in groups if managed(item)]
        if existing and existing != [group]:
            raise ValueError("existing guard hook differs; review and repair it explicitly before installing")
        if not existing:
            settings.setdefault("hooks", {}).setdefault(event, []).append(group)
    # Preflight ignore-file shape before the first write.
    dirs = [project / ".aham"] + ([settings_path.parent] if settings is not None else [])
    for directory in dirs:
        ignore = require_managed_path(project, directory / ".gitignore", label="guard ignore file")
        require_regular_or_missing(ignore, "guard ignore file")
        if ignore.exists() and ignore.stat().st_nlink != 1:
            raise ValueError("guard ignore file has a hard-link alias")
    state_dir = require_managed_path(project, STATE, label="guard state directory")
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(state_dir, 0o700)
    add_ignore(project, project / ".aham", "command-guard/")
    if settings is not None:
        settings_path.parent.mkdir(mode=0o700, exist_ok=True)
        add_ignore(project, settings_path.parent, settings_path.name)
    # Verify effective ignore rules before writing local paths or approval data.
    if project_git_root(project) is not None:
        for relative in private_paths(project, runtime):
            if not git_path_effectively_ignored(project, relative):
                raise ValueError("Git ignore engine does not exclude private guard data: " + relative)
    atomic_write_json(state_path(project, "config.json"), {"version": 1, "max_bytes": limits.max_bytes, "max_files": limits.max_files})
    os.chmod(state_path(project, "config.json"), 0o600)
    with database(project, create=True):
        pass
    if settings is not None:
        atomic_write_json(settings_path, settings)
        os.chmod(settings_path, 0o600)
    return check_install(project, runtime)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--runtime", choices=(*TARGETS, "wrapper"), required=True)
    parser.add_argument("--max-bytes", type=int)
    parser.add_argument("--max-files", type=int)
    parser.add_argument("--check", action="store_true", help="Read-only configuration check; does not establish native trust")
    args = parser.parse_args()
    try:
        result = install(args.project, args.runtime, max_bytes=args.max_bytes, max_files=args.max_files, check=args.check)
        print(json.dumps(result, indent=2))
        return 0 if result["configured"] else 1
    except (ValueError, OSError, RuntimeError, sqlite3.Error, subprocess.SubprocessError, StateError) as exc:
        print(f"Command guard installation refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
