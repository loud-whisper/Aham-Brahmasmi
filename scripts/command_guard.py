#!/usr/bin/env python3
"""Optional hook endpoint, exact chat-approval recorder and fallback argv wrapper."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sqlite3
import subprocess
import sys
from pathlib import Path

from command_guard_policy import Decision, classify, operands
from command_guard_store import audit, binding, consume, grant, read_policy
from state_io import StateError

RUNTIMES = ("claude", "codex", "gemini", "wrapper")


def message(decision, command):
    exact = json.dumps(command, ensure_ascii=True)
    if decision.tier == "ask":
        return (f"{decision.effect}; undo: {decision.undo}. Ask the user in chat for yes to this exact command: {exact}. "
                "After yes, record it with command_guard.py approve for this runtime/session/cwd, then retry once.")
    return (f"User runs it: {decision.reason}. Explain the effect and give the user this exact command to run themselves: "
            f"{exact}. Agent approval cannot authorize this command.")


def output(runtime, choice, reason):
    if runtime == "gemini":
        return {"decision": choice, "reason": reason}
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": choice,
                                   "permissionDecisionReason": reason}}


def recorder_hint(project, runtime, session, command, cwd, undo):
    invocation = shlex.join([sys.executable, str(Path(__file__).resolve()), "approve", "--project", str(project),
                             "--runtime", runtime, "--session-id", session, "--command", command,
                             "--cwd", str(cwd), "--user-response", "yes", "--undo", undo])
    return "\nApproval recorder, only after the user's yes:\n" + invocation


def classify_runtime(runtime, command, cwd, project, limits):
    decision = classify(command, cwd, project, limits=limits)
    if runtime == "codex" and decision.tier == "ask":
        targets, _ = operands(decision.argv)
        if any(not Path(target).is_absolute() for target in targets):
            return Decision("user_runs", "Codex exposes session cwd, not effective tool cwd; use absolute mutation targets or run it yourself")
    return decision


def approve(project, runtime, session, command, cwd, response, undo):
    if runtime not in {"codex", "gemini", "wrapper"}:
        raise ValueError("this runtime must use its native confirmation prompt")
    if not isinstance(session, str) or not session.strip() or response.strip().lower() != "yes" or not undo.strip():
        raise ValueError("record only the user's explicit yes, with the exact session and an undo plan")
    limits = read_policy(project)
    decision = classify_runtime(runtime, command, cwd, project, limits)
    if decision.tier != "ask":
        raise ValueError("approval may only authorize a currently measured tier-2 command: " + decision.reason)
    details = {"runtime": runtime, "session": session, "command": command, "cwd": str(cwd),
               "user_response": response, "effect": decision.effect, "undo": undo}
    return grant(project, binding(runtime, session, command, cwd, limits, decision), details)


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="mode", required=True)
    for mode in ("hook", "classify", "approve", "run"):
        item = sub.add_parser(mode)
        item.add_argument("--project", required=True, type=Path)
        if mode == "hook":
            item.add_argument("--runtime", choices=RUNTIMES[:-1], required=True)
            continue
        item.add_argument("--command", required=True)
        item.add_argument("--cwd", type=Path)
        if mode in {"approve", "run"}:
            item.add_argument("--session-id", required=True)
        if mode == "approve":
            item.add_argument("--runtime", choices=("codex", "gemini", "wrapper"), required=True)
            item.add_argument("--user-response", required=True)
            item.add_argument("--undo", required=True)
    return result


def approval_request(command, runtime, session, cwd, project):
    """Permit only this trusted recorder through its own shell hook.

    This path logs a human yes asserted by a cooperating agent. It is not human
    authentication against malicious code running as the same OS user.
    """
    try:
        args = shlex.split(command)
        if len(args) < 3 or args[:3] != [sys.executable, str(Path(__file__).resolve()), "approve"]:
            return False
        # Avoid argparse printing to stdout/stderr or exiting the hook. Only the
        # fixed recorder options may appear once, each with a value.
        pairs = args[3:]
        expected = {"--project", "--runtime", "--session-id", "--command", "--cwd", "--user-response", "--undo"}
        if len(pairs) != 2 * len(expected) or set(pairs[::2]) != expected:
            return False
        values = dict(zip(pairs[::2], pairs[1::2]))
        if (values["--project"] != str(project) or values["--runtime"] != runtime
                or values["--session-id"] != session or values["--cwd"] != str(cwd)
                or values["--user-response"].strip().lower() != "yes" or not values["--undo"].strip()):
            return False
        # The actual shell could evaluate substitutions inside quoted data even
        # though shlex treats them as strings. Require exact POSIX shell quoting.
        if command != shlex.join(args):
            return False
        return classify_runtime(runtime, values["--command"], cwd, project, read_policy(project)).tier == "ask"
    except (ValueError, OSError):
        return False


def evaluate(runtime, payload, project):
    try:
        if runtime not in RUNTIMES[:-1] or not isinstance(payload, dict):
            raise ValueError("unsupported runtime or malformed hook object")
        event = "BeforeTool" if runtime == "gemini" else "PreToolUse"
        if payload.get("hook_event_name") != event:
            raise ValueError("wrong or missing hook event")
        tool = payload.get("tool_name")
        allowed_tools = {"run_shell_command"} if runtime == "gemini" else {"Bash", "PowerShell"} if runtime == "claude" else {"Bash"}
        if not isinstance(tool, str) or tool not in allowed_tools:
            raise ValueError("unexpected tool; shell adapter does not recognize its input")
        data = payload.get("tool_input")
        if not isinstance(data, dict) or not isinstance(data.get("command"), str):
            raise ValueError("shell input must have a string command")
        if set(data) & {"cwd", "workdir", "directory", "shell"}:
            raise ValueError("unverified shell directory/environment fields; use the documented hook input")
        command = data["command"]
        session = payload.get("session_id")
        if not isinstance(session, str) or not session.strip() or not isinstance(payload.get("cwd"), str):
            raise ValueError("missing hook session or working directory")
        cwd = Path(payload["cwd"])
        if not cwd.is_absolute() or not cwd.is_dir():
            raise ValueError("hook working directory is not an existing absolute directory")
        cwd = cwd.resolve()
        project = Path(project).resolve(strict=True)
        # Gemini exposes dir_path; see its official shell-tool documentation.
        if runtime == "gemini" and data.get("dir_path") is not None:
            if not isinstance(data["dir_path"], str):
                raise ValueError("invalid Gemini dir_path")
            if not Path(data["dir_path"]).is_absolute() and cwd != project:
                raise ValueError("relative Gemini dir_path requires the verified workspace root")
            cwd = (project / data["dir_path"]).resolve(strict=True)
        limits = read_policy(project)
        if tool == "PowerShell" or os.name != "posix":
            decision = Decision("user_runs", "this adapter only measures literal POSIX commands")
        elif approval_request(command, runtime, session, cwd, project):
            audit(project, "approval_path_requested", {"runtime": runtime, "session": session, "command": command})
            return output(runtime, "allow", "Record only the user's prior explicit yes to that exact measured command.")
        else:
            decision = classify_runtime(runtime, command, cwd, project, limits)
        details = {"runtime": runtime, "session": session, "command": command, "cwd": str(cwd), "tier": decision.tier}
        audit(project, "classified", details)
        if decision.tier == "allow":
            return output(runtime, "allow", decision.reason)
        reason = message(decision, command)
        if decision.tier == "ask":
            if runtime == "claude":
                return output(runtime, "ask", f"{decision.effect}; undo: {decision.undo}. Confirm only this exact command: {json.dumps(command)}")
            if consume(project, binding(runtime, session, command, cwd, limits, decision), details):
                return output(runtime, "allow", "Consumed one exact, logged tier-2 approval.")
            reason += recorder_hint(project, runtime, session, command, cwd, decision.undo)
        return output(runtime, "deny", reason)
    except (TypeError, ValueError, OSError, RuntimeError, sqlite3.Error, StateError) as exc:
        return output(runtime, "deny", f"Command guard could not verify this call: {exc}. Repair/check the guard; do not execute.")


def main():
    args = parser().parse_args()
    try:
        project = args.project.resolve(strict=True)
        if args.mode == "hook":
            try:
                raw = sys.stdin.read(1_048_577)
                payload = json.loads(raw) if len(raw) <= 1_048_576 else None
            except (ValueError, UnicodeError):
                payload = None
            print(json.dumps(evaluate(args.runtime, payload, project)))
            return 0
        cwd = (args.cwd or project).resolve(strict=True)
        limits = read_policy(project)
        decision = classify(args.command, cwd, project, limits=limits)
        if args.mode == "classify":
            print(json.dumps(decision.to_dict()))
            return 0
        if args.mode == "approve":
            print(json.dumps(approve(project, args.runtime, args.session_id, args.command, cwd, args.user_response, args.undo)))
            return 0
        if os.name != "posix":
            raise ValueError("fallback execution supports literal POSIX argv only")
        details = {"runtime": "wrapper", "session": args.session_id, "command": args.command,
                   "cwd": str(cwd), "tier": decision.tier}
        audit(project, "classified", details)
        allowed = decision.tier == "allow"
        if decision.tier == "ask":
            allowed = consume(project, binding("wrapper", args.session_id, args.command, cwd, limits, decision), details)
        if not allowed:
            reason = message(decision, args.command)
            if decision.tier == "ask":
                reason += recorder_hint(project, "wrapper", args.session_id, args.command, cwd, decision.undo)
            print(reason, file=sys.stderr)
            return 2
        # Do not invoke a shell or accept piped stdin. argv is the same literal
        # grammar that was measured, not a second interpretation of the string.
        result = subprocess.run(decision.argv, cwd=cwd, stdin=subprocess.DEVNULL, check=False)
        audit(project, "executed", {**details, "returncode": result.returncode})
        return result.returncode
    except (OSError, ValueError, RuntimeError, sqlite3.Error, StateError) as exc:
        if args.mode == "hook":
            print(json.dumps(output(args.runtime, "deny", f"Guard verification failed: {exc}")))
            return 0
        print(f"Command guard refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
