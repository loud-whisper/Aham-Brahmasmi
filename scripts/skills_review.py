"""Human finding acceptance recorded in the existing immutable operation ledger."""
from __future__ import annotations

import copy
import argparse
import json
from pathlib import Path
import re
import uuid
import sys

from external_identity import report_digest, tree_digest
from operation_receipt import receipt_for_operation
from scanner_rules import rule_pack_version
from session_authority import advance_session_revision, require_operation_authority
from state_io import StateError, require_managed_path
from state_store import (advance_store_head, commit_operation, digest_json,
                         list_operation_records, writer_lock)


def _binding(source_id: str, report: dict, item: dict) -> dict:
    return {"source_id": source_id, "tree_digest": report.get("tree_digest"),
            "rule_pack_version": report.get("rule_pack_version"),
            "finding_id": item.get("finding_id"), "rule_id": item.get("rule_id"),
            "file_digest": item.get("file_digest"), "path": item.get("path"),
            "line": item.get("line"), "severity": item.get("severity"),
            "finding_digest": report_digest(item)}


def _current(tree: Path, report: dict) -> bool:
    return (isinstance(report, dict) and report.get("rule_pack_version") == rule_pack_version()
            and report.get("tree_digest") == tree_digest(tree))


def validated_report(workspace: Path, source_id: str, tree: Path, report: dict) -> dict:
    """Recheck mandatory findings before considering any supplied review evidence."""
    if not _current(tree, report):
        raise StateError("source content or scanner rule pack changed; scan again")
    from scan_external import scan_tree
    fresh = scan_tree(tree)
    if any(item not in report.get("findings", []) for item in fresh["findings"]):
        raise StateError("report omits or changes a deterministic finding")
    from scanner_rules import verdict
    if verdict(report.get("findings", [])) != report.get("verdict"):
        raise StateError("report verdict differs from its findings")
    return effective_report(workspace, source_id, tree, report)


def effective_report(workspace: Path, source_id: str, tree: Path, report: dict) -> dict:
    result = copy.deepcopy(report)
    result["effective_verdict"] = report["verdict"]
    result["waivers"] = []
    if report["verdict"] != "REVIEW" or not _current(tree, report):
        return result
    accepted = []
    for _, record in list_operation_records(workspace):
        if record["kind"] != "skill_review":
            continue
        details = record["details"]
        if digest_json(details) != record["payload_digest"]:
            raise StateError("finding acceptance conflicts with its immutable ledger digest")
        accepted.append((details.get("binding"), record["operation_id"]))
    reviews = [item for item in report["findings"] if item["severity"] == "REVIEW"]
    for item in reviews:
        if item["rule_id"].startswith("structural.") or item["rule_id"] == "external.incomplete":
            return result  # An incomplete scan must be completed, rather than waived.
        binding = _binding(source_id, report, item)
        match = next((operation for saved, operation in accepted if saved == binding), None)
        if match is None:
            return result
        result["waivers"].append({"finding_id": item["finding_id"], "operation_id": match})
    if reviews:
        result["effective_verdict"] = "PASS-WITH-WAIVER"
    return result


def accept_finding(workspace: Path, source_id: str, tree: Path, report: dict,
                   finding_id: str, reason: str, *, human_approval: str | None,
                   session_id: str | None = None) -> dict:
    if human_approval != finding_id or not finding_id:
        raise StateError("acceptance requires explicit human confirmation of the exact finding ID")
    if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 2000:
        raise StateError("finding acceptance requires a bounded, nonempty reason")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", source_id):
        raise StateError("invalid source identity")
    with writer_lock(workspace) as head:
        session = require_operation_authority(workspace, "wrap_up", session_id=session_id,
                                              committed_revision=head["revision"])
        for pending in ("state/pending_checkpoint.json", "state/pending_wrap_up.json"):
            if require_managed_path(workspace, pending, label="pending operation").exists():
                raise StateError("recover the pending operation before accepting findings")
        if not _current(tree, report):
            raise StateError("source content or scanner rule pack changed; scan again")
        # Verify the mandatory deterministic findings instead of trusting a supplied verdict.
        from scan_external import scan_tree
        fresh = scan_tree(tree)
        if fresh["verdict"] == "FAIL" or report["verdict"] == "FAIL":
            raise StateError("FAIL cannot be accepted or waived")
        for item in fresh["findings"]:
            if item not in report["findings"]:
                raise StateError("report omits or changes a deterministic finding")
        matches = [item for item in report["findings"] if item.get("finding_id") == finding_id]
        if len(matches) != 1 or matches[0].get("severity") != "REVIEW":
            raise StateError("only a single REVIEW finding can be accepted")
        item = matches[0]
        if item["rule_id"].startswith("structural.") or item["rule_id"] == "external.incomplete":
            raise StateError("incomplete scans cannot be waived; complete the scan first")
        details = {"binding": _binding(source_id, report, item), "reason": reason,
                   "human_confirmation": finding_id}
        operation_id = "skill-review-" + uuid.uuid4().hex
        path, record = commit_operation(workspace, operation_id=operation_id, kind="skill_review",
                                        payload_digest=digest_json(details), details=details,
                                        target_revision=head["revision"] + 1)
        advance_store_head(workspace, path, record)
        advance_session_revision(workspace, session, record["revision"])
        return receipt_for_operation(workspace, operation_id, expected_kind="skill_review")


def main() -> int:
    parser = argparse.ArgumentParser(description="Record a human's explicit acceptance of one REVIEW finding.")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--tree", required=True)
    parser.add_argument("--finding", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--human-approval", help="Exact finding ID explicitly confirmed by the human")
    parser.add_argument("--session-id")
    parser.add_argument("--report", help="Retained report including any optional reviews; otherwise scan offline")
    args = parser.parse_args()
    try:
        from scan_external import read_bounded_json, scan_tree
        tree = Path(args.tree).expanduser().resolve()
        report = read_bounded_json(Path(args.report), 8 * 1024 * 1024) if args.report else scan_tree(tree)
        receipt = accept_finding(Path(args.workspace).expanduser().resolve(), args.source, tree, report,
                                 args.finding, args.reason, human_approval=args.human_approval,
                                 session_id=args.session_id)
        print(json.dumps(receipt, sort_keys=True, ensure_ascii=True))
        return 0
    except (StateError, OSError, ValueError, KeyError, TypeError) as error:
        print("REVIEW ERROR: " + json.dumps(str(error), ensure_ascii=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
