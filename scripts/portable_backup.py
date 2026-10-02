#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any

from session_authority import issue_bootstrap_session
from state_io import StateError, read_json, require_managed_path, require_workspace, resolve_workspace, workspace_fingerprint, windows_component_invalid
from state_store import list_operation_records, validate_store, writer_lock
from windows_access import private_temporary_directory

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "core" / "portable_backup.json"
FORMAT = "aham-brahmasmi-portable-export"
VERSION = 1
PENDING = (
    "state/pending_checkpoint.json",
    "state/pending_wrap_up.json",
    "state/pending_migration.json",
    "state/pending_external_activation.json",
)
REQUIRED_DIRS = (
    "projects",
    "history",
    "external",
    "state/checkpoints",
    "state/wrapups",
    "state/operations",
    "state/project_heads",
    "state/migrations",
    "state/quarantine",
    "state/scan_reports",
    "state/replaced_sources",
)


class PortableError(StateError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def portable_path_key(value: str) -> str:
    """Normalize a portable path for collision checks on common filesystems."""
    return unicodedata.normalize("NFC", value).casefold()


def ensure_portable_path_uniqueness(paths: list[str] | set[str] | dict[str, Any]) -> None:
    seen: dict[str, str] = {}
    for raw in paths:
        validate_portable_name(raw)
        key = portable_path_key(raw)
        prior = seen.get(key)
        if prior is not None and prior != raw:
            raise PortableError(
                "portable paths have a case-insensitive or Unicode-normalized collision: "
                f"{prior} and {raw}"
            )
        seen[key] = raw


def validate_portable_name(raw: str) -> None:
    for part in raw.split("/"):
        if windows_component_invalid(part):
            raise PortableError("portable path contains a Windows-invalid component: " + repr(raw))


def load_contract() -> dict[str, Any]:
    value = read_json(CONTRACT)
    if value.get("version") != 1 or value.get("id") != "portable_backup":
        raise PortableError("portable export contract is missing or unsupported")
    paths = value.get("paths")
    if not isinstance(paths, list) or not paths:
        raise PortableError("portable export contract has no path rules")
    for item in paths:
        if not isinstance(item, dict) or set(item) != {"path", "class"}:
            raise PortableError("portable export path rule is malformed")
        if item["class"] not in {"record", "artifact"}:
            raise PortableError("portable export path class is unsupported")
        if not isinstance(item["path"], str) or not item["path"]:
            raise PortableError("portable export path rule has no path")
    return value


def ensure_no_pending(workspace: Path) -> None:
    found = [relative for relative in PENDING if (workspace / relative).exists() or (workspace / relative).is_symlink()]
    if found:
        raise PortableError("pending Aham state must be resolved before portable export: " + ", ".join(found))


def source_revision(workspace: Path) -> int:
    records = list_operation_records(workspace)
    revision = records[-1][1]["revision"] if records else 0
    store = workspace / "state" / "store.json"
    if store.exists():
        cached = validate_store(read_json(store))
        if cached["revision"] != revision:
            raise PortableError(
                f"cached state-store revision {cached['revision']} does not match immutable ledger revision {revision}"
            )
    elif revision:
        raise PortableError("immutable operation ledger exists but state/store.json is missing")
    return revision


def files_for_rule(workspace: Path, rule: str) -> list[Path]:
    relative = rule.rstrip("/")
    path = require_managed_path(workspace, relative, label="portable export path")
    if not path.exists():
        return []
    if path.is_symlink():
        raise PortableError(f"portable export path is symlinked: {relative}")
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise PortableError(f"portable export path is not a regular file/directory: {relative}")
    out: list[Path] = []
    for candidate in sorted(path.rglob("*")):
        require_managed_path(workspace, candidate, label="portable export file")
        if candidate.is_symlink():
            raise PortableError(f"portable export contains symlink: {candidate.relative_to(workspace).as_posix()}")
        if candidate.is_file():
            out.append(candidate)
    return out


def build_manifest(workspace: Path) -> dict[str, Any]:
    brain = require_workspace(workspace)
    ensure_no_pending(workspace)
    revision = source_revision(workspace)
    contract = load_contract()
    by_path: dict[str, dict[str, Any]] = {}
    for rule in contract["paths"]:
        for path in files_for_rule(workspace, rule["path"]):
            relative = path.relative_to(workspace).as_posix()
            data = path.read_bytes()
            entry = {
                "path": relative,
                "class": rule["class"],
                "size": len(data),
                "sha256": sha256_bytes(data),
            }
            prior = by_path.get(relative)
            if prior is not None and prior != entry:
                raise PortableError(f"portable export contract classifies one file inconsistently: {relative}")
            by_path[relative] = entry
    ensure_portable_path_uniqueness(by_path)
    files = [by_path[key] for key in sorted(by_path)]
    if "BRAIN.json" not in by_path or "state/schema.json" not in by_path:
        raise PortableError("portable export is missing required workspace identity/schema state")
    return {
        "format": FORMAT,
        "version": VERSION,
        "claim_scope": "portable_local_export",
        "replicated_backup": False,
        "workspace_id": brain["workspace_id"],
        "workspace_fingerprint": workspace_fingerprint(brain),
        "source_revision": revision,
        "files": files,
        "summary": {
            "file_count": len(files),
            "record_count": sum(1 for item in files if item["class"] == "record"),
            "artifact_count": sum(1 for item in files if item["class"] == "artifact"),
        },
    }


def validate_manifest(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PortableError("portable manifest must be an object")
    required = {
        "format",
        "version",
        "claim_scope",
        "replicated_backup",
        "workspace_id",
        "workspace_fingerprint",
        "source_revision",
        "files",
        "summary",
    }
    if set(value) != required:
        raise PortableError("portable manifest structure is not recognized")
    if value.get("format") != FORMAT or value.get("version") != VERSION:
        raise PortableError("portable manifest format/version is unsupported")
    if value.get("claim_scope") != "portable_local_export" or value.get("replicated_backup") is not False:
        raise PortableError("portable manifest success scope is invalid")
    if not isinstance(value.get("workspace_id"), str) or not value["workspace_id"]:
        raise PortableError("portable manifest has no workspace identity")
    if not isinstance(value.get("workspace_fingerprint"), str) or len(value["workspace_fingerprint"]) != 64:
        raise PortableError("portable manifest workspace fingerprint is invalid")
    if not isinstance(value.get("source_revision"), int) or value["source_revision"] < 0:
        raise PortableError("portable manifest source revision is invalid")
    files = value.get("files")
    if not isinstance(files, list):
        raise PortableError("portable manifest files must be a list")
    seen: set[str] = set()
    portable_seen: dict[str, str] = {}
    for item in files:
        if not isinstance(item, dict) or set(item) != {"path", "class", "size", "sha256"}:
            raise PortableError("portable manifest file entry is malformed")
        raw = item.get("path")
        if not isinstance(raw, str) or not raw or raw in seen:
            raise PortableError("portable manifest contains an invalid/duplicate path")
        path = PurePosixPath(raw)
        validate_portable_name(raw)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise PortableError("portable manifest contains an unsafe path")
        key = portable_path_key(raw)
        prior = portable_seen.get(key)
        if prior is not None and prior != raw:
            raise PortableError(
                "portable manifest has a case-insensitive or Unicode-normalized path collision: "
                f"{prior} and {raw}"
            )
        portable_seen[key] = raw
        seen.add(raw)
        if item.get("class") not in {"record", "artifact"}:
            raise PortableError("portable manifest file class is invalid")
        if not isinstance(item.get("size"), int) or item["size"] < 0:
            raise PortableError("portable manifest file size is invalid")
        digest = item.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise PortableError("portable manifest file digest is invalid")
    summary = value.get("summary")
    if not isinstance(summary, dict) or set(summary) != {"file_count", "record_count", "artifact_count"}:
        raise PortableError("portable manifest summary is invalid")
    if summary["file_count"] != len(files):
        raise PortableError("portable manifest file count does not match entries")
    if summary["record_count"] != sum(1 for item in files if item["class"] == "record"):
        raise PortableError("portable manifest record count does not match entries")
    if summary["artifact_count"] != sum(1 for item in files if item["class"] == "artifact"):
        raise PortableError("portable manifest artifact count does not match entries")
    return value


def validate_bundle(bundle: Path) -> dict[str, Any]:
    manifest_path = bundle / "manifest.json"
    payload = bundle / "payload"
    if not manifest_path.is_file() or manifest_path.is_symlink() or not payload.is_dir() or payload.is_symlink():
        raise PortableError("portable export bundle is incomplete")
    manifest = validate_manifest(read_json(manifest_path))
    expected = {item["path"] for item in manifest["files"]}
    actual: set[str] = set()
    for path in sorted(payload.rglob("*")):
        if path.is_symlink():
            raise PortableError("portable payload contains a symlink")
        if path.is_file():
            relative = path.relative_to(payload).as_posix()
            actual.add(relative)
    if actual != expected:
        raise PortableError("portable payload files do not match manifest")
    for item in manifest["files"]:
        data = (payload / item["path"]).read_bytes()
        if len(data) != item["size"] or sha256_bytes(data) != item["sha256"]:
            raise PortableError(f"portable payload digest/size mismatch: {item['path']}")
    return manifest


def command_manifest(workspace: Path, as_json: bool) -> int:
    manifest = build_manifest(workspace)
    if as_json:
        print(canonical_json(manifest))
    else:
        print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


def command_export(workspace: Path, output: Path) -> int:
    workspace = workspace.resolve()
    output = output.expanduser().resolve()
    if output == workspace or workspace in output.parents:
        raise PortableError("portable export output must be outside the source workspace")
    if output.exists():
        raise PortableError("portable export output already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    with writer_lock(workspace):
        manifest = build_manifest(workspace)
        temporary = private_temporary_directory(output.parent, f".{output.name}.tmp-")
        try:
            payload = temporary / "payload"
            payload.mkdir()
            for item in manifest["files"]:
                source = require_managed_path(workspace, item["path"], label="portable export source")
                target = payload / item["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
            (temporary / "manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            validate_bundle(temporary)
            os.replace(temporary, output)
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
    print("PORTABLE EXPORT CREATED")
    print(f"Workspace ID: {manifest['workspace_id']}")
    print(f"Revision: {manifest['source_revision']}")
    print(f"Files: {manifest['summary']['file_count']}")
    print("Replicated backup: no")
    return 0


def prepare_destination(destination: Path) -> tuple[Path, bool]:
    existed_empty = False
    if destination.exists():
        if not destination.is_dir():
            raise PortableError("restore destination exists and is not a directory")
        if any(destination.iterdir()):
            raise PortableError("restore destination is not empty; nothing was overwritten")
        existed_empty = True
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = private_temporary_directory(destination.parent, f".{destination.name}.restore-")
    return temporary, existed_empty


def command_restore(bundle: Path, destination: Path) -> int:
    bundle = bundle.expanduser().resolve()
    destination = destination.expanduser().resolve()
    manifest = validate_bundle(bundle)
    temporary, existed_empty = prepare_destination(destination)
    try:
        for relative in REQUIRED_DIRS:
            (temporary / relative).mkdir(parents=True, exist_ok=True)
        for item in manifest["files"]:
            source = bundle / "payload" / item["path"]
            target = temporary / item["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
        restored = build_manifest(temporary)
        if restored != manifest:
            raise PortableError("restored record/artifact manifest does not match source export")
        issue_bootstrap_session(temporary)
        if build_manifest(temporary) != manifest:
            raise PortableError("fresh restore-local session authority changed portable manifest")
        if existed_empty:
            destination.rmdir()
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    print("PORTABLE RESTORE VERIFIED")
    print(f"Workspace ID: {manifest['workspace_id']}")
    print(f"Revision: {manifest['source_revision']}")
    print("Fresh session authority: issued")
    print("Replicated backup: no")
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Create and restore provider-neutral portable Brain exports.")
    sub = p.add_subparsers(dest="command", required=True)
    m = sub.add_parser("manifest")
    m.add_argument("--workspace", required=True)
    m.add_argument("--json", action="store_true")
    e = sub.add_parser("export")
    e.add_argument("--workspace", required=True)
    e.add_argument("--output", required=True)
    r = sub.add_parser("restore")
    r.add_argument("--input", required=True)
    r.add_argument("--workspace", required=True)
    return p


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "manifest":
            return command_manifest(resolve_workspace(args.workspace), args.json)
        if args.command == "export":
            return command_export(resolve_workspace(args.workspace), Path(args.output))
        if args.command == "restore":
            return command_restore(Path(args.input), Path(args.workspace))
        raise PortableError("unsupported portable backup command")
    except (PortableError, StateError, OSError, json.JSONDecodeError) as exc:
        print(f"PORTABLE BACKUP FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
