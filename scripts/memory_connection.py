"""Optional recall configuration and indexing over verified committed records."""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import uuid

from context_packet import record_scopes
from project_state import project_by_id, load_registry, project_names_from_record, project_ids_from_record
from record_lifecycle import replay_records
from session_authority import advance_session_revision, require_operation_authority
from state_io import StateError, atomic_write_json, require_managed_path, require_workspace
from state_store import (advance_store_head, commit_operation, digest_json, find_operation,
                         list_operation_records, writer_lock)
from wrap_up_core import completed_from_record

KIND = "memory_control"
STAMP = "AHAM_RECORD_JSON:"
PROVIDERS = {"mempalace", "lite"}
WING = re.compile(r"[a-z0-9][a-z0-9_-]{0,127}")
OUTPUT_LIMIT = 128 * 1024


def _workspace(workspace: Path) -> Path:
    require_workspace(workspace)
    return workspace.resolve()


def _request(value: object) -> dict:
    fields = {
        "configure": {"provider", "default_wing", "index_opt_in", "verified_cli"},
        "connect_project": {"project_id", "wing"},
        "set_indexing": {"project_id", "enabled"}, "disable": set(),
        "index_result": {"project_id", "content_revision", "content_digest", "status", "reason"},
    }
    if not isinstance(value, dict) or not isinstance(value.get("action"), str) or value["action"] not in fields:
        raise StateError("invalid recall control request")
    if set(value) != fields[value["action"]] | {"action"}:
        raise StateError("recall control fields do not match the action")
    if value["action"] == "configure":
        if (not isinstance(value["provider"], str) or value["provider"] not in PROVIDERS or type(value["index_opt_in"]) is not bool
                or (value["default_wing"] is not None and (not isinstance(value["default_wing"], str) or not WING.fullmatch(value["default_wing"])))
                or (value["verified_cli"] is not None and (not isinstance(value["verified_cli"], str) or len(value["verified_cli"]) > 256))):
            raise StateError("invalid recall provider configuration")
    if value["action"] == "connect_project" and (value["project_id"] is None or not isinstance(value["wing"], str) or not WING.fullmatch(value["wing"])):
        raise StateError("invalid project recall wing")
    if value["action"] == "set_indexing" and type(value["enabled"]) is not bool:
        raise StateError("index opt-in must be a boolean")
    if "project_id" in value and value["project_id"] is not None and (not isinstance(value["project_id"], str) or not re.fullmatch(r"prj_[a-f0-9]{32}", value["project_id"])):
        raise StateError("invalid recall project identity")
    if value["action"] == "index_result":
        if (value["project_id"] is None or type(value["content_revision"]) is not int or value["content_revision"] < 0
                or not isinstance(value["content_digest"], str) or not re.fullmatch(r"[a-f0-9]{64}", value["content_digest"])
                or not isinstance(value["status"], str) or value["status"] not in {"indexed", "failed"}
                or (value["reason"] is not None and (not isinstance(value["reason"], str) or len(value["reason"]) > 2000))):
            raise StateError("invalid recall index result")
    return value


def _empty() -> dict:
    return {"provider": None, "default_wing": None, "index_opt_in": False,
            "projects": {}, "indexed": {}, "verified_cli": None, "legacy_read_only": False}


def get_configuration(workspace: Path) -> dict:
    workspace = _workspace(workspace)
    records = list_operation_records(workspace)
    config = _empty()
    controls = [record for _, record in records if record["kind"] == KIND]
    if not controls:
        optional = require_workspace(workspace).get("optional_integrations", {})
        legacy = optional.get("semantic_memory") if isinstance(optional, dict) else None
        if legacy is not None:
            if not isinstance(legacy, dict) or legacy.get("provider") not in PROVIDERS:
                raise StateError("legacy recall configuration is unreadable")
            wing = legacy.get("wing")
            if wing is not None and (not isinstance(wing, str) or not wing.strip()):
                raise StateError("legacy recall scope is invalid")
            config.update(provider=legacy["provider"], default_wing=wing,
                          verified_cli=legacy.get("verified_cli"), legacy_read_only=True)
    for record in controls:
        if set(record["details"]) != {"request"}:
            raise StateError("invalid recall control details")
        request = _request(record["details"].get("request"))
        if digest_json(request) != record["payload_digest"]:
            raise StateError("recall control conflicts with its immutable payload digest")
        action = request["action"]
        if action == "configure":
            config.update(provider=request["provider"], default_wing=request["default_wing"],
                          index_opt_in=request["index_opt_in"], verified_cli=request["verified_cli"],
                          legacy_read_only=False, indexed={})
            for project in config["projects"].values():
                project.pop("index_opt_in", None)
        elif action == "disable":
            config = _empty()
        elif action == "connect_project":
            saved = config["projects"].setdefault(request["project_id"], {})
            if saved.get("wing") != request["wing"]:
                config["indexed"].pop(request["project_id"], None)
            saved["wing"] = request["wing"]
        elif action == "set_indexing":
            if request["project_id"] is None:
                config["index_opt_in"] = request["enabled"]
            else:
                config["projects"].setdefault(request["project_id"], {})["index_opt_in"] = request["enabled"]
        elif action == "index_result":
            saved = config["indexed"].setdefault(request["project_id"], {"indexed_revision": 0, "content_digest": None})
            saved.update(attempt_revision=request["content_revision"], status=request["status"], reason=request["reason"])
            if request["status"] == "indexed":
                saved.update(indexed_revision=request["content_revision"], content_digest=request["content_digest"])
    config["revision"] = records[-1][1]["revision"] if records else 0
    return config


def _materialize(workspace: Path) -> None:
    config = get_configuration(workspace)
    brain = require_workspace(workspace)
    value = None if config["provider"] is None else {
        "provider": config["provider"], "verified_cli": config["verified_cli"],
        "index_opt_in": config["index_opt_in"], "projects": config["projects"],
        "indexed": config["indexed"], "revision": config["revision"]}
    if value is not None and config["default_wing"]:
        value["wing"] = config["default_wing"]
    brain["optional_integrations"]["semantic_memory"] = value
    atomic_write_json(require_managed_path(workspace, "BRAIN.json", label="recall configuration view"), brain)


def _control(workspace: Path, request: dict, *, session_id=None, verifier=None) -> dict:
    workspace = _workspace(workspace)
    _request(request)
    with writer_lock(workspace) as head:
        project_id = request.get("project_id")
        if project_id:
            project_by_id(workspace, project_id)
        session = require_operation_authority(workspace, "wrap_up", session_id=session_id,
                                              project_id=project_id, committed_revision=head["revision"])
        for name in ("pending_wrap_up.json", "pending_checkpoint.json"):
            if require_managed_path(workspace, "state/" + name, label="pending writer operation").exists():
                raise StateError("recover the pending operation before changing recall configuration")
        if request["action"] == "connect_project":
            config = get_configuration(workspace)
            if config["provider"] is None:
                raise StateError("configure a recall provider before connecting a project")
            if any(other != project_id and value.get("wing", other) == request["wing"]
                   for other in load_registry(workspace)["projects"]
                   for value in [config["projects"].get(other, {})]):
                raise StateError("another project already uses that recall wing")
        if verifier:
            request["verified_cli"] = verifier()
            _request(request)
        return _commit_control(workspace, request, head, session)


def _commit_control(workspace, request, head, session):
    operation_id = "memory-control-" + uuid.uuid4().hex
    path, record = commit_operation(workspace, operation_id=operation_id, kind=KIND,
                                    payload_digest=digest_json(request), details={"request": request},
                                    target_revision=head["revision"] + 1)
    advance_store_head(workspace, path, record)
    advance_session_revision(workspace, session, record["revision"])
    _materialize(workspace)
    from operation_receipt import receipt_for_operation
    return receipt_for_operation(workspace, operation_id, expected_kind=KIND)

def _runner(runner=None):
    if runner is not None:
        return runner
    from semantic_memory import run_provider
    return run_provider


def configure_provider(workspace: Path, *, provider="mempalace", default_wing=None,
                       index_opt_in=False, session_id=None, runner=None) -> dict:
    verifier = None
    if provider == "mempalace":
        def verifier():
            run = _runner(runner)
            version = run("--version", timeout=10).stdout.strip()
            run("status")
            if not version or len(version) > 256:
                raise StateError("provider version output is empty or too long")
            return version
    return _control(workspace, {"action": "configure", "provider": provider, "default_wing": default_wing,
                               "index_opt_in": index_opt_in, "verified_cli": None},
                    session_id=session_id, verifier=verifier)


def connect_project(workspace: Path, project_id: str, *, wing=None, session_id=None) -> dict:
    return _control(workspace, {"action": "connect_project", "project_id": project_id, "wing": wing or project_id}, session_id=session_id)


def set_indexing(workspace: Path, enabled: bool, *, project_id=None, session_id=None) -> dict:
    return _control(workspace, {"action": "set_indexing", "project_id": project_id, "enabled": enabled}, session_id=session_id)


def disable_provider(workspace: Path, *, session_id=None) -> dict:
    return _control(workspace, {"action": "disable"}, session_id=session_id)


def repair_configuration(workspace: Path, *, session_id=None) -> dict:
    workspace = _workspace(workspace)
    with writer_lock(workspace) as head:
        require_operation_authority(workspace, "wrap_up", session_id=session_id,
                                    committed_revision=head["revision"])
        for name in ("pending_wrap_up.json", "pending_checkpoint.json"):
            if require_managed_path(workspace, "state/" + name, label="pending writer operation").exists():
                raise StateError("recover the pending operation before repairing recall configuration")
        config = get_configuration(workspace)
        if config["legacy_read_only"]:
            raise StateError("configure the legacy provider before creating a derived configuration view")
        _materialize(workspace)
        return {"status": "repaired", "revision": head["revision"]}


def project_scope(workspace: Path, project_id: str) -> str:
    project_by_id(workspace, project_id)
    return get_configuration(workspace)["projects"].get(project_id, {}).get("wing", project_id)


def catalog(workspace: Path, *, project_id=None, all_scopes=False) -> dict:
    workspace = _workspace(workspace)
    if project_id:
        project_by_id(workspace, project_id)
    if not project_id and not all_scopes:
        raise StateError("recall catalog requires an explicit project or all-scopes choice")
    records = list_operation_records(workspace)
    state = replay_records(records)
    scopes = {record["operation_id"]: project_ids_from_record(workspace, record) for _, record in records}
    fact_scopes, task_scopes = record_scopes(state, scopes)
    rows = []
    workspace_id = require_workspace(workspace)["workspace_id"]
    def add(record_id, kind, text, status, revision, operation_id, projects):
        if not all_scopes and project_id not in projects:
            return
        row = {"record_id": record_id, "workspace_id": workspace_id,
               "project_id": next(iter(projects)) if len(projects) == 1 else None,
               "kind": kind, "text": text, "status": status, "revision": revision, "operation_id": operation_id}
        row["binding_digest"] = digest_json(row)
        rows.append(row)
    for _, record in records:
        if record["kind"] == "wrap_up":
            completed_from_record(record)  # Verify canonical bundle and receipt payload before use.
    for kind, group, id_key, text_key, binding in (
            ("fact", state["facts"], "fact_id", "statement", fact_scopes),
            ("task", state["tasks"], "task_id", "description", task_scopes)):
        for item in group:
            add(item[id_key], kind, item[text_key], item["status"],
                max(event["revision"] for event in item["events"]), item["provenance"]["operation_id"],
                binding.get(item[id_key], set()))
    for _, record in records:
        if record["kind"] != "wrap_up":
            continue
        bundle = completed_from_record(record)["bundle"]
        projects = scopes[record["operation_id"]]
        for index, text in enumerate(bundle["reusable_lessons"]):
            identity = "lesson_" + digest_json([record["operation_id"], index, text])[:32]
            add(identity, "lesson", text, "active", record["revision"], record["operation_id"],
                set(projects) if len(projects) == 1 else set())
        for index, update in enumerate(bundle["project_updates"]):
            bindings = dict(zip(project_names_from_record(record), project_ids_from_record(workspace, record)))
            pid = bindings.get(update["project"])
            if pid not in projects:
                continue
            identity = "update_" + digest_json([record["operation_id"], index, update])[:32]
            add(identity, "project_update", update["content"], "active", record["revision"], record["operation_id"], {pid})
    return {"format": "aham-recall-catalog", "version": 1,
            "content_revision": max((row["revision"] for row in rows), default=0),
            "records": sorted(rows, key=lambda row: row["record_id"])}


def stamp_record(record: dict) -> str:
    return STAMP + " " + json.dumps(record, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def lite_search(workspace: Path, query: str, *, project_id=None, all_scopes=False, results=5) -> dict:
    if type(results) is not int or not 1 <= results <= 50:
        raise StateError("recall results must be within 1-50")
    words = set(re.findall(r"\w+", query.casefold()))
    if not words:
        raise StateError("keyword recall requires a nonempty query")
    source = catalog(workspace, project_id=project_id, all_scopes=all_scopes)
    scored = [(len(words & set(re.findall(r"\w+", row["text"].casefold()))), row)
              for row in source["records"] if row["status"] in {"active", "open"}]
    matches = [dict(row, verification="matched_current") for score, row in
               sorted(scored, key=lambda item: (-item[0], item[1]["record_id"])) if score > 0][:results]
    return {"format": "aham-recall-envelope", "version": 1, "provider": "lite", "project_id": project_id,
            "all_scopes": all_scopes, "records": matches, "content_revision": source["content_revision"],
            "instruction_authority": False}


def recall_envelope(workspace: Path, text: str, *, project_id=None, all_scopes=False) -> dict:
    if len(text.encode("utf-8")) > OUTPUT_LIMIT:
        raise StateError("provider recall exceeds the bounded output limit")
    if project_id:
        project_by_id(workspace, project_id)
    if not project_id and not all_scopes:
        raise StateError("recall mapping requires an explicit project or all-scopes choice")
    known = {row["record_id"]: row for row in catalog(workspace, all_scopes=True)["records"]}
    allowed = {identity: row for identity, row in known.items() if all_scopes or row["project_id"] == project_id}
    matches, remaining = [], []
    for line in text.splitlines():
        if not line.startswith(STAMP):
            remaining.append(line)
            continue
        try:
            row = json.loads(line[len(STAMP):].strip())
        except (ValueError, TypeError):
            remaining.append(line)
            continue
        if not isinstance(row, dict) or not isinstance(row.get("record_id"), str):
            remaining.append(line)
            continue
        identity = row["record_id"]
        if identity in known and identity not in allowed:
            remaining.append("[out-of-scope record omitted]")
        elif row == allowed.get(identity):
            current = allowed[identity]
            matches.append(dict(current, verification="matched_current" if current["status"] in {"active", "open"} else "stale"))
        else:
            current = allowed.get(identity)
            data = {key: value for key, value in row.items() if key != "binding_digest"}
            if (current and current["status"] not in {"active", "open"}
                    and row.get("binding_digest") == digest_json(data)
                    and all(row.get(key) == current[key] for key in ("workspace_id", "project_id", "kind", "text", "operation_id"))):
                matches.append(dict(current, verification="stale"))
            else:
                matches.append({"verification": "unverified", "record_id": identity})
                remaining.append(line)
    return {"format": "aham-recall-envelope", "version": 1, "provider": "mempalace", "project_id": project_id,
            "all_scopes": all_scopes, "records": matches, "unverified_text": "\n".join(remaining),
            "instruction_authority": False}


def index_status(workspace: Path, project_id: str) -> dict:
    config = get_configuration(workspace)
    current = catalog(workspace, project_id=project_id)
    progress = config["indexed"].get(project_id, {})
    indexed = current["content_revision"] if config["provider"] == "lite" else progress.get("indexed_revision", 0)
    return {"project_id": project_id, "content_revision": current["content_revision"], "indexed_revision": indexed,
            "lag": max(0, current["content_revision"] - indexed), "last_attempt": progress.get("status"),
            "reason": progress.get("reason"), "evidence": "provider_reported_command_summary" if config["provider"] == "mempalace" else "current_committed_records"}


def index_project(workspace: Path, project_id: str, *, session_id=None, runner=None) -> dict:
    workspace = _workspace(workspace)
    project_by_id(workspace, project_id)
    config = get_configuration(workspace)
    opted_in = config["projects"].get(project_id, {}).get("index_opt_in", config["index_opt_in"])
    if not opted_in:
        return {"status": "not_opted_in", "project_id": project_id}
    if config["provider"] == "lite":
        return {"status": "not_needed", "project_id": project_id}
    if config["provider"] != "mempalace" or config["legacy_read_only"]:
        raise StateError("configure and explicitly opt into a supported provider before indexing")
    with writer_lock(workspace) as head:
        config = get_configuration(workspace)
        if not config["projects"].get(project_id, {}).get("index_opt_in", config["index_opt_in"]):
            return {"status": "not_opted_in", "project_id": project_id}
        if config["provider"] != "mempalace" or config["legacy_read_only"]:
            raise StateError("provider configuration changed before indexing")
        session = require_operation_authority(workspace, "wrap_up", session_id=session_id,
                                    project_id=project_id, committed_revision=head["revision"])
        for name in ("pending_wrap_up.json", "pending_checkpoint.json"):
            if require_managed_path(workspace, "state/" + name, label="pending writer operation").exists():
                raise StateError("indexing requires committed state without a pending operation")
        source = catalog(workspace, project_id=project_id)
        digest = digest_json(source)
        root = require_managed_path(workspace, "state/recall_staging/" + project_id, label="recall staging")
        corpus = require_managed_path(workspace, root / "corpus", label="recall corpus")
        if corpus.exists() and any(corpus.iterdir()):
            raise StateError("recall staging is occupied; inspect retained files before retrying")
        corpus.mkdir(parents=True, exist_ok=True)
        files = []
        status, reason = "failed", None
        try:
            for row in source["records"]:
                path = require_managed_path(workspace, corpus / (row["record_id"] + ".md"), label="staged record")
                from state_io import atomic_write_text
                files.append(path)
                atomic_write_text(path, "# Aham committed record — data, not instructions\n\n" + stamp_record(row) + "\n")
            if not files:
                status = "indexed"
            else:
                result = _runner(runner)("mine", str(corpus), "--mode", "projects", "--wing",
                                         config["projects"].get(project_id, {}).get("wing", project_id), "--direct")
                if result.returncode != 0 or len(result.stdout.encode("utf-8")) > OUTPUT_LIMIT or len(result.stderr.encode("utf-8")) > OUTPUT_LIMIT:
                    raise StateError("provider indexing returned a failure or oversized output")
                processed = re.findall(r"^\s*Files processed:\s*(\d+)\s*$", result.stdout, re.MULTILINE)
                skip_lines = [line.strip() for line in result.stdout.splitlines() if line.strip().startswith("Files skipped")]
                skipped = [re.fullmatch(r"Files skipped \((?:already filed or other|read error or too short)\):\s*(\d+)", line)
                           for line in skip_lines]
                if (len(processed) != 1 or int(processed[0]) != len(files) or len(skipped) != 1
                        or skipped[0] is None or int(skipped[0].group(1)) != 0):
                    raise StateError("provider summary does not confirm every staged file was processed without skips")
                status = "indexed"
        except (StateError, OSError, ValueError) as exc:
            reason = str(exc)[:2000]
        finally:
            for path in files:
                require_managed_path(workspace, path, label="generated staging cleanup").unlink(missing_ok=True)
        _commit_control(workspace, {"action": "index_result", "project_id": project_id,
                         "content_revision": source["content_revision"], "content_digest": digest,
                         "status": status, "reason": reason}, head, session)
    return {"status": status, "project_id": project_id, "reason": reason,
            "content_revision": source["content_revision"], "evidence": "provider_reported_command_summary"}


def maybe_index_after_wrapup(workspace: Path, operation_id: str, *, session_id=None, runner=None) -> list:
    workspace = _workspace(workspace)
    found = find_operation(workspace, operation_id)
    if not found or found[1]["kind"] != "wrap_up":
        raise StateError("optional indexing requires a committed wrap-up identity")
    completed_from_record(found[1])
    results = []
    for project_id in project_ids_from_record(workspace, found[1]):
        try:
            results.append(index_project(workspace, project_id, session_id=session_id, runner=runner))
        except (StateError, OSError, ValueError) as exc:
            results.append({"status": "failed", "project_id": project_id, "reason": str(exc)[:2000]})
    return results


def setup_options() -> dict:
    return {"cli_available": shutil.which("mempalace") is not None, "provider_required": False,
            "choices": ["Offline lite recall: no install", "uv tool install mempalace", "pipx install mempalace",
                        "Docker: upstream container instructions", "npx skills add installs a setup skill; it does not install the CLI"],
            "source": "https://github.com/MemPalace/mempalace/blob/f8b9ed1507888cab47c7c7e1d90755f89e0353c4/README.md",
            "automatic_install": False}
