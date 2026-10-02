#!/usr/bin/env python3
"""Stable project identity, rebuildable project indexes, and repository verification helpers."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path, PurePosixPath
from typing import Any

from state_io import StateError, read_json, require_managed_path, require_workspace, run_git, safe_slug
from state_store import durable_write_json, list_operation_records, sync_directory

REGISTRY_FORMAT = "aham-brahmasmi-project-registry"
REGISTRY_VERSION = 1
HEAD_FORMAT = "aham-brahmasmi-project-head"
HEAD_VERSION = 1
PROJECT_ID = re.compile(r"^prj_[0-9a-f]{32}$")
CHECKPOINT_FILE = re.compile(r"^[A-Za-z0-9._-]+\.json$")


def allocated_project_id(workspace: Path, operation_id: str, slot: str) -> str:
    """Allocate a replay-stable opaque ID without using display name or path as identity."""
    workspace_id = require_workspace(workspace)["workspace_id"]
    material = f"{workspace_id}\0{operation_id}\0{slot}".encode("utf-8")
    return "prj_" + hashlib.sha256(material).hexdigest()[:32]


def registry_path(workspace: Path) -> Path:
    return require_managed_path(workspace, "state/projects.json", label="project registry")


def project_file_path(workspace: Path, project_id: str) -> Path:
    if not PROJECT_ID.fullmatch(project_id):
        raise StateError("project ID is not a canonical stable identity")
    return require_managed_path(workspace, f"projects/{project_id}.md", label="project state file")


def empty_registry() -> dict[str, Any]:
    return {"format": REGISTRY_FORMAT, "version": REGISTRY_VERSION, "projects": {}}


def validate_registry(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"format", "version", "projects"}:
        raise StateError("project registry structure is not recognized")
    if value.get("format") != REGISTRY_FORMAT or value.get("version") != REGISTRY_VERSION:
        raise StateError("project registry format/version is not recognized")
    projects = value.get("projects")
    if not isinstance(projects, dict):
        raise StateError("project registry projects must be an object")
    seen_names: set[str] = set()
    for project_id, entry in projects.items():
        if not isinstance(project_id, str) or not PROJECT_ID.fullmatch(project_id):
            raise StateError("project registry contains an invalid project ID")
        if not isinstance(entry, dict) or set(entry) - {"display_name", "file", "legacy_slug", "location"}:
            raise StateError(f"project registry entry {project_id} is malformed")
        name = entry.get("display_name")
        if not isinstance(name, str) or not name.strip() or name != name.strip() or name in seen_names:
            raise StateError(f"project registry entry {project_id} has invalid or duplicate display_name")
        seen_names.add(name)
        if entry.get("file") != f"projects/{project_id}.md":
            raise StateError(f"project registry entry {project_id} has an invalid file binding")
        if not isinstance(entry.get("legacy_slug"), str) or not entry["legacy_slug"]:
            raise StateError(f"project registry entry {project_id} has no legacy slug")
        if entry.get("location") is not None and (not isinstance(entry["location"], str) or not entry["location"]):
            raise StateError(f"project registry entry {project_id} has invalid location")
    return value


def load_registry(workspace: Path) -> dict[str, Any]:
    require_workspace(workspace)
    path = registry_path(workspace)
    return empty_registry() if not path.exists() else validate_registry(read_json(path))


def project_id_by_name(workspace: Path, display_name: str) -> str | None:
    name = display_name.strip()
    for project_id, entry in load_registry(workspace)["projects"].items():
        if entry["display_name"] == name:
            return project_id
    return None


def resolve_project_id(workspace: Path, display_name: str, *, operation_id: str, slot: str) -> str:
    name = display_name.strip()
    if not name:
        raise StateError("project display name must be non-empty")
    return project_id_by_name(workspace, name) or allocated_project_id(workspace, operation_id, slot)


def _legacy_heading_matches(path: Path, display_name: str) -> bool:
    try:
        first_line = path.read_text(encoding="utf-8").splitlines()[0]
    except (OSError, IndexError):
        return False
    return first_line.strip() == f"# {display_name}"


def _migrate_legacy_file(workspace: Path, project_id: str, display_name: str) -> None:
    stable_file = project_file_path(workspace, project_id)
    legacy_file = require_managed_path(
        workspace,
        f"projects/{safe_slug(display_name)}.md",
        label="legacy project state file",
    )
    if not legacy_file.exists() or legacy_file == stable_file:
        return
    if not _legacy_heading_matches(legacy_file, display_name):
        raise StateError(
            f"legacy project migration collision for '{display_name}'; existing {legacy_file.name} cannot be attributed safely"
        )
    stable_file.parent.mkdir(parents=True, exist_ok=True)
    if stable_file.exists():
        raise StateError(f"stable project destination already exists for {project_id}")
    os.replace(legacy_file, stable_file)
    sync_directory(stable_file.parent)


def ensure_project(
    workspace: Path,
    display_name: str,
    *,
    project_id: str,
    location: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Persist a provisional binding; committed reconciliation later decides whether it survives."""
    name = display_name.strip()
    if not name or not isinstance(project_id, str) or not PROJECT_ID.fullmatch(project_id):
        raise StateError("project name or ID is invalid")
    project_file_path(workspace, project_id)
    registry = load_registry(workspace)
    projects = registry["projects"]
    for existing_id, entry in projects.items():
        if entry["display_name"] == name:
            project_file_path(workspace, existing_id)
            if location and entry.get("location") != location:
                entry["location"] = location
                durable_write_json(registry_path(workspace), registry)
            return existing_id, entry
    if project_id in projects and projects[project_id].get("display_name") != name:
        raise StateError("stable project identity collision detected")
    _migrate_legacy_file(workspace, project_id, name)
    entry = {
        "display_name": name,
        "file": f"projects/{project_id}.md",
        "legacy_slug": safe_slug(name),
        "location": location,
    }
    projects[project_id] = entry
    durable_write_json(registry_path(workspace), registry)
    return project_id, entry


def project_by_id(workspace: Path, project_id: str) -> dict[str, Any]:
    project_file_path(workspace, project_id)
    entry = load_registry(workspace)["projects"].get(project_id)
    if not isinstance(entry, dict):
        raise StateError(f"unknown project ID: {project_id}")
    return entry


def project_names_from_record(record: dict[str, Any]) -> list[str]:
    details = record.get("details")
    if not isinstance(details, dict):
        return []
    names = details.get("project_display_names")
    if isinstance(names, list) and all(isinstance(item, str) and item for item in names):
        return list(dict.fromkeys(names))
    if record.get("kind") == "checkpoint":
        checkpoint = details.get("checkpoint")
        if isinstance(checkpoint, dict) and isinstance(checkpoint.get("project"), str):
            return [checkpoint["project"]]
    if record.get("kind") == "wrap_up":
        receipt = details.get("receipt")
        bundle = receipt.get("bundle") if isinstance(receipt, dict) else None
        if isinstance(bundle, dict):
            found: list[str] = []
            for update in bundle.get("project_updates", []):
                if isinstance(update, dict) and isinstance(update.get("project"), str):
                    found.append(update["project"])
            checkpoint = bundle.get("checkpoint")
            if isinstance(checkpoint, dict) and isinstance(checkpoint.get("project"), str):
                found.append(checkpoint["project"])
            return list(dict.fromkeys(found))
    return []


def explicit_project_ids(record: dict[str, Any]) -> list[str] | None:
    details = record.get("details")
    if not isinstance(details, dict):
        return None
    value = details.get("project_ids")
    if isinstance(value, list) and all(isinstance(item, str) and PROJECT_ID.fullmatch(item) for item in value):
        return value
    return None


def project_ids_from_record(workspace: Path, record: dict[str, Any]) -> list[str]:
    names = project_names_from_record(record)
    explicit = explicit_project_ids(record)
    if explicit is not None:
        if names and len(explicit) != len(names):
            raise StateError("committed project identity list does not match project display-name list")
        return list(dict.fromkeys(explicit))
    resolved: list[str] = []
    for index, name in enumerate(names):
        existing = project_id_by_name(workspace, name)
        resolved.append(existing or allocated_project_id(workspace, record["operation_id"], f"project-{index}"))
    return list(dict.fromkeys(resolved))


def _canonical_checkpoint_reference(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    path = PurePosixPath(value)
    if len(path.parts) != 3 or path.parts[:2] != ("state", "checkpoints"):
        return None
    filename = path.parts[2]
    if filename in {".", ".."} or not CHECKPOINT_FILE.fullmatch(filename):
        return None
    return value


def checkpoint_file_from_record(record: dict[str, Any]) -> str | None:
    details = record.get("details")
    if not isinstance(details, dict):
        return None
    direct = _canonical_checkpoint_reference(details.get("checkpoint_file"))
    if direct is not None:
        return direct
    receipt = details.get("receipt") if record.get("kind") == "wrap_up" else None
    value = receipt.get("checkpoint_file") if isinstance(receipt, dict) else None
    return _canonical_checkpoint_reference(value)


def checkpoint_id_from_record(record: dict[str, Any]) -> str | None:
    details = record.get("details")
    if not isinstance(details, dict):
        return None
    if record.get("kind") == "checkpoint":
        checkpoint = details.get("checkpoint")
        return checkpoint.get("id") if isinstance(checkpoint, dict) and isinstance(checkpoint.get("id"), str) else None
    return f"wrap-{record['operation_id']}" if record.get("kind") == "wrap_up" else None


def _record_location(record: dict[str, Any]) -> str | None:
    details = record.get("details") if isinstance(record.get("details"), dict) else {}
    if record.get("kind") == "checkpoint":
        checkpoint = details.get("checkpoint") if isinstance(details, dict) else None
        repository = checkpoint.get("repository") if isinstance(checkpoint, dict) else None
    else:
        receipt = details.get("receipt") if isinstance(details, dict) else None
        repository = receipt.get("repository") if isinstance(receipt, dict) else None
    return repository.get("root") if isinstance(repository, dict) and isinstance(repository.get("root"), str) else None


def reconcile_project_registry(workspace: Path) -> dict[str, Any]:
    """Rebuild the registry solely from committed records, dropping pre-commit provisional bindings."""
    expected = empty_registry()
    by_name: dict[str, str] = {}
    for _, record in list_operation_records(workspace):
        names = project_names_from_record(record)
        explicit = explicit_project_ids(record)
        if explicit is not None and names and len(explicit) != len(names):
            raise StateError("committed project identity list does not match project display-name list")
        for index, name in enumerate(names):
            if name in by_name:
                project_id = by_name[name]
                if explicit is not None and explicit[index] != project_id:
                    raise StateError("committed records bind one project name to conflicting stable IDs")
            else:
                project_id = explicit[index] if explicit is not None else allocated_project_id(
                    workspace, record["operation_id"], f"project-{index}"
                )
                if project_id in expected["projects"] and expected["projects"][project_id]["display_name"] != name:
                    raise StateError("committed records contain a stable project ID collision")
                by_name[name] = project_id
            location = _record_location(record) or expected["projects"].get(project_id, {}).get("location")
            expected["projects"][project_id] = {
                "display_name": name,
                "file": f"projects/{project_id}.md",
                "legacy_slug": safe_slug(name),
                "location": location,
            }
    for project_id, entry in expected["projects"].items():
        _migrate_legacy_file(workspace, project_id, entry["display_name"])
    durable_write_json(registry_path(workspace), expected)
    return validate_registry(expected)


def head_path(workspace: Path, project_id: str) -> Path:
    if not PROJECT_ID.fullmatch(project_id):
        raise StateError("project head contains an invalid project ID")
    return require_managed_path(workspace, f"state/project_heads/{project_id}.json", label="project checkpoint head")


def compute_project_heads(workspace: Path) -> dict[str, dict[str, Any]]:
    heads: dict[str, dict[str, Any]] = {}
    for _, record in list_operation_records(workspace):
        checkpoint_file = checkpoint_file_from_record(record)
        if not checkpoint_file:
            continue
        require_managed_path(workspace, checkpoint_file, label="committed checkpoint reference")
        for project_id in project_ids_from_record(workspace, record):
            heads[project_id] = {
                "format": HEAD_FORMAT,
                "version": HEAD_VERSION,
                "project_id": project_id,
                "revision": record["revision"],
                "operation_id": record["operation_id"],
                "checkpoint_file": checkpoint_file,
            }
    return heads


def reconcile_project_heads(workspace: Path) -> dict[str, dict[str, Any]]:
    reconcile_project_registry(workspace)
    heads = compute_project_heads(workspace)
    directory = require_managed_path(workspace, "state/project_heads", label="project heads directory")
    directory.mkdir(parents=True, exist_ok=True)
    sync_directory(directory.parent)
    expected_names = {f"{project_id}.json" for project_id in heads}
    for existing in directory.glob("*.json"):
        if existing.is_symlink():
            raise StateError(f"project heads directory contains a symlinked record: {existing.name}")
        if existing.name not in expected_names:
            existing.unlink()
    for project_id, head in heads.items():
        durable_write_json(head_path(workspace, project_id), head)
    sync_directory(directory)
    return heads


def reconcile_latest_checkpoint(workspace: Path) -> dict[str, Any] | None:
    records = [record for _, record in list_operation_records(workspace) if checkpoint_file_from_record(record)]
    path = require_managed_path(workspace, "state/latest_checkpoint.json", label="latest checkpoint pointer")
    if not records:
        if path.exists():
            path.unlink()
            sync_directory(path.parent)
        return None
    record = records[-1]
    checkpoint_file = checkpoint_file_from_record(record)
    checkpoint_id = checkpoint_id_from_record(record)
    if not checkpoint_file or not checkpoint_id:
        raise StateError("latest committed checkpoint record cannot produce a canonical pointer")
    require_managed_path(workspace, checkpoint_file, label="latest committed checkpoint")
    pointer = {
        "format": "aham-brahmasmi-checkpoint",
        "version": 1,
        "id": checkpoint_id,
        "file": checkpoint_file,
        "revision": record["revision"],
    }
    durable_write_json(path, pointer)
    return pointer


def git_snapshot_strong(repo_value: str | Path) -> dict[str, Any]:
    repo = Path(repo_value).expanduser().resolve()
    top = Path(run_git(repo, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    head = run_git(top, "rev-parse", "HEAD").stdout.strip()
    branch_result = run_git(top, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    branch = branch_result.stdout.strip() if branch_result.returncode == 0 else None
    common_raw = run_git(top, "rev-parse", "--git-common-dir").stdout.strip()
    common = Path(common_raw)
    common = (top / common).resolve() if not common.is_absolute() else common.resolve()
    remote_result = run_git(top, "config", "--get", "remote.origin.url", check=False)
    remote_url = remote_result.stdout.strip() if remote_result.returncode == 0 and remote_result.stdout.strip() else None
    status = run_git(top, "status", "--porcelain=v1", "--untracked-files=all").stdout
    lines = [line for line in status.splitlines() if line]
    identity = hashlib.sha256(f"{top}\0{common}".encode("utf-8")).hexdigest()
    return {
        "name": top.name,
        "branch": branch,
        "head": head,
        "identity": identity,
        "root": str(top),
        "git_common_dir": str(common),
        "remote_url": remote_url,
        "tracked_dirty": any(not line.startswith("?? ") for line in lines),
        "untracked_present": any(line.startswith("?? ") for line in lines),
        "status_digest": hashlib.sha256(status.encode("utf-8")).hexdigest(),
    }
