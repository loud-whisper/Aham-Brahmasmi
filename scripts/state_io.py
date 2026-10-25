#!/usr/bin/env python3
"""Shared state helpers for Aham Brahmasmi lifecycle scripts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

IS_WINDOWS = os.name == "nt"


def windows_component_invalid(part: str) -> bool:
    device = part.split(".", 1)[0].upper()
    reserved = device in {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
    reserved = reserved or (len(device) == 4 and device[:3] in {"COM", "LPT"}
                           and device[3] in "123456789¹²³")
    return (not part or part in {".", ".."} or part.endswith((".", " ")) or reserved
            or any(ord(char) < 32 or char in '<>:"\\|?*' for char in part))

from schema_compat import (
    IDENTITY_FORMAT,
    IDENTITY_VERSION,
    SchemaCompatibilityError,
    compatibility_error,
    workspace_schema_version,
)


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_FORMAT = IDENTITY_FORMAT
CHECKPOINT_FORMAT = "aham-brahmasmi-checkpoint"
WORKSPACE_ID = re.compile(r"^[0-9a-f]{32}$")
GIT_TIMEOUT_SECONDS = 30
REQUIRED_FILES = ("BRAIN.json", "MEMORY.md", "TODO.md", "LESSONS.md")
REQUIRED_DIRS = ("projects", "history", "state/checkpoints", "state/wrapups")
OPTIONAL_MANAGED_PATHS = (
    "state/operations",
    "state/project_heads",
    "state/store.json",
    "state/.writer.lock",
    "state/latest_checkpoint.json",
    "state/pending_checkpoint.json",
    "state/pending_wrap_up.json",
    "state/projects.json",
    "state/session_authority.json",
    "state/schema.json",
    "state/pending_migration.json",
    "state/pending_external_activation.json",
    "state/migrations",
    "state/skills_index.json",
)


class StateError(RuntimeError):
    """Raised when durable workspace state cannot be safely read or written."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_workspace(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def _absolute_without_resolving(path: Path) -> Path:
    """Make a path absolute without following filesystem symlinks."""
    return Path(os.path.abspath(os.fspath(path.expanduser())))


def _managed_relative(workspace: Path, path: str | Path) -> tuple[Path, Path]:
    # Keep the caller's spelling long enough to preserve detection of managed
    # symlink components. macOS can expose the same temporary tree as both
    # /var/... and /private/var/..., so canonical containment is a fallback
    # only when lexical containment against the caller's workspace spelling fails.
    raw_root = _absolute_without_resolving(Path(workspace))
    root = raw_root.resolve()
    candidate = Path(path).expanduser()
    if IS_WINDOWS:
        parts = candidate.parts[1:] if candidate.anchor else candidate.parts
        if any(windows_component_invalid(part) for part in parts):
            raise StateError("managed path contains a Windows-invalid component before normalization")
    if not candidate.is_absolute():
        candidate = raw_root / candidate
    candidate = _absolute_without_resolving(candidate)
    try:
        relative = candidate.relative_to(raw_root)
    except ValueError:
        try:
            canonical_candidate = candidate.resolve(strict=False)
            relative = canonical_candidate.relative_to(root)
        except ValueError as exc:
            raise StateError(f"managed path escapes workspace: {candidate}") from exc
    if not relative.parts or any(part in {"..", ""} for part in relative.parts):
        raise StateError(f"managed path is not a safe workspace-relative path: {candidate}")
    return root, relative


def require_managed_path(workspace: Path, path: str | Path, *, label: str = "managed path") -> Path:
    """Require containment and reject symlinked managed path components."""
    root, relative = _managed_relative(workspace, path)
    current = root
    for part in relative.parts:
        if IS_WINDOWS and windows_component_invalid(part):
            raise StateError(f"{label} has a Windows-invalid component: {part!r}")
        current = current / part
        if is_link_or_reparse(current):
            raise StateError(f"{label} contains a symlinked component: {current.relative_to(root)}")
    return root / relative


def is_link_or_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return path.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StateError(f"could not read valid JSON from {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise StateError(f"{path.name} must contain a JSON object")
    return value


def workspace_identity_errors(workspace: Path) -> list[str]:
    """Validate immutable workspace identity/shape without requiring current schema."""
    errors: list[str] = []
    workspace = workspace.expanduser().resolve()
    if workspace == ROOT or ROOT in workspace.parents:
        errors.append("workspace is inside the public framework repository")
        return errors
    if not workspace.is_dir():
        errors.append("workspace directory does not exist")
        return errors

    for relative in REQUIRED_FILES:
        try:
            path = require_managed_path(workspace, relative, label=f"required file {relative}")
        except StateError as exc:
            errors.append(str(exc))
            continue
        if not path.is_file():
            errors.append(f"missing required file: {relative}")
    for relative in REQUIRED_DIRS:
        try:
            path = require_managed_path(workspace, relative, label=f"required directory {relative}")
        except StateError as exc:
            errors.append(str(exc))
            continue
        if not path.is_dir():
            errors.append(f"missing required directory: {relative}")
    for relative in OPTIONAL_MANAGED_PATHS:
        path = workspace / relative
        if path.exists() or path.is_symlink():
            try:
                require_managed_path(workspace, relative, label=f"managed state path {relative}")
            except StateError as exc:
                errors.append(str(exc))

    brain_path = workspace / "BRAIN.json"
    if brain_path.is_file() and not brain_path.is_symlink():
        try:
            brain = read_json(brain_path)
        except StateError as exc:
            errors.append(str(exc))
        else:
            if brain.get("format") != WORKSPACE_FORMAT:
                errors.append("BRAIN.json has an unrecognized workspace identity envelope format")
            if brain.get("version") != IDENTITY_VERSION:
                errors.append(
                    f"BRAIN.json identity envelope version is unsupported; expected {IDENTITY_VERSION}"
                )
            if brain.get("workspace_owner") != "user":
                errors.append("BRAIN.json does not identify the workspace as user-owned")
            workspace_id = brain.get("workspace_id")
            if not isinstance(workspace_id, str) or not WORKSPACE_ID.fullmatch(workspace_id):
                errors.append("BRAIN.json has no valid unique workspace_id")
    return errors


def workspace_errors(workspace: Path) -> list[str]:
    workspace = workspace.expanduser().resolve()
    errors = workspace_identity_errors(workspace)
    if errors:
        return errors
    try:
        schema_version = workspace_schema_version(workspace)
    except SchemaCompatibilityError as exc:
        errors.append(str(exc))
    else:
        schema_error = compatibility_error(schema_version)
        if schema_error:
            errors.append(schema_error)
    return errors


def require_workspace_identity(workspace: Path) -> dict[str, Any]:
    workspace = workspace.expanduser().resolve()
    errors = workspace_identity_errors(workspace)
    if errors:
        raise StateError("; ".join(errors))
    return read_json(workspace / "BRAIN.json")


def require_workspace(workspace: Path) -> dict[str, Any]:
    workspace = workspace.expanduser().resolve()
    errors = workspace_errors(workspace)
    if errors:
        raise StateError("; ".join(errors))
    return read_json(workspace / "BRAIN.json")


def workspace_fingerprint(brain: dict[str, Any]) -> str:
    identity = {
        "format": brain.get("format"),
        "version": brain.get("version"),
        "framework": brain.get("framework"),
        "workspace_owner": brain.get("workspace_owner"),
        "workspace_id": brain.get("workspace_id"),
    }
    payload = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    temp_path = Path(handle.name)
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def append_marked_block(path: Path, marker: str, body: str) -> bool:
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    marker_line = f"<!-- aham:{marker} -->"
    if marker_line in current:
        return False
    separator = "" if not current or current.endswith("\n\n") else "\n" if current.endswith("\n") else "\n\n"
    block = f"{marker_line}\n{body.rstrip()}\n"
    atomic_write_text(path, current + separator + block)
    return True


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    if not slug:
        raise StateError("project name does not contain a safe filename component")
    return slug[:80]


def run_git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            text=True,
            capture_output=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise StateError(f"Git command timed out after {GIT_TIMEOUT_SECONDS} seconds") from exc
    if check and result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "git command failed"
        raise StateError(message)
    return result


def git_snapshot(repo_value: str | Path) -> dict[str, str | None]:
    repo = Path(repo_value).expanduser().resolve()
    top = run_git(repo, "rev-parse", "--show-toplevel").stdout.strip()
    top_path = Path(top).resolve()
    head = run_git(top_path, "rev-parse", "HEAD").stdout.strip()
    branch_result = run_git(top_path, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    branch = branch_result.stdout.strip() if branch_result.returncode == 0 else None
    return {"name": top_path.name, "branch": branch, "head": head}


def git_contains_ancestor(repo_value: str | Path, ancestor: str) -> bool:
    repo = Path(repo_value).expanduser().resolve()
    result = run_git(repo, "merge-base", "--is-ancestor", ancestor, "HEAD", check=False)
    return result.returncode == 0


def validate_checkpoint(value: dict[str, Any]) -> list[str]:
    required = {
        "format",
        "version",
        "id",
        "created_at",
        "workspace_fingerprint",
        "summary",
        "completed",
        "next_steps",
        "status",
    }
    errors: list[str] = []
    missing = required - set(value)
    if missing:
        errors.append(f"checkpoint missing fields: {', '.join(sorted(missing))}")
        return errors
    if value.get("format") != CHECKPOINT_FORMAT:
        errors.append("checkpoint format is not recognized")
    if value.get("version") != 1:
        errors.append("checkpoint version is not supported")
    if value.get("status") != "durable":
        errors.append("checkpoint is not marked durable")
    if not isinstance(value.get("summary"), str) or not value["summary"].strip():
        errors.append("checkpoint summary must be a non-empty string")
    for field in ("completed", "next_steps", "artifacts"):
        if field in value and not isinstance(value[field], list):
            errors.append(f"checkpoint field '{field}' must be a list")
    if "revision" in value and (not isinstance(value["revision"], int) or value["revision"] < 1):
        errors.append("checkpoint revision must be a positive integer")
    return errors


def build_checkpoint(
    workspace: Path,
    *,
    summary: str,
    completed: list[str] | None = None,
    next_steps: list[str] | None = None,
    project: str | None = None,
    artifacts: list[str] | None = None,
    repository: dict[str, str | None] | None = None,
    checkpoint_id: str | None = None,
    revision: int | None = None,
) -> dict[str, Any]:
    brain = require_workspace(workspace)
    created_at = utc_now()
    checkpoint_id = checkpoint_id or f"{created_at.replace(':', '').replace('-', '')}-{uuid.uuid4().hex[:8]}"
    checkpoint: dict[str, Any] = {
        "format": CHECKPOINT_FORMAT,
        "version": 1,
        "id": checkpoint_id,
        "created_at": created_at,
        "workspace_fingerprint": workspace_fingerprint(brain),
        "summary": summary.strip(),
        "completed": completed or [],
        "next_steps": next_steps or [],
        "artifacts": artifacts or [],
        "status": "durable",
    }
    if project:
        checkpoint["project"] = project
    if repository:
        checkpoint["repository"] = repository
    if revision is not None:
        checkpoint["revision"] = revision
    errors = validate_checkpoint(checkpoint)
    if errors:
        raise StateError("; ".join(errors))
    return checkpoint


def persist_checkpoint(workspace: Path, checkpoint: dict[str, Any]) -> Path:
    errors = validate_checkpoint(checkpoint)
    if errors:
        raise StateError("; ".join(errors))
    filename = safe_slug(str(checkpoint["id"])) + ".json"
    checkpoint_path = require_managed_path(workspace, workspace / "state" / "checkpoints" / filename, label="checkpoint destination")
    atomic_write_json(checkpoint_path, checkpoint)
    latest = {"format": CHECKPOINT_FORMAT, "version": 1, "id": checkpoint["id"], "file": f"state/checkpoints/{filename}"}
    if "revision" in checkpoint:
        latest["revision"] = checkpoint["revision"]
    latest_path = require_managed_path(workspace, workspace / "state" / "latest_checkpoint.json", label="latest checkpoint pointer")
    atomic_write_json(latest_path, latest)
    return checkpoint_path


def write_checkpoint(
    workspace: Path,
    *,
    summary: str,
    completed: list[str] | None = None,
    next_steps: list[str] | None = None,
    project: str | None = None,
    artifacts: list[str] | None = None,
    repository: dict[str, str | None] | None = None,
    checkpoint_id: str | None = None,
    revision: int | None = None,
) -> tuple[Path, dict[str, Any]]:
    checkpoint = build_checkpoint(
        workspace,
        summary=summary,
        completed=completed,
        next_steps=next_steps,
        project=project,
        artifacts=artifacts,
        repository=repository,
        checkpoint_id=checkpoint_id,
        revision=revision,
    )
    return persist_checkpoint(workspace, checkpoint), checkpoint


def newest_valid_checkpoint(workspace: Path) -> tuple[Path, dict[str, Any]] | None:
    candidates: list[tuple[str, Path, dict[str, Any]]] = []
    checkpoint_dir = require_managed_path(workspace, workspace / "state" / "checkpoints", label="checkpoint directory")
    for path in checkpoint_dir.glob("*.json"):
        if path.is_symlink():
            continue
        try:
            value = read_json(path)
        except StateError:
            continue
        if validate_checkpoint(value):
            continue
        candidates.append((str(value.get("created_at", "")), path, value))
    if not candidates:
        return None
    _, path, value = max(candidates, key=lambda item: (item[0], item[1].name))
    return path, value
