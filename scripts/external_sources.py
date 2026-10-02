#!/usr/bin/env python3
"""List and safely fetch approved external sources into a private workspace."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scan_external import scan_tree
from scanner_rules import annotate_diff
from state_io import StateError, atomic_write_json, require_workspace
from third_party import (
    ThirdPartyError,
    activate_source,
    fetch_exact_source,
    get_source,
    load_registry,
    read_installed_manifest,
    installed_source_problem,
    recover_external_activation,
    run_git,
)
from session_authority import require_operation_authority
from state_store import writer_lock


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Browse or install reviewed external sources without copying them into the public framework."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="Show reviewed external sources and how they are connected")

    status = sub.add_parser("status", help="Show external sources already fetched into a private workspace")
    status.add_argument("--workspace", required=True)

    recover = sub.add_parser("recover", help="Recover an interrupted external-source activation")
    recover.add_argument("--workspace", required=True)
    recover.add_argument("--session-id", help="Exact authority for an active runtime session")

    install = sub.add_parser("install", help="Fetch one approved installer source through quarantine and scanning")
    install.add_argument("source_id")
    install.add_argument("--workspace", required=True)
    install.add_argument("--session-id", help="Exact authority for an active runtime session")
    install.add_argument(
        "--replace",
        action="store_true",
        help="Replace an existing installation only after the new copy passes scanning",
    )

    defaults = sub.add_parser("install-defaults", help="Install the approved sources marked as useful defaults")
    defaults.add_argument("--workspace", required=True)
    defaults.add_argument("--session-id", help="Exact authority for an active runtime session")

    reviewed = sub.add_parser("activate-reviewed", help="Activate a retained quarantine after explicit finding acceptance")
    reviewed.add_argument("source_id")
    reviewed.add_argument("--workspace", required=True)
    reviewed.add_argument("--quarantine", required=True)
    reviewed.add_argument("--replace", action="store_true")
    reviewed.add_argument("--session-id")

    return parser.parse_args()


def print_sources(registry: dict) -> None:
    print("Reviewed external sources")
    for source in registry["sources"]:
        installable = source["integration"] == "installer" and source["review_status"] == "approved"
        default = "yes" if source["default_offer"] else "no"
        print(f"- {source['name']} ({source['id']})")
        print(f"  role: {source['role']}")
        print(f"  license: {source['license']}")
        print(f"  reviewed source: {source['source_ref']}")
        print(f"  automatic fetch: {'available' if installable else 'not offered'}")
        print(f"  suggested during setup: {default}")
        print(f"  upstream: {source['upstream_url']}")


def verify_quarantine_integrity(quarantine: Path, source: dict) -> None:
    """Re-check provenance and Git state immediately before activation."""
    provenance_path = quarantine / "provenance.json"
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ThirdPartyError(f"quarantine provenance is unreadable: {exc}") from exc

    expected = {
        "format": "aham-brahmasmi-quarantine",
        "version": 1,
        "source_id": source["id"],
        "upstream_url": source["upstream_url"],
        "source_ref": source["source_ref"],
        "verified_head": source["source_ref"],
    }
    for field, value in expected.items():
        if provenance.get(field) != value:
            raise ThirdPartyError(
                f"quarantine provenance mismatch for {source['id']}: field '{field}' no longer matches the reviewed source"
            )

    repo = quarantine / "source"
    if not repo.is_dir():
        raise ThirdPartyError("quarantined source directory is missing")

    head = run_git("-C", str(repo), "rev-parse", "HEAD").stdout.strip()
    if head != source["source_ref"]:
        raise ThirdPartyError(
            f"quarantined source changed commit after verification: expected {source['source_ref']}, got {head}"
        )

    status = run_git("-C", str(repo), "status", "--porcelain=v1", "--untracked-files=all").stdout.strip()
    if status:
        raise ThirdPartyError(
            "quarantined source changed after fetching or scanning; refusing activation until it is fetched and scanned again"
        )


def install_one(workspace: Path, source: dict, *, replace: bool = False, session_id: str | None = None) -> bool:
    require_workspace(workspace)
    recover_external_activation(workspace, session_id=session_id)
    manifest = read_installed_manifest(workspace)
    existing = manifest["sources"].get(source["id"])
    active = workspace / "external" / source["id"]
    if existing and existing.get("source_ref") == source["source_ref"] and active.is_dir() and not replace:
        reason = installed_source_problem(workspace, source["id"], existing)
        if reason:
            raise ThirdPartyError(reason + "; use explicit --replace to fetch and review a fresh candidate")
        print(f"{source['name']} is already installed at the reviewed source.")
        return True

    with writer_lock(workspace) as head:
        require_operation_authority(workspace, "wrap_up", session_id=session_id, committed_revision=head["revision"])

    print(f"Fetching {source['name']} at reviewed commit {source['source_ref']} into quarantine...")
    quarantine, _ = fetch_exact_source(workspace, source)
    from skills_lifecycle import _scan_candidate
    report = _scan_candidate(workspace, source, quarantine, (existing or {}).get("scan_report"))
    report_path = workspace / "state" / "scan_reports" / f"{quarantine.name}.json"

    if report["effective_verdict"] not in {"PASS", "PASS-WITH-WAIVER"}:
        print(f"NOT ACTIVATED: scanner verdict is {report['verdict']}.")
        print("The existing active copy, if any, was not changed.")
        print(f"Quarantine: {quarantine}")
        print(f"Scan report: {report_path}")
        return False

    verify_quarantine_integrity(quarantine, source)
    receipt = {}
    destination = activate_source(workspace, source, quarantine, report, replace=replace, session_id=session_id,
                                  receipt_out=receipt)
    print(f"INSTALLED: {source['name']}")
    print(f"Source: {source['upstream_url']}")
    print(f"Reviewed commit: {source['source_ref']}")
    print(f"License: {source['license']}")
    print(f"Location: {destination}")
    print("The source is available in the private workspace. Runtime-specific activation is a separate step.")
    print("Activation receipt: " + json.dumps(receipt, sort_keys=True))
    return True


def main() -> int:
    args = parse_args()
    try:
        registry = load_registry()
        if args.command == "list":
            print_sources(registry)
            return 0

        workspace = Path(args.workspace).expanduser().resolve()
        require_workspace(workspace)

        if args.command == "recover":
            result = recover_external_activation(workspace, session_id=args.session_id)
            print("EXTERNAL ACTIVATION RECOVERY")
            print(f"Result: {result}")
            return 0

        if args.command == "status":
            manifest = read_installed_manifest(workspace)
            if not manifest["sources"]:
                print("No external sources are installed in this workspace.")
                return 0
            print("Installed external sources")
            for source_id, record in sorted(manifest["sources"].items()):
                print(f"- {record.get('name', source_id)} ({source_id})")
                print(f"  source ref: {record.get('source_ref')}")
                print(f"  license: {record.get('license')}")
                print(f"  scan verdict: {record.get('scan_verdict')}")
                reason = installed_source_problem(workspace, source_id, record)
                print("  usable: " + (reason if reason else "reviewed content identity verified"))
            return 0

        if args.command == "install":
            source = get_source(args.source_id, registry)
            if source["integration"] != "installer":
                raise ThirdPartyError(
                    f"{source['name']} is registered as '{source['integration']}' and is not offered for automatic fetching"
                )
            return 0 if install_one(workspace, source, replace=args.replace, session_id=args.session_id) else 2

        if args.command == "activate-reviewed":
            from skills_lifecycle import activate_reviewed
            result = activate_reviewed(workspace, args.source_id, Path(args.quarantine), replace=args.replace,
                                       registry=registry, session_id=args.session_id)
            print(json.dumps(result, sort_keys=True, ensure_ascii=True))
            return 0 if result["status"] == "active" else 2

        if args.command == "install-defaults":
            defaults = [
                source
                for source in registry["sources"]
                if source["default_offer"]
                and source["review_status"] == "approved"
                and source["integration"] == "installer"
            ]
            if not defaults:
                print("No automatic default sources are currently offered.")
                return 0
            failures: list[str] = []
            for source in defaults:
                try:
                    if not install_one(workspace, source, session_id=args.session_id):
                        failures.append(source["id"])
                except (ThirdPartyError, StateError) as exc:
                    print(f"FAILED: {source['name']}: {exc}", file=sys.stderr)
                    failures.append(source["id"])
            if failures:
                print(f"Default installation incomplete: {', '.join(failures)}", file=sys.stderr)
                return 2
            print("DEFAULT EXTERNAL SOURCES INSTALLED")
            return 0

        return 1
    except (ThirdPartyError, StateError) as exc:
        print(f"EXTERNAL SOURCE ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
