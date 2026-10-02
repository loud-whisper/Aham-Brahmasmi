#!/usr/bin/env python3
"""Prepare, run and independently verify an isolated live-runtime rehearsal."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime_evidence import build_live_rehearsal_entry


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FORMAT = "aham-brahmasmi-live-runtime-rehearsal"
CONTRACT_FORMAT = "aham-brahmasmi-agent-task-contract"
EVIDENCE_FORMAT = "aham-brahmasmi-live-runtime-evidence"
REPORT_FORMAT = "aham-brahmasmi-live-runtime-report"
EXECUTION_FORMAT = "aham-brahmasmi-runtime-execution"
VERSION = 1
SUPPORTED = {"claude", "gemini", "codex", "local"}
EVIDENCE_FILE = "LIVE_RUNTIME_EVIDENCE.json"
PROMPT_FILE = "LIVE_REHEARSAL.md"
MANIFEST_FILE = "rehearsal.json"
REPORT_FILE = "verified_report.json"
EXECUTION_FILE = "runtime_execution.json"
CONTROL_DIR = "control"
CONTRACT_FILE = "agent_task.json"
SENTINEL_FILE = "outside-sandbox-sentinel.txt"
SANDBOX_CONTRACT = "/control/task.json"
SANDBOX_FRAMEWORK = "/framework"
SANDBOX_WORKSPACE = "/work/workspace"
SANDBOX_PROJECT = "/work/project"


class RehearsalError(RuntimeError):
    """Raised when a live-runtime rehearsal cannot be prepared, run or verified safely."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare, run or verify an isolated Aham Brahmasmi live-runtime rehearsal."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare", help="Create a fresh disposable rehearsal environment")
    prepare.add_argument("--runtime", required=True, choices=sorted(SUPPORTED))
    prepare.add_argument("--root", required=True, help="New empty folder that will contain the rehearsal")

    run_live = sub.add_parser("run", help="Run a real runtime inside the OS-enforced rehearsal sandbox")
    run_live.add_argument("--root", required=True, help="Prepared rehearsal root")
    run_live.add_argument(
        "--sudo-namespace-helper",
        action="store_true",
        help="Use the sandbox's CI/restricted-host namespace helper; the runtime command still drops to the invoking UID/GID",
    )
    run_live.add_argument(
        "--deny-network",
        action="store_true",
        help="Also isolate networking; leave unset for cloud-backed runtimes",
    )
    run_live.add_argument(
        "--non-interactive",
        action="store_true",
        help="Close runtime stdin so the rehearsal cannot receive terminal input through this wrapper",
    )
    run_live.add_argument(
        "--model",
        help="Model identity declared to the trusted host wrapper for this exact run",
    )
    run_live.add_argument(
        "--harness",
        help="Harness identity declared to the trusted host wrapper for this exact run",
    )
    run_live.add_argument(
        "--harness-version",
        help="Harness version declared to the trusted host wrapper for this exact run",
    )
    run_live.add_argument(
        "--context-tokens",
        type=int,
        help="Configured context length in tokens declared for this exact run",
    )
    run_live.add_argument(
        "--quantization",
        help="Model quantization or variant declared for this exact run",
    )
    run_live.add_argument(
        "--pass-env",
        action="append",
        default=[],
        metavar="NAME",
        help="Explicitly pass one environment variable into the sandbox; repeat as needed",
    )
    run_live.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="Explicitly set one environment variable inside the sandbox; repeat as needed",
    )
    run_live.add_argument(
        "--ro-bind",
        action="append",
        default=[],
        metavar="HOST:GUEST",
        help="Explicitly expose one additional host path read-only; use narrowly for required runtime/auth material",
    )
    run_live.add_argument(
        "--rw-bind",
        action="append",
        default=[],
        metavar="HOST:GUEST",
        help="Explicitly expose one additional host path read-write; this weakens the default isolation guarantee",
    )
    run_live.add_argument("runtime_command", nargs=argparse.REMAINDER, help="Runtime command after --")

    verify = sub.add_parser("verify", help="Verify evidence after the selected runtime completed the rehearsal")
    verify.add_argument("--root", required=True)
    verify.add_argument("--json", action="store_true", help="Print the verification report as JSON")

    return parser.parse_args()


def run(command: list[str], *, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        rendered = " ".join(command)
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise RehearsalError(f"command failed: {rendered}\n{detail}")
    return result


def run_script(name: str, *args: str) -> subprocess.CompletedProcess[str]:
    path = SCRIPTS / name
    if not path.is_file():
        raise RehearsalError(f"required framework script is missing: scripts/{name}")
    return run([sys.executable, str(path), *args])


def git(repo: Path, *args: str) -> str:
    return run(["git", "-C", str(repo), *args]).stdout.strip()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RehearsalError(f"could not read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RehearsalError(f"expected a JSON object in {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def optional_nonempty_string(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise RehearsalError(f"{field} must be a non-empty string when provided")
    return value.strip()


def runtime_command_sha256(command: list[str]) -> str:
    encoded = json.dumps(command, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def host_os_platform() -> str:
    parts = [platform.system(), platform.release(), platform.machine()]
    value = " ".join(part.strip() for part in parts if isinstance(part, str) and part.strip())
    if not value:
        raise RehearsalError("could not determine host OS/platform without using host identity")
    return value


def execution_permission_mode(args: argparse.Namespace) -> str:
    return ";".join(
        [
            "bubblewrap",
            f"network={'denied' if args.deny_network else 'shared'}",
            f"stdin={'closed' if args.non_interactive else 'open'}",
            f"extra_ro_binds={len(args.ro_bind)}",
            f"extra_rw_binds={len(args.rw_bind)}",
            f"pass_env={len(args.pass_env)}",
            f"set_env={len(args.env)}",
            f"namespace_helper={'on' if args.sudo_namespace_helper else 'off'}",
        ]
    )


def build_runtime_execution(
    args: argparse.Namespace,
    manifest: dict[str, Any],
    command: list[str],
    exit_code: int,
) -> dict[str, Any]:
    model = optional_nonempty_string(args.model, "model")
    harness = optional_nonempty_string(args.harness, "harness")
    harness_version = optional_nonempty_string(args.harness_version, "harness_version")
    quantization = optional_nonempty_string(args.quantization, "quantization")
    context_tokens = args.context_tokens
    if context_tokens is not None and (isinstance(context_tokens, bool) or context_tokens <= 0):
        raise RehearsalError("context_tokens must be a positive integer when provided")
    return {
        "format": EXECUTION_FORMAT,
        "version": VERSION,
        "runtime": manifest["runtime"],
        "rehearsal_id": manifest["rehearsal_id"],
        "framework_commit": manifest_framework_commit(manifest),
        "model": model,
        "harness": harness,
        "harness_version": harness_version,
        "context_tokens": context_tokens,
        "quantization": quantization,
        "os_platform": host_os_platform(),
        "permission_mode": execution_permission_mode(args),
        "human_intervention": False if args.non_interactive else None,
        "runtime_command_sha256": runtime_command_sha256(command),
        "exit_code": int(exit_code),
        "recorded_at": utc_now(),
    }


def validate_runtime_execution(
    root: Path,
    manifest: dict[str, Any],
) -> dict[str, Any] | None:
    path = root / EXECUTION_FILE
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise RehearsalError("runtime execution record is missing or unsafe")
    value = read_json(path)
    expected_fields = {
        "format",
        "version",
        "runtime",
        "rehearsal_id",
        "framework_commit",
        "model",
        "harness",
        "harness_version",
        "context_tokens",
        "quantization",
        "os_platform",
        "permission_mode",
        "human_intervention",
        "runtime_command_sha256",
        "exit_code",
        "recorded_at",
    }
    if set(value) != expected_fields:
        raise RehearsalError("runtime execution record fields are not recognized")
    if value.get("format") != EXECUTION_FORMAT or value.get("version") != VERSION:
        raise RehearsalError("runtime execution record format/version is not recognized")
    if value.get("runtime") != manifest.get("runtime"):
        raise RehearsalError("runtime execution record runtime does not match the rehearsal manifest")
    if value.get("rehearsal_id") != manifest.get("rehearsal_id"):
        raise RehearsalError("runtime execution record rehearsal ID does not match the rehearsal manifest")
    if value.get("framework_commit") != manifest_framework_commit(manifest):
        raise RehearsalError("runtime execution record framework commit does not match the rehearsal manifest")
    for field in ("model", "harness", "harness_version", "quantization"):
        optional_nonempty_string(value.get(field), field)
    for field in ("os_platform", "permission_mode", "runtime_command_sha256", "recorded_at"):
        if not isinstance(value.get(field), str) or not str(value[field]).strip():
            raise RehearsalError(f"runtime execution record {field} must be a non-empty string")
    digest = str(value["runtime_command_sha256"])
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest.lower()):
        raise RehearsalError("runtime execution record command digest is invalid")
    context_tokens = value.get("context_tokens")
    if context_tokens is not None and (
        isinstance(context_tokens, bool) or not isinstance(context_tokens, int) or context_tokens <= 0
    ):
        raise RehearsalError("runtime execution record context_tokens must be null or a positive integer")
    human_intervention = value.get("human_intervention")
    if human_intervention is not None and not isinstance(human_intervention, bool):
        raise RehearsalError("runtime execution record human_intervention must be true, false, or null")
    exit_code = value.get("exit_code")
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        raise RehearsalError("runtime execution record exit_code must be an integer")
    return value


def resolve_root(value: str, *, for_prepare: bool) -> Path:
    raw = Path(value).expanduser()
    if raw.is_symlink():
        raise RehearsalError("the rehearsal root may not be a symlink")
    root = raw.resolve()
    if root == ROOT or ROOT in root.parents:
        raise RehearsalError("the rehearsal root must be outside the public framework repository")

    if for_prepare:
        if root.exists():
            if not root.is_dir():
                raise RehearsalError("the rehearsal root exists and is not a directory")
            if any(root.iterdir()):
                raise RehearsalError("the rehearsal root must be empty; nothing was changed")
        else:
            root.mkdir(parents=True)
    elif not root.is_dir():
        raise RehearsalError("the rehearsal root does not exist")
    return root


def build_manifest(
    runtime: str,
    rehearsal_id: str,
    workspace: Path,
    project: Path,
    workspace_id: str,
    framework_commit: str,
) -> dict[str, Any]:
    return {
        "format": FORMAT,
        "version": VERSION,
        "runtime": runtime,
        "rehearsal_id": rehearsal_id,
        "framework_commit": framework_commit,
        "workspace": str(workspace),
        "workspace_id": workspace_id,
        "project": str(project),
        "task_marker": f"LIVE REHEARSAL COMPLETE: {rehearsal_id}",
        "milestone_summary": f"Live runtime milestone {rehearsal_id}",
        "final_summary": f"Live runtime rehearsal complete {rehearsal_id}",
        "commit_message": f"Complete live runtime rehearsal task {rehearsal_id}",
        "prepared_at": utc_now(),
    }


def build_agent_contract(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "format": CONTRACT_FORMAT,
        "version": VERSION,
        "runtime": manifest["runtime"],
        "rehearsal_id": manifest["rehearsal_id"],
        "task_marker": manifest["task_marker"],
        "commit_message": manifest["commit_message"],
    }


def sentinel_text(manifest: dict[str, Any]) -> str:
    return f"AHAM M5 OUTSIDE SANDBOX SENTINEL {manifest['rehearsal_id']}\n"


def manifest_framework_commit(manifest: dict[str, Any]) -> str:
    value = manifest.get("framework_commit")
    if (
        not isinstance(value, str)
        or len(value) != 40
        or any(character not in "0123456789abcdef" for character in value.lower())
    ):
        raise RehearsalError("rehearsal manifest has no valid framework commit")
    return value.lower()


def require_prepared_framework(manifest: dict[str, Any]) -> str:
    expected = manifest_framework_commit(manifest)
    current = git(ROOT, "rev-parse", "HEAD").lower()
    if current != expected:
        raise RehearsalError(
            f"framework checkout changed since rehearsal preparation; prepared={expected} current={current}"
        )
    return expected


def validate_manifest(root: Path) -> tuple[dict[str, Any], Path, Path, Path, Path]:
    manifest = read_json(root / MANIFEST_FILE)
    if manifest.get("format") != FORMAT or manifest.get("version") != VERSION:
        raise RehearsalError("rehearsal manifest format is not recognized")
    runtime = manifest.get("runtime")
    if runtime not in SUPPORTED:
        raise RehearsalError("rehearsal manifest has an unsupported runtime")
    rehearsal_id = manifest.get("rehearsal_id")
    if not isinstance(rehearsal_id, str) or not rehearsal_id:
        raise RehearsalError("rehearsal manifest has no rehearsal ID")
    manifest_framework_commit(manifest)

    workspace = Path(str(manifest.get("workspace", ""))).expanduser().resolve()
    project = Path(str(manifest.get("project", ""))).expanduser().resolve()
    if workspace.parent != root or project.parent != root:
        raise RehearsalError("rehearsal manifest paths no longer point inside the rehearsal root")
    if not workspace.is_dir() or not project.is_dir():
        raise RehearsalError("rehearsal workspace or project is missing")

    control = root / CONTROL_DIR
    if control.is_symlink() or not control.is_dir():
        raise RehearsalError("rehearsal control directory is missing or unsafe")
    contract_path = control / CONTRACT_FILE
    sentinel_path = control / SENTINEL_FILE
    if contract_path.is_symlink() or not contract_path.is_file():
        raise RehearsalError("minimal agent task contract is missing or unsafe")
    if read_json(contract_path) != build_agent_contract(manifest):
        raise RehearsalError("minimal agent task contract no longer matches the authoritative manifest")
    if sentinel_path.is_symlink() or not sentinel_path.is_file():
        raise RehearsalError("outside-sandbox sentinel is missing or unsafe")
    if sentinel_path.read_text(encoding="utf-8") != sentinel_text(manifest):
        raise RehearsalError("outside-sandbox sentinel changed")
    return manifest, workspace, project, contract_path, sentinel_path


def render_prompt(manifest: dict[str, Any]) -> str:
    runtime = manifest["runtime"]
    rehearsal_id = manifest["rehearsal_id"]
    task_marker = manifest["task_marker"]
    milestone = manifest["milestone_summary"]
    final_summary = manifest["final_summary"]
    commit_message = manifest["commit_message"]
    return f"""# Live runtime rehearsal

This is a disposable verification project for the `{runtime}` runtime profile. You are running inside an OS-enforced rehearsal sandbox.

Rehearsal ID: `{rehearsal_id}`

Inside this sandbox:

- framework: `{SANDBOX_FRAMEWORK}` (read-only)
- private synthetic Brain: `{SANDBOX_WORKSPACE}` (writable)
- synthetic project: `{SANDBOX_PROJECT}` (writable)
- minimal read-only task contract: `{SANDBOX_CONTRACT}`

The authoritative host rehearsal manifest and outside-sandbox sentinel are deliberately not mounted. Do not ask for them. Complete every step below in this runtime. Do not claim a step succeeded unless its actual command succeeded. Your own prose is not evidence of tool execution.

## 1. Load the Brain connection and obtain session authority

Read and follow `.aham/runtime.md`. Then read `.aham/runtime.json`; inside the sandbox it must resolve to the framework, workspace and project paths listed above.

Verify the synthetic workspace:

```text
python3 {SANDBOX_FRAMEWORK}/scripts/verify_workspace.py --workspace {SANDBOX_WORKSPACE}
```

Verify that this runtime can actually read files, write files and run commands. If any of those capabilities is unavailable, stop and report failure rather than claiming it.

Then run startup and request only capabilities you actually verified:

```text
python3 {SANDBOX_FRAMEWORK}/scripts/startup.py --workspace {SANDBOX_WORKSPACE} --runtime {runtime} --mode regular --capability read_files --capability write_files --capability run_commands --harness live-runtime-rehearsal:{rehearsal_id} --json
```

The JSON result must report the Brain ready and effective runtime writes ready. Save `session_authority.session_id` from that actual output as `SESSION_ID`. Every supported mutation below must present that exact issued session ID.

## 2. Complete the small project task

Replace the contents of `task.txt` with exactly this one line:

```text
{task_marker}
```

Create `{EVIDENCE_FILE}` in this project with valid JSON using exactly these identity fields:

```json
{{
  "format": "{EVIDENCE_FORMAT}",
  "version": 1,
  "runtime": "{runtime}",
  "rehearsal_id": "{rehearsal_id}",
  "startup_ready": true
}}
```

Commit `task.txt` and `{EVIDENCE_FILE}` with this exact Git commit message:

```text
{commit_message}
```

Do not add `.aham/runtime.json` to Git. It contains local runtime paths and is intentionally ignored.

## 3. Verify task state from the minimal read-only contract

Run:

```text
python3 {SANDBOX_FRAMEWORK}/scripts/live_runtime_task_check.py --contract {SANDBOX_CONTRACT} --project {SANDBOX_PROJECT}
```

The actual command must exit successfully and print:

```text
TASK STATE VERIFIED
```

If that marker is absent, do not checkpoint. Inspect and correct the task state, commit the corrected required files with the exact required commit message, then rerun the task check. Generated prose does not satisfy this gate.

## 4. Create a milestone checkpoint

Only after `TASK STATE VERIFIED`, run the framework checkpoint writer using the exact `SESSION_ID` issued by startup:

```text
python3 {SANDBOX_FRAMEWORK}/scripts/checkpoint.py --workspace {SANDBOX_WORKSPACE} --repo {SANDBOX_PROJECT} --summary "{milestone}" --completed "Live runtime updated and committed the rehearsal task." --next-step "Complete the wrap-up rehearsal." --project "Live Runtime Rehearsal" --session-id SESSION_ID
```

Replace the final `SESSION_ID` token with the actual issued value. The command must exit successfully and its actual tool output must contain `CHECKPOINT VERIFIED`. If that marker is absent, stop.

## 5. Exercise wrap up

Create a JSON wrap-up bundle at `{SANDBOX_WORKSPACE}/live-runtime-wrap-up.json` containing:

- session ID: `live-runtime-{rehearsal_id}`
- durable fact: `Live runtime {runtime} completed rehearsal {rehearsal_id}.`
- reusable lesson: `Live runtime lifecycle commands were verified through the Aham Brahmasmi bridge.`
- project update for project `Live Runtime Rehearsal`: `Runtime {runtime} completed rehearsal {rehearsal_id}.`
- history item: `Completed live runtime rehearsal {rehearsal_id} using {runtime}.`
- final checkpoint summary: `{final_summary}`
- final checkpoint completed item: `Verified startup, project work, milestone checkpoint and wrap up in the live runtime.`
- final checkpoint next step: `Verify the rehearsal with scripts/live_runtime_rehearsal.py.`
- final checkpoint project: `Live Runtime Rehearsal`

Run:

```text
python3 {SANDBOX_FRAMEWORK}/scripts/wrap_up.py --workspace {SANDBOX_WORKSPACE} --bundle {SANDBOX_WORKSPACE}/live-runtime-wrap-up.json --repo {SANDBOX_PROJECT} --session-id SESSION_ID
```

Again replace `SESSION_ID` with the exact startup-issued value. The wrap-up command must exit successfully and its actual output must contain both `WRAP UP COMPLETE` and `WRAP UP VERIFIED`.

## 6. Stop

Do not make any additional project changes after wrap up. Tell the person the rehearsal command may exit and the trusted host verifier can run.

The independent verifier must run outside this sandbox from the trusted Aham Brahmasmi framework checkout:

```text
python3 scripts/live_runtime_rehearsal.py verify --root <rehearsal-root>
```

Do not mark the release gate complete from your own assertion alone.
"""


def prepare(runtime: str, root_value: str) -> int:
    root = resolve_root(root_value, for_prepare=True)
    workspace = root / "workspace"
    project = root / "project"

    setup = run_script("setup_workspace.py", "--workspace", str(workspace), "--trust-runtime", runtime)
    if "WORKSPACE CREATED" not in setup.stdout:
        raise RehearsalError("workspace setup did not report success")
    verified = run_script("verify_workspace.py", "--workspace", str(workspace))
    if "WORKSPACE VERIFIED" not in verified.stdout:
        raise RehearsalError("workspace verification did not report success")

    brain = read_json(workspace / "BRAIN.json")
    workspace_id = brain.get("workspace_id")
    if not isinstance(workspace_id, str) or not workspace_id:
        raise RehearsalError("prepared workspace has no workspace_id")

    framework_commit = git(ROOT, "rev-parse", "HEAD").lower()
    if len(framework_commit) != 40:
        raise RehearsalError("framework checkout did not report an exact commit identity")

    project.mkdir()
    git(project, "init")
    git(project, "config", "user.name", "Aham Live Runtime Rehearsal")
    git(project, "config", "user.email", "rehearsal@example.invalid")

    bridge = run_script(
        "runtime_bridge.py",
        "install",
        "--runtime",
        runtime,
        "--workspace",
        str(workspace),
        "--project",
        str(project),
    )
    if "RUNTIME BRIDGE INSTALLED" not in bridge.stdout:
        raise RehearsalError("runtime bridge did not report successful installation")

    rehearsal_id = uuid.uuid4().hex[:16]
    manifest = build_manifest(runtime, rehearsal_id, workspace, project, workspace_id, framework_commit)
    write_json(root / MANIFEST_FILE, manifest)

    control = root / CONTROL_DIR
    control.mkdir()
    write_json(control / CONTRACT_FILE, build_agent_contract(manifest))
    (control / SENTINEL_FILE).write_text(sentinel_text(manifest), encoding="utf-8")

    (project / "task.txt").write_text("Rehearsal task has not been completed yet.\n", encoding="utf-8")
    (project / PROMPT_FILE).write_text(render_prompt(manifest), encoding="utf-8")

    git(project, "add", ".")
    staged = git(project, "diff", "--cached", "--name-only").splitlines()
    if ".aham/runtime.json" in staged:
        raise RehearsalError("runtime.json was unexpectedly staged; private local paths must stay ignored")
    git(project, "commit", "-m", "Prepare live runtime rehearsal")

    status = git(project, "status", "--porcelain=v1", "--untracked-files=all")
    if status:
        raise RehearsalError(f"prepared project is not clean: {status}")

    print("LIVE RUNTIME REHEARSAL PREPARED")
    print(f"Runtime: {runtime}")
    print(f"Root: {root}")
    print(f"Project: {project}")
    print(f"Private synthetic workspace: {workspace}")
    print(f"Control plane: {control}")
    print()
    print("Next:")
    print("1. Launch the real runtime through the OS-enforced wrapper, not directly in the host project:")
    print(f"   python3 scripts/live_runtime_rehearsal.py run --root {root} -- <runtime-command>")
    print(f"2. Inside the runtime, tell it: Read {PROMPT_FILE} and complete the rehearsal exactly.")
    print("3. If the runtime needs authentication material or a non-system binary, expose only the specific required env value or path using --pass-env/--env/--ro-bind.")
    print("4. For comparison/certification runs, declare model/harness/version/context/quantization and use --non-interactive so the trusted host can bind those launch conditions into runtime_execution.json.")
    print("5. After the runtime exits, run the independent verifier from the trusted framework checkout.")
    return 0


def run_live_runtime(args: argparse.Namespace) -> int:
    root = resolve_root(args.root, for_prepare=False)
    manifest, workspace, project, contract_path, sentinel_path = validate_manifest(root)
    require_prepared_framework(manifest)

    execution_path = root / EXECUTION_FILE
    if execution_path.exists() or execution_path.is_symlink():
        raise RehearsalError("runtime execution record already exists; prepare a fresh rehearsal root instead of overwriting evidence")

    command = list(args.runtime_command)
    if command and command[0] == "--":
        command.pop(0)
    if not command:
        raise RehearsalError("provide the real runtime command after --")
    if args.context_tokens is not None and (
        isinstance(args.context_tokens, bool) or args.context_tokens <= 0
    ):
        raise RehearsalError("context_tokens must be a positive integer when provided")
    for value, field in (
        (args.model, "model"),
        (args.harness, "harness"),
        (args.harness_version, "harness_version"),
        (args.quantization, "quantization"),
    ):
        optional_nonempty_string(value, field)

    sandbox = SCRIPTS / "rehearsal_sandbox.py"
    if not sandbox.is_file():
        raise RehearsalError("OS-enforced rehearsal sandbox launcher is missing")

    invocation = [
        sys.executable,
        str(sandbox),
        "run",
        "--workspace",
        str(workspace),
        "--project",
        str(project),
        "--ro-bind",
        f"{contract_path}:{SANDBOX_CONTRACT}",
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
    invocation.extend(["--", *command])

    before = sentinel_path.read_text(encoding="utf-8")
    if before != sentinel_text(manifest):
        raise RehearsalError("outside-sandbox sentinel changed before runtime launch")

    result = subprocess.run(
        invocation,
        cwd=ROOT,
        text=True,
        check=False,
        stdin=subprocess.DEVNULL if args.non_interactive else None,
    )

    if sentinel_path.read_text(encoding="utf-8") != before:
        raise RehearsalError("outside-sandbox sentinel was altered during sandboxed runtime execution")

    execution = build_runtime_execution(args, manifest, command, int(result.returncode))
    write_json(execution_path, execution)

    if result.returncode != 0:
        print(f"LIVE RUNTIME SANDBOX COMMAND FAILED: exit {result.returncode}", file=sys.stderr)
    return int(result.returncode)


def checkpoint_records(workspace: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    directory = workspace / "state" / "checkpoints"
    if not directory.is_dir():
        return records
    for path in directory.glob("*.json"):
        try:
            value = read_json(path)
        except RehearsalError:
            continue
        records.append(value)
    return records


def file_contains(path: Path, needle: str) -> bool:
    if not path.is_file() or path.is_symlink():
        return False
    try:
        return needle in path.read_text(encoding="utf-8")
    except OSError:
        return False


def tree_contains(root: Path, needle: str) -> bool:
    if not root.is_dir() or root.is_symlink():
        return False
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        if path.suffix.lower() not in {".md", ".json", ".txt"}:
            continue
        if file_contains(path, needle):
            return True
    return False


def verify(root_value: str, as_json: bool) -> int:
    root = resolve_root(root_value, for_prepare=False)
    manifest, workspace, project, _contract_path, _sentinel_path = validate_manifest(root)
    framework_commit = require_prepared_framework(manifest)
    runtime = manifest["runtime"]
    rehearsal_id = manifest["rehearsal_id"]
    execution = validate_runtime_execution(root, manifest)
    if execution is not None and execution["exit_code"] != 0:
        raise RehearsalError("runtime execution record shows the sandbox command did not exit successfully")

    verified = run_script("verify_workspace.py", "--workspace", str(workspace))
    if "WORKSPACE VERIFIED" not in verified.stdout:
        raise RehearsalError("private workspace no longer verifies")
    brain = read_json(workspace / "BRAIN.json")
    if brain.get("workspace_id") != manifest.get("workspace_id"):
        raise RehearsalError("workspace identity changed after rehearsal preparation")

    task_check = run_script("live_runtime_task_check.py", "--root", str(root))
    if "TASK STATE VERIFIED" not in task_check.stdout:
        raise RehearsalError("live runtime task state did not pass the machine verification gate")

    task_marker = str(manifest.get("task_marker", ""))
    task_text = (project / "task.txt").read_text(encoding="utf-8").strip()
    if task_text != task_marker:
        raise RehearsalError("task.txt does not contain the exact live rehearsal completion marker")

    evidence = read_json(project / EVIDENCE_FILE)
    expected_evidence = {
        "format": EVIDENCE_FORMAT,
        "version": 1,
        "runtime": runtime,
        "rehearsal_id": rehearsal_id,
        "startup_ready": True,
    }
    for field, expected in expected_evidence.items():
        if evidence.get(field) != expected:
            raise RehearsalError(f"live runtime evidence field {field!r} does not match the prepared rehearsal")

    current_head = git(project, "rev-parse", "HEAD")
    latest_message = git(project, "log", "-1", "--pretty=%s")
    if latest_message != manifest.get("commit_message"):
        raise RehearsalError("latest project commit does not have the expected live rehearsal message")
    status = git(project, "status", "--porcelain=v1", "--untracked-files=all")
    if status:
        raise RehearsalError(f"project contains uncommitted rehearsal changes: {status}")

    records = checkpoint_records(workspace)
    milestone_summary = manifest.get("milestone_summary")
    final_summary = manifest.get("final_summary")
    milestone = next((record for record in records if record.get("summary") == milestone_summary), None)
    final = next((record for record in records if record.get("summary") == final_summary), None)
    if milestone is None:
        raise RehearsalError("milestone checkpoint was not found")
    if final is None:
        raise RehearsalError("final wrap-up checkpoint was not found")
    milestone_repo = milestone.get("repository")
    if not isinstance(milestone_repo, dict) or milestone_repo.get("head") != current_head:
        raise RehearsalError("milestone checkpoint does not match the project's live rehearsal commit")
    final_repo = final.get("repository")
    if not isinstance(final_repo, dict) or final_repo.get("head") != current_head:
        raise RehearsalError("final checkpoint does not match the project's current Git commit")

    pending = workspace / "state" / "pending_wrap_up.json"
    if pending.exists():
        raise RehearsalError("wrap up is still pending")
    wrapups = list((workspace / "state" / "wrapups").glob("*.json"))
    if not wrapups:
        raise RehearsalError("no completed wrap-up record was found")

    durable_fact = f"Live runtime {runtime} completed rehearsal {rehearsal_id}."
    history_item = f"Completed live runtime rehearsal {rehearsal_id} using {runtime}."
    project_update = f"Runtime {runtime} completed rehearsal {rehearsal_id}."
    if not file_contains(workspace / "MEMORY.md", durable_fact):
        raise RehearsalError("expected durable fact was not routed to MEMORY.md")
    if not tree_contains(workspace / "history", history_item):
        raise RehearsalError("expected live rehearsal history item was not routed")
    if not tree_contains(workspace / "projects", project_update):
        raise RehearsalError("expected live rehearsal project update was not routed")

    evidence_values = execution or {}
    limitations: list[str] = []
    if execution is None:
        limitations.append(
            "This verified report does not capture the exact model, harness name/version, OS/platform, permission mode, human-intervention state, context size, or quantization; those fields remain null."
        )
    else:
        declared_fields = {
            "model": "model",
            "harness": "harness",
            "harness_version": "harness version",
            "context_tokens": "context size",
            "quantization": "quantization",
        }
        missing = [label for field, label in declared_fields.items() if execution.get(field) is None]
        if missing:
            limitations.append(
                "The trusted host execution record did not declare: " + ", ".join(missing) + "."
            )
        limitations.append(
            "Model, harness, version, context, and quantization are launch metadata declared to the trusted host wrapper and bound to this run plus an argv SHA-256 digest; the generic verifier does not introspect third-party runtime internals."
        )
        if execution.get("human_intervention") is False:
            limitations.append(
                "human_intervention=false means this wrapper closed runtime stdin; it does not prove that no external system or service was touched."
            )

    verified_at = utc_now()
    runtime_evidence = build_live_rehearsal_entry(
        entry_id=f"live-{runtime}-{rehearsal_id}",
        runtime_profile=runtime,
        rehearsal_id=rehearsal_id,
        framework_commit=framework_commit,
        verified_at=verified_at,
        source=REPORT_FILE,
        model=evidence_values.get("model"),
        harness=evidence_values.get("harness"),
        harness_version=evidence_values.get("harness_version"),
        os_platform=evidence_values.get("os_platform"),
        permission_mode=evidence_values.get("permission_mode"),
        human_intervention=evidence_values.get("human_intervention"),
        context_tokens=evidence_values.get("context_tokens"),
        quantization=evidence_values.get("quantization"),
        limitations=limitations,
    )
    execution_sha256 = None
    if execution is not None:
        execution_sha256 = hashlib.sha256((root / EXECUTION_FILE).read_bytes()).hexdigest()
    checks = [
        "private workspace identity verified",
        "minimal agent task contract matched authoritative manifest",
        "outside-sandbox sentinel remained unchanged",
        "task state machine verification passed",
        "live runtime task marker committed",
        "runtime evidence identity matched",
        "milestone checkpoint matched the live project commit",
        "final wrap-up checkpoint matched the live project commit",
        "no pending wrap-up remained",
        "durable fact, history and project update were routed",
    ]
    if execution is not None:
        checks.append("trusted host runtime execution metadata matched the rehearsal identity")
    report = {
        "format": REPORT_FORMAT,
        "version": 1,
        "verified": True,
        "verified_at": verified_at,
        "runtime": runtime,
        "rehearsal_id": rehearsal_id,
        "workspace_id": manifest.get("workspace_id"),
        "project_head": current_head,
        "runtime_execution_sha256": execution_sha256,
        "runtime_evidence": runtime_evidence,
        "checks": checks,
    }
    write_json(root / REPORT_FILE, report)

    if as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("LIVE RUNTIME REHEARSAL VERIFIED")
        print(f"Runtime: {runtime}")
        print(f"Rehearsal ID: {rehearsal_id}")
        print(f"Project commit: {current_head}")
        print(f"Report: {root / REPORT_FILE}")
    return 0


def main() -> int:
    args = parse_args()
    try:
        if args.command == "prepare":
            return prepare(args.runtime, args.root)
        if args.command == "run":
            return run_live_runtime(args)
        if args.command == "verify":
            return verify(args.root, args.json)
        return 1
    except (RehearsalError, OSError) as exc:
        print(f"LIVE RUNTIME REHEARSAL FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
