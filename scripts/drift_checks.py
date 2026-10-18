"""Read-only workspace inventory and startup source byte accounting."""

from __future__ import annotations

from pathlib import Path
import os
import unicodedata

from state_io import StateError, is_link_or_reparse, read_json, require_managed_path

ROOT = Path(__file__).resolve().parents[1]
INDEX_FORMAT = "aham-brahmasmi-workspace-index"
VCS_FILES = {".gitignore", ".gitattributes", ".git"}


def names(value, label):
    if not isinstance(value, list):
        raise StateError(f"INDEX.json {label} must be a list")
    seen = set()
    for name in value:
        if (not isinstance(name, str) or not name or name != name.strip()
                or name in {".", ".."} or any(c in name for c in "/\\\0:")):
            raise StateError(f"INDEX.json {label} must contain single relative names")
        key = unicodedata.normalize("NFC", name).casefold()
        if key in seen:
            raise StateError(f"INDEX.json {label} has duplicate or colliding names")
        seen.add(key)
    return value


def load_index(workspace):
    path = require_managed_path(workspace, "INDEX.json", label="workspace index")
    if not path.is_file():
        raise StateError("missing INDEX.json; review templates/private-workspace/INDEX.json and inventory this workspace")
    index = read_json(path)
    fields = {"format", "version", "files", "projects", "startup_budget_bytes"}
    if (not isinstance(index, dict) or set(index) != fields or index.get("format") != INDEX_FORMAT
            or type(index.get("version")) is not int or index["version"] != 1):
        raise StateError("INDEX.json has an unsupported structure or version")
    names(index["files"], "files")
    names(index["projects"], "projects")
    if "INDEX.json" not in index["files"]:
        raise StateError("INDEX.json must list itself in files")
    if type(index["startup_budget_bytes"]) is not int or index["startup_budget_bytes"] <= 0:
        raise StateError("INDEX.json startup_budget_bytes must be a positive integer")
    return index


def startup_sources(workspace, index, runtime):
    """Count the declared source set, including generated bridge instructions.

    Source bytes are counted without truncating context or reading integrations.
    Runtime conversation/history and diagnostic report output are separate budgets.
    """
    from runtime_bridge import load_contract, render_bridge, runtime_native_block

    contract = read_json(ROOT / "core/startup.json")
    relatives = {source for phase in contract["phases"] if phase.get("required")
                 for source in phase.get("sources", [])}
    profiles = load_contract()["runtimes"]
    profile = runtime if runtime in profiles else "unknown"
    relatives.add(f"runtime_profiles/{profile}.json")
    sizes = {}
    for relative in sorted(relatives):
        path = require_managed_path(ROOT, relative, label="startup source")
        if not path.is_file():
            raise StateError(f"missing startup source: {relative}")
        sizes["framework/" + relative] = path.stat().st_size
    for relative in index["files"]:
        path = require_managed_path(workspace, relative, label="indexed startup source")
        if path.is_file():
            sizes["workspace/" + relative] = path.stat().st_size
    selected = profiles[profile]
    sizes["generated/.aham/runtime.md"] = len(render_bridge(runtime).replace("\n", os.linesep).encode("utf-8"))
    native = runtime_native_block(runtime, selected)
    if native is not None:
        from runtime_bridge import update_managed_block
        sizes["generated/native-instruction-block"] = len(
            update_managed_block("", native).replace("\n", os.linesep).encode("utf-8"))
    total = sum(sizes.values())
    return {"total_bytes": total, "budget_bytes": index["startup_budget_bytes"],
            "sources": sizes, "encoding": "UTF-8", "scope": "declared_startup_sources"}


def workspace_drift(workspace: Path, runtime="unknown"):
    workspace = workspace.resolve()
    errors = []
    accounting = None
    try:
        index = load_index(workspace)
        for path in sorted(workspace.iterdir()):
            if path.name in VCS_FILES:
                continue
            if is_link_or_reparse(path):
                raise StateError(f"refusing symlink or reparse point in workspace: {path.name}")
            if path.is_file() and path.name not in index["files"]:
                errors.append(f"unindexed top-level file: {path.name}")
        for name in index["files"]:
            path = require_managed_path(workspace, name, label="indexed file")
            if not path.is_file():
                errors.append(f"missing indexed file: {name}")
        projects = require_managed_path(workspace, "projects", label="projects directory")
        if not projects.is_dir():
            errors.append("missing projects directory")
        else:
            folders = set()
            for folder in sorted(projects.iterdir()):
                if is_link_or_reparse(folder):
                    raise StateError(f"refusing symlink or reparse point in projects: {folder.name}")
                if not folder.is_dir():
                    continue
                folders.add(folder.name)
                if folder.name not in index["projects"]:
                    errors.append(f"unlisted project folder: {folder.name}")
                record = require_managed_path(workspace, f"projects/{folder.name}/PROJECT.md", label="project record")
                if not record.is_file():
                    errors.append(f"missing project record: projects/{folder.name}/PROJECT.md")
            for name in sorted(set(index["projects"]) - folders):
                errors.append(f"missing listed project folder: {name}")
        accounting = startup_sources(workspace, index, runtime)
        if accounting["total_bytes"] > accounting["budget_bytes"]:
            errors.append(f"startup context exceeds byte budget: {accounting['total_bytes']} > {accounting['budget_bytes']}")
    except (StateError, OSError, ValueError) as exc:
        errors.append(str(exc))
    return {"errors": errors, "startup_context": accounting}
