#!/usr/bin/env python3
"""Plain commands for the existing Aham lifecycle and optional integrations."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))
from state_io import StateError, resolve_workspace

COMMANDS = {
    "setup": ("setup_workspace.py", []), "check": ("doctor.py", []),
    "start": ("startup.py", []), "save": ("checkpoint.py", []),
    "wrap-up": ("wrap_up.py", []), "resume": ("resume.py", []),
    "connect": ("runtime_bridge.py", ["install"]), "memory": ("semantic_memory.py", []),
    "backup": ("portable_backup.py", ["export"]), "restore": ("portable_backup.py", ["restore"]),
    "migrate": ("migrate_workspace.py", []), "trust-runtime": ("runtime_trust.py", ["trust"]),
    "revoke-runtime": ("runtime_trust.py", ["revoke"]), "runtimes": ("runtime_trust.py", ["list"]),
    "recover-access": ("runtime_trust.py", ["owner-recovery"]),
    "phrases": ("owner_phrases.py", []),
}


def delegate(script, arguments, *, compact=False) -> int:
    command = [sys.executable, str(ROOT / "scripts" / script), *arguments]
    if not compact:
        result = subprocess.run(command, check=False)
        if result.returncode:
            print("Next: keep the failing command and output. Use aham.py check --workspace WORKSPACE and docs/TROUBLESHOOTING.md; do not repair framework code during setup.", file=sys.stderr)
        return result.returncode
    result = subprocess.run([*command, "--json"], check=False, text=True, capture_output=True)
    if result.stderr:
        sys.stderr.write(result.stderr)
    if result.returncode:
        print("Next: read the reported blockers and use aham.py check --workspace WORKSPACE before new work.", file=sys.stderr)
    if not result.stdout:
        return result.returncode
    try:
        report = json.loads(result.stdout)
    except ValueError:
        sys.stdout.write(result.stdout)
        return result.returncode
    keys = ("format", "version", "ready", "requested_runtime", "runtime", "mode", "capabilities",
            "workspace_status", "write_policy", "writer_self_test", "session_authority", "blockers",
            "skills", "semantic_memory_status", "semantic_memory_scope", "owner_phrases")
    compact_report = {key: report[key] for key in keys if key in report}
    encoded = json.dumps(compact_report, sort_keys=True, ensure_ascii=True)
    if len(encoded.encode()) > 8 * 1024:
        raise StateError("compact startup metadata exceeds 8192 bytes; use start --json for diagnostics")
    print(encoded)
    return result.returncode


def chat_command(command, arguments) -> int:
    import chat_access
    parser = argparse.ArgumentParser(prog="aham " + command)
    parser.add_argument("--workspace", required=True)
    if command == "context":
        parser.add_argument("--project-id", required=True)
        parser.add_argument("--for-chat", action="store_true")
        parser.add_argument("--max-bytes", type=int, default=12000)
    else:
        parser.add_argument("file")
        parser.add_argument("--session-id", required=True)
        parser.add_argument("--json", action="store_true")
    args = parser.parse_args(arguments)
    workspace = resolve_workspace(args.workspace)
    if command == "context":
        if args.for_chat:
            packet = chat_access.chat_packet(workspace, args.project_id, max_bytes=args.max_bytes)
        else:
            from context_packet import build_packet
            packet = build_packet(workspace, args.project_id, args.max_bytes)
        print(json.dumps(packet, sort_keys=True, ensure_ascii=True))
        return 0
    return chat_access.import_response(workspace, Path(args.file).expanduser(),
                                       session_id=args.session_id, as_json=args.json)


def main(argv=None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description="Aham Brahmasmi: user-owned durable context for any assistant.",
                                     epilog="Run a command with --help for its options. Owner trust commands require --confirm NAME.")
    parser.add_argument("command", choices=sorted([*COMMANDS, "skills", "context", "import-wrapup"]), nargs="?")
    if not arguments or arguments[0] in {"-h", "--help"}:
        parser.print_help()
        return 0
    command, *rest = arguments
    try:
        if command in {"context", "import-wrapup"}:
            return chat_command(command, rest)
        if command == "skills":
            if not rest or rest[0] in {"-h", "--help"}:
                print("Skills: list, refresh, enable, disable, check-updates, check-upstream, update, remove, rollback, add-local, activate-reviewed.\n"
                      "Use aham.py skills COMMAND --help for options. Source review: scripts/skills_review.py.")
                return 0
            if rest[0] in {"list", "refresh", "enable", "disable"}:
                return delegate("skills_index.py", rest)
            return delegate("skills_lifecycle.py", rest)
        if command not in COMMANDS:
            parser.error("unknown command: " + command)
        script, prefix = COMMANDS[command]
        compact = command == "start" and "--compact" in rest
        if compact:
            rest.remove("--compact")
        return delegate(script, [*prefix, *rest], compact=compact)
    except (StateError, OSError, ValueError) as exc:
        print("AHAM FAILED: " + json.dumps(str(exc), ensure_ascii=True), file=sys.stderr)
        print("Next: preserve the input and error, run aham.py check for the chosen workspace, and follow docs/TROUBLESHOOTING.md.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
