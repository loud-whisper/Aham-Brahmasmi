#!/usr/bin/env python3
"""Run rehearsal commands inside a narrow Linux Bubblewrap mount namespace."""

from __future__ import annotations

import argparse
import json
import os
import posixpath
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SANDBOX_HOME = "/" + "home/aham"
TASK_CONTRACT_GUEST = "/control/task.json"
TASK_CONTRACT_FORMAT = "aham-brahmasmi-agent-task-contract"
TASK_CONTRACT_FIELDS = {"format", "version", "runtime", "rehearsal_id", "task_marker", "commit_message"}
PROTECTED_GUEST_ROOTS = {
    "/framework",
    "/work",
    "/home",
    "/control",
    "/proc",
    "/dev",
    "/tmp",
    "/usr",
    "/bin",
    "/sbin",
    "/lib",
    "/lib64",
}
FORBIDDEN_BROAD_HOSTS = {Path("/"), Path("/home"), Path("/run"), Path("/var/run")}


class SandboxError(RuntimeError):
    """Raised when the rehearsal cannot be placed inside the declared sandbox."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an Aham rehearsal command inside a Linux Bubblewrap sandbox.")
    sub = parser.add_subparsers(dest="subcommand", required=True)
    run = sub.add_parser("run", help="Run one command inside the isolated rehearsal environment")
    run.add_argument("--workspace", required=True, help="Synthetic rehearsal Brain workspace")
    run.add_argument("--project", required=True, help="Synthetic rehearsal project")
    run.add_argument(
        "--task-contract",
        help="Trusted read-only minimal task contract mounted at the protected /control/task.json path",
    )
    run.add_argument(
        "--deny-network",
        action="store_true",
        help="Also unshare the network namespace; some restricted hosts cannot provide this extra isolation",
    )
    run.add_argument(
        "--sudo-namespace-helper",
        action="store_true",
        help="Use sudo only to create restricted namespaces, then drop to the invoking UID/GID before the command runs",
    )
    run.add_argument(
        "--pass-env",
        action="append",
        default=[],
        metavar="NAME",
        help="Explicitly copy one environment variable into the sandbox; repeat as needed",
    )
    run.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="Explicitly set one environment variable inside the sandbox; repeat as needed",
    )
    run.add_argument(
        "--ro-bind",
        action="append",
        default=[],
        metavar="HOST:GUEST",
        help="Explicitly expose one additional host path read-only at a non-protected absolute guest path",
    )
    run.add_argument(
        "--rw-bind",
        action="append",
        default=[],
        metavar="HOST:GUEST",
        help="Explicitly expose one additional host path read-write at a non-protected absolute guest path",
    )
    run.add_argument("command", nargs=argparse.REMAINDER, help="Command after --")
    return parser.parse_args()


def require_linux_bwrap() -> str:
    if not sys.platform.startswith("linux"):
        raise SandboxError("OS-enforced rehearsal isolation currently supports Linux only")
    bwrap = shutil.which("bwrap")
    if not bwrap:
        raise SandboxError("bubblewrap (bwrap) is required for OS-enforced rehearsal isolation")
    return bwrap


def existing_directory(value: str, label: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        raise SandboxError(f"{label} does not exist or is not a directory: {path}")
    return path


def validate_task_contract(path: Path) -> Path:
    if path.is_symlink() or not path.is_file():
        raise SandboxError("task contract is missing, symlinked, or not a regular file")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SandboxError(f"task contract is unreadable: {exc}") from exc
    if not isinstance(payload, dict) or set(payload) != TASK_CONTRACT_FIELDS:
        raise SandboxError("task contract does not match the minimal contract schema")
    if payload.get("format") != TASK_CONTRACT_FORMAT or payload.get("version") != 1:
        raise SandboxError("task contract format/version is not recognized")
    for field in ("runtime", "rehearsal_id", "task_marker", "commit_message"):
        if not isinstance(payload.get(field), str) or not payload[field]:
            raise SandboxError(f"task contract field '{field}' must be a non-empty string")
    return path


def trusted_contract(value: str | None) -> Path | None:
    if value is None:
        return None
    raw = Path(value).expanduser()
    if raw.is_symlink():
        raise SandboxError("task contract may not be a symlink")
    return validate_task_contract(raw.resolve())


def parse_binding(value: str, *, writable: bool) -> tuple[Path, str, bool]:
    if ":" not in value:
        raise SandboxError("additional bindings must use HOST:GUEST syntax")
    host_raw, guest = value.split(":", 1)
    raw_host = Path(host_raw).expanduser()
    if raw_host.is_symlink():
        raise SandboxError("explicit bind source may not itself be a symlink")
    host = raw_host.resolve()
    if not host.exists():
        raise SandboxError(f"explicit bind source does not exist: {host}")
    forbidden_hosts = set(FORBIDDEN_BROAD_HOSTS)
    forbidden_hosts.add(Path.home().expanduser().resolve())
    if host in forbidden_hosts:
        raise SandboxError(f"refusing broad host bind for {host}; expose only the specific file or directory required")
    if not guest.startswith("/") or guest == "/":
        raise SandboxError("explicit bind destination must be an absolute non-root path")
    normalized_guest = posixpath.normpath(guest)
    if normalized_guest != guest:
        raise SandboxError(f"explicit bind destination must be canonical and traversal-free: {guest}")
    if normalized_guest == TASK_CONTRACT_GUEST:
        if writable:
            raise SandboxError("the protected task contract may only be mounted read-only")
        validate_task_contract(host)
        return host, normalized_guest, False
    if any(normalized_guest == root or normalized_guest.startswith(root + "/") for root in PROTECTED_GUEST_ROOTS):
        raise SandboxError(f"explicit bind may not override protected sandbox destination: {guest}")
    return host, normalized_guest, writable


def system_mounts() -> list[tuple[Path, str]]:
    mounts: list[tuple[Path, str]] = []
    for name in ("usr", "bin", "sbin", "lib", "lib64"):
        host = Path("/") / name
        if host.exists():
            mounts.append((host, f"/{name}"))
    return mounts


def sandbox_runtime_override(project: Path, control: Path) -> Path | None:
    source = project / ".aham" / "runtime.json"
    if not source.is_file() or source.is_symlink():
        return None
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SandboxError(f"project runtime configuration is unreadable: {exc}") from exc
    if not isinstance(payload, dict):
        raise SandboxError("project runtime configuration must be a JSON object")
    payload["framework_root"] = "/framework"
    payload["workspace"] = "/work/workspace"
    payload["project"] = "/work/project"
    override = control / "runtime.json"
    override.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return override


def sanitized_environment(args: argparse.Namespace) -> list[str]:
    pairs: dict[str, str] = {
        "HOME": SANDBOX_HOME,
        "USER": "aham",
        "LOGNAME": "aham",
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "XDG_CONFIG_HOME": f"{SANDBOX_HOME}/.config",
        "XDG_CACHE_HOME": f"{SANDBOX_HOME}/.cache",
        "XDG_DATA_HOME": f"{SANDBOX_HOME}/.local/share",
        "PYTHONNOUSERSITE": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "AHAM_REHEARSAL_SANDBOX": "1",
    }
    for name in args.pass_env:
        if not name or "=" in name or "\x00" in name:
            raise SandboxError(f"invalid --pass-env name: {name!r}")
        if name in {"HOME", "USER", "LOGNAME", "SSH_AUTH_SOCK", "DOCKER_HOST"}:
            raise SandboxError(f"refusing reserved or high-risk environment passthrough: {name}")
        if name not in os.environ:
            raise SandboxError(f"requested environment variable is not set: {name}")
        pairs[name] = os.environ[name]
    for assignment in args.env:
        if "=" not in assignment:
            raise SandboxError("--env requires NAME=VALUE")
        name, value = assignment.split("=", 1)
        if not name or "\x00" in name or "\x00" in value:
            raise SandboxError("invalid --env assignment")
        if name in {"HOME", "USER", "LOGNAME", "SSH_AUTH_SOCK", "DOCKER_HOST"}:
            raise SandboxError(f"refusing reserved or high-risk environment override: {name}")
        pairs[name] = value
    rendered: list[str] = ["--clearenv"]
    for name, value in pairs.items():
        rendered.extend(["--setenv", name, value])
    return rendered


def bubblewrap_prefix(args: argparse.Namespace, bwrap: str) -> list[str]:
    if not args.sudo_namespace_helper:
        prefix = [bwrap, "--die-with-parent", "--new-session", "--unshare-all"]
        if not args.deny_network:
            prefix.append("--share-net")
        return prefix

    sudo = shutil.which("sudo")
    if not sudo:
        raise SandboxError("--sudo-namespace-helper requires sudo")
    if os.geteuid() == 0:
        raise SandboxError("--sudo-namespace-helper must be invoked by a non-root user")
    prefix = [
        sudo,
        "--non-interactive",
        bwrap,
        "--die-with-parent",
        "--new-session",
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-uts",
        "--unshare-cgroup-try",
    ]
    if args.deny_network:
        prefix.append("--unshare-net")
    return prefix


def command_for_sandbox(args: argparse.Namespace, command: list[str]) -> list[str]:
    if not args.sudo_namespace_helper:
        return command
    setpriv = shutil.which("setpriv")
    if not setpriv or not setpriv.startswith("/usr/"):
        raise SandboxError("--sudo-namespace-helper requires util-linux setpriv under /usr")
    return [
        setpriv,
        f"--reuid={os.getuid()}",
        f"--regid={os.getgid()}",
        "--clear-groups",
        "--inh-caps=-all",
        "--bounding-set=-all",
        "--no-new-privs",
        "--",
        *command,
    ]


def run_sandbox(args: argparse.Namespace) -> int:
    bwrap = require_linux_bwrap()
    workspace = existing_directory(args.workspace, "rehearsal workspace")
    project = existing_directory(args.project, "rehearsal project")
    contract = trusted_contract(args.task_contract)
    if workspace == project or workspace in project.parents or project in workspace.parents:
        raise SandboxError("rehearsal workspace and project must be separate directories")

    command = list(args.command)
    if command and command[0] == "--":
        command.pop(0)
    if not command:
        raise SandboxError("provide a command after --")
    command = command_for_sandbox(args, command)

    extra_bindings = [parse_binding(item, writable=False) for item in args.ro_bind]
    extra_bindings += [parse_binding(item, writable=True) for item in args.rw_bind]
    guest_destinations = [guest for _host, guest, _writable in extra_bindings]
    if len(guest_destinations) != len(set(guest_destinations)):
        raise SandboxError("duplicate explicit bind destinations are not allowed")
    if contract is not None and TASK_CONTRACT_GUEST in guest_destinations:
        raise SandboxError("task contract destination was supplied more than once")

    with tempfile.TemporaryDirectory(prefix="aham-sandbox-home-") as home_raw, tempfile.TemporaryDirectory(
        prefix="aham-sandbox-control-"
    ) as control_raw:
        home = Path(home_raw)
        control = Path(control_raw)
        runtime_override = sandbox_runtime_override(project, control)

        invocation = bubblewrap_prefix(args, bwrap)
        invocation += sanitized_environment(args)
        invocation += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp"]
        for host, guest in system_mounts():
            invocation += ["--ro-bind", str(host), guest]
        invocation += [
            "--dir",
            "/work",
            "--dir",
            "/home",
            "--dir",
            "/control",
            "--ro-bind",
            str(ROOT),
            "/framework",
            "--bind",
            str(workspace),
            "/work/workspace",
            "--bind",
            str(project),
            "/work/project",
            "--bind",
            str(home),
            SANDBOX_HOME,
        ]
        if runtime_override is not None:
            invocation += ["--ro-bind", str(runtime_override), "/work/project/.aham/runtime.json"]
        if contract is not None:
            invocation += ["--ro-bind", str(contract), TASK_CONTRACT_GUEST]
        for host, guest, writable in extra_bindings:
            invocation += ["--bind" if writable else "--ro-bind", str(host), guest]
        invocation += ["--chdir", "/work/project", "--", *command]

        result = subprocess.run(invocation, text=True, check=False)
        return int(result.returncode)


def main() -> int:
    args = parse_args()
    try:
        if args.subcommand == "run":
            return run_sandbox(args)
        raise SandboxError("unknown sandbox command")
    except (SandboxError, OSError) as exc:
        print(f"REHEARSAL SANDBOX FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
