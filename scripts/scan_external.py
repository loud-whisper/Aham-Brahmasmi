#!/usr/bin/env python3
"""Bounded offline structural, instruction and execution-surface heuristics."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from external_identity import IdentityLimit, tree_digest
from state_io import StateError
from scanner_rules import finding, rule_pack_version, scan_rule_findings, verdict as rules_verdict


SCANNER_NAME = "aham-static-skill-scanner"
SCANNER_VERSION = 3
MAX_SINGLE_FILE = 25 * 1024 * 1024
MAX_FILES = 10000
TEXT_READ_LIMIT = 2 * 1024 * 1024


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def inside(root: Path, target: Path) -> bool:
    return target == root or root in target.parents


def finalize(report: dict[str, Any], root: Path) -> dict[str, Any]:
    report["rule_pack_version"] = rule_pack_version()
    report["findings"] = [finding("structural.integrity", item["severity"].upper(),
                                 item["path"], 0, "", item["message"],
                                 "Review or repair the source before activation.", "")
                          if "rule_id" not in item else item for item in report["findings"]]
    report["findings"] = list({item["finding_id"]: item for item in report["findings"]}.values())
    report["verdict"] = rules_verdict(report["findings"])
    return report


def scan_tree(root: Path) -> dict[str, Any]:
    root = root.resolve()
    findings: list[dict[str, str]] = []
    file_count = 0
    byte_count = 0

    if not root.is_dir():
        return finalize({
            "scanner": SCANNER_NAME,
            "version": SCANNER_VERSION,
            "verdict": "FAIL",
            "findings": [{"severity": "fail", "path": ".", "message": "source directory does not exist"}],
            "scanned_at": utc_now(),
            "stats": {"files": 0, "bytes": 0},
        }, root)

    private_key_marker = "BEGIN " + "PRIVATE KEY"
    rsa_key_marker = "BEGIN RSA " + "PRIVATE KEY"

    try:
        identity = tree_digest(root)
    except (OSError, RuntimeError, StateError) as exc:
        limited = isinstance(exc, IdentityLimit)
        return finalize({"scanner": SCANNER_NAME, "version": SCANNER_VERSION, "verdict": "REVIEW" if limited else "FAIL",
                "findings": [{"severity": "review" if limited else "fail", "path": ".", "message": str(exc)}],
                "scanned_at": utc_now(), "stats": {"files": 0, "bytes": 0}}, root)

    for path in root.rglob("*"):
        if ".git" in path.relative_to(root).parts:
            continue
        relative = path.relative_to(root)

        if path.is_symlink():
            try:
                target = path.resolve(strict=True)
            except FileNotFoundError:
                findings.append({"severity": "fail", "path": str(relative), "message": "broken symlink"})
                continue
            if not inside(root, target):
                findings.append(
                    {"severity": "fail", "path": str(relative), "message": "symlink escapes quarantined source"}
                )
            continue

        if not path.is_file():
            continue

        file_count += 1
        try:
            size = path.stat().st_size
        except OSError as exc:
            findings.append({"severity": "fail", "path": str(relative), "message": f"cannot stat file: {exc}"})
            continue
        byte_count += size

        if size > MAX_SINGLE_FILE:
            findings.append(
                {
                    "severity": "review",
                    "path": str(relative),
                    "message": f"file exceeds {MAX_SINGLE_FILE} bytes and needs review",
                }
            )
            continue

        if size <= TEXT_READ_LIMIT:
            try:
                raw = path.read_bytes()
            except OSError as exc:
                findings.append({"severity": "fail", "path": str(relative), "message": f"cannot read file: {exc}"})
                continue
            if b"\x00" not in raw:
                text = raw.decode("utf-8", errors="ignore")
                if private_key_marker in text or rsa_key_marker in text:
                    findings.append(
                        {
                            "severity": "fail",
                            "path": str(relative),
                            "message": "possible private key material in fetched source",
                        }
                    )

    if file_count > MAX_FILES:
        findings.append(
            {
                "severity": "review",
                "path": ".",
                "message": f"source contains {file_count} files and exceeds the basic scanner limit",
            }
        )

    try:
        if tree_digest(root) != identity:
            findings.append({"severity": "fail", "path": ".", "message": "source changed during scan"})
    except (OSError, RuntimeError, StateError) as exc:
        findings.append({"severity": "fail", "path": ".", "message": str(exc)})
    try:
        findings.extend(scan_rule_findings(root))
        if tree_digest(root) != identity:
            findings.append({"severity": "fail", "path": ".", "message": "source changed during rule evaluation"})
    except (OSError, RuntimeError, StateError, ValueError) as exc:
        findings.append({"severity": "fail", "path": ".", "message": str(exc)})
    severities = {item["severity"] for item in findings}
    verdict = "FAIL" if "fail" in severities else "REVIEW" if "review" in severities else "PASS"
    return finalize({
        "scanner": SCANNER_NAME,
        "version": SCANNER_VERSION,
        "tree_digest": identity,
        "verdict": verdict,
        "findings": findings,
        "scanned_at": utc_now(),
        "stats": {"files": file_count, "bytes": byte_count},
        "limitations": "Bounded static heuristics only; PASS does not prove that third-party code or instructions are safe.",
    }, root)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan a quarantined external source tree.")
    parser.add_argument("path", help="Quarantined source directory to scan")
    parser.add_argument("--json-out", help="Optional path for the JSON scan report")
    parser.add_argument("--external-scanner", action="append", default=[], metavar="SOURCE_ID",
                        help="Explicitly invoke a registered, user-installed JSON scanner adapter")
    parser.add_argument("--registry", help="Registry containing explicitly reviewed scanner adapters")
    parser.add_argument("--advisory-packet-out", help="Write an escaped review packet for optional model review")
    parser.add_argument("--advisory-packet", help="Previously prepared packet for this unchanged tree")
    parser.add_argument("--advisory-response", help="Explicit advisory JSON response to validate")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tree = Path(args.path)
    try:
        report = scan_tree(tree)
        if args.external_scanner:
            from third_party import get_source, load_registry
            from scanner_external import run_external_scanner
            registry = load_registry(Path(args.registry)) if args.registry else load_registry()
            for source_id in args.external_scanner:
                report = run_external_scanner(tree, report, get_source(source_id, registry))
        if bool(args.advisory_packet) != bool(args.advisory_response):
            raise StateError("advisory review requires both packet and response paths")
        if args.advisory_packet_out:
            from scanner_advisory import prepare_packet
            Path(args.advisory_packet_out).write_text(json.dumps(prepare_packet(tree, report),
                                                               indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        if args.advisory_response:
            from scanner_advisory import apply_advisory
            packet = read_bounded_json(Path(args.advisory_packet), 8 * 1024 * 1024)
            response = read_bounded_json(Path(args.advisory_response), 32 * 1024)
            report = apply_advisory(tree, report, packet, response)
    except (StateError, OSError, ValueError, TypeError) as error:
        print("SCANNER ERROR: " + json.dumps(str(error), ensure_ascii=True), file=sys.stderr)
        return 1
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.json_out:
        destination = Path(args.json_out)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["verdict"] == "PASS" else 2 if report["verdict"] == "REVIEW" else 1


def read_bounded_json(path: Path, limit: int) -> Any:
    with path.open("rb") as handle:
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        raise StateError("review JSON exceeds its input limit")
    return json.loads(raw)


if __name__ == "__main__":
    raise SystemExit(main())
