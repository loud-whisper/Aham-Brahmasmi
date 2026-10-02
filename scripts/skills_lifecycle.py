#!/usr/bin/env python3
"""Reviewed updates, archive-preserving removal and local skill quarantine."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import uuid

from external_identity import tree_digest
from operation_receipt import receipt_for_operation
from scan_external import read_bounded_json, scan_tree
from scanner_rules import annotate_diff, finding, verdict
from session_authority import advance_session_revision, require_operation_authority
from skills_index import list_skills, refresh_index_views
from skills_review import effective_report
from state_io import StateError, atomic_write_json, require_managed_path, require_workspace
from state_store import (advance_store_head, commit_operation, digest_json, find_operation,
                         list_operation_records, reconcile_store, writer_lock)
from third_party import (PENDING_ACTIVATION_FORMAT, SOURCE_ID_RE, ThirdPartyError,
                         _recover_external_activation, _relative_managed, activate_source,
                         fetch_exact_source, get_source, load_registry, move_source_tree,
                         pending_activation_path, read_installed_manifest, run_git, test_crash_point, utc_now)


def _workspace(workspace: Path) -> Path:
    require_workspace(workspace)
    return workspace.resolve()


def _prepare(workspace: Path, session_id: str | None) -> None:
    with writer_lock(workspace, allow_external_pending=True):
        require_operation_authority(workspace, "wrap_up", session_id=session_id)
        _recover_external_activation(workspace, session_id=session_id)
        head = reconcile_store(workspace)
        require_operation_authority(workspace, "wrap_up", session_id=session_id, committed_revision=head["revision"])
        for name in ("pending_checkpoint.json", "pending_wrap_up.json"):
            if require_managed_path(workspace, "state/" + name, label="pending writer operation").exists():
                raise StateError("recover the pending writer operation before changing skills")


def _installed(workspace: Path, source_id: str) -> dict:
    if not isinstance(source_id, str) or not SOURCE_ID_RE.fullmatch(source_id):
        raise StateError("invalid source identity")
    entry = read_installed_manifest(workspace)["sources"].get(source_id)
    if not isinstance(entry, dict):
        raise StateError("source is not installed: " + source_id)
    _verify_historical_entry(workspace, source_id, entry)
    return entry


def _verify_historical_entry(workspace: Path, source_id: str, entry: dict) -> None:
    if not isinstance(entry, dict):
        raise StateError("invalid historical source entry")
    found = find_operation(workspace, entry.get("activation_id", ""))
    details = found[1]["details"] if found else {}
    if (not found or found[1]["kind"] != "external_activation"
            or set(details) not in ({"source_id", "entry"}, {"source_id", "entry", "archive", "prior_manifest_entry"})
            or details.get("source_id") != source_id or details.get("entry") != entry
            or found[1]["payload_digest"] != digest_json(details)):
        raise StateError("source has no matching immutable activation record")


def check_updates(workspace: Path, *, registry: dict | None = None) -> dict:
    workspace = _workspace(workspace)
    registry = load_registry() if registry is None else registry
    reviewed = {s["id"]: s for s in registry["sources"]}
    rows = []
    for source_id, entry in sorted(read_installed_manifest(workspace)["sources"].items()):
        if not isinstance(entry, dict):
            raise StateError("installed source entry is unreadable: " + source_id)
        source = reviewed.get(source_id)
        if entry.get("source_type") == "local_digest":
            status = "local"
        elif not source or source.get("review_status") != "approved" or source.get("integration") != "installer":
            status = "unregistered"
        else:
            status = "current" if entry.get("source_ref") == source["source_ref"] else "reviewed_update_available"
        rows.append({"source_id": source_id, "installed_ref": entry.get("source_ref"),
                     "reviewed_ref": source["source_ref"] if source else None, "status": status})
    return {"format": "aham-skill-updates", "version": 1, "network": False, "sources": rows,
            "reviewed_updates": sum(row["status"] == "reviewed_update_available" for row in rows)}


def check_upstream(workspace: Path, *, registry: dict | None = None, announce=print) -> dict:
    workspace = _workspace(workspace)
    registry = load_registry() if registry is None else registry
    announce("Network check: reading upstream HEAD refs only; results are unreviewed and never installed.")
    rows = []
    installed = read_installed_manifest(workspace)["sources"]
    if any(not isinstance(entry, dict) for entry in installed.values()):
        raise StateError("installed source entries are unreadable")
    for source in registry["sources"]:
        if (source["id"] not in installed or installed[source["id"]].get("source_type") == "local_digest"
                or source.get("review_status") != "approved" or source.get("integration") != "installer"):
            continue
        try:
            result = run_git("ls-remote", "--", source["upstream_url"], "HEAD").stdout.strip().splitlines()
            if len(result) != 1:
                raise StateError("upstream did not return exactly one HEAD ref")
            fields = result[0].split()
            import re
            if len(fields) != 2 or fields[1] != "HEAD" or not re.fullmatch(r"[a-f0-9]{40}", fields[0]):
                raise StateError("upstream returned an invalid HEAD ref")
            ref = fields[0]
            rows.append({"source_id": source["id"], "upstream_ref": ref,
                         "status": "reviewed_ref_matches" if ref == source["source_ref"] else "unreviewed_ref_differs"})
        except StateError as exc:
            rows.append({"source_id": source["id"], "status": "unavailable", "reason": str(exc)})
    return {"format": "aham-skill-upstream", "version": 1, "network": True, "sources": rows}


def _check_expected_scan(report: dict, source: dict, *, deterministic: dict | None = None) -> dict:
    expected = source.get("expected_scan")
    if expected:
        actual = {key: (deterministic or report).get(key) for key in ("verdict", "tree_digest", "rule_pack_version")}
        matches = all(actual[key] == expected.get(key) for key in actual)
        report["expected_scan_check"] = {"matches": matches, "expected": expected, "actual": actual}
        if not matches:
            item = finding("provenance.expected_scan", "REVIEW", ".", 0,
                           digest_json({"expected": expected, "actual": actual}),
                           "The current scan differs from the maintainer-reviewed scan identity.",
                           "Investigate content and rule-pack changes before accepting this finding.", "")
            if item not in report["findings"]:
                report["findings"].append(item)
            report["verdict"] = verdict(report["findings"])
    return report


def _scan_candidate(workspace: Path, source: dict, quarantine: Path, previous: dict | None) -> dict:
    report = annotate_diff(_check_expected_scan(scan_tree(quarantine / "source"), source), previous)
    report = effective_report(workspace, source["id"], quarantine / "source", report)
    atomic_write_json(require_managed_path(workspace, quarantine / "scan_report.json", label="candidate report"), report)
    reports = require_managed_path(workspace, "state/scan_reports", label="scan reports")
    reports.mkdir(parents=True, exist_ok=True)
    atomic_write_json(require_managed_path(workspace, reports / (quarantine.name + ".json"), label="retained report"), report)
    return report


def _publish(workspace: Path, source: dict, quarantine: Path, report: dict, *, replace: bool,
             session_id: str | None, expected_activation_id: str | None = None) -> dict:
    result = {"source_id": source["id"], "quarantine": str(quarantine), "report": report}
    if report.get("effective_verdict") not in {"PASS", "PASS-WITH-WAIVER"}:
        return dict(result, status="blocked", review_action="Review exact findings using skills_review.py; FAIL cannot be accepted.")
    receipt = {}
    active = activate_source(workspace, source, quarantine, report, replace=replace, session_id=session_id,
                             receipt_out=receipt, expected_activation_id=expected_activation_id)
    return dict(result, status="active", location=str(active), receipt=receipt)


def update_source(workspace: Path, source_id: str, *, registry: dict | None = None,
                  session_id: str | None = None, fetch_url_override: str | None = None) -> dict:
    workspace = _workspace(workspace)
    _prepare(workspace, session_id)
    old = _installed(workspace, source_id)
    if old.get("source_type") == "local_digest":
        raise StateError("update a local skill using add-local with explicit --replace")
    source = get_source(source_id, load_registry() if registry is None else registry)
    quarantine, _ = fetch_exact_source(workspace, source, fetch_url_override=fetch_url_override)
    report = _scan_candidate(workspace, source, quarantine, old.get("scan_report"))
    from external_sources import verify_quarantine_integrity
    verify_quarantine_integrity(quarantine, source)
    return _publish(workspace, source, quarantine, report, replace=True, session_id=session_id,
                    expected_activation_id=old["activation_id"])


def _write_archive(workspace: Path, source_id: str, entry: dict, archive: str, replaced_by: str) -> None:
    tree = require_managed_path(workspace, archive, label="archived source")
    if tree.parent != (workspace / "state/replaced_sources").resolve() or not tree.is_dir():
        raise StateError("archived source is missing or outside the archive directory")
    value = {"format": "aham-source-archive", "version": 1, "source_id": source_id,
             "entry": entry, "archive": archive, "replaced_by": replaced_by}
    path = require_managed_path(workspace, tree.with_name(tree.name + ".json"), label="archive metadata")
    if path.exists() and read_bounded_json(path, 8 * 1024 * 1024) != value:
        raise StateError("archive metadata conflicts with the committed replacement")
    atomic_write_json(path, value)


def _archives(workspace: Path, source_id: str) -> list[dict]:
    root = require_managed_path(workspace, "state/replaced_sources", label="source archive directory")
    rows = []
    if not root.exists():
        return rows
    for path in root.glob("*.json"):
        path = require_managed_path(workspace, path, label="archive metadata")
        value = read_bounded_json(path, 8 * 1024 * 1024)
        if not isinstance(value, dict) or value.get("source_id") != source_id:
            continue
        if set(value) != {"format", "version", "source_id", "entry", "archive", "replaced_by"} or value["format"] != "aham-source-archive" or value["version"] != 1:
            raise StateError("invalid source archive metadata")
        tree = require_managed_path(workspace, value["archive"], label="archived source")
        if tree.parent != root or path != tree.with_name(tree.name + ".json"):
            raise StateError("archive metadata path binding is invalid")
        _verify_historical_entry(workspace, source_id, value["entry"])
        replaced = find_operation(workspace, value["replaced_by"])
        if not replaced or replaced[1]["kind"] not in {"external_activation", "external_deactivation"} or replaced[1]["details"].get("source_id") != source_id:
            raise StateError("archive has no committed replacement/deactivation")
        details = replaced[1]["details"]
        if digest_json(details) != replaced[1]["payload_digest"]:
            raise StateError("archive replacement payload conflicts with its immutable ledger digest")
        prior_key = "prior_manifest_entry" if replaced[1]["kind"] == "external_activation" else "entry"
        if details.get("archive") != value["archive"] or details.get(prior_key) != value["entry"]:
            raise StateError("archive does not match its immutable replacement binding")
        rows.append(dict(value, replacement_revision=replaced[1]["revision"]))
    return sorted(rows, key=lambda row: row["replacement_revision"], reverse=True)


def _candidate_directory(workspace: Path, source_id: str) -> Path:
    root = require_managed_path(workspace, "state/quarantine", label="quarantine root")
    root.mkdir(parents=True, exist_ok=True)
    candidate = require_managed_path(workspace, root / (source_id + "-" + uuid.uuid4().hex[:10]), label="skill quarantine")
    candidate.mkdir()
    return candidate


def rollback_source(workspace: Path, source_id: str, *, session_id: str | None = None) -> dict:
    workspace = _workspace(workspace)
    _prepare(workspace, session_id)
    current = _installed(workspace, source_id)
    archives = _archives(workspace, source_id)
    if not archives:
        raise StateError("no recorded prior copy is available for rollback")
    archive = archives[0]
    entry = archive["entry"]
    tree = require_managed_path(workspace, archive["archive"], label="rollback archive")
    if tree_digest(tree) != entry["tree_digest"]:
        raise StateError("archive changed since its reviewed activation; rollback refused")
    candidate = _candidate_directory(workspace, source_id)
    shutil.copytree(tree, candidate / "source", symlinks=True)
    source = {key: entry[key] for key in ("name", "upstream_url", "source_ref", "license", "attribution")}
    source.update(id=source_id, source_type=entry.get("source_type", "git_commit"))
    atomic_write_json(candidate / "provenance.json", {"format": "aham-skill-candidate", "version": 1,
                      "mode": "rollback", "source": source, "historical_entry": entry,
                      "expected_activation_id": current["activation_id"]})
    report = _scan_candidate(workspace, source, candidate, current.get("scan_report"))
    return _publish(workspace, source, candidate, report, replace=True, session_id=session_id,
                    expected_activation_id=current["activation_id"])


def add_local(workspace: Path, path: Path, *, source_id: str | None = None,
              replace: bool = False, session_id: str | None = None) -> dict:
    workspace = _workspace(workspace)
    _prepare(workspace, session_id)
    path = path.expanduser().resolve()
    if not path.is_dir() or not (path / "SKILL.md").is_file():
        raise StateError("add-local requires a skill folder containing SKILL.md")
    source_id = source_id or "local-" + path.name
    if not SOURCE_ID_RE.fullmatch(source_id) or not source_id.startswith("local-"):
        raise StateError("local source identity must start with local- and use safe characters")
    existing = read_installed_manifest(workspace)["sources"].get(source_id)
    if existing and (not replace or existing.get("source_type") != "local_digest"):
        raise StateError("local source already exists; use explicit --replace for a local installation")
    tree_digest(path)  # Reject outside links, hardlinks and special entries before copying.
    candidate = _candidate_directory(workspace, source_id)
    target = candidate / "source" / "skills" / path.name
    shutil.copytree(path, target, symlinks=True)
    digest = tree_digest(candidate / "source")
    source = {"id": source_id, "name": path.name, "source_type": "local_digest", "source_ref": digest,
              "upstream_url": None, "license": "User-provided; license not asserted",
              "attribution": "User-provided local skill; no public upstream asserted."}
    expected = existing["activation_id"] if existing else None
    atomic_write_json(candidate / "provenance.json", {"format": "aham-skill-candidate", "version": 1,
                      "mode": "local", "source": source, "historical_entry": None,
                      "expected_activation_id": expected})
    report = _scan_candidate(workspace, source, candidate, (existing or {}).get("scan_report"))
    return _publish(workspace, source, candidate, report, replace=replace, session_id=session_id,
                    expected_activation_id=expected)


def activate_reviewed(workspace: Path, source_id: str, quarantine: Path, *, replace: bool = False,
                      registry: dict | None = None, session_id: str | None = None) -> dict:
    """Activation still requires current, exact finding acceptances; never auto-accept."""
    workspace = _workspace(workspace)
    _prepare(workspace, session_id)
    quarantine = require_managed_path(workspace, quarantine.resolve(), label="reviewed skill candidate")
    root = require_managed_path(workspace, "state/quarantine", label="quarantine root")
    if quarantine.parent != root:
        raise StateError("reviewed candidate must be a direct child of the quarantine directory")
    provenance = read_bounded_json(require_managed_path(workspace, quarantine / "provenance.json",
                                                       label="candidate provenance"), 8 * 1024 * 1024)
    if not isinstance(provenance, dict):
        raise StateError("invalid reviewed skill provenance")
    if provenance.get("format") == "aham-brahmasmi-quarantine":
        source = get_source(source_id, load_registry() if registry is None else registry)
        if source["integration"] != "installer" or source["review_status"] != "approved":
            raise StateError("reviewed activation requires an approved installer source")
        from external_sources import verify_quarantine_integrity
        verify_quarantine_integrity(quarantine, source)
        expected = read_installed_manifest(workspace)["sources"].get(source_id, {}).get("activation_id")
    else:
        if (not isinstance(provenance, dict) or set(provenance) != {"format", "version", "mode", "source", "historical_entry", "expected_activation_id"}
                or provenance["format"] != "aham-skill-candidate" or provenance["version"] != 1
                or provenance["mode"] not in {"local", "rollback"} or not isinstance(provenance["source"], dict)):
            raise StateError("invalid reviewed skill provenance")
        source = provenance["source"]
        if (set(source) != {"id", "name", "source_type", "source_ref", "upstream_url", "license", "attribution"}
                or source.get("id") != source_id or not SOURCE_ID_RE.fullmatch(source_id)
                or not all(isinstance(source[key], str) and source[key] for key in ("name", "source_ref", "license", "attribution"))):
            raise StateError("reviewed candidate source identity does not match")
        if provenance["mode"] == "local":
            if (not source_id.startswith("local-") or source.get("source_type") != "local_digest"
                    or source.get("upstream_url") is not None
                    or source.get("source_ref") != tree_digest(quarantine / "source")):
                raise StateError("local candidate no longer matches its digest-only provenance")
        else:
            entry = provenance["historical_entry"]
            _verify_historical_entry(workspace, source_id, entry)
            expected_source = {key: entry[key] for key in ("name", "upstream_url", "source_ref", "license", "attribution")}
            expected_source.update(id=source_id, source_type=entry.get("source_type", "git_commit"))
            if source != expected_source or tree_digest(quarantine / "source") != entry["tree_digest"]:
                raise StateError("rollback candidate changed since its historical reviewed activation")
        expected = provenance["expected_activation_id"]
        current = read_installed_manifest(workspace)["sources"].get(source_id)
        if (current or {}).get("activation_id") != expected:
            raise StateError("active source changed since this candidate was prepared")
    # Revalidate mandatory findings while retaining every advisory/external finding.
    report = read_bounded_json(require_managed_path(workspace, quarantine / "scan_report.json",
                                                   label="reviewed scan report"), 8 * 1024 * 1024)
    if not isinstance(report, dict):
        raise StateError("invalid reviewed scan report")
    from skills_review import validated_report
    report = validated_report(workspace, source_id, quarantine / "source",
                              _check_expected_scan(report, source, deterministic=scan_tree(quarantine / "source")))
    return _publish(workspace, source, quarantine, report, replace=replace, session_id=session_id,
                    expected_activation_id=expected)


def _finish_deactivation(workspace: Path, pending: dict, session_id: str | None) -> dict:
    session = require_operation_authority(workspace, "wrap_up", session_id=session_id)
    _verify_historical_entry(workspace, pending["source_id"], pending["entry"])
    if pending["source_id"] in read_installed_manifest(workspace)["sources"]:
        raise StateError("pending deactivation does not match the manifest")
    archive = require_managed_path(workspace, pending["backup"], label="deactivated archive")
    if not archive.is_dir():
        raise StateError("deactivated archive is missing")
    details = {"source_id": pending["source_id"], "entry": pending["entry"], "archive": pending["backup"]}
    digest = digest_json(details)
    found = find_operation(workspace, pending["activation_id"])
    if found:
        path, record = found
        if record["kind"] != "external_deactivation" or record["payload_digest"] != digest:
            raise StateError("deactivation identity conflicts with immutable ledger")
    else:
        path, record = commit_operation(workspace, operation_id=pending["activation_id"], kind="external_deactivation",
                                        payload_digest=digest, details=details, target_revision=pending["base_revision"] + 1)
    test_crash_point("external_deactivation_after_operation_record")
    advance_store_head(workspace, path, record)
    _write_archive(workspace, pending["source_id"], pending["entry"], pending["backup"], pending["activation_id"])
    refresh_index_views(workspace)
    advance_session_revision(workspace, session, record["revision"])
    return receipt_for_operation(workspace, pending["activation_id"], expected_kind="external_deactivation")


def _recover_deactivation(workspace: Path, pending: dict, session_id: str | None) -> str:
    workspace = _workspace(workspace)
    require_operation_authority(workspace, "wrap_up", session_id=session_id)
    _verify_historical_entry(workspace, pending["source_id"], pending["entry"])
    destination = require_managed_path(workspace, pending["destination"], label="deactivation destination")
    archive = require_managed_path(workspace, pending["backup"], label="deactivation archive")
    if (destination != workspace / "external" / pending["source_id"]
            or archive.parent != workspace / "state/replaced_sources"):
        raise StateError("deactivation journal paths do not match the managed source/archive layout")
    current = read_installed_manifest(workspace)["sources"].get(pending["source_id"])
    if current is None:
        if destination.exists():
            raise StateError("deactivation manifest conflicts with an occupied active destination")
        _finish_deactivation(workspace, pending, session_id)
        result = "committed"
    elif current == pending["prior_manifest_entry"]:
        if archive.exists():
            if destination.exists():
                raise StateError("deactivation recovery found both active and archived copies")
            move_source_tree(archive, destination)
        if not destination.is_dir():
            raise StateError("deactivation recovery could not restore the prior tree")
        result = "rolled_back"
    else:
        raise StateError("deactivation recovery found an unexpected manifest entry")
    pending_activation_path(workspace).unlink(missing_ok=True)
    return result


def remove_source(workspace: Path, source_id: str, *, session_id: str | None = None) -> dict:
    workspace = _workspace(workspace)
    _prepare(workspace, session_id)
    with writer_lock(workspace) as head:
        require_operation_authority(workspace, "wrap_up", session_id=session_id, committed_revision=head["revision"])
        for name in ("pending_checkpoint.json", "pending_wrap_up.json"):
            if require_managed_path(workspace, "state/" + name, label="pending writer operation").exists():
                raise StateError("recover the pending writer operation before changing skills")
        entry = _installed(workspace, source_id)
        destination = require_managed_path(workspace, "external/" + source_id, label="deactivation destination")
        if not destination.is_dir():
            raise StateError("active source directory is missing")
        root = require_managed_path(workspace, "state/replaced_sources", label="deactivation archive root")
        root.mkdir(parents=True, exist_ok=True)
        archive = require_managed_path(workspace, root / (source_id + "-" + uuid.uuid4().hex[:10]), label="deactivation archive")
        pending = {"format": PENDING_ACTIVATION_FORMAT, "version": 4, "action": "deactivate",
                   "source_type": entry.get("source_type", "git_commit"), "source_id": source_id,
                   "source_ref": entry["source_ref"], "quarantine": "state/quarantine/deactivation-" + uuid.uuid4().hex,
                   "destination": _relative_managed(workspace, destination, label="deactivation destination"),
                   "backup": _relative_managed(workspace, archive, label="deactivation archive"),
                   "prior_manifest_entry": entry, "entry": entry, "created_at": utc_now(),
                   "activation_id": uuid.uuid4().hex, "base_revision": head["revision"]}
        atomic_write_json(pending_activation_path(workspace), pending)
        test_crash_point("external_deactivation_after_pending_record")
        try:
            move_source_tree(destination, archive)
            test_crash_point("external_deactivation_after_archive_move")
            manifest = read_installed_manifest(workspace)
            manifest["sources"].pop(source_id)
            atomic_write_json(workspace / "state/installed_sources.json", manifest)
            test_crash_point("external_deactivation_after_manifest_write")
            receipt = _finish_deactivation(workspace, pending, session_id)
        except Exception:
            _recover_deactivation(workspace, pending, session_id)
            raise
        pending_activation_path(workspace).unlink(missing_ok=True)
        return {"status": "removed", "source_id": source_id, "archive": str(archive), "receipt": receipt}


def summary(workspace: Path) -> dict:
    try:
        index = list_skills(workspace)
        updates = check_updates(workspace)
        return {"active": len(index["skills"]), "reviewed_updates": updates["reviewed_updates"],
                "status": "review_required" if index["excluded_sources"] else "available"}
    except (StateError, OSError, ValueError) as exc:
        return {"active": 0, "reviewed_updates": 0, "status": "unavailable", "reason": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("check-updates", "check-upstream", "update", "rollback", "remove", "add-local", "activate-reviewed"):
        command = sub.add_parser(name)
        command.add_argument("--workspace", required=True)
        if name in {"update", "rollback", "remove", "add-local", "activate-reviewed"}:
            command.add_argument("--session-id")
            command.add_argument("target")
        if name in {"add-local", "activate-reviewed"}:
            command.add_argument("--replace", action="store_true")
        if name == "add-local":
            command.add_argument("--source-id")
        if name == "activate-reviewed":
            command.add_argument("--quarantine", required=True)
    args = parser.parse_args()
    workspace = Path(args.workspace).expanduser()
    try:
        if args.command == "check-updates":
            result = check_updates(workspace)
        elif args.command == "check-upstream":
            result = check_upstream(workspace, announce=lambda text: print(text, file=sys.stderr, flush=True))
        elif args.command == "add-local":
            result = add_local(workspace, Path(args.target), source_id=args.source_id,
                               replace=args.replace, session_id=args.session_id)
        elif args.command == "activate-reviewed":
            result = activate_reviewed(workspace, args.target, Path(args.quarantine),
                                       replace=args.replace, session_id=args.session_id)
        else:
            function = {"update": update_source, "rollback": rollback_source, "remove": remove_source}[args.command]
            result = function(workspace, args.target, session_id=args.session_id)
        print(json.dumps(result, sort_keys=True, ensure_ascii=True))
        return 2 if result.get("status") == "blocked" else 0
    except (StateError, OSError, ValueError) as exc:
        print("SKILL LIFECYCLE ERROR: " + json.dumps(str(exc), ensure_ascii=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
