#!/usr/bin/env python3
"""Exercise malformed, denied, and interrupted runtime paths with trusted verification."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from live_runtime_rehearsal import host_os_platform, runtime_command_sha256, utc_now
from operation_receipt import operation_record, receipt_for_operation
from runtime_evidence import validate_entry
from state_io import read_json as state_read_json
from state_store import list_operation_records, reconcile_store


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FORMAT = "aham-brahmasmi-runtime-negative-path-rehearsal"
CONTROLLER_FORMAT = "aham-brahmasmi-runtime-negative-path-controller-verification"
EXECUTION_FORMAT = "aham-brahmasmi-runtime-negative-path-execution"
RESULT_FORMAT = "aham-brahmasmi-runtime-negative-path-result"
REPORT_FORMAT = "aham-brahmasmi-runtime-negative-path-report"
VERSION = 1
MANIFEST_FILE = "negative_manifest.json"
CONTROLLER_FILE = "controller_verified.json"
TARGET_EXECUTION_FILE = "target_execution.json"
RESULT_FILE = "result/recovered.json"
REPORT_FILE = "verified_negative_report.json"
TARGET_TASK = "control/target_task.md"
SANDBOX_TARGET_TASK = "/negative/target_task.md"
SANDBOX_RESULT_DIR = "/evidence"
CRASH_POINT = "wrap_up_after_commit_record"
CONTINUATION_FLAGS = {"--continue", "-c", "--session", "-s", "--attach", "--fork"}


class NegativePathError(RuntimeError):
    """Raised when negative-path evidence cannot be trusted or verified."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify malformed, denied, and interrupted Aham runtime paths.")
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare", help="Create a fresh negative-path rehearsal")
    prepare.add_argument("--root", required=True)

    exercise = sub.add_parser("exercise", help="Run trusted malformed, denied, and writer-interruption probes")
    exercise.add_argument("--root", required=True)

    target = sub.add_parser("run-target", help="Run a fresh runtime to recover the interrupted operation")
    add_run_arguments(target)

    verify = sub.add_parser("verify", help="Independently verify all three negative paths")
    verify.add_argument("--root", required=True)
    verify.add_argument("--json", action="store_true")
    return parser.parse_args()


def add_run_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", required=True)
    parser.add_argument("--sudo-namespace-helper", action="store_true")
    parser.add_argument("--deny-network", action="store_true")
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument("--model")
    parser.add_argument("--harness")
    parser.add_argument("--harness-version")
    parser.add_argument("--context-tokens", type=int)
    parser.add_argument("--quantization")
    parser.add_argument("--pass-env", action="append", default=[], metavar="NAME")
    parser.add_argument("--env", action="append", default=[], metavar="NAME=VALUE")
    parser.add_argument("--ro-bind", action="append", default=[], metavar="HOST:GUEST")
    parser.add_argument("--rw-bind", action="append", default=[], metavar="HOST:GUEST")
    parser.add_argument("runtime_command", nargs=argparse.REMAINDER)


def run_capture(command: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    result = run_capture(command)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise NegativePathError(f"command failed: {' '.join(command)}\n{detail}")
    return result


def run_script(name: str, *args: str) -> subprocess.CompletedProcess[str]:
    path = SCRIPTS / name
    if not path.is_file():
        raise NegativePathError(f"required framework script is missing: scripts/{name}")
    return run([sys.executable, str(path), *args])


def git(*args: str) -> str:
    return run(["git", "-C", str(ROOT), *args]).stdout.strip()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NegativePathError(f"could not read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise NegativePathError(f"expected a JSON object in {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def state_digest(manifest: dict[str, Any], revision: int, checkpoint_id: str) -> str:
    payload = {
        "rehearsal_id": manifest["rehearsal_id"],
        "operation_id": manifest["interrupted_operation_id"],
        "fact": manifest["interrupted_fact"],
        "revision": revision,
        "checkpoint_id": checkpoint_id,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def resolve_root(value: str, *, for_prepare: bool = False) -> Path:
    raw = Path(value).expanduser()
    if raw.is_symlink():
        raise NegativePathError("negative-path rehearsal root may not be a symlink")
    root = raw.resolve()
    if for_prepare:
        if root.exists():
            if not root.is_dir():
                raise NegativePathError("negative-path rehearsal root exists but is not a directory")
            if any(root.iterdir()):
                raise NegativePathError("negative-path rehearsal root must be new or empty")
        else:
            root.mkdir(parents=True)
    elif not root.is_dir():
        raise NegativePathError("negative-path rehearsal root does not exist")
    return root


def render_target_task(manifest: dict[str, Any]) -> str:
    return f"""# Interrupted-operation recovery session

This is a fresh recovery runtime. It has no prior chat/session from the controller that created the interrupted write. The durable fact value is intentionally absent from this task.

Rehearsal ID: `{manifest['rehearsal_id']}`

1. Read `/work/project/.aham/runtime.md` and `/work/project/.aham/runtime.json`.
2. Run `python3 /framework/scripts/verify_workspace.py --workspace /work/workspace` and require `WORKSPACE VERIFIED`.
3. Run startup in `wrap_up` mode with the capabilities actually available:

```text
python3 /framework/scripts/startup.py --workspace /work/workspace --runtime local --mode wrap_up --capability read_files --capability write_files --capability run_commands --harness negative-target:{manifest['rehearsal_id']} --json
```

Require `ready: true`, `pending_wrap_up: true`, and retain the exact issued `session_authority.session_id`.

4. Recover the interrupted operation with the exact issued session ID:

```text
python3 /framework/scripts/wrap_up.py --workspace /work/workspace --recover-pending --session-id SESSION_ID
```

Require both `WRAP UP COMPLETE` and `WRAP UP VERIFIED`.

5. Run:

```text
python3 /framework/scripts/resume.py --workspace /work/workspace
```

Require `RESUME STATE VERIFIED: durable checkpoint continuation`.

6. Recover from the durable Brain only:
- the durable fact from the interrupted operation;
- the recovered revision;
- the recovered checkpoint ID.

Do not invent missing values and do not ask the person to locate a handoff file.

7. Write exactly one result file at `/evidence/recovered.json`:

```json
{{
  "format": "{RESULT_FORMAT}",
  "version": 1,
  "rehearsal_id": "{manifest['rehearsal_id']}",
  "recovered_fact": "EXACT RECOVERED FACT",
  "recovered_revision": 2,
  "recovered_checkpoint_id": "EXACT RECOVERED CHECKPOINT ID",
  "resume_verified": true
}}
```

Replace only the placeholder values with the exact values recovered from durable state. Then stop.
"""


def prepare(root_value: str) -> int:
    root = resolve_root(root_value, for_prepare=True)
    workspace = root / "workspace"
    project = root / "project"
    control = root / "control"
    result = root / "result"
    project.mkdir()
    control.mkdir()
    result.mkdir()

    setup = run_script("setup_workspace.py", "--workspace", str(workspace))
    if "WORKSPACE CREATED" not in setup.stdout:
        raise NegativePathError("workspace setup did not report success")
    checked = run_script("verify_workspace.py", "--workspace", str(workspace))
    if "WORKSPACE VERIFIED" not in checked.stdout:
        raise NegativePathError("workspace verification did not report success")
    bridge = run_script(
        "runtime_bridge.py",
        "install",
        "--runtime",
        "local",
        "--workspace",
        str(workspace),
        "--project",
        str(project),
    )
    if "RUNTIME BRIDGE INSTALLED" not in bridge.stdout:
        raise NegativePathError("runtime bridge installation did not report success")

    brain = state_read_json(workspace / "BRAIN.json")
    workspace_id = brain.get("workspace_id")
    if not isinstance(workspace_id, str) or not workspace_id:
        raise NegativePathError("prepared workspace has no stable identity")

    rehearsal_id = uuid.uuid4().hex[:16]
    manifest: dict[str, Any] = {
        "format": FORMAT,
        "version": VERSION,
        "rehearsal_id": rehearsal_id,
        "framework_commit": git("rev-parse", "HEAD").lower(),
        "workspace_id": workspace_id,
        "workspace": str(workspace),
        "project": str(project),
        "malformed_marker": f"Malformed request marker {rehearsal_id}",
        "interrupted_operation_id": f"negative-interrupt-{rehearsal_id}",
        "interrupted_fact": f"Interrupted recovery fact {rehearsal_id}",
        "checkpoint_summary": f"Interrupted recovery checkpoint {rehearsal_id}",
        "prepared_at": utc_now(),
    }
    if len(manifest["framework_commit"]) != 40:
        raise NegativePathError("framework checkout did not report an exact commit")
    target_task = control / "target_task.md"
    target_task.write_text(render_target_task(manifest), encoding="utf-8")
    manifest["target_task_sha256"] = sha256_file(target_task)
    write_json(root / MANIFEST_FILE, manifest)

    print("RUNTIME NEGATIVE-PATH REHEARSAL PREPARED")
    print(f"Rehearsal ID: {rehearsal_id}")
    print(f"Root: {root}")
    print("Next: run trusted controller probes with exercise.")
    return 0


def validate_manifest(root: Path) -> tuple[dict[str, Any], Path, Path]:
    path = root / MANIFEST_FILE
    if path.is_symlink() or not path.is_file():
        raise NegativePathError("negative-path manifest is missing or unsafe")
    manifest = read_json(path)
    expected = {
        "format", "version", "rehearsal_id", "framework_commit", "workspace_id", "workspace", "project",
        "malformed_marker", "interrupted_operation_id", "interrupted_fact", "checkpoint_summary", "prepared_at",
        "target_task_sha256",
    }
    if set(manifest) != expected:
        raise NegativePathError("negative-path manifest fields are not recognized")
    if manifest.get("format") != FORMAT or manifest.get("version") != VERSION:
        raise NegativePathError("negative-path manifest format/version is not recognized")
    workspace = (root / "workspace").resolve()
    project = (root / "project").resolve()
    if manifest.get("workspace") != str(workspace) or manifest.get("project") != str(project):
        raise NegativePathError("negative-path manifest paths do not match the prepared root")
    brain = state_read_json(workspace / "BRAIN.json")
    if brain.get("workspace_id") != manifest.get("workspace_id"):
        raise NegativePathError("negative-path workspace identity changed")
    if manifest.get("framework_commit") != git("rev-parse", "HEAD").lower():
        raise NegativePathError("current framework checkout does not match the prepared rehearsal")
    if sha256_file(root / TARGET_TASK) != manifest["target_task_sha256"]:
        raise NegativePathError("target recovery task changed after preparation")
    return manifest, workspace, project


def no_durable_operations(workspace: Path) -> bool:
    return not list_operation_records(workspace) and reconcile_store(workspace)["revision"] == 0


def exercise(root_value: str) -> int:
    root = resolve_root(root_value)
    manifest, workspace, _project = validate_manifest(root)
    controller_path = root / CONTROLLER_FILE
    if controller_path.exists() or controller_path.is_symlink():
        raise NegativePathError("controller verification evidence already exists; exercise is single-use")
    if not no_durable_operations(workspace):
        raise NegativePathError("negative-path workspace is not at revision zero before exercise")

    malformed_bundle = root / "control" / "malformed.json"
    write_json(
        malformed_bundle,
        {
            "operation_id": f"malformed-{manifest['rehearsal_id']}",
            "factz": [manifest["malformed_marker"]],
            "checkpoint": {"summary": "malformed request must be rejected"},
        },
    )
    malformed = run_capture(
        [sys.executable, str(SCRIPTS / "wrap_up.py"), "--workspace", str(workspace), "--bundle", str(malformed_bundle)]
    )
    malformed_zero_mutation = (
        malformed.returncode != 0
        and "unknown field" in (malformed.stderr + malformed.stdout).lower()
        and not (workspace / "state" / "pending_wrap_up.json").exists()
        and no_durable_operations(workspace)
        and manifest["malformed_marker"] not in (workspace / "MEMORY.md").read_text(encoding="utf-8")
    )
    if not malformed_zero_mutation:
        raise NegativePathError("malformed request did not fail with zero durable mutation")

    degraded = run_script(
        "startup.py",
        "--workspace",
        str(workspace),
        "--runtime",
        "local",
        "--mode",
        "degraded_offline",
        "--harness",
        f"negative-denied:{manifest['rehearsal_id']}",
        "--json",
    )
    degraded_report = json.loads(degraded.stdout)
    session_id = degraded_report.get("session_authority", {}).get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise NegativePathError("degraded startup did not issue a session identity")
    denied = run_capture(
        [
            sys.executable,
            str(SCRIPTS / "checkpoint.py"),
            "--workspace",
            str(workspace),
            "--summary",
            f"denied checkpoint {manifest['rehearsal_id']}",
            "--session-id",
            session_id,
        ]
    )
    denied_zero_mutation = (
        denied.returncode != 0
        and "authority" in (denied.stderr + denied.stdout).lower()
        and not (workspace / "state" / "pending_checkpoint.json").exists()
        and no_durable_operations(workspace)
    )
    if not denied_zero_mutation:
        raise NegativePathError("permission-denied operation did not fail with zero durable mutation")

    # The explicit synthetic controller grants trust only after both zero-mutation probes.
    trust = run_script("runtime_trust.py", "trust", "local", "--workspace", str(workspace), "--confirm", "local")
    if trust.returncode != 0:
        raise NegativePathError("synthetic controller runtime trust failed")
    writable = run_script(
        "startup.py",
        "--workspace",
        str(workspace),
        "--runtime",
        "local",
        "--mode",
        "regular",
        "--capability",
        "read_files",
        "--capability",
        "write_files",
        "--capability",
        "run_commands",
        "--harness",
        f"negative-interrupt-controller:{manifest['rehearsal_id']}",
        "--json",
    )
    writable_report = json.loads(writable.stdout)
    write_session = writable_report.get("session_authority", {}).get("session_id")
    if not isinstance(write_session, str) or not write_session:
        raise NegativePathError("write-capable startup did not issue a session identity")

    interrupted_bundle = root / "control" / "interrupted.json"
    write_json(
        interrupted_bundle,
        {
            "operation_id": manifest["interrupted_operation_id"],
            "durable_facts": [manifest["interrupted_fact"]],
            "unfinished_work": [],
            "reusable_lessons": [],
            "project_updates": [],
            "history": [],
            "checkpoint": {
                "summary": manifest["checkpoint_summary"],
                "completed": ["Writer accepted the interrupted operation."],
                "next_steps": ["Recover the pending operation in a fresh runtime."],
                "artifacts": [],
                "project": None,
            },
        },
    )
    crash_env = os.environ.copy()
    crash_env["AHAM_BRAHMASMI_TEST_MODE"] = "1"
    crash_env["AHAM_BRAHMASMI_TEST_CRASH_POINT"] = CRASH_POINT
    interrupted = run_capture(
        [
            sys.executable,
            str(SCRIPTS / "wrap_up.py"),
            "--workspace",
            str(workspace),
            "--bundle",
            str(interrupted_bundle),
            "--session-id",
            write_session,
        ],
        env=crash_env,
    )
    if interrupted.returncode != 86:
        raise NegativePathError(f"writer interruption returned {interrupted.returncode}, expected 86")
    pending_path = workspace / "state" / "pending_wrap_up.json"
    if not pending_path.is_file():
        raise NegativePathError("writer interruption did not preserve pending wrap-up state")
    pending = state_read_json(pending_path)
    if pending.get("operation_id") != manifest["interrupted_operation_id"]:
        raise NegativePathError("pending interrupted operation identity does not match the rehearsal")

    record = operation_record(workspace, manifest["interrupted_operation_id"], expected_kind="wrap_up")
    receipt = receipt_for_operation(workspace, manifest["interrupted_operation_id"], expected_kind="wrap_up")
    revision = record.get("revision")
    checkpoint = receipt.get("checkpoint")
    if not isinstance(revision, int) or revision < 1:
        raise NegativePathError("interrupted operation has no committed revision")
    if not isinstance(checkpoint, dict) or not isinstance(checkpoint.get("id"), str):
        raise NegativePathError("interrupted operation has no committed checkpoint identity")
    if (workspace / "state" / "wrapups" / f"{manifest['interrupted_operation_id']}.json").exists():
        raise NegativePathError("writer interruption unexpectedly reached the final wrap-up receipt boundary")
    if (workspace / "MEMORY.md").read_text(encoding="utf-8").count(manifest["interrupted_fact"]) != 1:
        raise NegativePathError("interrupted accepted fact is not present exactly once before recovery")

    cached_store = state_read_json(workspace / "state" / "store.json")
    controller = {
        "format": CONTROLLER_FORMAT,
        "version": VERSION,
        "rehearsal_id": manifest["rehearsal_id"],
        "framework_commit": manifest["framework_commit"],
        "malformed_rejected": True,
        "malformed_exit_code": int(malformed.returncode),
        "malformed_stderr_sha256": sha256_text(malformed.stderr),
        "malformed_zero_mutation": True,
        "denied_rejected": True,
        "denied_exit_code": int(denied.returncode),
        "denied_stderr_sha256": sha256_text(denied.stderr),
        "denied_zero_mutation": True,
        "interrupted_operation_id": manifest["interrupted_operation_id"],
        "crash_point": CRASH_POINT,
        "writer_crash_exit_code": int(interrupted.returncode),
        "source_revision": revision,
        "source_checkpoint_id": checkpoint["id"],
        "state_digest": state_digest(manifest, revision, checkpoint["id"]),
        "pending_preserved": True,
        "final_receipt_absent": True,
        "cached_store_revision_after_crash": cached_store.get("revision"),
        "verified_at": utc_now(),
    }
    write_json(controller_path, controller)
    print("RUNTIME NEGATIVE-PATH CONTROLLER PROBES VERIFIED")
    print(f"Rehearsal ID: {manifest['rehearsal_id']}")
    print("Malformed request: rejected with zero durable mutation")
    print("Denied operation: rejected with zero durable mutation")
    print(f"Interrupted writer: exit 86 at {CRASH_POINT}")
    print(f"Committed revision before recovery: {revision}")
    print(f"Pending operation: {manifest['interrupted_operation_id']}")
    return 0


def validate_controller(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    path = root / CONTROLLER_FILE
    if path.is_symlink() or not path.is_file():
        raise NegativePathError("trusted controller verification record is missing")
    value = read_json(path)
    expected = {
        "format", "version", "rehearsal_id", "framework_commit", "malformed_rejected", "malformed_exit_code",
        "malformed_stderr_sha256", "malformed_zero_mutation", "denied_rejected", "denied_exit_code",
        "denied_stderr_sha256", "denied_zero_mutation", "interrupted_operation_id", "crash_point",
        "writer_crash_exit_code", "source_revision", "source_checkpoint_id", "state_digest", "pending_preserved",
        "final_receipt_absent", "cached_store_revision_after_crash", "verified_at",
    }
    if set(value) != expected or value.get("format") != CONTROLLER_FORMAT or value.get("version") != VERSION:
        raise NegativePathError("controller verification record fields are not recognized")
    if value.get("rehearsal_id") != manifest["rehearsal_id"] or value.get("framework_commit") != manifest["framework_commit"]:
        raise NegativePathError("controller verification identity does not match the rehearsal")
    if value.get("malformed_rejected") is not True or value.get("malformed_zero_mutation") is not True:
        raise NegativePathError("controller did not verify malformed-request rejection")
    if value.get("denied_rejected") is not True or value.get("denied_zero_mutation") is not True:
        raise NegativePathError("controller did not verify permission denial")
    if value.get("writer_crash_exit_code") != 86 or value.get("crash_point") != CRASH_POINT:
        raise NegativePathError("controller did not verify the required writer interruption")
    if value.get("interrupted_operation_id") != manifest["interrupted_operation_id"]:
        raise NegativePathError("controller interrupted operation identity does not match")
    revision = value.get("source_revision")
    checkpoint = value.get("source_checkpoint_id")
    if not isinstance(revision, int) or revision < 1 or not isinstance(checkpoint, str) or not checkpoint:
        raise NegativePathError("controller source revision/checkpoint is invalid")
    if value.get("state_digest") != state_digest(manifest, revision, checkpoint):
        raise NegativePathError("controller state digest no longer matches the rehearsal")
    for field in ("malformed_stderr_sha256", "denied_stderr_sha256", "state_digest"):
        if not isinstance(value.get(field), str) or len(value[field]) != 64:
            raise NegativePathError(f"controller {field} is invalid")
    return value


def optional_string(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise NegativePathError(f"{field} must be a non-empty string when provided")
    return value.strip()


def command_has_continuation(command: list[str]) -> bool:
    for token in command:
        if token in CONTINUATION_FLAGS:
            return True
        if any(token.startswith(flag + "=") for flag in CONTINUATION_FLAGS if flag.startswith("--")):
            return True
    return False


def target_binding_exposes_controller(root: Path, binding: str) -> bool:
    if ":" not in binding:
        return True
    host = Path(binding.split(":", 1)[0]).expanduser().resolve()
    sensitive = [root / MANIFEST_FILE, root / CONTROLLER_FILE, root / "control"]
    return any(host == item.resolve() or host in item.resolve().parents for item in sensitive)


def target_permission_mode(args: argparse.Namespace) -> str:
    return ";".join(
        [
            "bubblewrap",
            f"network={'denied' if args.deny_network else 'shared'}",
            f"stdin={'closed' if args.non_interactive else 'open'}",
            f"extra_ro_binds={len(args.ro_bind) + 1}",
            "extra_rw_binds=1",
            f"pass_env={len(args.pass_env)}",
            f"set_env={len(args.env)}",
            f"namespace_helper={'on' if args.sudo_namespace_helper else 'off'}",
        ]
    )


def run_target(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    manifest, workspace, project = validate_manifest(root)
    validate_controller(root, manifest)
    execution_path = root / TARGET_EXECUTION_FILE
    if execution_path.exists() or execution_path.is_symlink():
        raise NegativePathError("target execution evidence already exists; target phase is single-use")
    if not (workspace / "state" / "pending_wrap_up.json").is_file():
        raise NegativePathError("interrupted pending operation must exist before fresh target recovery")
    if args.rw_bind:
        raise NegativePathError("fresh target recovery forbids user-supplied read-write binds")
    if any(target_binding_exposes_controller(root, binding) for binding in args.ro_bind):
        raise NegativePathError("fresh target recovery may not expose controller-only evidence")

    command = list(args.runtime_command)
    if command and command[0] == "--":
        command.pop(0)
    if not command:
        raise NegativePathError("provide a runtime command after --")
    if command_has_continuation(command):
        raise NegativePathError("fresh target recovery may not use session continuation/attach flags")
    if args.context_tokens is not None and (isinstance(args.context_tokens, bool) or args.context_tokens <= 0):
        raise NegativePathError("context_tokens must be a positive integer when provided")

    invocation = [
        sys.executable,
        str(SCRIPTS / "rehearsal_sandbox.py"),
        "run",
        "--workspace",
        str(workspace),
        "--project",
        str(project),
    ]
    if args.sudo_namespace_helper:
        invocation.append("--sudo-namespace-helper")
    if args.deny_network:
        invocation.append("--deny-network")
    for name in args.pass_env:
        invocation.extend(["--pass-env", name])
    for assignment in args.env:
        invocation.extend(["--env", assignment])
    for binding in args.ro_bind:
        invocation.extend(["--ro-bind", binding])
    invocation.extend(["--ro-bind", f"{root / TARGET_TASK}:{SANDBOX_TARGET_TASK}"])
    invocation.extend(["--rw-bind", f"{root / 'result'}:{SANDBOX_RESULT_DIR}"])
    invocation.extend(["--", *command])

    result = subprocess.run(
        invocation,
        cwd=ROOT,
        text=True,
        check=False,
        stdin=subprocess.DEVNULL if args.non_interactive else None,
    )
    record = {
        "format": EXECUTION_FORMAT,
        "version": VERSION,
        "phase": "target",
        "rehearsal_id": manifest["rehearsal_id"],
        "framework_commit": manifest["framework_commit"],
        "runtime_profile": "local",
        "model": optional_string(args.model, "model"),
        "harness": optional_string(args.harness, "harness"),
        "harness_version": optional_string(args.harness_version, "harness_version"),
        "context_tokens": args.context_tokens,
        "quantization": optional_string(args.quantization, "quantization"),
        "os_platform": host_os_platform(),
        "permission_mode": target_permission_mode(args),
        "human_intervention": False if args.non_interactive else None,
        "runtime_command_sha256": runtime_command_sha256(command),
        "exit_code": int(result.returncode),
        "fresh_session": bool(args.non_interactive and not command_has_continuation(command)),
        "recorded_at": utc_now(),
    }
    write_json(execution_path, record)
    if result.returncode != 0:
        print(f"RUNTIME NEGATIVE-PATH TARGET FAILED: exit {result.returncode}", file=sys.stderr)
    return int(result.returncode)


def validate_target_execution(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    path = root / TARGET_EXECUTION_FILE
    if path.is_symlink() or not path.is_file():
        raise NegativePathError("target execution record is missing or unsafe")
    value = read_json(path)
    expected = {
        "format", "version", "phase", "rehearsal_id", "framework_commit", "runtime_profile", "model", "harness",
        "harness_version", "context_tokens", "quantization", "os_platform", "permission_mode", "human_intervention",
        "runtime_command_sha256", "exit_code", "fresh_session", "recorded_at",
    }
    if set(value) != expected or value.get("format") != EXECUTION_FORMAT or value.get("version") != VERSION:
        raise NegativePathError("target execution record fields are not recognized")
    if value.get("phase") != "target" or value.get("rehearsal_id") != manifest["rehearsal_id"]:
        raise NegativePathError("target execution identity does not match the rehearsal")
    if value.get("framework_commit") != manifest["framework_commit"] or value.get("runtime_profile") != "local":
        raise NegativePathError("target execution framework/runtime identity does not match")
    if value.get("exit_code") != 0:
        raise NegativePathError("target execution record shows a failed runtime command")
    if value.get("fresh_session") is not True:
        raise NegativePathError("target execution was not recorded as a fresh session")
    digest = value.get("runtime_command_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise NegativePathError("target execution command digest is invalid")
    for field in ("os_platform", "permission_mode", "recorded_at"):
        if not isinstance(value.get(field), str) or not value[field].strip():
            raise NegativePathError(f"target execution {field} is invalid")
    return value


def validate_result(root: Path, manifest: dict[str, Any], controller: dict[str, Any]) -> dict[str, Any]:
    path = root / RESULT_FILE
    if path.is_symlink() or not path.is_file():
        raise NegativePathError("target recovery result is missing or unsafe")
    value = read_json(path)
    expected = {"format", "version", "rehearsal_id", "recovered_fact", "recovered_revision", "recovered_checkpoint_id", "resume_verified"}
    if set(value) != expected or value.get("format") != RESULT_FORMAT or value.get("version") != VERSION:
        raise NegativePathError("target recovery result fields are not recognized")
    if value.get("rehearsal_id") != manifest["rehearsal_id"]:
        raise NegativePathError("target recovery result rehearsal identity does not match")
    if value.get("recovered_fact") != manifest["interrupted_fact"]:
        raise NegativePathError("target recovered fact does not match the interrupted accepted write")
    if value.get("recovered_revision") != controller["source_revision"]:
        raise NegativePathError("target recovered_revision does not match the accepted write revision")
    if value.get("recovered_checkpoint_id") != controller["source_checkpoint_id"]:
        raise NegativePathError("target recovered checkpoint does not match the accepted write checkpoint")
    if value.get("resume_verified") is not True:
        raise NegativePathError("target did not report verified durable resume")
    return value


def verify(root_value: str, as_json: bool) -> int:
    root = resolve_root(root_value)
    manifest, workspace, _project = validate_manifest(root)
    controller = validate_controller(root, manifest)
    target = validate_target_execution(root, manifest)
    recovered = validate_result(root, manifest, controller)

    if (workspace / "state" / "pending_wrap_up.json").exists():
        raise NegativePathError("interrupted pending wrap-up still exists after target recovery")
    receipt = receipt_for_operation(workspace, manifest["interrupted_operation_id"], expected_kind="wrap_up")
    checkpoint = receipt.get("checkpoint")
    if receipt.get("revision") != controller["source_revision"]:
        raise NegativePathError("recovered operation revision changed from the accepted write")
    if not isinstance(checkpoint, dict) or checkpoint.get("id") != controller["source_checkpoint_id"]:
        raise NegativePathError("recovered operation checkpoint changed from the accepted write")
    if reconcile_store(workspace)["revision"] != controller["source_revision"]:
        raise NegativePathError("authoritative store did not reconcile to the accepted write revision")
    if (workspace / "MEMORY.md").read_text(encoding="utf-8").count(manifest["interrupted_fact"]) != 1:
        raise NegativePathError("interrupted durable fact was not conserved exactly once after recovery")
    resume = run_script("resume.py", "--workspace", str(workspace))
    if "RESUME STATE VERIFIED: durable checkpoint continuation" not in resume.stdout:
        raise NegativePathError("trusted host resume did not verify recovered continuation")
    if f"Revision: {controller['source_revision']}" not in resume.stdout or f"Checkpoint: {controller['source_checkpoint_id']}" not in resume.stdout:
        raise NegativePathError("trusted host resume did not select the accepted write revision/checkpoint")

    verified_at = utc_now()
    limitations = [
        "Malformed-request and permission-denied probes are trusted controller checks of Aham's writer/authority interfaces; they do not require a language model to generate the invalid action.",
        "The interrupted-write probe uses Aham's test-only crash injection at wrap_up_after_commit_record, which terminates the writer process with exit code 86 after the immutable operation record is accepted.",
        "Target model/harness metadata is declared to the trusted host wrapper; the verifier does not introspect third-party runtime internals.",
        "This is one negative-path rehearsal, not a reliability percentage or proof that every failure mode is covered.",
    ]
    evidence = {
        "entry_id": f"negative-{manifest['rehearsal_id']}",
        "evidence_type": "runtime_failure_paths",
        "rehearsal_id": manifest["rehearsal_id"],
        "framework_commit": manifest["framework_commit"],
        "malformed_exit_code": controller["malformed_exit_code"],
        "malformed_stderr_sha256": controller["malformed_stderr_sha256"],
        "malformed_zero_mutation": controller["malformed_zero_mutation"],
        "denied_exit_code": controller["denied_exit_code"],
        "denied_stderr_sha256": controller["denied_stderr_sha256"],
        "denied_zero_mutation": controller["denied_zero_mutation"],
        "interrupted_operation_id": controller["interrupted_operation_id"],
        "crash_point": controller["crash_point"],
        "writer_crash_exit_code": controller["writer_crash_exit_code"],
        "source_revision": controller["source_revision"],
        "recovered_revision": recovered["recovered_revision"],
        "source_checkpoint_id": controller["source_checkpoint_id"],
        "recovered_checkpoint_id": recovered["recovered_checkpoint_id"],
        "state_digest": controller["state_digest"],
        "target_runtime_profile": target["runtime_profile"],
        "target_model": target.get("model"),
        "target_harness": target.get("harness"),
        "target_harness_version": target.get("harness_version"),
        "target_context_tokens": target.get("context_tokens"),
        "target_quantization": target.get("quantization"),
        "target_os_platform": target["os_platform"],
        "target_permission_mode": target["permission_mode"],
        "target_human_intervention": target.get("human_intervention"),
        "target_runtime_command_sha256": target["runtime_command_sha256"],
        "fresh_target_session": True,
        "result": "pass",
        "verified_at": verified_at,
        "independently_verified": True,
        "claim_scope": "single_failure_path_rehearsal",
        "source": REPORT_FILE,
        "limitations": limitations,
    }
    evidence = validate_entry(evidence)
    report = {
        "format": REPORT_FORMAT,
        "version": VERSION,
        "verified": True,
        "rehearsal_id": manifest["rehearsal_id"],
        "framework_commit": manifest["framework_commit"],
        "verified_at": verified_at,
        "checks": [
            "intentionally malformed wrap-up request was rejected before durable mutation",
            "degraded/read-only authority denied a checkpoint with zero durable mutation",
            f"writer terminated with exit 86 at {CRASH_POINT} after the immutable operation record was accepted",
            "pending interrupted operation was preserved for recovery",
            "fresh target runtime recovered the pending operation without session continuation flags",
            "recovered revision and checkpoint exactly matched the accepted interrupted write",
            "interrupted durable fact survived exactly once",
            "trusted host resume independently selected the same recovered revision and checkpoint",
        ],
        "runtime_evidence": evidence,
    }
    report_path = root / REPORT_FILE
    if report_path.exists() or report_path.is_symlink():
        raise NegativePathError("verified negative-path report already exists; refusing overwrite")
    write_json(report_path, report)
    if as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("RUNTIME NEGATIVE-PATH REHEARSAL VERIFIED")
        print(f"Rehearsal ID: {manifest['rehearsal_id']}")
        print(f"Recovered revision: {recovered['recovered_revision']}")
        print(f"Recovered checkpoint: {recovered['recovered_checkpoint_id']}")
        print(f"Report: {report_path}")
    return 0


def main() -> int:
    args = parse_args()
    try:
        if args.command == "prepare":
            return prepare(args.root)
        if args.command == "exercise":
            return exercise(args.root)
        if args.command == "run-target":
            return run_target(args)
        if args.command == "verify":
            return verify(args.root, args.json)
        raise NegativePathError("unknown command")
    except (NegativePathError, OSError, KeyError, TypeError, ValueError) as exc:
        print(f"RUNTIME NEGATIVE-PATH FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
