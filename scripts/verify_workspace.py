#!/usr/bin/env python3
"""Verify the minimum structure of a user-owned Aham Brahmasmi workspace."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from schema_compat import SchemaCompatibilityError, compatibility_error, workspace_schema_version


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    "BRAIN.json",
    "README.md",
    "MEMORY.md",
    "TODO.md",
    "LESSONS.md",
    "state/installed_sources.json",
)
REQUIRED_DIRS = (
    "projects",
    "history",
    "external",
    "state/checkpoints",
    "state/wrapups",
    "state/quarantine",
    "state/scan_reports",
    "state/replaced_sources",
)
WORKSPACE_ID = re.compile(r"^[0-9a-f]{32}$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a private Aham Brahmasmi workspace.")
    parser.add_argument("--workspace", required=True, help="Path to the private workspace")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workspace = Path(args.workspace).expanduser().resolve()
    errors: list[str] = []

    if workspace == ROOT or ROOT in workspace.parents:
        errors.append("workspace is inside the public framework repository")

    if not workspace.is_dir():
        errors.append("workspace directory does not exist")
    else:
        for relative in REQUIRED_FILES:
            if not (workspace / relative).is_file():
                errors.append(f"missing required file: {relative}")
        for relative in REQUIRED_DIRS:
            if not (workspace / relative).is_dir():
                errors.append(f"missing required directory: {relative}")

        brain_path = workspace / "BRAIN.json"
        if brain_path.is_file():
            try:
                brain = json.loads(brain_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                errors.append(f"BRAIN.json could not be read as valid JSON: {exc}")
            else:
                if brain.get("format") != "aham-brahmasmi-workspace":
                    errors.append("BRAIN.json has an unrecognized workspace format")
                if brain.get("version") != 1:
                    errors.append("BRAIN.json has an unsupported workspace identity envelope version")
                if brain.get("workspace_owner") != "user":
                    errors.append("BRAIN.json does not identify the workspace as user-owned")
                workspace_id = brain.get("workspace_id")
                if not isinstance(workspace_id, str) or not WORKSPACE_ID.fullmatch(workspace_id):
                    errors.append("BRAIN.json has no valid unique workspace_id")

        try:
            schema_version = workspace_schema_version(workspace)
        except SchemaCompatibilityError as exc:
            errors.append(str(exc))
        else:
            schema_error = compatibility_error(schema_version)
            if schema_error:
                errors.append(schema_error)

        manifest_path = workspace / "state" / "installed_sources.json"
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                errors.append(f"installed_sources.json could not be read as valid JSON: {exc}")
            else:
                if manifest.get("format") != "aham-brahmasmi-installed-sources":
                    errors.append("installed_sources.json has an unrecognized format")
                if manifest.get("version") != 1 or not isinstance(manifest.get("sources"), dict):
                    errors.append("installed_sources.json has an unsupported structure")

    if errors:
        print("WORKSPACE VERIFICATION FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("WORKSPACE VERIFIED")
    print(f"Workspace: {workspace}")
    print("- required files present")
    print("- required directories present")
    print("- workspace is separate from the public framework")
    print("- BRAIN.json format and workspace identity recognized")
    print("- workspace schema version is current")
    print("- external source state is initialized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
