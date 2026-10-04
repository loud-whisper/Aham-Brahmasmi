#!/usr/bin/env python3
"""Versioned structured receipts for committed and pending Aham Brahmasmi operations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from state_io import StateError, read_json, require_managed_path, require_workspace
from state_store import find_operation, reconcile_store


RECEIPT_FORMAT = "aham-brahmasmi-operation-receipt"
RECEIPT_VERSION = 1


def operation_record(workspace: Path, operation_id: str, *, expected_kind: str | None = None) -> dict[str, Any]:
    require_workspace(workspace)
    found = find_operation(workspace, operation_id)
    if not found:
        raise StateError(f"no committed operation found for {operation_id}")
    _, record = found
    if expected_kind is not None and record.get("kind") != expected_kind:
        raise StateError(f"operation {operation_id} is {record.get('kind')}, expected {expected_kind}")
    return record


def _checkpoint_view(workspace: Path, checkpoint_file: str, expected: dict[str, Any]) -> dict[str, Any]:
    if not checkpoint_file.startswith("state/checkpoints/"):
        raise StateError("committed operation has no valid checkpoint file")
    path = require_managed_path(workspace, checkpoint_file, label="committed checkpoint receipt file")
    persisted = read_json(path)
    if persisted != expected:
        raise StateError("persisted checkpoint no longer matches the committed operation record")
    checkpoint_id = persisted.get("id")
    revision = persisted.get("revision")
    if not isinstance(checkpoint_id, str) or not checkpoint_id:
        raise StateError("committed checkpoint has no valid identity")
    if not isinstance(revision, int) or revision < 1:
        raise StateError("committed checkpoint has no valid revision")
    return {"id": checkpoint_id, "file": checkpoint_file, "revision": revision}


def _scope(kind: str, repository: Any) -> dict[str, list[str]]:
    verified = ["immutable_operation_record", "durable_workspace_checkpoint_data"]
    if kind == "wrap_up":
        verified.insert(1, "durable_workspace_routed_content")
    excluded = [
        "unsaved_editor_buffers",
        "replicated_backup",
        "runtime_instruction_compliance",
        "end_to_end_recovery",
    ]
    if kind == "wrap_up":
        excluded.insert(0, "unrelated_project_artifacts")
    if repository is None:
        excluded.insert(0, "repository_state")
    else:
        verified.append("repository_snapshot_metadata")
        excluded.insert(0, "repository_working_tree_contents")
    return {"verified": verified, "excluded": excluded}


def _pending_scope() -> dict[str, list[str]]:
    return {
        "verified": ["pending_operation_metadata"],
        "excluded": [
            "committed_workspace_state",
            "repository_state",
            "unsaved_editor_buffers",
            "replicated_backup",
            "runtime_instruction_compliance",
            "end_to_end_recovery",
        ],
    }


def _warnings(repository: Any) -> list[str]:
    if not isinstance(repository, dict):
        return []
    warnings: list[str] = []
    if repository.get("tracked_dirty") is True:
        warnings.append("repository_tracked_working_tree_changes_were_recorded_as_metadata_but_not_preserved")
    if repository.get("untracked_present") is True:
        warnings.append("repository_untracked_files_were_recorded_as_metadata_but_not_preserved")
    return warnings


def pending_receipt(kind: str, pending: dict[str, Any], *, recovery_action: str) -> dict[str, Any]:
    if kind not in {"checkpoint", "wrap_up"}:
        raise StateError(f"pending receipt kind is not supported: {kind}")
    operation_id = pending.get("operation_id")
    target_revision = pending.get("target_revision")
    payload_digest = pending.get("payload_digest")
    if not isinstance(operation_id, str) or not operation_id:
        raise StateError("pending operation has no valid operation identity")
    if not isinstance(target_revision, int) or target_revision < 1:
        raise StateError("pending operation has no valid target revision")
    if not isinstance(payload_digest, str) or len(payload_digest) != 64:
        raise StateError("pending operation has no valid payload digest")
    return {
        "format": RECEIPT_FORMAT,
        "version": RECEIPT_VERSION,
        "status": "pending",
        "kind": kind,
        "operation_id": operation_id,
        "revision": None,
        "target_revision": target_revision,
        "payload_digest": payload_digest,
        "accepted_items": [],
        "accepted_item_count": 0,
        "checkpoint": None,
        "verification_scope": _pending_scope(),
        "warnings": ["operation_not_committed"],
        "recovery_action": recovery_action,
    }


def _checkpoint_receipt(workspace: Path, record: dict[str, Any]) -> dict[str, Any]:
    details = record.get("details")
    if not isinstance(details, dict):
        raise StateError("committed checkpoint operation has no details")
    checkpoint = details.get("checkpoint")
    checkpoint_file = details.get("checkpoint_file")
    if not isinstance(checkpoint, dict) or not isinstance(checkpoint_file, str):
        raise StateError("committed checkpoint operation has no canonical checkpoint payload")
    checkpoint_view = _checkpoint_view(workspace, checkpoint_file, checkpoint)
    accepted_items = [
        {
            "item_id": checkpoint_view["id"],
            "kind": "checkpoint",
            "index": 0,
            "destination": checkpoint_file,
            "content_digest": record["payload_digest"],
        }
    ]
    repository = checkpoint.get("repository")
    return {
        "format": RECEIPT_FORMAT,
        "version": RECEIPT_VERSION,
        "status": "complete",
        "kind": "checkpoint",
        "operation_id": record["operation_id"],
        "revision": record["revision"],
        "target_revision": record["revision"],
        "payload_digest": record["payload_digest"],
        "accepted_items": accepted_items,
        "accepted_item_count": len(accepted_items),
        "checkpoint": checkpoint_view,
        "verification_scope": _scope("checkpoint", repository),
        "warnings": _warnings(repository),
        "recovery_action": None,
    }


def _wrap_up_receipt(workspace: Path, record: dict[str, Any]) -> dict[str, Any]:
    details = record.get("details")
    if not isinstance(details, dict) or not isinstance(details.get("receipt"), dict):
        raise StateError("committed wrap-up operation has no canonical receipt payload")
    completed = details["receipt"]
    if completed.get("operation_id") != record.get("operation_id"):
        raise StateError("committed wrap-up receipt operation identity conflicts with its record")
    if completed.get("revision") != record.get("revision"):
        raise StateError("committed wrap-up receipt revision conflicts with its record")
    if completed.get("payload_digest") != record.get("payload_digest"):
        raise StateError("committed wrap-up receipt digest conflicts with its record")
    checkpoint_file = completed.get("checkpoint_file")
    bundle = completed.get("bundle")
    if not isinstance(checkpoint_file, str) or not isinstance(bundle, dict) or not isinstance(bundle.get("checkpoint"), dict):
        raise StateError("committed wrap-up receipt has no canonical checkpoint payload")
    expected_checkpoint = dict(bundle["checkpoint"])
    expected_checkpoint["id"] = f"wrap-{record['operation_id']}"
    expected_checkpoint["revision"] = record["revision"]
    expected_checkpoint["repository"] = completed.get("repository")
    path = require_managed_path(workspace, checkpoint_file, label="committed wrap-up checkpoint file")
    persisted = read_json(path)
    for field, value in expected_checkpoint.items():
        if persisted.get(field) != value:
            raise StateError(f"persisted wrap-up checkpoint {field} no longer matches the committed operation record")
    checkpoint_id = persisted.get("id")
    checkpoint_revision = persisted.get("revision")
    if not isinstance(checkpoint_id, str) or not isinstance(checkpoint_revision, int):
        raise StateError("persisted wrap-up checkpoint identity is invalid")
    checkpoint_view = {"id": checkpoint_id, "file": checkpoint_file, "revision": checkpoint_revision}
    committed_items = completed.get("committed_items")
    if not isinstance(committed_items, list) or any(not isinstance(item, dict) for item in committed_items):
        raise StateError("committed wrap-up receipt does not enumerate accepted items")
    accepted_items = [dict(item) for item in committed_items]
    repository = completed.get("repository")
    return {
        "format": RECEIPT_FORMAT,
        "version": RECEIPT_VERSION,
        "status": "complete",
        "kind": "wrap_up",
        "operation_id": record["operation_id"],
        "revision": record["revision"],
        "target_revision": record["revision"],
        "payload_digest": record["payload_digest"],
        "accepted_items": accepted_items,
        "accepted_item_count": len(accepted_items),
        "checkpoint": checkpoint_view,
        "verification_scope": _scope("wrap_up", repository),
        "warnings": _warnings(repository),
        "recovery_action": None,
    }


def receipt_from_record(workspace: Path, record: dict[str, Any]) -> dict[str, Any]:
    kind = record.get("kind")
    if kind == "runtime_control":
        from runtime_trust import _request
        from state_store import digest_json
        if set(record["details"]) != {"request"}:
            raise StateError("runtime trust receipt has invalid details")
        request = _request(record["details"]["request"])
        if digest_json(request) != record["payload_digest"]:
            raise StateError("runtime trust receipt conflicts with its ledger record")
        return {"format": RECEIPT_FORMAT, "version": RECEIPT_VERSION, "status": "complete", "kind": kind,
                "operation_id": record["operation_id"], "revision": record["revision"],
                "payload_digest": record["payload_digest"], "checkpoint": None,
                "accepted_items": [{"item_id": request["runtime"], "kind": kind, "index": 0,
                                    "destination": "state/runtime_trust.json"}], "accepted_item_count": 1,
                "verification_scope": {"verified": ["immutable_operation_record", "recorded_runtime_trust_choice"],
                                       "excluded": ["human_identity_authentication", "runtime_tool_availability",
                                                    "runtime_instruction_compliance", "physical_power_loss"]},
                "warnings": [], "recovery_action": None}
    if kind == "phrase_control":
        from owner_phrases import PROCEDURES, _request
        from state_store import digest_json
        if set(record["details"]) != {"request"}:
            raise StateError("phrase receipt has invalid details")
        request = _request(record["details"]["request"])
        if digest_json(request) != record["payload_digest"]:
            raise StateError("phrase receipt conflicts with its ledger record")
        items = [{"item_id": procedure, "kind": kind, "index": index, "destination": "operation_ledger"}
                 for index, procedure in enumerate(PROCEDURES)]
        return {"format": RECEIPT_FORMAT, "version": RECEIPT_VERSION, "status": "complete", "kind": kind,
                "operation_id": record["operation_id"], "revision": record["revision"],
                "payload_digest": record["payload_digest"], "checkpoint": None,
                "accepted_items": items, "accepted_item_count": len(items),
                "verification_scope": {"verified": ["immutable_operation_record", "recorded_owner_phrases",
                                                    "phrases_grant_no_authority"],
                                       "excluded": ["human_identity_authentication", "runtime_instruction_compliance",
                                                    "physical_power_loss"]},
                "warnings": [], "recovery_action": None}
    if kind == "memory_control":
        from memory_connection import _request
        from state_store import digest_json
        if set(record["details"]) != {"request"}:
            raise StateError("recall control receipt has invalid details")
        request = _request(record["details"].get("request"))
        if digest_json(request) != record["payload_digest"]:
            raise StateError("recall control receipt conflicts with its ledger record")
        return {"format": RECEIPT_FORMAT, "version": RECEIPT_VERSION, "status": "complete", "kind": kind,
                "operation_id": record["operation_id"], "revision": record["revision"],
                "payload_digest": record["payload_digest"], "checkpoint": None,
                "accepted_items": [{"item_id": request.get("project_id") or request["action"],
                                    "kind": kind, "index": 0, "destination": "BRAIN.json"}],
                "accepted_item_count": 1, "verification_scope": {
                    "verified": ["immutable_operation_record", "recorded_recall_control"],
                    "excluded": ["provider_index_durability", "provider_result_truth", "runtime_instruction_compliance",
                                 "replicated_backup", "physical_power_loss"]},
                "warnings": [], "recovery_action": None}
    if kind == "checkpoint":
        return _checkpoint_receipt(workspace, record)
    if kind == "wrap_up":
        return _wrap_up_receipt(workspace, record)
    if kind == "skills_control":
        from skills_index import _request
        from state_store import digest_json
        request = _request(record["details"].get("request"))
        if digest_json(request) != record["payload_digest"]:
            raise StateError("skill preference receipt conflicts with its ledger record")
        items = [] if request["action"] == "refresh" else [{"item_id": request["skill_id"], "kind": kind,
                                                           "index": 0, "destination": "state/skills_index.json",
                                                           "content_digest": request["tree_digest"]}]
        return {"format": RECEIPT_FORMAT, "version": RECEIPT_VERSION, "status": "complete", "kind": kind,
                "operation_id": record["operation_id"], "revision": record["revision"],
                "payload_digest": record["payload_digest"], "checkpoint": None,
                "accepted_items": items, "accepted_item_count": len(items),
                "verification_scope": {"verified": ["immutable_operation_record", "recorded_skill_preference"],
                                       "excluded": ["current_source_identity", "runtime_instruction_compliance",
                                                    "third_party_safety", "physical_power_loss"]},
                "warnings": [], "recovery_action": None}
    if kind == "skill_review":
        from state_store import digest_json
        details = record["details"]
        if digest_json(details) != record["payload_digest"] or not isinstance(details.get("binding"), dict):
            raise StateError("finding acceptance receipt conflicts with its ledger record")
        binding = details["binding"]
        if binding.get("severity") != "REVIEW" or details.get("human_confirmation") != binding.get("finding_id"):
            raise StateError("finding acceptance record has no valid confirmation")
        return {"format": RECEIPT_FORMAT, "version": RECEIPT_VERSION, "status": "complete", "kind": kind,
                "operation_id": record["operation_id"], "revision": record["revision"],
                "payload_digest": record["payload_digest"], "checkpoint": None,
                "accepted_items": [{"item_id": binding["finding_id"], "kind": kind, "index": 0,
                                    "destination": binding["path"], "content_digest": binding["file_digest"]}],
                "accepted_item_count": 1, "verification_scope": {
                    "verified": ["immutable_operation_record", "recorded_finding_acceptance"],
                    "excluded": ["current_source_identity", "human_identity_authentication", "third_party_safety",
                                 "runtime_instruction_compliance", "physical_power_loss"]},
                "warnings": [], "recovery_action": None}
    if kind == "external_deactivation":
        from state_store import digest_json
        details = record.get("details", {})
        if (set(details) != {"source_id", "entry", "archive"} or not isinstance(details["entry"], dict)
                or not isinstance(details["source_id"], str) or not isinstance(details["archive"], str)
                or digest_json(details) != record["payload_digest"]):
            raise StateError("external deactivation receipt conflicts with its ledger record")
        return {"format": RECEIPT_FORMAT, "version": RECEIPT_VERSION, "status": "complete", "kind": kind,
                "operation_id": record["operation_id"], "revision": record["revision"],
                "payload_digest": record["payload_digest"], "checkpoint": None,
                "accepted_items": [{"item_id": details["source_id"], "kind": kind, "index": 0,
                                    "destination": details["archive"]}], "accepted_item_count": 1,
                "verification_scope": {"verified": ["immutable_operation_record", "recorded_deactivation"],
                                       "excluded": ["current_archive_identity", "file_deletion", "physical_power_loss"]},
                "warnings": [], "recovery_action": None}
    if kind == "external_activation":
        from external_identity import report_digest
        from state_store import digest_json
        details = record.get("details", {})
        source_id, entry = details.get("source_id"), details.get("entry")
        if not isinstance(source_id, str) or not isinstance(entry, dict):
            raise StateError("external activation record has no reviewed content identity")
        if (set(details) not in ({"source_id", "entry"}, {"source_id", "entry", "archive", "prior_manifest_entry"})
                or digest_json(details) != record["payload_digest"]):
            raise StateError("external activation receipt content conflicts with its ledger record")
        report = entry.get("scan_report")
        if not isinstance(report, dict) or report_digest(report) != entry.get("scan_report_digest"):
            raise StateError("external activation record has an invalid reviewed report digest")
        return {"format": RECEIPT_FORMAT, "version": RECEIPT_VERSION, "status": "complete", "kind": kind,
                "operation_id": record["operation_id"], "revision": record["revision"],
                "payload_digest": record["payload_digest"], "checkpoint": None,
                "accepted_items": [{"item_id": source_id, "kind": kind, "index": 0,
                                    "destination": "external/" + source_id, "content_digest": entry["tree_digest"]}],
                "accepted_item_count": 1, "verification_scope": {
                    "verified": ["immutable_operation_record", "reviewed_external_content"],
                    "excluded": ["current_external_tree_identity", "third_party_safety", "runtime_instruction_compliance",
                                 "replicated_backup", "physical_power_loss"]},
                "warnings": [], "recovery_action": None}
    raise StateError(f"operation kind is not supported by the receipt schema: {kind}")


def receipt_for_operation(workspace: Path, operation_id: str, *, expected_kind: str | None = None) -> dict[str, Any]:
    record = operation_record(workspace, operation_id, expected_kind=expected_kind)
    return receipt_from_record(workspace, record)


def latest_receipt(workspace: Path, *, expected_kind: str | None = None) -> dict[str, Any]:
    head = reconcile_store(workspace)
    operation_id = head.get("last_operation_id")
    if not isinstance(operation_id, str) or not operation_id:
        raise StateError("workspace has no committed operation to report")
    return receipt_for_operation(workspace, operation_id, expected_kind=expected_kind)


def print_json_receipt(receipt: dict[str, Any]) -> None:
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def _human_scope_token(token: str) -> str:
    labels = {
        "repository_state": "repository state",
        "repository_working_tree_contents": "repository working-tree contents",
        "unrelated_project_artifacts": "unrelated project artifacts",
        "unsaved_editor_buffers": "unsaved editor buffers",
        "replicated_backup": "replicated backup",
        "runtime_instruction_compliance": "runtime instruction compliance",
        "end_to_end_recovery": "end-to-end recovery",
        "committed_workspace_state": "committed workspace state",
    }
    return labels.get(token, token.replace("_", " "))


def print_text_receipt(receipt: dict[str, Any]) -> None:
    kind = receipt["kind"]
    status = receipt["status"]
    if status == "complete" and kind == "checkpoint":
        print("CHECKPOINT SAVED: local durable state committed")
        print("CHECKPOINT VERIFIED: local durable checkpoint state")
        print("Persistence: committed local durable state")
        scope_summary = "durable workspace checkpoint data"
    elif status == "complete" and kind == "wrap_up":
        print("WRAP UP COMPLETE: local durable state committed")
        print("WRAP UP VERIFIED: routed durable workspace state and final checkpoint")
        print("Persistence: committed local durable state")
        scope_summary = "routed durable workspace content and final checkpoint"
    else:
        print(f"{str(kind).replace('_', ' ').upper()} PENDING")
        print("Persistence: not committed")
        scope_summary = "pending operation metadata only"

    print("OPERATION RECEIPT")
    print(f"Kind: {kind}")
    print(f"Status: {status}")
    print(f"Operation: {receipt['operation_id']}")
    revision = receipt.get("revision")
    print(f"Revision: {revision if revision is not None else '(not committed)'}")
    if receipt.get("target_revision") is not None:
        print(f"Target revision: {receipt['target_revision']}")
    print(f"Payload digest: {receipt['payload_digest']}")
    print(f"Accepted items: {receipt['accepted_item_count']}")
    checkpoint = receipt.get("checkpoint")
    if isinstance(checkpoint, dict):
        print(f"Checkpoint: {checkpoint['id']} ({checkpoint['file']})")
    else:
        print("Checkpoint: not committed")
    print(f"Verification scope: {scope_summary}")
    excluded = receipt["verification_scope"]["excluded"]
    print("Excluded scope: " + ", ".join(_human_scope_token(item) for item in excluded))
    warnings = receipt["warnings"]
    print("Warnings: " + (", ".join(warnings) if warnings else "none"))
    recovery = receipt.get("recovery_action")
    print("Recovery action: " + (str(recovery) if recovery else "none"))
