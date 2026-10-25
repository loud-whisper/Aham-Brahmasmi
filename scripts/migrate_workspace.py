#!/usr/bin/env python3
"""Migrate an Aham Brahmasmi workspace to the current workspace-state schema."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from schema_compat import (
    CURRENT_SCHEMA_VERSION,
    LEGACY_SCHEMA_VERSION,
    SchemaCompatibilityError,
    current_schema_manifest,
    workspace_schema_version,
)
from state_io import (
    StateError,
    atomic_write_json,
    read_json,
    require_managed_path,
    require_workspace_identity,
    utc_now,
)


PENDING_FORMAT = "aham-brahmasmi-workspace-migration-pending"
RECEIPT_FORMAT = "aham-brahmasmi-workspace-migration-receipt"
MIGRATION_RECORD_VERSION = 1
MIGRATION_ID = "workspace-schema-0-to-1"
PENDING_RELATIVE = "state/pending_migration.json"
MIGRATIONS_RELATIVE = "state/migrations"
SCHEMA_RELATIVE = "state/schema.json"


class MigrationError(RuntimeError):
    """Raised when migration cannot proceed safely."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate an Aham Brahmasmi workspace schema safely.")
    parser.add_argument("--workspace", required=True, help="Path to the private workspace")
    return parser.parse_args()


def canonical_digest(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def sync_directory(directory: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(directory, flags)
    except OSError:
        return
    try:
        try:
            os.fsync(descriptor)
        except OSError:
            pass
    finally:
        os.close(descriptor)


def durable_unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    sync_directory(path.parent)


def test_crash_point(name: str) -> None:
    if (
        os.environ.get("AHAM_BRAHMASMI_TEST_MODE") == "1"
        and os.environ.get("AHAM_BRAHMASMI_TEST_CRASH_POINT") == name
    ):
        raise SystemExit(86)


def pending_path(workspace: Path) -> Path:
    return require_managed_path(workspace, PENDING_RELATIVE, label="pending migration record")


def migrations_dir(workspace: Path) -> Path:
    path = require_managed_path(workspace, MIGRATIONS_RELATIVE, label="migration receipts directory")
    path.mkdir(parents=True, exist_ok=True)
    sync_directory(path.parent)
    return path


def receipt_path(workspace: Path) -> Path:
    return require_managed_path(
        workspace,
        migrations_dir(workspace) / f"{MIGRATION_ID}.json",
        label="migration receipt",
    )


def schema_path(workspace: Path) -> Path:
    return require_managed_path(workspace, SCHEMA_RELATIVE, label="workspace schema manifest")


def validate_pending(value: Any, workspace_id: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MigrationError("pending migration must be a JSON object")
    required = {
        "format",
        "version",
        "migration_id",
        "workspace_id",
        "from_version",
        "to_version",
        "status",
        "step",
        "started_at",
    }
    unknown = set(value) - required
    missing = required - set(value)
    if unknown:
        raise MigrationError("pending migration contains unknown fields: " + ", ".join(sorted(unknown)))
    if missing:
        raise MigrationError("pending migration is missing fields: " + ", ".join(sorted(missing)))
    if value.get("format") != PENDING_FORMAT or value.get("version") != MIGRATION_RECORD_VERSION:
        raise MigrationError("pending migration format/version is not recognized")
    if value.get("migration_id") != MIGRATION_ID:
        raise MigrationError("pending migration identity is not recognized")
    if value.get("workspace_id") != workspace_id:
        raise MigrationError("pending migration belongs to a different workspace identity")
    if value.get("from_version") != LEGACY_SCHEMA_VERSION or value.get("to_version") != CURRENT_SCHEMA_VERSION:
        raise MigrationError("pending migration version transition is not supported")
    if value.get("status") != "pending":
        raise MigrationError("pending migration status is not pending")
    if value.get("step") not in {"prepared", "schema_written", "receipt_written"}:
        raise MigrationError("pending migration step is not recognized")
    if not isinstance(value.get("started_at"), str) or not value["started_at"]:
        raise MigrationError("pending migration has no start timestamp")
    return value


def validate_receipt(value: Any, workspace_id: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MigrationError("migration receipt must be a JSON object")
    required = {
        "format",
        "version",
        "migration_id",
        "workspace_id",
        "from_version",
        "to_version",
        "status",
        "schema_digest",
        "completed_at",
    }
    unknown = set(value) - required
    missing = required - set(value)
    if unknown:
        raise MigrationError("migration receipt contains unknown fields: " + ", ".join(sorted(unknown)))
    if missing:
        raise MigrationError("migration receipt is missing fields: " + ", ".join(sorted(missing)))
    if value.get("format") != RECEIPT_FORMAT or value.get("version") != MIGRATION_RECORD_VERSION:
        raise MigrationError("migration receipt format/version is not recognized")
    if value.get("migration_id") != MIGRATION_ID:
        raise MigrationError("migration receipt identity is not recognized")
    if value.get("workspace_id") != workspace_id:
        raise MigrationError("migration receipt belongs to a different workspace identity")
    if value.get("from_version") != LEGACY_SCHEMA_VERSION or value.get("to_version") != CURRENT_SCHEMA_VERSION:
        raise MigrationError("migration receipt version transition is not supported")
    if value.get("status") != "complete":
        raise MigrationError("migration receipt status is not complete")
    expected_digest = canonical_digest(current_schema_manifest())
    if value.get("schema_digest") != expected_digest:
        raise MigrationError("migration receipt schema digest does not match the current schema manifest")
    if not isinstance(value.get("completed_at"), str) or not value["completed_at"]:
        raise MigrationError("migration receipt has no completion timestamp")
    return value


def write_pending(path: Path, value: dict[str, Any]) -> None:
    atomic_write_json(path, value)
    sync_directory(path.parent)


def build_receipt(workspace_id: str) -> dict[str, Any]:
    return {
        "format": RECEIPT_FORMAT,
        "version": MIGRATION_RECORD_VERSION,
        "migration_id": MIGRATION_ID,
        "workspace_id": workspace_id,
        "from_version": LEGACY_SCHEMA_VERSION,
        "to_version": CURRENT_SCHEMA_VERSION,
        "status": "complete",
        "schema_digest": canonical_digest(current_schema_manifest()),
        "completed_at": utc_now(),
    }


def apply_or_resume(workspace: Path, workspace_id: str, pending: dict[str, Any], *, recovered: bool) -> int:
    current_version = workspace_schema_version(workspace, allow_pending_migration=True)
    if current_version not in {LEGACY_SCHEMA_VERSION, CURRENT_SCHEMA_VERSION}:
        if current_version > CURRENT_SCHEMA_VERSION:
            raise MigrationError(
                f"workspace schema version {current_version} is newer than supported version {CURRENT_SCHEMA_VERSION}"
            )
        raise MigrationError(f"workspace schema version {current_version} is unsupported")

    schema = schema_path(workspace)
    if current_version == LEGACY_SCHEMA_VERSION:
        atomic_write_json(schema, current_schema_manifest())
        sync_directory(schema.parent)
    elif read_json(schema) != current_schema_manifest():
        raise MigrationError("current workspace schema manifest does not match the canonical schema 1 manifest")

    pending["step"] = "schema_written"
    write_pending(pending_path(workspace), pending)
    test_crash_point("migration_after_schema_write")

    receipt = receipt_path(workspace)
    if receipt.exists():
        validate_receipt(read_json(receipt), workspace_id)
    else:
        atomic_write_json(receipt, build_receipt(workspace_id))
        sync_directory(receipt.parent)
        validate_receipt(read_json(receipt), workspace_id)

    pending["step"] = "receipt_written"
    write_pending(pending_path(workspace), pending)
    test_crash_point("migration_after_receipt_write")

    durable_unlink(pending_path(workspace))

    if workspace_schema_version(workspace) != CURRENT_SCHEMA_VERSION:
        raise MigrationError("workspace schema did not reach the current version after migration")

    if recovered:
        print("MIGRATION RECOVERED")
    else:
        print("MIGRATION COMPLETE")
    print(f"Workspace: {workspace}")
    print(f"Schema: {LEGACY_SCHEMA_VERSION} -> {CURRENT_SCHEMA_VERSION}")
    print(f"Receipt: {receipt}")
    return 0


def migrate(workspace: Path) -> int:
    workspace = workspace.expanduser().resolve()
    brain = require_workspace_identity(workspace)
    workspace_id = brain["workspace_id"]
    pending = pending_path(workspace)

    if pending.exists():
        pending_value = validate_pending(read_json(pending), workspace_id)
        return apply_or_resume(workspace, workspace_id, pending_value, recovered=True)

    current_version = workspace_schema_version(workspace)
    if current_version == CURRENT_SCHEMA_VERSION:
        print("MIGRATION NOT NEEDED")
        print(f"Workspace: {workspace}")
        print(f"Schema: {CURRENT_SCHEMA_VERSION}")
        return 0
    if current_version > CURRENT_SCHEMA_VERSION:
        raise MigrationError(
            f"workspace schema version {current_version} is newer than supported version {CURRENT_SCHEMA_VERSION}; "
            "use a newer compatible Aham framework"
        )
    if current_version != LEGACY_SCHEMA_VERSION:
        raise MigrationError(f"workspace schema version {current_version} is unsupported")

    pending_value = {
        "format": PENDING_FORMAT,
        "version": MIGRATION_RECORD_VERSION,
        "migration_id": MIGRATION_ID,
        "workspace_id": workspace_id,
        "from_version": LEGACY_SCHEMA_VERSION,
        "to_version": CURRENT_SCHEMA_VERSION,
        "status": "pending",
        "step": "prepared",
        "started_at": utc_now(),
    }
    write_pending(pending, pending_value)
    test_crash_point("migration_after_pending_write")
    return apply_or_resume(workspace, workspace_id, pending_value, recovered=False)


def main() -> int:
    args = parse_args()
    try:
        return migrate(Path(args.workspace))
    except (MigrationError, SchemaCompatibilityError, StateError, OSError, json.JSONDecodeError) as exc:
        print(f"MIGRATION FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
