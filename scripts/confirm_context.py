#!/usr/bin/env python3
"""Record that an assistant presented every part digest of its startup packet.

This is reported reading coverage: it shows the assistant handled each part of the
packet the controller issued. It does not prove comprehension or compliance.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from session_authority import authority_path, load_session, validate_session
from state_io import StateError, require_workspace, resolve_workspace
from state_store import durable_write_json, writer_lock

DIGEST = re.compile(r"^[0-9a-f]{64}$")
EXIT_CONFIRMED, EXIT_INCOMPLETE, EXIT_STALE = 0, 1, 2


class StaleContext(StateError):
    """The packet the session was issued for is no longer the current packet."""


def current_packet(workspace: Path, session: dict[str, Any]) -> dict[str, Any]:
    import runtime_trust
    from startup_packet import build_startup_packet

    return build_startup_packet(workspace, session["context"]["mode"],
                                runtime=runtime_trust.runtime_name(session["requested_runtime"]))


def confirm(workspace: Path, session_id: str, digests: list[str]) -> dict[str, Any]:
    """Mark the presented parts as read. Returns status, missing indexes and part count."""
    if any(not isinstance(value, str) or not DIGEST.fullmatch(value) for value in digests):
        raise StateError("each --part-digest must be the 64-character part_sha256 printed with a part")
    with writer_lock(workspace) as head:
        session = load_session(workspace)
        if session_id != session["session_id"]:
            raise StateError("presented session ID does not match the active session authority")
        context = session.get("context")
        if context is None:
            return {"status": "not_required", "missing": [], "parts": 0, "unmatched": 0}
        if session["current_revision"] != head["revision"]:
            raise StaleContext("the workspace revision moved after this session started")
        if context["status"] == "confirmed":
            return {"status": "confirmed", "missing": [], "parts": len(context["confirmed_parts"]), "unmatched": 0}
        packet = current_packet(workspace, session)
        if packet["packet_sha256"] != context["packet_sha256"]:
            raise StaleContext("the startup context changed after this session started")
        presented = set(digests)
        by_digest = {part["part_sha256"]: part["index"] for part in packet["parts"]}
        confirmed = set(context["confirmed_parts"]) | {by_digest[value] for value in presented if value in by_digest}
        missing = [part["index"] for part in packet["parts"] if part["index"] not in confirmed]
        updated = dict(session)
        updated["context"] = dict(context, confirmed_parts=sorted(confirmed),
                                  status="pending" if missing else "confirmed",
                                  method=None if missing else "packet_parts")
        validate_session(updated, workspace)
        durable_write_json(authority_path(workspace), updated)
        return {"status": updated["context"]["status"], "missing": missing, "parts": len(packet["parts"]),
                "unmatched": len(presented - set(by_digest))}


def read_all_and_confirm(workspace: Path, session_id: str) -> dict[str, Any]:
    """Read every part and confirm it, for a controller or test that stands in for an
    assistant. Deliberately not a command: an assistant confirms part by part."""
    session = load_session(workspace)
    if session.get("context") is None:
        return {"status": "not_required", "missing": [], "parts": 0, "unmatched": 0}
    digests = [part["part_sha256"] for part in current_packet(workspace, session)["parts"]]
    result = confirm(workspace, session_id, digests)
    if result["status"] != "confirmed":
        raise StateError("startup context could not be confirmed for this session")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Confirm that every part of the startup packet was read. Present the part_sha256 of each part.")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--part-digest", action="append", default=[], metavar="SHA256",
                        help="part_sha256 of one part that was read; repeat for each part, in part order")
    args = parser.parse_args(argv)
    try:
        workspace = resolve_workspace(args.workspace)
        require_workspace(workspace)
        result = confirm(workspace, args.session_id, args.part_digest)
    except StaleContext as exc:
        print(f"CONTEXT CHECK COULD NOT RUN: {exc}. Run start again and read the new packet.", file=sys.stderr)
        return EXIT_STALE
    except StateError as exc:
        print(f"CONTEXT CONFIRMATION FAILED: {exc}", file=sys.stderr)
        return EXIT_STALE
    if result["status"] == "not_required":
        print("CONTEXT CONFIRMATION NOT REQUIRED: this session was not issued by startup.")
        return EXIT_CONFIRMED
    if result["status"] == "confirmed":
        print("CONTEXT CONFIRMED")
        return EXIT_CONFIRMED
    missing = ", ".join(str(index) for index in result["missing"])
    print(f"CONTEXT INCOMPLETE: missing part(s) {missing} of {result['parts']}. "
          "Read each with context --startup --part N and present its part_sha256.")
    if result["unmatched"]:
        print(f"{result['unmatched']} presented digest(s) match no part of this packet.")
    return EXIT_INCOMPLETE


if __name__ == "__main__":
    raise SystemExit(main())
