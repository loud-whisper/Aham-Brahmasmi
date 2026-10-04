"""Owner-chosen phrases that request existing lifecycle procedures."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import unicodedata
import uuid

from session_authority import advance_session_revision, issue_session, require_operation_authority
from state_io import StateError, require_managed_path, require_workspace, resolve_workspace
from state_store import advance_store_head, commit_operation, digest_json, list_operation_records, writer_lock

KIND = "phrase_control"
CONFIRMATION = "set-phrases"
PROCEDURES = ("regular_start", "quick_start", "wrap_up")
DEFAULTS = {"regular_start": ("regular start",), "quick_start": ("quick start",), "wrap_up": ("wrap up",)}
MAX_PER_PROCEDURE = 5
MAX_LENGTH = 40


def normalize_phrase(value: object) -> str:
    if not isinstance(value, str):
        raise StateError("each phrase must be text")
    # Casefolded NFKC text so "Wrap Up" and "wrap up" cannot be recorded as distinct triggers.
    phrase = " ".join(unicodedata.normalize("NFKC", value).casefold().split())
    if not phrase or len(phrase) > MAX_LENGTH:
        raise StateError(f"each phrase must contain 1-{MAX_LENGTH} characters")
    # Phrases reach assistant instructions, so only words, spaces, apostrophes and hyphens are allowed.
    if not (phrase[0].isalnum() and phrase[-1].isalnum()) or any(
            not (character.isalnum() or character in " '-") for character in phrase):
        raise StateError("phrases may contain only letters, digits, spaces, apostrophes and hyphens")
    return phrase


def _mapping(value: object) -> dict[str, list[str]]:
    if not isinstance(value, dict) or set(value) != set(PROCEDURES):
        raise StateError("phrase mapping must name exactly: " + ", ".join(PROCEDURES))
    seen: set[str] = set()
    for procedure in PROCEDURES:
        phrases = value[procedure]
        if not isinstance(phrases, list) or not 1 <= len(phrases) <= MAX_PER_PROCEDURE:
            raise StateError(f"{procedure} needs 1-{MAX_PER_PROCEDURE} phrases")
        for phrase in phrases:
            if normalize_phrase(phrase) != phrase:
                raise StateError("recorded phrases must already be normalized")
            if phrase in seen:
                raise StateError(f"phrase is used more than once: {phrase!r}")
            seen.add(phrase)
    return value


def _request(value: object) -> dict:
    if (not isinstance(value, dict) or set(value) != {"action", "phrases", "human_confirmation"}
            or value["action"] != "set" or value["human_confirmation"] != CONFIRMATION):
        raise StateError("phrase request is invalid")
    _mapping(value["phrases"])
    return value


def owner_phrases(workspace: Path) -> dict:
    require_workspace(workspace)
    current = None
    for _, record in list_operation_records(workspace):
        if record["kind"] != KIND:
            continue
        if set(record["details"]) != {"request"}:
            raise StateError("phrase record details are invalid")
        request = _request(record["details"]["request"])
        if digest_json(request) != record["payload_digest"]:
            raise StateError("phrase record conflicts with its immutable digest")
        current = request["phrases"]  # Records are in revision order; the newest choice wins.
    if current is None:
        return {"source": "default", "phrases": {key: list(value) for key, value in DEFAULTS.items()}}
    return {"source": "owner", "phrases": {key: list(current[key]) for key in PROCEDURES}}


def set_phrases(workspace: Path, changes: dict, *, human_confirmation: str) -> dict:
    workspace = workspace.resolve()
    require_workspace(workspace)
    if human_confirmation != CONFIRMATION:
        raise StateError(f"changing phrases requires --confirm {CONFIRMATION}")
    if not isinstance(changes, dict) or not changes or not set(changes) <= set(PROCEDURES):
        raise StateError("name at least one procedure to change: " + ", ".join(PROCEDURES))
    with writer_lock(workspace) as head:
        for path in ("state/pending_wrap_up.json", "state/pending_checkpoint.json"):
            if require_managed_path(workspace, path, label="pending writer operation").exists():
                raise StateError("recover the pending operation before changing phrases")
        merged = owner_phrases(workspace)["phrases"]  # Also refuses corrupt history before mutation.
        for procedure, phrases in changes.items():
            if not isinstance(phrases, (list, tuple)):
                raise StateError(f"{procedure} phrases must be a list")
            merged[procedure] = [normalize_phrase(phrase) for phrase in phrases]
        request = _request({"action": "set", "phrases": merged, "human_confirmation": human_confirmation})
        # Explicit local owner command, as for runtime trust. Confirmation records
        # intent; it does not authenticate human identity.
        session = issue_session(workspace, source="workspace_owner", requested_runtime="direct_cli",
                                runtime="direct_cli", mode="owner_control",
                                capabilities=("read_files", "write_files", "run_commands"),
                                allowed_operations=("checkpoint", "recover_checkpoint", "wrap_up", "recover_wrap_up"),
                                current_revision=head["revision"])
        session = require_operation_authority(workspace, "wrap_up", session_id=session["session_id"],
                                              committed_revision=head["revision"])
        operation_id = "phrase-control-" + uuid.uuid4().hex
        path, record = commit_operation(workspace, operation_id=operation_id, kind=KIND,
                                        payload_digest=digest_json(request), details={"request": request},
                                        target_revision=head["revision"] + 1)
        advance_store_head(workspace, path, record)
        advance_session_revision(workspace, session, record["revision"])
        from operation_receipt import receipt_for_operation
        return receipt_for_operation(workspace, operation_id, expected_kind=KIND)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="aham phrases",
        description="List or set the phrases an owner says to request Regular start, Quick start or wrap up. "
                    "Phrases name existing procedures; they grant no permissions.")
    parser.add_argument("action", choices=("list", "set"))
    parser.add_argument("--workspace", required=True)
    for procedure in PROCEDURES:
        parser.add_argument("--" + procedure.replace("_", "-"), action="append", dest=procedure, metavar="PHRASE",
                            help="Repeat for up to %d phrases; replaces this procedure's phrases." % MAX_PER_PROCEDURE)
    parser.add_argument("--confirm", help=f"Owner confirmation for set: {CONFIRMATION}")
    args = parser.parse_args()
    try:
        workspace = resolve_workspace(args.workspace)
        if args.action == "list":
            result = owner_phrases(workspace)
        else:
            changes = {procedure: getattr(args, procedure) for procedure in PROCEDURES
                       if getattr(args, procedure) is not None}
            result = set_phrases(workspace, changes, human_confirmation=args.confirm)
        print(json.dumps(result, sort_keys=True, ensure_ascii=True))
        return 0
    except (StateError, OSError, ValueError) as exc:
        print("PHRASES FAILED: " + json.dumps(str(exc), ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
