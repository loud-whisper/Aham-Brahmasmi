#!/usr/bin/env python3
"""Third-party registry and safe source-installation helpers."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from state_io import StateError, atomic_write_json, require_managed_path, require_workspace
from external_identity import freeze_tree, report_digest, tree_digest
from session_authority import advance_session_revision, require_operation_authority
from state_store import advance_store_head, commit_operation, digest_json, find_operation, reconcile_store, writer_lock


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "third_party" / "registry.json"
SOURCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
ALLOWED_KINDS = {"skill-collection", "semantic-memory", "tool", "adapter-source"}
ALLOWED_INTEGRATIONS = {"link", "installer", "adapter"}
ALLOWED_REVIEW_STATUSES = {"approved", "review-required", "disabled"}
ALLOWED_ACTIVATION = {"manual", "workspace_external", "runtime_adapter"}
GIT_TIMEOUT_SECONDS = 120
PENDING_ACTIVATION_FORMAT = "aham-brahmasmi-pending-external-activation"
PENDING_ACTIVATION_VERSION = 4
REQUIRED_FIELDS = {
    "id",
    "name",
    "kind",
    "upstream_url",
    "source_type",
    "source_ref",
    "license",
    "license_url",
    "integration",
    "local_changes",
    "checked_at",
    "review_status",
    "role",
    "default_offer",
    "activation",
    "attribution",
    "notes",
}
OPTIONAL_FIELDS = {"local_adaptation", "scanner_adapter", "expected_scan"}


class ThirdPartyError(StateError):
    """Raised when an external source cannot be safely processed."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def validate_registry(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("version") != 1:
        errors.append("registry version must be 1")
    if data.get("policy") != "link-upstream":
        errors.append("registry policy must be 'link-upstream'")
    sources = data.get("sources")
    if not isinstance(sources, list):
        return errors + ["registry sources must be a list"]

    seen: set[str] = set()
    for index, source in enumerate(sources):
        label = f"source #{index + 1}"
        if not isinstance(source, dict):
            errors.append(f"{label} must be an object")
            continue
        missing = REQUIRED_FIELDS - set(source)
        extra = set(source) - REQUIRED_FIELDS - OPTIONAL_FIELDS
        if missing:
            errors.append(f"{label} missing fields: {', '.join(sorted(missing))}")
        if extra:
            errors.append(f"{label} has unrecognized fields: {', '.join(sorted(extra))}")
        if missing:
            continue

        source_id = source["id"]
        if not isinstance(source_id, str) or not SOURCE_ID_RE.fullmatch(source_id):
            errors.append(f"{label} has invalid id")
        elif source_id in seen:
            errors.append(f"duplicate source id: {source_id}")
        else:
            seen.add(source_id)

        for field in ("name", "license", "role", "attribution"):
            if not isinstance(source[field], str) or not source[field].strip():
                errors.append(f"{label} field '{field}' must be a non-empty string")

        for field in ("upstream_url", "license_url"):
            parsed = urlparse(str(source[field]))
            if parsed.scheme != "https" or not parsed.netloc:
                errors.append(f"{label} field '{field}' must be a public HTTPS URL")

        if source["source_type"] != "git_commit":
            errors.append(f"{label} source_type must be 'git_commit'")
        if not isinstance(source["source_ref"], str) or not COMMIT_RE.fullmatch(source["source_ref"]):
            errors.append(f"{label} source_ref must be a 40-character lowercase Git commit")
        if source["kind"] not in ALLOWED_KINDS:
            errors.append(f"{label} has unsupported kind")
        if source["integration"] not in ALLOWED_INTEGRATIONS:
            errors.append(f"{label} has unsupported integration")
        if source["review_status"] not in ALLOWED_REVIEW_STATUSES:
            errors.append(f"{label} has unsupported review status")
        if source["activation"] not in ALLOWED_ACTIVATION:
            errors.append(f"{label} has unsupported activation mode")
        if not isinstance(source["local_changes"], bool):
            errors.append(f"{label} local_changes must be boolean")
        if not isinstance(source["default_offer"], bool):
            errors.append(f"{label} default_offer must be boolean")
        if not isinstance(source["checked_at"], str) or not DATE_RE.fullmatch(source["checked_at"]):
            errors.append(f"{label} checked_at must use YYYY-MM-DD")
        if not isinstance(source["notes"], str):
            errors.append(f"{label} notes must be a string")

        adaptation = source.get("local_adaptation")
        if source["local_changes"]:
            if not isinstance(adaptation, dict):
                errors.append(f"{label} local_changes requires local_adaptation metadata")
            else:
                required_adaptation = {"based_on_ref", "summary", "changed_paths"}
                if set(adaptation) != required_adaptation:
                    errors.append(f"{label} local_adaptation must contain exactly based_on_ref, summary, changed_paths")
                else:
                    if not COMMIT_RE.fullmatch(str(adaptation["based_on_ref"])):
                        errors.append(f"{label} local_adaptation based_on_ref must be a Git commit")
                    if not isinstance(adaptation["summary"], str) or not adaptation["summary"].strip():
                        errors.append(f"{label} local_adaptation summary must be non-empty")
                    if not isinstance(adaptation["changed_paths"], list) or not all(
                        isinstance(item, str) and item.strip() for item in adaptation["changed_paths"]
                    ):
                        errors.append(f"{label} local_adaptation changed_paths must be a list of paths")
        elif adaptation is not None:
            errors.append(f"{label} local_adaptation is only allowed when local_changes is true")

        if source["default_offer"] and source["review_status"] != "approved":
            errors.append(f"{label} cannot be a default offer unless approved")
        if source["integration"] == "installer" and source["activation"] != "workspace_external":
            errors.append(f"{label} installer sources must activate as workspace_external")
        if "scanner_adapter" in source:
            from scanner_external import validate_adapter
            try:
                validate_adapter(source, require_approved=False)
            except StateError as error:
                errors.append(f"{label}: {error}")
        if "expected_scan" in source:
            expected = source["expected_scan"]
            if (not isinstance(expected, dict) or set(expected) != {"verdict", "tree_digest", "rule_pack_version", "reviewed_at"}
                    or not isinstance(expected.get("verdict"), str) or expected.get("verdict") not in {"PASS", "REVIEW", "FAIL"}
                    or not re.fullmatch(r"[a-f0-9]{64}", str(expected.get("tree_digest")))
                    or not re.fullmatch(r"1:[a-f0-9]{64}", str(expected.get("rule_pack_version")))
                    or not DATE_RE.fullmatch(str(expected.get("reviewed_at")))):
                errors.append(f"{label} expected_scan has an invalid reviewed scan identity")
            elif source["default_offer"] and expected["verdict"] == "FAIL":
                errors.append(f"{label} a FAIL source cannot be a default offer")

    return errors


def load_registry(path: Path = REGISTRY) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ThirdPartyError(f"could not read third-party registry: {exc}") from exc
    if not isinstance(data, dict):
        raise ThirdPartyError("third-party registry must contain a JSON object")
    errors = validate_registry(data)
    if errors:
        raise ThirdPartyError("; ".join(errors))
    return data


def get_source(source_id: str, registry: dict[str, Any]) -> dict[str, Any]:
    for source in registry["sources"]:
        if source["id"] == source_id:
            return source
    raise ThirdPartyError(f"unknown third-party source: {source_id}")


def run_git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise ThirdPartyError(f"Git command timed out after {GIT_TIMEOUT_SECONDS} seconds") from exc
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "git command failed"
        raise ThirdPartyError(message)
    return result


def fetch_exact_source(
    workspace: Path,
    source: dict[str, Any],
    *,
    fetch_url_override: str | None = None,
) -> tuple[Path, str]:
    require_workspace(workspace)
    if source["review_status"] != "approved":
        raise ThirdPartyError(f"source '{source['id']}' is not approved")
    if source["integration"] != "installer":
        raise ThirdPartyError(f"source '{source['id']}' is not configured for installation")

    quarantine_root = workspace / "state" / "quarantine"
    quarantine_root.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex[:10]
    quarantine = quarantine_root / f"{source['id']}-{token}"
    repo = quarantine / "source"
    quarantine.mkdir(parents=True)

    fetch_url = fetch_url_override or source["upstream_url"]
    try:
        run_git("init", "--quiet", str(repo))
        run_git("-C", str(repo), "remote", "add", "origin", fetch_url)
        run_git("-C", str(repo), "fetch", "--quiet", "--depth", "1", "origin", source["source_ref"])
        run_git("-C", str(repo), "checkout", "--quiet", "--detach", "FETCH_HEAD")
        head = run_git("-C", str(repo), "rev-parse", "HEAD").stdout.strip()
        if head != source["source_ref"]:
            raise ThirdPartyError(
                f"fetched source mismatch for {source['id']}: expected {source['source_ref']}, got {head}"
            )
        atomic_write_json(
            quarantine / "provenance.json",
            {
                "format": "aham-brahmasmi-quarantine",
                "version": 1,
                "source_id": source["id"],
                "upstream_url": source["upstream_url"],
                "source_ref": source["source_ref"],
                "license": source["license"],
                "fetched_at": utc_now(),
                "verified_head": head,
            },
        )
    except Exception:
        atomic_write_json(
            quarantine / "fetch_failure.json",
            {
                "format": "aham-brahmasmi-fetch-failure",
                "version": 1,
                "source_id": source["id"],
                "failed_at": utc_now(),
            },
        )
        raise
    return quarantine, head


def read_installed_manifest(workspace: Path) -> dict[str, Any]:
    path = workspace / "state" / "installed_sources.json"
    if not path.exists():
        return {"format": "aham-brahmasmi-installed-sources", "version": 1, "sources": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ThirdPartyError(f"installed source manifest is unreadable: {exc}") from exc
    if not isinstance(data, dict) or data.get("format") != "aham-brahmasmi-installed-sources":
        raise ThirdPartyError("installed source manifest has an unrecognized format")
    if data.get("version") != 1 or not isinstance(data.get("sources"), dict):
        raise ThirdPartyError("installed source manifest has an unsupported structure")
    return data


def pending_activation_path(workspace: Path) -> Path:
    return require_managed_path(
        workspace,
        "state/pending_external_activation.json",
        label="pending external activation",
    )


def _relative_managed(workspace: Path, path: Path, *, label: str) -> str:
    managed = require_managed_path(workspace, path, label=label)
    return managed.relative_to(workspace.resolve()).as_posix()


def _validate_pending_activation(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ThirdPartyError("pending external activation must be a JSON object")
    required = {
        "format",
        "version",
        "source_id",
        "source_ref",
        "quarantine",
        "destination",
        "backup",
        "prior_manifest_entry",
        "created_at",
    }
    if value.get("version") in {2, 3, 4}:
        required.add("activation_id")
        if not isinstance(value.get("activation_id"), str) or not re.fullmatch(r"[a-f0-9]{32}", value["activation_id"]):
            raise ThirdPartyError("pending external activation has an invalid activation identity")
    if value.get("version") == 4:
        required.update({"action", "source_type"})
        if value.get("action") not in {"activate", "deactivate"} or value.get("source_type") not in {"git_commit", "local_digest"}:
            raise ThirdPartyError("pending external lifecycle action/type is invalid")
    if value.get("version") in {3, 4}:
        required.update({"entry", "base_revision"})
        entry = value.get("entry")
        deactivating = value.get("action") == "deactivate"
        if (not isinstance(entry, dict) or (not deactivating and entry.get("activation_id") != value["activation_id"])
                or entry.get("source_ref") != value.get("source_ref")):
            raise ThirdPartyError("pending activation content identity is invalid")
        if deactivating and (entry != value.get("prior_manifest_entry") or not value.get("backup")):
            raise ThirdPartyError("pending deactivation has no prior entry/archive")
        if value["version"] == 4 and entry.get("source_type", "git_commit") != value["source_type"]:
            raise ThirdPartyError("pending lifecycle source type conflicts with its entry")
        if type(value.get("base_revision")) is not int or value["base_revision"] < 0:
            raise ThirdPartyError("pending activation base revision is invalid")
    if set(value) != required:
        raise ThirdPartyError("pending external activation has an unrecognized structure")
    if value.get("format") != PENDING_ACTIVATION_FORMAT or value.get("version") not in {1, 2, 3, 4}:
        raise ThirdPartyError("pending external activation format/version is not recognized")
    if not isinstance(value.get("source_id"), str) or not SOURCE_ID_RE.fullmatch(value["source_id"]):
        raise ThirdPartyError("pending external activation has an invalid source id")
    ref_pattern = re.compile(r"[a-f0-9]{64}") if value.get("source_type") == "local_digest" else COMMIT_RE
    if not isinstance(value.get("source_ref"), str) or not ref_pattern.fullmatch(value["source_ref"]):
        raise ThirdPartyError("pending external activation has an invalid source ref")
    for field in ("quarantine", "destination"):
        if not isinstance(value.get(field), str) or not value[field]:
            raise ThirdPartyError(f"pending external activation has an invalid {field} path")
    backup = value.get("backup")
    if backup is not None and (not isinstance(backup, str) or not backup):
        raise ThirdPartyError("pending external activation has an invalid backup path")
    prior = value.get("prior_manifest_entry")
    if prior is not None and not isinstance(prior, dict):
        raise ThirdPartyError("pending external activation prior manifest entry is invalid")
    if not isinstance(value.get("created_at"), str) or not value["created_at"]:
        raise ThirdPartyError("pending external activation has no creation timestamp")
    return value


def test_crash_point(name: str) -> None:
    if (
        os.environ.get("AHAM_BRAHMASMI_TEST_MODE") == "1"
        and os.environ.get("AHAM_BRAHMASMI_TEST_CRASH_POINT") == name
    ):
        raise SystemExit(86)


def move_source_tree(source: Path, destination: Path) -> None:
    # Moving between parents can require updating the directory's parent entry.
    # Only its root needs a temporary owner write bit; contained files stay frozen.
    mode = source.stat().st_mode
    if os.name == "posix":
        source.chmod(mode | 0o200)
    moved = False
    try:
        os.replace(source, destination)
        moved = True
    finally:
        if os.name == "posix":
            (destination if moved else source).chmod(mode)


def recover_external_activation(workspace: Path, *, session_id: str | None = None) -> str:
    require_workspace(workspace)
    if not pending_activation_path(workspace).exists():
        return "none"
    with writer_lock(workspace, allow_external_pending=True):
        return _recover_external_activation(workspace, session_id=session_id)


def _finish_activation(workspace: Path, pending: dict[str, Any], session_id: str | None) -> None:
    session = require_operation_authority(workspace, "wrap_up", session_id=session_id)
    entry = pending["entry"]
    source_id = pending["source_id"]
    if read_installed_manifest(workspace)["sources"].get(source_id) != entry:
        raise ThirdPartyError("activation manifest does not match its pending reviewed identity")
    reason = installed_source_problem(workspace, source_id, entry)
    if reason:
        raise ThirdPartyError(reason)
    operation_id = pending["activation_id"]
    details = {"source_id": source_id, "entry": entry}
    if pending["version"] >= 4 and pending.get("backup"):
        details.update(archive=pending["backup"], prior_manifest_entry=pending["prior_manifest_entry"])
    digest = digest_json(details)
    found = find_operation(workspace, operation_id)
    if found:
        path, record = found
        if record["kind"] != "external_activation" or record["payload_digest"] != digest:
            raise ThirdPartyError("activation operation identity conflicts with the immutable ledger")
    else:
        path, record = commit_operation(workspace, operation_id=operation_id, kind="external_activation",
                                        payload_digest=digest, details=details,
                                        target_revision=pending["base_revision"] + 1)
    test_crash_point("external_activation_after_operation_record")
    advance_store_head(workspace, path, record)
    if pending.get("backup") and pending.get("prior_manifest_entry"):
        from skills_lifecycle import _write_archive
        _write_archive(workspace, pending["source_id"], pending["prior_manifest_entry"],
                       pending["backup"], pending["activation_id"])
    from skills_index import refresh_index_views
    refresh_index_views(workspace)
    advance_session_revision(workspace, session, record["revision"])


def _recover_external_activation(workspace: Path, *, session_id: str | None = None) -> str:
    """Recover an interrupted activation to the state represented by its durable manifest."""
    require_workspace(workspace)
    pending_path = pending_activation_path(workspace)
    if not pending_path.exists():
        return "none"
    try:
        pending = _validate_pending_activation(json.loads(pending_path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        raise ThirdPartyError(f"pending external activation is unreadable: {exc}") from exc

    source_id = pending["source_id"]
    if pending.get("action") == "deactivate":
        from skills_lifecycle import _recover_deactivation
        return _recover_deactivation(workspace, pending, session_id)
    quarantine = require_managed_path(workspace, pending["quarantine"], label="external activation quarantine")
    source_tree = require_managed_path(workspace, quarantine / "source", label="external activation source tree")
    destination = require_managed_path(workspace, pending["destination"], label="external activation destination")
    backup = (
        require_managed_path(workspace, pending["backup"], label="external activation backup")
        if pending["backup"] is not None
        else None
    )

    manifest = read_installed_manifest(workspace)
    current = manifest["sources"].get(source_id)
    if pending["version"] in {3, 4}:
        require_operation_authority(workspace, "wrap_up", session_id=session_id)
    committed = (isinstance(current, dict) and current.get("source_ref") == pending["source_ref"]
                 and (pending["version"] == 1 or current.get("activation_id") == pending["activation_id"]))
    if committed:
        if not destination.is_dir():
            raise ThirdPartyError(
                "external activation manifest records the new source but the active destination is missing; manual recovery is required"
            )
        if pending["version"] in {3, 4}:
            _finish_activation(workspace, pending, session_id)
        pending_path.unlink(missing_ok=True)
        return "committed"

    prior = pending["prior_manifest_entry"]
    if current != prior:
        raise ThirdPartyError(
            "external activation manifest no longer matches either the prior or pending source; refusing ambiguous recovery"
        )

    # If both trees are already in their pre-activation locations and the backup move
    # never happened (or a previous recovery completed), only the stale journal remains.
    if source_tree.exists() and destination.exists() and (backup is None or not backup.exists()):
        pending_path.unlink(missing_ok=True)
        return "rolled_back"
    if source_tree.exists() and not destination.exists() and backup is None:
        pending_path.unlink(missing_ok=True)
        return "rolled_back"

    # If the new tree reached the active destination, move it back to quarantine first.
    if destination.exists() and not source_tree.exists():
        source_tree.parent.mkdir(parents=True, exist_ok=True)
        move_source_tree(destination, source_tree)

    # Restore the previous active tree when replacement had already moved it aside.
    if backup is not None and backup.exists():
        if destination.exists():
            raise ThirdPartyError("external activation recovery found an unexpected occupied destination")
        move_source_tree(backup, destination)

    if backup is not None and prior is not None and not destination.exists():
        raise ThirdPartyError("external activation recovery could not restore the previous active source")
    if not source_tree.exists():
        raise ThirdPartyError("external activation recovery could not restore the quarantined candidate")

    pending_path.unlink(missing_ok=True)
    return "rolled_back"


def activate_source(
    workspace: Path,
    source: dict[str, Any],
    quarantine: Path,
    scan_report: dict[str, Any],
    *,
    replace: bool = False,
    session_id: str | None = None,
    receipt_out: dict[str, Any] | None = None,
    expected_activation_id: str | None = None,
) -> Path:
    with writer_lock(workspace, allow_external_pending=True):
        for filename in ("pending_wrap_up.json", "pending_checkpoint.json"):
            if require_managed_path(workspace, "state/" + filename, label="pending writer operation").exists():
                raise ThirdPartyError("another Brain operation is pending; recover it before activation")
        result = _activate_source(workspace, source, quarantine, scan_report, replace=replace, session_id=session_id,
                                  expected_activation_id=expected_activation_id)
        if receipt_out is not None:
            from operation_receipt import receipt_for_operation
            entry = read_installed_manifest(workspace)["sources"][source["id"]]
            receipt_out.update(receipt_for_operation(workspace, entry["activation_id"], expected_kind="external_activation"))
        return result


def _activate_source(workspace: Path, source: dict[str, Any], quarantine: Path,
                     scan_report: dict[str, Any], *, replace: bool, session_id: str | None,
                     expected_activation_id: str | None = None) -> Path:
    require_workspace(workspace)
    _recover_external_activation(workspace, session_id=session_id)
    repo = require_managed_path(workspace, quarantine / "source", label="quarantined source directory")
    if not repo.is_dir():
        raise ThirdPartyError("quarantined source directory is missing")
    expected_digest = scan_report.get("tree_digest")
    if not isinstance(expected_digest, str) or not re.fullmatch(r"[a-f0-9]{64}", expected_digest):
        raise ThirdPartyError("scan report is not bound to reviewed content; scan the candidate again")
    if tree_digest(repo) != expected_digest:
        raise ThirdPartyError("source changed since scanning; refusing activation until reviewed again")
    from skills_review import validated_report
    scan_report = validated_report(workspace, source["id"], repo, scan_report)
    if scan_report["effective_verdict"] not in {"PASS", "PASS-WITH-WAIVER"}:
        raise ThirdPartyError("source cannot be activated without PASS or explicit valid finding acceptance")

    active_root = require_managed_path(workspace, "external", label="external source root")
    active_root.mkdir(parents=True, exist_ok=True)
    destination = require_managed_path(workspace, active_root / source["id"], label="external source destination")
    manifest = read_installed_manifest(workspace)
    current = manifest["sources"].get(source["id"])
    if expected_activation_id is not None and (not current or current.get("activation_id") != expected_activation_id):
        raise ThirdPartyError("active source changed while the candidate was prepared; review the current installation again")
    if current and current.get("source_ref") == source["source_ref"] and destination.is_dir() and not replace:
        reason = installed_source_problem(workspace, source["id"], current)
        if reason:
            raise ThirdPartyError(reason)
        return destination
    if destination.exists() and not replace:
        raise ThirdPartyError(
            f"source '{source['id']}' is already installed; use an explicit replacement after reviewing the new source"
        )

    head = reconcile_store(workspace)
    require_operation_authority(workspace, "wrap_up", session_id=session_id, committed_revision=head["revision"])

    backup: Path | None = None
    if destination.exists():
        backup_root = require_managed_path(workspace, "state/replaced_sources", label="replaced source archive")
        backup_root.mkdir(parents=True, exist_ok=True)
        backup = require_managed_path(
            workspace,
            backup_root / f"{source['id']}-{uuid.uuid4().hex[:10]}",
            label="replaced source backup",
        )

    activation_id = uuid.uuid4().hex
    entry = {
        "name": source["name"], "upstream_url": source["upstream_url"], "source_ref": source["source_ref"],
        "source_type": source.get("source_type", "git_commit"),
        "license": source["license"], "attribution": source["attribution"], "installed_at": utc_now(),
        "scanner": scan_report.get("scanner"), "scanner_version": scan_report.get("version"),
        "scan_verdict": scan_report.get("verdict"), "tree_digest": expected_digest,
        "effective_verdict": scan_report["effective_verdict"],
        "scan_report_digest": report_digest(scan_report), "scan_report": scan_report, "activation_id": activation_id,
    }
    pending = {
        "format": PENDING_ACTIVATION_FORMAT,
        "version": PENDING_ACTIVATION_VERSION,
        "source_id": source["id"],
        "source_ref": source["source_ref"],
        "quarantine": _relative_managed(workspace, quarantine, label="activation quarantine"),
        "destination": _relative_managed(workspace, destination, label="activation destination"),
        "backup": _relative_managed(workspace, backup, label="activation backup") if backup is not None else None,
        "prior_manifest_entry": current,
        "created_at": utc_now(),
        "activation_id": activation_id,
        "entry": entry,
        "base_revision": head["revision"],
        "action": "activate",
        "source_type": source.get("source_type", "git_commit"),
    }
    if source.get("source_type") == "local_digest":
        if source["source_ref"] != expected_digest or source["upstream_url"] is not None:
            raise ThirdPartyError("local source provenance must bind only the reviewed content digest")
        pending.update(version=4, action="activate", source_type="local_digest")
    pending_path = pending_activation_path(workspace)
    atomic_write_json(pending_path, pending)
    test_crash_point("external_activation_after_pending_record")

    try:
        if destination.exists():
            if backup is None:
                raise ThirdPartyError("replacement destination exists without a recovery backup path")
            move_source_tree(destination, backup)
            test_crash_point("external_activation_after_backup_move")

        move_source_tree(repo, destination)
        test_crash_point("external_activation_after_destination_move")

        freeze_tree(destination)
        if tree_digest(destination) != expected_digest:
            raise ThirdPartyError("source changed during activation; refusing manifest publication")

        manifest["sources"][source["id"]] = entry
        atomic_write_json(workspace / "state" / "installed_sources.json", manifest)
        test_crash_point("external_activation_after_manifest_write")
        _finish_activation(workspace, pending, session_id)
    except Exception:
        _recover_external_activation(workspace, session_id=session_id)
        raise

    pending_path.unlink(missing_ok=True)
    return destination


def installed_source_problem(workspace: Path, source_id: str, entry: Any) -> str | None:
    """Legacy/unbound or changed content is never usable based on its commit alone."""
    if not isinstance(source_id, str) or not SOURCE_ID_RE.fullmatch(source_id):
        return "invalid external source identity: not used until reviewed again"
    if not isinstance(entry, dict):
        return "invalid installed source entry: not used until reviewed again"
    report = entry.get("scan_report")
    digest = entry.get("tree_digest")
    if (not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)
            or not isinstance(report, dict) or report.get("tree_digest") != digest
            or report.get("verdict") not in {"PASS", "REVIEW"}
            or entry.get("scan_verdict") != report.get("verdict")):
        return "source has no bound acceptable review: not used until reviewed again"
    try:
        if report_digest(report) != entry.get("scan_report_digest"):
            return "scan report changed since review: not used until reviewed again"
        active = require_managed_path(workspace, f"external/{source_id}", label="reviewed external source")
        if tree_digest(active) != digest:
            return "source changed since review: not used until reviewed again"
        from scanner_rules import rule_pack_version
        if report.get("rule_pack_version") != rule_pack_version():
            return "scanner rule pack changed since review: not used until reviewed again"
        from skills_review import effective_report
        if effective_report(workspace, source_id, active, report)["effective_verdict"] not in {"PASS", "PASS-WITH-WAIVER"}:
            return "source has unaccepted findings: not used until reviewed again"
    except (StateError, OSError, RuntimeError, ValueError) as exc:
        return f"source identity could not be verified: not used until reviewed again ({exc})"
    return None


def installed_source_status(workspace: Path) -> dict[str, Any]:
    try:
        sources = read_installed_manifest(workspace)["sources"]
        excluded = {source_id: reason for source_id, entry in sources.items()
                    if (reason := installed_source_problem(workspace, source_id, entry))}
    except (StateError, OSError, ValueError):
        return {"status": "unreadable", "count": 0, "excluded": {}, "usable": []}
    usable = sorted(set(sources) - set(excluded))
    return {"status": "review_required" if excluded else "available" if usable else "none",
            "count": len(usable), "usable": usable, "excluded": excluded}


def cleanup_quarantine_if_empty(quarantine: Path) -> None:
    source = quarantine / "source"
    if source.exists():
        return
    for child in quarantine.iterdir():
        if child.name in {"provenance.json", "scan_report.json"}:
            continue
        return
    shutil.rmtree(quarantine, ignore_errors=True)
