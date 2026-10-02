"""Portable discovery from committed activations and revisioned skill preferences."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import uuid

from external_identity import tree_digest, tree_entries
from project_state import project_by_id
from scanner_rules import frontmatter
from session_authority import advance_session_revision, require_operation_authority
from state_io import StateError, require_managed_path, require_workspace
from state_store import (advance_store_head, commit_operation, digest_json, durable_write_json,
                         list_operation_records, writer_lock)

FORMAT = "aham-skills-index"
VERSION = 1
KIND = "skills_control"


def _request(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != {"action", "skill_id", "enabled", "project_id", "tree_digest"}:
        raise StateError("invalid skill preference request")
    if value["action"] == "refresh":
        if any(value[key] is not None for key in ("skill_id", "enabled", "project_id", "tree_digest")):
            raise StateError("invalid skill refresh request")
    elif value["action"] == "set_enabled":
        if (not isinstance(value["skill_id"], str) or not value["skill_id"]
                or type(value["enabled"]) is not bool
                or (value["project_id"] is not None and not isinstance(value["project_id"], str))
                or not isinstance(value["tree_digest"], str) or len(value["tree_digest"]) != 64):
            raise StateError("invalid skill enable/disable request")
    else:
        raise StateError("unknown skill preference action")
    return value


def _preferences(records: list) -> dict:
    preferences: dict = {}
    for _, record in records:
        if record["kind"] != KIND:
            continue
        request = _request(record["details"].get("request"))
        if digest_json(request) != record["payload_digest"]:
            raise StateError("skill preference conflicts with its immutable ledger digest")
        if request["action"] == "set_enabled":
            preference = preferences.setdefault(request["skill_id"], {"enabled": True, "projects": {}})
            if request["project_id"] is None:
                preference["enabled"] = request["enabled"]
            else:
                preference["projects"][request["project_id"]] = request["enabled"]
    return preferences


def list_skills(workspace: Path, *, project_id: str | None = None, include_disabled: bool = False) -> dict:
    """Read-only derivation; cached index and BRAIN summary never grant authority."""
    require_workspace(workspace)
    workspace = workspace.resolve()
    if project_id is not None:
        project_by_id(workspace, project_id)
    records = list_operation_records(workspace)
    committed = {record["operation_id"]: record for _, record in records}
    preferences = _preferences(records)
    from third_party import installed_source_problem, read_installed_manifest
    sources = read_installed_manifest(workspace)["sources"]
    skills, excluded, unsupported = [], {}, []
    for source_id, entry in sorted(sources.items()):
        problem = installed_source_problem(workspace, source_id, entry)
        if problem:
            excluded[source_id] = problem
            continue
        record = committed.get(entry.get("activation_id"))
        details = record["details"] if record else {}
        if (not record or record["kind"] != "external_activation"
                or set(details) not in ({"source_id", "entry"}, {"source_id", "entry", "archive", "prior_manifest_entry"})
                or details.get("source_id") != source_id or details.get("entry") != entry
                or digest_json(details) != record["payload_digest"]):
            excluded[source_id] = "source has no matching committed activation"
            continue
        root = require_managed_path(workspace, f"external/{source_id}", label="active skill source")
        candidates = []
        try:
            for path in tree_entries(root):
                if path.name != "SKILL.md" or path.is_symlink() or not path.is_file():
                    continue
                relative = path.relative_to(workspace).as_posix()
                with path.open("rb") as handle:
                    text = handle.read(64 * 1024).decode("utf-8")
                fields, error = frontmatter(text)
                name, description = fields.get("name", ""), fields.get("description", "")
                if error or name != path.parent.name or not description:
                    unsupported.append({"source_id": source_id, "path": relative,
                                        "reason": error or "skill name/description cannot be indexed"})
                    continue
                source_path = path.relative_to(root).as_posix()
                skill_id = source_id + ":" + source_path
                preference = preferences.get(skill_id, {"enabled": True, "projects": {}})
                enabled = preference["projects"].get(project_id, preference["enabled"])
                qualified_name = source_id + ":" + name + "@" + hashlib.sha256(source_path.encode()).hexdigest()[:8]
                candidates.append({"skill_id": skill_id, "name": name, "display_name": qualified_name,
                                   "description": " ".join(description.split()), "source_id": source_id,
                                   "reviewed_ref": entry["source_ref"], "tree_digest": entry["tree_digest"],
                                   "verdict": entry["scan_verdict"],
                                   "effective_verdict": entry.get("effective_verdict", entry["scan_verdict"]),
                                   "path": relative, "enabled": enabled,
                                   "project_scopes": dict(preference["projects"])})
            if tree_digest(root) != entry["tree_digest"]:
                excluded[source_id] = "source changed during skill indexing"
                continue
        except (OSError, UnicodeError, StateError) as error:
            excluded[source_id] = "source could not be indexed: " + str(error)
            continue
        skills.extend(item for item in candidates if include_disabled or item["enabled"])
    return {"format": FORMAT, "version": VERSION,
            "revision": records[-1][1]["revision"] if records else 0,
            "skills": sorted(skills, key=lambda item: item["skill_id"]),
            "excluded_sources": excluded, "unsupported_skills": unsupported}


def refresh_index_views(workspace: Path) -> dict:
    """Called only inside the authoritative writer lock after ledger commitment."""
    index = list_skills(workspace, include_disabled=True)
    path = require_managed_path(workspace, "state/skills_index.json", label="skill index")
    durable_write_json(path, index)
    brain = require_workspace(workspace)
    integrations = brain.setdefault("optional_integrations", {})
    if not isinstance(integrations, dict):
        raise StateError("optional integrations must be an object before updating the skill summary")
    integrations["skills"] = [{key: item[key] for key in
                               ("skill_id", "name", "source_id", "path", "enabled", "project_scopes")}
                              for item in index["skills"]]
    durable_write_json(require_managed_path(workspace, "BRAIN.json", label="skill compatibility summary"), brain)
    return index


def _control(workspace: Path, skill_id: str | None, enabled: bool | None,
             project_id: str | None, session_id: str | None) -> dict:
    with writer_lock(workspace) as head:
        session = require_operation_authority(workspace, "wrap_up", session_id=session_id,
                                              project_id=project_id, committed_revision=head["revision"])
        for filename in ("pending_wrap_up.json", "pending_checkpoint.json"):
            if require_managed_path(workspace, "state/" + filename, label="pending writer operation").exists():
                raise StateError("recover the pending operation before changing skills")
        current = list_skills(workspace, project_id=project_id, include_disabled=True)
        if skill_id is None:
            request = {"action": "refresh", "skill_id": None, "enabled": None,
                       "project_id": None, "tree_digest": None}
        else:
            item = next((s for s in current["skills"] if s["skill_id"] == skill_id), None)
            if not item:
                raise StateError("skill is unavailable or not bound to a reviewed active source")
            request = {"action": "set_enabled", "skill_id": skill_id, "enabled": enabled,
                       "project_id": project_id, "tree_digest": item["tree_digest"]}
        _request(request)
        operation_id = "skills-" + uuid.uuid4().hex
        path, record = commit_operation(workspace, operation_id=operation_id, kind=KIND,
                                        payload_digest=digest_json(request), details={"request": request},
                                        target_revision=head["revision"] + 1)
        advance_store_head(workspace, path, record)
        advance_session_revision(workspace, session, record["revision"])
        refresh_index_views(workspace)
        from operation_receipt import receipt_for_operation
        return receipt_for_operation(workspace, operation_id, expected_kind=KIND)


def set_enabled(workspace: Path, skill_id: str, enabled: bool, *, project_id: str | None = None,
                session_id: str | None = None) -> dict:
    return _control(workspace, skill_id, enabled, project_id, session_id)


def rebuild_index(workspace: Path, *, session_id: str | None = None) -> dict:
    return _control(workspace, None, None, None, session_id)


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover verified skills or change revisioned preferences.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("list", "refresh", "enable", "disable"):
        command = commands.add_parser(name)
        command.add_argument("--workspace", required=True)
        command.add_argument("--session-id")
        if name in ("enable", "disable"):
            command.add_argument("skill_id")
        if name != "refresh":
            command.add_argument("--project-id")
        if name == "list":
            command.add_argument("--include-disabled", action="store_true")
    args = parser.parse_args()
    try:
        workspace = Path(args.workspace).expanduser().resolve()
        if args.command == "list":
            result = list_skills(workspace, project_id=args.project_id, include_disabled=args.include_disabled)
        elif args.command == "refresh":
            result = rebuild_index(workspace, session_id=args.session_id)
        else:
            result = set_enabled(workspace, args.skill_id, args.command == "enable",
                                 project_id=args.project_id, session_id=args.session_id)
        print(json.dumps(result, sort_keys=True, ensure_ascii=True))
        return 0
    except (StateError, OSError, ValueError) as error:
        print("SKILLS ERROR: " + json.dumps(str(error), ensure_ascii=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
