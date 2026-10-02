#!/usr/bin/env python3
"""Prepare, run, and independently verify a two-session runtime switch recovery rehearsal."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from live_runtime_rehearsal import host_os_platform, runtime_command_sha256, utc_now
from operation_receipt import operation_record, receipt_for_operation
from runtime_evidence import build_switch_recovery_entry
from state_io import read_json as state_read_json


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FORMAT = "aham-brahmasmi-runtime-switch-rehearsal"
EXECUTION_FORMAT = "aham-brahmasmi-runtime-switch-execution"
SOURCE_VERIFIED_FORMAT = "aham-brahmasmi-runtime-switch-source-verification"
RESULT_FORMAT = "aham-brahmasmi-runtime-switch-recovery-result"
REPORT_FORMAT = "aham-brahmasmi-runtime-switch-report"
VERSION = 1
MANIFEST_FILE = "switch_manifest.json"
SOURCE_EXECUTION_FILE = "source_execution.json"
TARGET_EXECUTION_FILE = "target_execution.json"
SOURCE_VERIFIED_FILE = "source_verified.json"
REPORT_FILE = "verified_switch_report.json"
SOURCE_TASK = "control/source_task.md"
TARGET_TASK = "control/target_task.md"
RESULT_FILE = "result/recovered.json"
SANDBOX_SOURCE_TASK = "/switch/source_task.md"
SANDBOX_TARGET_TASK = "/switch/target_task.md"
SANDBOX_RESULT_DIR = "/evidence"
CONTINUATION_FLAGS = {"--continue", "-c", "--session", "-s", "--attach", "--fork"}


class SwitchError(RuntimeError):
    """Raised when a runtime-switch rehearsal cannot be trusted or verified."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a fresh runtime/harness switch through durable Aham state.")
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare", help="Create a fresh synthetic switch-recovery rehearsal")
    prepare.add_argument("--root", required=True)

    for name, help_text in (
        ("run-source", "Run runtime A, which must persist the source state"),
        ("run-target", "Run fresh runtime B, which must recover only from durable state"),
    ):
        run_parser = sub.add_parser(name, help=help_text)
        add_run_arguments(run_parser)

    verify_source_parser = sub.add_parser("verify-source", help="Independently verify runtime A's committed source state")
    verify_source_parser.add_argument("--root", required=True)

    verify = sub.add_parser("verify", help="Independently verify runtime B recovered the exact source state")
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


def run(command: list[str], *, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise SwitchError(f"command failed: {' '.join(command)}\n{detail}")
    return result


def run_script(name: str, *args: str) -> subprocess.CompletedProcess[str]:
    path = SCRIPTS / name
    if not path.is_file():
        raise SwitchError(f"required framework script is missing: scripts/{name}")
    return run([sys.executable, str(path), *args])


def git(*args: str) -> str:
    return run(["git", "-C", str(ROOT), *args]).stdout.strip()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SwitchError(f"could not read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SwitchError(f"expected a JSON object in {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def tree_digest(root: Path) -> str:
    entries: list[dict[str, str]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            entries.append({"path": relative, "type": "symlink", "target": str(path.readlink())})
        elif path.is_file():
            entries.append({"path": relative, "type": "file", "sha256": sha256_file(path)})
        elif path.is_dir():
            entries.append({"path": relative, "type": "dir"})
    encoded = json.dumps(entries, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return sha256_bytes(encoded)


def state_digest(manifest: dict[str, Any], revision: int, checkpoint_id: str) -> str:
    payload = {
        "durable_fact": manifest["durable_fact"],
        "unfinished_task": manifest["unfinished_task"],
        "project_update": manifest["project_update"],
        "source_revision": revision,
        "source_checkpoint_id": checkpoint_id,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return sha256_bytes(encoded)


def resolve_root(value: str, *, for_prepare: bool = False) -> Path:
    raw = Path(value).expanduser()
    if raw.is_symlink():
        raise SwitchError("switch rehearsal root may not be a symlink")
    root = raw.resolve()
    if for_prepare:
        if root.exists():
            if not root.is_dir():
                raise SwitchError("switch rehearsal root exists but is not a directory")
            if any(root.iterdir()):
                raise SwitchError("switch rehearsal root must be new or empty")
        else:
            root.mkdir(parents=True)
    elif not root.is_dir():
        raise SwitchError("switch rehearsal root does not exist")
    return root


def render_source_task(manifest: dict[str, Any]) -> str:
    return f"""# Runtime switch source session

This is runtime A. Complete the steps using actual framework commands. Do not merely describe them.

1. Read `/work/project/.aham/runtime.md` and `/work/project/.aham/runtime.json`.
2. Run `python3 /framework/scripts/verify_workspace.py --workspace /work/workspace` and require `WORKSPACE VERIFIED`.
3. Probe read, write and command execution. Then run startup in Regular mode with exactly the capabilities actually verified:

```text
python3 /framework/scripts/startup.py --workspace /work/workspace --runtime local --mode regular --capability read_files --capability write_files --capability run_commands --harness runtime-switch-source:{manifest['switch_id']} --json
```

Retain the exact issued `session_authority.session_id`.

4. Create `/tmp/runtime-switch-source-bundle.json` with exactly this canonical payload:

```json
{{
  "operation_id": "{manifest['source_operation_id']}",
  "durable_facts": ["{manifest['durable_fact']}"],
  "unfinished_work": ["{manifest['unfinished_task']}"],
  "reusable_lessons": [],
  "project_updates": [
    {{"project": "{manifest['project_name']}", "content": "{manifest['project_update']}"}}
  ],
  "history": [],
  "checkpoint": {{
    "summary": "{manifest['checkpoint_summary']}",
    "completed": ["Runtime A committed the switch-source state."],
    "next_steps": ["{manifest['checkpoint_next_step']}"],
    "artifacts": [],
    "project": "{manifest['project_name']}"
  }}
}}
```

5. Run:

```text
python3 /framework/scripts/wrap_up.py --workspace /work/workspace --bundle /tmp/runtime-switch-source-bundle.json --session-id SESSION_ID
```

Replace `SESSION_ID` with the exact startup-issued session ID. Require both `WRAP UP COMPLETE` and `WRAP UP VERIFIED`.

6. Stop. Do not create any handoff file in the project or workspace. The trusted host will independently verify the committed state before runtime B starts.
"""


def render_target_task(manifest: dict[str, Any]) -> str:
    return f"""# Runtime switch recovery session

This is runtime B. Treat this as a fresh session with no prior chat or runtime-A conversation. The source marker values are intentionally absent from this task.

Switch ID: `{manifest['switch_id']}`

1. Read `/work/project/.aham/runtime.md` and `/work/project/.aham/runtime.json`. Do not ask the person to locate a handoff file.
2. Run `python3 /framework/scripts/verify_workspace.py --workspace /work/workspace` and require `WORKSPACE VERIFIED`.
3. Run Regular-mode startup without Aham write authority:

```text
python3 /framework/scripts/startup.py --workspace /work/workspace --runtime local --mode regular --capability read_files --capability run_commands --harness runtime-switch-target:{manifest['switch_id']} --json
```

Require `ready: true` and `state_freshness: verified_local`.

4. Run:

```text
python3 /framework/scripts/resume.py --workspace /work/workspace
```

Require the actual command to print `RESUME STATE VERIFIED: durable checkpoint continuation`.

5. Recover from the durable Brain only:
- the durable fact added by runtime A;
- the unfinished task added by runtime A;
- the project update added by runtime A;
- the revision and checkpoint ID reported by resume.

Do not modify the Brain. Do not infer or invent missing values.

6. Write exactly one result file at `/evidence/recovered.json`:

```json
{{
  "format": "{RESULT_FORMAT}",
  "version": 1,
  "switch_id": "{manifest['switch_id']}",
  "recovered_fact": "EXACT RECOVERED FACT",
  "recovered_unfinished_task": "EXACT RECOVERED UNFINISHED TASK",
  "recovered_project_update": "EXACT RECOVERED PROJECT UPDATE",
  "recovered_revision": 2,
  "recovered_checkpoint_id": "EXACT RECOVERED CHECKPOINT ID",
  "startup_state_freshness": "verified_local",
  "resume_verified": true
}}
```

Replace only the placeholder values with the exact durable values you recovered. Then stop.
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

    setup = run_script("setup_workspace.py", "--workspace", str(workspace), "--trust-runtime", "local")
    if "WORKSPACE CREATED" not in setup.stdout:
        raise SwitchError("workspace setup did not report success")
    verified = run_script("verify_workspace.py", "--workspace", str(workspace))
    if "WORKSPACE VERIFIED" not in verified.stdout:
        raise SwitchError("workspace verification did not report success")

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
        raise SwitchError("runtime bridge did not report successful installation")

    brain = state_read_json(workspace / "BRAIN.json")
    workspace_id = brain.get("workspace_id")
    if not isinstance(workspace_id, str) or not workspace_id:
        raise SwitchError("prepared workspace has no workspace identity")

    switch_id = uuid.uuid4().hex[:16]
    nonce = secrets.token_hex(8)
    manifest: dict[str, Any] = {
        "format": FORMAT,
        "version": VERSION,
        "switch_id": switch_id,
        "framework_commit": git("rev-parse", "HEAD").lower(),
        "workspace_id": workspace_id,
        "workspace": str(workspace),
        "project": str(project),
        "source_operation_id": f"switch-source-{switch_id}",
        "durable_fact": f"Switch recovery fact {switch_id}: {nonce}",
        "unfinished_task": f"Switch recovery unfinished task {switch_id}: {nonce[::-1]}",
        "project_name": "Runtime Switch Recovery",
        "project_update": f"Switch recovery project update {switch_id}: state-{nonce}",
        "checkpoint_summary": f"Runtime switch source checkpoint {switch_id}",
        "checkpoint_next_step": "Recover this state from a fresh second runtime session.",
        "prepared_at": utc_now(),
    }
    if len(manifest["framework_commit"]) != 40:
        raise SwitchError("framework checkout did not report an exact commit")

    source_task = control / "source_task.md"
    target_task = control / "target_task.md"
    source_task.write_text(render_source_task(manifest), encoding="utf-8")
    target_task.write_text(render_target_task(manifest), encoding="utf-8")
    manifest["source_task_sha256"] = sha256_file(source_task)
    manifest["target_task_sha256"] = sha256_file(target_task)
    manifest["project_tree_sha256"] = tree_digest(project)
    write_json(root / MANIFEST_FILE, manifest)

    print("RUNTIME SWITCH REHEARSAL PREPARED")
    print(f"Switch ID: {switch_id}")
    print(f"Root: {root}")
    print(f"Workspace: {workspace}")
    print(f"Project: {project}")
    print("Next: run runtime A with the trusted run-source wrapper.")
    return 0


def validate_manifest(root: Path) -> tuple[dict[str, Any], Path, Path]:
    manifest_path = root / MANIFEST_FILE
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise SwitchError("switch manifest is missing or unsafe")
    manifest = read_json(manifest_path)
    expected = {
        "format", "version", "switch_id", "framework_commit", "workspace_id", "workspace", "project",
        "source_operation_id", "durable_fact", "unfinished_task", "project_name", "project_update",
        "checkpoint_summary", "checkpoint_next_step", "prepared_at", "source_task_sha256", "target_task_sha256",
        "project_tree_sha256",
    }
    if set(manifest) != expected:
        raise SwitchError("switch manifest fields are not recognized")
    if manifest.get("format") != FORMAT or manifest.get("version") != VERSION:
        raise SwitchError("switch manifest format/version is not recognized")
    workspace = (root / "workspace").resolve()
    project = (root / "project").resolve()
    if manifest.get("workspace") != str(workspace) or manifest.get("project") != str(project):
        raise SwitchError("switch manifest paths do not match the prepared root")
    brain = state_read_json(workspace / "BRAIN.json")
    if brain.get("workspace_id") != manifest.get("workspace_id"):
        raise SwitchError("switch workspace identity changed")
    if manifest.get("framework_commit") != git("rev-parse", "HEAD").lower():
        raise SwitchError("current framework checkout does not match the prepared switch rehearsal")
    source_task = root / SOURCE_TASK
    target_task = root / TARGET_TASK
    if sha256_file(source_task) != manifest["source_task_sha256"]:
        raise SwitchError("source task contract changed after preparation")
    if sha256_file(target_task) != manifest["target_task_sha256"]:
        raise SwitchError("target task contract changed after preparation")
    if tree_digest(project) != manifest["project_tree_sha256"]:
        raise SwitchError("project changed after preparation; possible project handoff leakage")
    return manifest, workspace, project


def optional_string(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise SwitchError(f"{field} must be a non-empty string when provided")
    return value.strip()


def actual_permission_mode(args: argparse.Namespace, *, phase: str) -> str:
    ro_binds = len(args.ro_bind) + 1
    rw_binds = len(args.rw_bind) + (1 if phase == "target" else 0)
    return ";".join(
        [
            "bubblewrap",
            f"network={'denied' if args.deny_network else 'shared'}",
            f"stdin={'closed' if args.non_interactive else 'open'}",
            f"extra_ro_binds={ro_binds}",
            f"extra_rw_binds={rw_binds}",
            f"pass_env={len(args.pass_env)}",
            f"set_env={len(args.env)}",
            f"namespace_helper={'on' if args.sudo_namespace_helper else 'off'}",
        ]
    )


def command_has_continuation(command: list[str]) -> bool:
    for token in command:
        if token in CONTINUATION_FLAGS:
            return True
        if any(token.startswith(flag + "=") for flag in CONTINUATION_FLAGS if flag.startswith("--")):
            return True
    return False


def target_binding_exposes_source(root: Path, binding: str) -> bool:
    if ":" not in binding:
        return True
    host_raw = binding.split(":", 1)[0]
    host = Path(host_raw).expanduser().resolve()
    sensitive = [root / MANIFEST_FILE, root / SOURCE_TASK, root / SOURCE_VERIFIED_FILE]
    return any(host == item.resolve() or host in item.resolve().parents for item in sensitive)


def build_execution_record(
    args: argparse.Namespace,
    manifest: dict[str, Any],
    command: list[str],
    exit_code: int,
    *,
    phase: str,
    fresh_session: bool | None,
) -> dict[str, Any]:
    context = args.context_tokens
    if context is not None and (isinstance(context, bool) or context <= 0):
        raise SwitchError("context_tokens must be a positive integer when provided")
    return {
        "format": EXECUTION_FORMAT,
        "version": VERSION,
        "phase": phase,
        "switch_id": manifest["switch_id"],
        "framework_commit": manifest["framework_commit"],
        "runtime_profile": "local",
        "model": optional_string(args.model, "model"),
        "harness": optional_string(args.harness, "harness"),
        "harness_version": optional_string(args.harness_version, "harness_version"),
        "context_tokens": context,
        "quantization": optional_string(args.quantization, "quantization"),
        "os_platform": host_os_platform(),
        "permission_mode": actual_permission_mode(args, phase=phase),
        "human_intervention": False if args.non_interactive else None,
        "runtime_command_sha256": runtime_command_sha256(command),
        "exit_code": int(exit_code),
        "fresh_session": fresh_session,
        "recorded_at": utc_now(),
    }


def validate_execution(path: Path, manifest: dict[str, Any], phase: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise SwitchError(f"{phase} execution record is missing or unsafe")
    value = read_json(path)
    expected = {
        "format", "version", "phase", "switch_id", "framework_commit", "runtime_profile", "model", "harness",
        "harness_version", "context_tokens", "quantization", "os_platform", "permission_mode", "human_intervention",
        "runtime_command_sha256", "exit_code", "fresh_session", "recorded_at",
    }
    if set(value) != expected:
        raise SwitchError(f"{phase} execution record fields are not recognized")
    if value.get("format") != EXECUTION_FORMAT or value.get("version") != VERSION or value.get("phase") != phase:
        raise SwitchError(f"{phase} execution record identity is not recognized")
    if value.get("switch_id") != manifest["switch_id"] or value.get("framework_commit") != manifest["framework_commit"]:
        raise SwitchError(f"{phase} execution record does not match the switch rehearsal")
    if value.get("runtime_profile") != "local":
        raise SwitchError(f"{phase} execution runtime profile is not local")
    if not isinstance(value.get("exit_code"), int) or isinstance(value.get("exit_code"), bool):
        raise SwitchError(f"{phase} execution exit code is invalid")
    digest = value.get("runtime_command_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise SwitchError(f"{phase} execution command digest is invalid")
    for field in ("os_platform", "permission_mode", "recorded_at"):
        if not isinstance(value.get(field), str) or not value[field].strip():
            raise SwitchError(f"{phase} execution {field} is invalid")
    if phase == "target" and value.get("fresh_session") is not True:
        raise SwitchError("target execution was not recorded as a fresh session")
    return value


def run_phase(args: argparse.Namespace, *, phase: str) -> int:
    root = resolve_root(args.root)
    manifest, workspace, project = validate_manifest(root)
    execution_path = root / (SOURCE_EXECUTION_FILE if phase == "source" else TARGET_EXECUTION_FILE)
    if execution_path.exists() or execution_path.is_symlink():
        raise SwitchError(f"{phase} execution evidence already exists; this phase is single-use")

    if phase == "target":
        if not (root / SOURCE_VERIFIED_FILE).is_file():
            raise SwitchError("source state must pass trusted verify-source before target runtime begins")
        if args.rw_bind:
            raise SwitchError("fresh target session forbids user-supplied read-write binds")
        if any(target_binding_exposes_source(root, binding) for binding in args.ro_bind):
            raise SwitchError("fresh target session may not expose source-only switch evidence")

    command = list(args.runtime_command)
    if command and command[0] == "--":
        command.pop(0)
    if not command:
        raise SwitchError("provide a runtime command after --")
    if phase == "target" and command_has_continuation(command):
        raise SwitchError("fresh target session may not use session continuation/attach flags")

    sandbox = SCRIPTS / "rehearsal_sandbox.py"
    invocation = [
        sys.executable,
        str(sandbox),
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
    for binding in args.rw_bind:
        invocation.extend(["--rw-bind", binding])

    if phase == "source":
        invocation.extend(["--ro-bind", f"{root / SOURCE_TASK}:{SANDBOX_SOURCE_TASK}"])
        fresh_session = None
    else:
        invocation.extend(["--ro-bind", f"{root / TARGET_TASK}:{SANDBOX_TARGET_TASK}"])
        invocation.extend(["--rw-bind", f"{root / 'result'}:{SANDBOX_RESULT_DIR}"])
        fresh_session = bool(args.non_interactive and not args.rw_bind and not command_has_continuation(command))
    invocation.extend(["--", *command])

    result = subprocess.run(
        invocation,
        cwd=ROOT,
        text=True,
        check=False,
        stdin=subprocess.DEVNULL if args.non_interactive else None,
    )
    write_json(
        execution_path,
        build_execution_record(args, manifest, command, int(result.returncode), phase=phase, fresh_session=fresh_session),
    )
    if result.returncode != 0:
        print(f"RUNTIME SWITCH {phase.upper()} SANDBOX COMMAND FAILED: exit {result.returncode}", file=sys.stderr)
    return int(result.returncode)


def canonical_source_bundle(record: dict[str, Any]) -> dict[str, Any]:
    details = record.get("details")
    if not isinstance(details, dict):
        raise SwitchError("source operation has no committed details")
    completed = details.get("receipt")
    if not isinstance(completed, dict):
        raise SwitchError("source operation has no canonical completed receipt")
    bundle = completed.get("bundle")
    if not isinstance(bundle, dict):
        raise SwitchError("source operation has no canonical bundle")
    return bundle


def verify_workspace_marker_containment(
    workspace: Path,
    manifest: dict[str, Any],
    receipt: dict[str, Any],
) -> None:
    allowed: set[str] = set()
    accepted_items = receipt.get("accepted_items")
    if not isinstance(accepted_items, list):
        raise SwitchError("source receipt does not enumerate accepted canonical destinations")
    for item in accepted_items:
        if not isinstance(item, dict) or not isinstance(item.get("destination"), str):
            raise SwitchError("source receipt has an invalid canonical destination")
        allowed.add(item["destination"])

    operation_id = manifest["source_operation_id"]
    allowed.add(f"state/wrapups/{operation_id}.json")
    for path in (workspace / "state" / "operations").glob("*.json"):
        allowed.add(path.relative_to(workspace).as_posix())

    markers = [
        manifest["durable_fact"].encode("utf-8"),
        manifest["unfinished_task"].encode("utf-8"),
        manifest["project_update"].encode("utf-8"),
    ]
    for path in workspace.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(workspace).as_posix()
        data = path.read_bytes()
        if any(marker in data for marker in markers) and relative not in allowed:
            raise SwitchError(
                f"workspace handoff leakage detected outside canonical Aham persistence artifacts: {relative}"
            )


def verify_source(root_value: str) -> int:
    root = resolve_root(root_value)
    manifest, workspace, _project = validate_manifest(root)
    execution = validate_execution(root / SOURCE_EXECUTION_FILE, manifest, "source")
    if execution["exit_code"] != 0:
        raise SwitchError("source execution record shows a failed sandbox command")

    operation_id = manifest["source_operation_id"]
    receipt = receipt_for_operation(workspace, operation_id, expected_kind="wrap_up")
    record = operation_record(workspace, operation_id, expected_kind="wrap_up")
    bundle = canonical_source_bundle(record)
    expected_updates = [{"project": manifest["project_name"], "content": manifest["project_update"]}]
    if bundle.get("durable_facts") != [manifest["durable_fact"]]:
        raise SwitchError("source committed durable fact does not match the prepared marker")
    if bundle.get("unfinished_work") != [manifest["unfinished_task"]]:
        raise SwitchError("source committed unfinished task does not match the prepared marker")
    if bundle.get("project_updates") != expected_updates:
        raise SwitchError("source committed project update does not match the prepared marker")
    verify_workspace_marker_containment(workspace, manifest, receipt)
    checkpoint = receipt.get("checkpoint")
    revision = receipt.get("revision")
    if not isinstance(checkpoint, dict) or not isinstance(checkpoint.get("id"), str):
        raise SwitchError("source receipt has no verified checkpoint identity")
    if not isinstance(revision, int) or revision < 1:
        raise SwitchError("source receipt has no verified revision")
    digest = state_digest(manifest, revision, checkpoint["id"])
    value = {
        "format": SOURCE_VERIFIED_FORMAT,
        "version": VERSION,
        "switch_id": manifest["switch_id"],
        "source_operation_id": operation_id,
        "revision": revision,
        "checkpoint_id": checkpoint["id"],
        "state_digest": digest,
        "verified_at": utc_now(),
    }
    path = root / SOURCE_VERIFIED_FILE
    if path.exists() or path.is_symlink():
        raise SwitchError("source verification record already exists; refusing overwrite")
    write_json(path, value)
    print("SWITCH SOURCE STATE VERIFIED")
    print(f"Switch ID: {manifest['switch_id']}")
    print(f"Revision: {revision}")
    print(f"Checkpoint: {checkpoint['id']}")
    return 0


def validate_source_verified(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    path = root / SOURCE_VERIFIED_FILE
    if path.is_symlink() or not path.is_file():
        raise SwitchError("trusted source verification record is missing")
    value = read_json(path)
    expected = {"format", "version", "switch_id", "source_operation_id", "revision", "checkpoint_id", "state_digest", "verified_at"}
    if set(value) != expected or value.get("format") != SOURCE_VERIFIED_FORMAT or value.get("version") != VERSION:
        raise SwitchError("source verification record fields are not recognized")
    if value.get("switch_id") != manifest["switch_id"] or value.get("source_operation_id") != manifest["source_operation_id"]:
        raise SwitchError("source verification record identity does not match the switch rehearsal")
    revision = value.get("revision")
    checkpoint_id = value.get("checkpoint_id")
    if not isinstance(revision, int) or revision < 1 or not isinstance(checkpoint_id, str) or not checkpoint_id:
        raise SwitchError("source verification record revision/checkpoint is invalid")
    if value.get("state_digest") != state_digest(manifest, revision, checkpoint_id):
        raise SwitchError("source verification state digest no longer matches the prepared markers")
    return value


def validate_recovery_result(path: Path, manifest: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise SwitchError("target recovery result is missing or unsafe")
    value = read_json(path)
    expected = {
        "format", "version", "switch_id", "recovered_fact", "recovered_unfinished_task", "recovered_project_update",
        "recovered_revision", "recovered_checkpoint_id", "startup_state_freshness", "resume_verified",
    }
    if set(value) != expected or value.get("format") != RESULT_FORMAT or value.get("version") != VERSION:
        raise SwitchError("target recovery result fields are not recognized")
    if value.get("switch_id") != manifest["switch_id"]:
        raise SwitchError("target recovery result switch ID does not match")
    if value.get("recovered_fact") != manifest["durable_fact"]:
        raise SwitchError("recovered durable fact does not match runtime A's committed state")
    if value.get("recovered_unfinished_task") != manifest["unfinished_task"]:
        raise SwitchError("recovered unfinished task does not match runtime A's committed state")
    if value.get("recovered_project_update") != manifest["project_update"]:
        raise SwitchError("recovered project update does not match runtime A's committed state")
    if value.get("recovered_revision") != source["revision"]:
        raise SwitchError("recovered revision does not match runtime A's committed revision")
    if value.get("recovered_checkpoint_id") != source["checkpoint_id"]:
        raise SwitchError("recovered checkpoint ID does not match runtime A's checkpoint")
    if value.get("startup_state_freshness") != "verified_local":
        raise SwitchError("target did not report Regular-mode verified_local state freshness")
    if value.get("resume_verified") is not True:
        raise SwitchError("target did not report successful durable resume")
    return value


def verify(root_value: str, as_json: bool) -> int:
    root = resolve_root(root_value)
    manifest, workspace, _project = validate_manifest(root)
    source_execution = validate_execution(root / SOURCE_EXECUTION_FILE, manifest, "source")
    target_execution = validate_execution(root / TARGET_EXECUTION_FILE, manifest, "target")
    if source_execution["exit_code"] != 0 or target_execution["exit_code"] != 0:
        raise SwitchError("source or target execution record shows a failed sandbox command")
    source = validate_source_verified(root, manifest)

    receipt = receipt_for_operation(workspace, manifest["source_operation_id"], expected_kind="wrap_up")
    checkpoint = receipt.get("checkpoint")
    if receipt.get("revision") != source["revision"] or not isinstance(checkpoint, dict) or checkpoint.get("id") != source["checkpoint_id"]:
        raise SwitchError("runtime A's committed state changed after source verification")

    recovered = validate_recovery_result(root / RESULT_FILE, manifest, source)
    resume = run_script("resume.py", "--workspace", str(workspace))
    if "RESUME STATE VERIFIED: durable checkpoint continuation" not in resume.stdout:
        raise SwitchError("trusted host resume did not verify durable continuation")
    if f"Revision: {source['revision']}" not in resume.stdout or f"Checkpoint: {source['checkpoint_id']}" not in resume.stdout:
        raise SwitchError("trusted host resume did not select runtime A's exact committed revision/checkpoint")

    verified_at = utc_now()
    limitations = [
        "Model, harness, version, context, and quantization are launch metadata declared to the trusted host wrapper; the generic verifier does not introspect third-party runtime internals.",
        "fresh_target_session=true means the target used a synthetic sandbox HOME, closed stdin, no user-supplied read-write binds, no recognized continuation/attach flags, and no explicit bind exposing the source-only contract; it cannot prove a remote provider retained no server-side state.",
        "This is one independently verified switch recovery, not a reliability percentage or proof that every model/harness switch behaves identically.",
    ]
    evidence = build_switch_recovery_entry(
        switch_id=manifest["switch_id"],
        framework_commit=manifest["framework_commit"],
        source_execution=source_execution,
        target_execution=target_execution,
        source_operation_id=manifest["source_operation_id"],
        source_revision=source["revision"],
        recovered_revision=recovered["recovered_revision"],
        source_checkpoint_id=source["checkpoint_id"],
        recovered_checkpoint_id=recovered["recovered_checkpoint_id"],
        state_digest=source["state_digest"],
        fresh_target_session=True,
        verified_at=verified_at,
        source=REPORT_FILE,
        limitations=limitations,
    )
    report = {
        "format": REPORT_FORMAT,
        "version": VERSION,
        "verified": True,
        "switch_id": manifest["switch_id"],
        "framework_commit": manifest["framework_commit"],
        "source_operation_id": manifest["source_operation_id"],
        "source_revision": source["revision"],
        "recovered_revision": recovered["recovered_revision"],
        "source_checkpoint_id": source["checkpoint_id"],
        "recovered_checkpoint_id": recovered["recovered_checkpoint_id"],
        "state_digest": source["state_digest"],
        "fresh_target_session": True,
        "verified_at": verified_at,
        "source_execution": source_execution,
        "target_execution": target_execution,
        "checks": [
            "runtime A committed the exact host-prepared durable fact, unfinished task and project update",
            "runtime A committed revision and checkpoint independently re-verified from the immutable operation receipt",
            "runtime A left no marker-bearing project handoff or noncanonical workspace handoff",
            "runtime B source contract did not contain the source marker values and the source-only contract was not mounted",
            "runtime B exact recovered markers matched runtime A's committed durable state",
            "runtime B recovered the exact source revision and checkpoint",
            "trusted host resume independently selected the same durable revision and checkpoint",
            "target execution used the fresh-session wrapper constraints",
        ],
        "runtime_evidence": evidence,
    }
    report_path = root / REPORT_FILE
    if report_path.exists() or report_path.is_symlink():
        raise SwitchError("verified switch report already exists; refusing overwrite")
    write_json(report_path, report)

    if as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("RUNTIME SWITCH RECOVERY VERIFIED")
        print(f"Switch ID: {manifest['switch_id']}")
        print(f"Source revision: {source['revision']}")
        print(f"Recovered revision: {recovered['recovered_revision']}")
        print(f"Checkpoint: {source['checkpoint_id']}")
        print(f"Report: {report_path}")
    return 0


def main() -> int:
    args = parse_args()
    try:
        if args.command == "prepare":
            return prepare(args.root)
        if args.command == "run-source":
            return run_phase(args, phase="source")
        if args.command == "verify-source":
            return verify_source(args.root)
        if args.command == "run-target":
            return run_phase(args, phase="target")
        if args.command == "verify":
            return verify(args.root, args.json)
        raise SwitchError("unknown command")
    except (SwitchError, OSError, KeyError, TypeError, ValueError) as exc:
        print(f"RUNTIME SWITCH FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
