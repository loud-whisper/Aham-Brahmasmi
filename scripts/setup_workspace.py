#!/usr/bin/env python3
"""Create a new user-owned Aham Brahmasmi workspace from the public template."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import uuid
from pathlib import Path

from session_authority import issue_bootstrap_session, load_session
from runtime_trust import change_trust, runtime_name
from state_io import StateError, is_link_or_reparse, windows_component_invalid
from windows_access import create_private_directory, permission_issue as windows_permission_issue


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "private-workspace"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a new private Aham Brahmasmi workspace outside the public framework repository."
    )
    parser.add_argument("--workspace", required=True, help="Destination folder for the private workspace")
    parser.add_argument("--trust-runtime", action="append", default=[],
                        help="Explicit owner choice to trust a runtime name (repeatable)")
    return parser.parse_args()


def is_inside_repo(path: Path) -> bool:
    return path == ROOT or ROOT in path.parents


def copy_private_template(workspace: Path) -> None:
    """Keep the containing boundary private before writing any workspace files."""
    if os.name != "posix":
        shutil.copytree(TEMPLATE, workspace, dirs_exist_ok=True)
        return
    workspace.chmod(0o700)
    for source in sorted(TEMPLATE.rglob("*"), key=lambda path: len(path.parts)):
        if source.is_symlink():
            raise StateError("workspace template contains an unsupported symlink")
        target = workspace / source.relative_to(TEMPLATE)
        if source.is_dir():
            target.mkdir(mode=0o700)
        else:
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as output, source.open("rb") as input_file:
                shutil.copyfileobj(input_file, output)


def seal_setup_permissions(workspace: Path) -> None:
    if os.name == "posix":
        for path in [workspace, *workspace.rglob("*")]:
            if path.is_symlink():
                raise StateError("setup created an unexpected symlink")
            path.chmod(0o700 if path.is_dir() else 0o600)


def setup_main() -> int:
    args = parse_args()
    try:
        names = list(dict.fromkeys(runtime_name(value) for value in args.trust_runtime))
    except StateError as exc:
        print(f"SETUP FAILED: {exc}", file=sys.stderr)
        return 2
    selected = Path(args.workspace).expanduser()
    if os.name == "nt" and any(windows_component_invalid(part) for part in
                               (selected.parts[1:] if selected.anchor else selected.parts)):
        raise StateError("choose a Windows-valid destination without reserved names, streams or trailing dots/spaces")
    if is_link_or_reparse(selected):
        print("SETUP FAILED: choose the actual destination directory, not a symlink", file=sys.stderr)
        return 2
    workspace = selected.resolve()

    if not TEMPLATE.is_dir():
        print("SETUP FAILED: workspace template is missing", file=sys.stderr)
        return 1

    if is_inside_repo(workspace):
        print("SETUP FAILED: the private workspace must be outside the public framework repository", file=sys.stderr)
        return 2

    if workspace.exists():
        if not workspace.is_dir():
            print("SETUP FAILED: destination exists and is not a directory", file=sys.stderr)
            return 3
        if any(workspace.iterdir()):
            print("SETUP FAILED: destination directory is not empty; nothing was overwritten", file=sys.stderr)
            return 4
        if os.name == "nt":
            issue = windows_permission_issue(workspace)
            if issue:
                raise StateError(issue + " Choose a new, absent destination for private setup.")
    else:
        workspace.parent.mkdir(parents=True, exist_ok=True)
        create_private_directory(workspace)

    brain_path = workspace / "BRAIN.json"
    try:
        copy_private_template(workspace)
        brain = json.loads(brain_path.read_text(encoding="utf-8"))
        brain["workspace_id"] = uuid.uuid4().hex
        brain_path.write_text(json.dumps(brain, indent=2) + "\n", encoding="utf-8")
        bootstrap = issue_bootstrap_session(workspace)
        for name in names:
            change_trust(workspace, name, trusted=True, human_confirmation=name, owner_control=True)
        controller = load_session(workspace)
        seal_setup_permissions(workspace)
    except (StateError, OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"SETUP FAILED: could not initialize workspace identity/controller authority: {exc}", file=sys.stderr)
        return 5

    print("WORKSPACE CREATED")
    print(f"Workspace: {workspace}")
    print(f"Controller session: {controller['session_id']} (local owner controller; runtime trust is separate)")
    print("Next: run aham.py check --workspace WORKSPACE before using it.")
    return 0


def main() -> int:
    try:
        return setup_main()
    except (StateError, OSError, ValueError) as exc:
        print(f"SETUP FAILED: {exc}", file=sys.stderr)
        print("Next: inspect the chosen folder and use aham.py check. Keep the failing command and output; do not overwrite existing data.", file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
