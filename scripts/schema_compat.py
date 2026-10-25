#!/usr/bin/env python3
"""Workspace schema compatibility primitives.

The BRAIN.json version is the immutable workspace identity-envelope version. It is
not used as the mutable workspace-state schema version because it participates in
the workspace fingerprint recorded by durable history.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


IDENTITY_FORMAT = "aham-brahmasmi-workspace"
IDENTITY_VERSION = 1
SCHEMA_FORMAT = "aham-brahmasmi-workspace-schema"
CURRENT_SCHEMA_VERSION = 1
LEGACY_SCHEMA_VERSION = 0
SCHEMA_RELATIVE_PATH = Path("state/schema.json")
PENDING_MIGRATION_RELATIVE_PATH = Path("state/pending_migration.json")


class SchemaCompatibilityError(RuntimeError):
    """Raised when workspace schema compatibility cannot be established safely."""


def current_schema_manifest() -> dict[str, Any]:
    return {"format": SCHEMA_FORMAT, "version": CURRENT_SCHEMA_VERSION}


def validate_schema_manifest(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SchemaCompatibilityError("workspace schema manifest must be a JSON object")
    required = {"format", "version"}
    unknown = set(value) - required
    missing = required - set(value)
    if unknown:
        raise SchemaCompatibilityError(
            "workspace schema manifest contains unknown fields: " + ", ".join(sorted(unknown))
        )
    if missing:
        raise SchemaCompatibilityError(
            "workspace schema manifest is missing fields: " + ", ".join(sorted(missing))
        )
    if value.get("format") != SCHEMA_FORMAT:
        raise SchemaCompatibilityError("workspace schema manifest format is not recognized")
    version = value.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise SchemaCompatibilityError("workspace schema manifest version must be a positive integer")
    return value


def read_schema_manifest(workspace: Path) -> dict[str, Any] | None:
    path = workspace / SCHEMA_RELATIVE_PATH
    if path.is_symlink():
        raise SchemaCompatibilityError("workspace schema manifest must not be a symlink")
    if not path.exists():
        return None
    if not path.is_file():
        raise SchemaCompatibilityError("workspace schema manifest is not a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SchemaCompatibilityError(f"workspace schema manifest is not valid JSON: {exc}") from exc
    return validate_schema_manifest(value)


def workspace_schema_version(workspace: Path, *, allow_pending_migration: bool = False) -> int:
    """Return schema version; pre-R1 workspaces without a manifest are schema 0.

    Normal lifecycle callers must not interpret a workspace while a schema
    migration is unresolved. The migration runner explicitly opts in while it
    validates/replays its own pending transaction.
    """
    pending = workspace / PENDING_MIGRATION_RELATIVE_PATH
    if not allow_pending_migration and (pending.exists() or pending.is_symlink()):
        raise SchemaCompatibilityError(
            "workspace has a pending migration that must be recovered before normal lifecycle work; "
            "run scripts/migrate_workspace.py --workspace <path>"
        )
    manifest = read_schema_manifest(workspace)
    if manifest is None:
        return LEGACY_SCHEMA_VERSION
    return int(manifest["version"])


def compatibility_error(version: int) -> str | None:
    if version == CURRENT_SCHEMA_VERSION:
        return None
    if version == LEGACY_SCHEMA_VERSION:
        return (
            "workspace schema migration required from schema 0 to schema 1; "
            "run scripts/migrate_workspace.py --workspace <path>"
        )
    if version > CURRENT_SCHEMA_VERSION:
        return (
            f"workspace schema version {version} is newer than supported version "
            f"{CURRENT_SCHEMA_VERSION}; use a newer compatible Aham framework"
        )
    return f"workspace schema version {version} is unsupported"
