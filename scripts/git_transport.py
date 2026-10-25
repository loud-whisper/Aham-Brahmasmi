#!/usr/bin/env python3
"""Optional host-neutral Git versioning for selected durable Brain state."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from state_io import StateError, read_json, require_workspace, resolve_workspace, utc_now


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "core" / "git_transport.json"
GIT_TIMEOUT_SECONDS = 30


class GitTransportError(StateError):
    """Raised when optional Git transport cannot proceed safely."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Version selected durable Brain state with local Git.")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Initialize local Git versioning in the private workspace")
    init.add_argument("--workspace", required=True)
    init.add_argument("--author-name")
    init.add_argument("--author-email")

    status = sub.add_parser("status", help="Inspect local Git transport state")
    status.add_argument("--workspace", required=True)

    snapshot = sub.add_parser("snapshot", help="Commit only the durable paths allowed by the Git transport contract")
    snapshot.add_argument("--workspace", required=True)
    snapshot.add_argument("--message", help="Commit message; a timestamped durable snapshot message is used when omitted")

    return parser.parse_args()


def _git_command(workspace: Path, *args: str) -> list[str]:
    # Keep automatic line-ending conversion from changing transport content on hosts
    # whose inherited Git configuration enables it globally.
    return [
        "git",
        "-c",
        "core.autocrlf=false",
        "-c",
        "core.safecrlf=false",
        "-C",
        str(workspace),
        *args,
    ]


def run_git(workspace: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            _git_command(workspace, *args),
            text=True,
            capture_output=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitTransportError(f"Git command timed out after {GIT_TIMEOUT_SECONDS} seconds") from exc
    if check and result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "git command failed"
        raise GitTransportError(message)
    return result


def run_commit_without_hooks(workspace: Path, message: str) -> None:
    """Create the transport commit without executing repository or configured Git hooks."""
    require_transport_repo(workspace)
    with tempfile.TemporaryDirectory(prefix="aham-git-hooks-") as hooks_dir:
        try:
            result = subprocess.run(
                _git_command(
                    workspace,
                    "-c",
                    f"core.hooksPath={hooks_dir}",
                    "-c",
                    "commit.gpgsign=false",
                    "commit",
                    "-m",
                    message,
                ),
                text=True,
                capture_output=True,
                check=False,
                timeout=GIT_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise GitTransportError(f"Git commit timed out after {GIT_TIMEOUT_SECONDS} seconds") from exc
    if result.returncode != 0:
        message_text = result.stderr.strip() or result.stdout.strip() or "git commit failed"
        raise GitTransportError(message_text)


def load_contract() -> dict[str, Any]:
    contract = read_json(CONTRACT_PATH)
    if contract.get("version") != 1 or contract.get("id") != "git":
        raise GitTransportError("Git transport contract is missing or unsupported")
    durable = contract.get("durable_paths")
    excluded = contract.get("excluded_paths")
    if not isinstance(durable, list) or not durable or not all(isinstance(item, str) and item for item in durable):
        raise GitTransportError("Git transport contract has no valid durable path allowlist")
    if not isinstance(excluded, list) or not all(isinstance(item, str) and item for item in excluded):
        raise GitTransportError("Git transport contract has no valid excluded path list")
    return contract


def require_git() -> None:
    if shutil.which("git") is None:
        raise GitTransportError("Git is not installed or not available on PATH")


def discovered_repo_root(workspace: Path) -> Path | None:
    result = run_git(workspace, "rev-parse", "--show-toplevel", check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return Path(result.stdout.strip()).resolve()


def _git_path(workspace: Path, argument: str) -> Path:
    raw = run_git(workspace, "rev-parse", argument).stdout.strip()
    path = Path(raw)
    if not path.is_absolute():
        path = workspace / path
    return path.resolve()


def require_transport_repo(workspace: Path) -> Path:
    root = workspace.resolve()
    discovered = discovered_repo_root(root)
    if discovered is None:
        raise GitTransportError("Git transport is not initialized; run the init command first")
    if discovered != root:
        raise GitTransportError(
            f"refusing unrelated enclosing Git repository; Brain root is {root} but Git top-level is {discovered}"
        )
    git_dir = _git_path(root, "--git-dir")
    common_dir = _git_path(root, "--git-common-dir")
    if git_dir != common_dir:
        raise GitTransportError("linked Git worktrees are not supported for Brain transport; use a standalone repository")
    return discovered


def is_repo(workspace: Path) -> bool:
    discovered = discovered_repo_root(workspace.resolve())
    return discovered == workspace.resolve()


def normalize_rule_path(value: str) -> str:
    return value.strip().lstrip("./")


def path_allowed(path: str, durable_paths: list[str]) -> bool:
    normalized = normalize_rule_path(path)
    for rule in durable_paths:
        rule_normalized = normalize_rule_path(rule)
        if rule_normalized.endswith("/"):
            prefix = rule_normalized.rstrip("/") + "/"
            if normalized.startswith(prefix):
                return True
        elif normalized == rule_normalized:
            return True
    return False


def staged_paths(workspace: Path) -> list[str]:
    require_transport_repo(workspace)
    result = run_git(workspace, "diff", "--cached", "--name-only", "--diff-filter=ACDMRTUXB")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def ensure_staged_paths_are_allowed(workspace: Path, durable_paths: list[str]) -> None:
    outside = [path for path in staged_paths(workspace) if not path_allowed(path, durable_paths)]
    if outside:
        raise GitTransportError(
            "refusing durable snapshot because unrelated paths are already staged: " + ", ".join(sorted(outside))
        )


def tracked_under(workspace: Path, relative: str) -> bool:
    require_transport_repo(workspace)
    result = run_git(workspace, "ls-files", "--", relative, check=False)
    return bool(result.stdout.strip())


def selected_durable_roots(workspace: Path, durable_paths: list[str]) -> list[str]:
    selected: list[str] = []
    for rule in durable_paths:
        relative = normalize_rule_path(rule).rstrip("/")
        if (workspace / relative).exists() or tracked_under(workspace, relative):
            selected.append(relative)
    return selected


def snapshot_candidate_paths(workspace: Path, durable_paths: list[str]) -> list[str]:
    selected = selected_durable_roots(workspace, durable_paths)
    if not selected:
        return []
    result = run_git(
        workspace,
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "--",
        *selected,
    )
    return sorted({line for line in result.stdout.splitlines() if line})


def ensure_no_git_filters(workspace: Path, durable_paths: list[str]) -> None:
    """Refuse clean/smudge filter attributes before Git inspects/stages durable content."""
    candidates = snapshot_candidate_paths(workspace, durable_paths)
    if not candidates:
        return
    result = run_git(workspace, "check-attr", "-z", "filter", "--", *candidates)
    fields = result.stdout.split("\0")
    if fields and fields[-1] == "":
        fields.pop()
    if len(fields) % 3 != 0:
        raise GitTransportError("Git returned malformed filter-attribute information")
    active: list[str] = []
    for index in range(0, len(fields), 3):
        path, attribute, value = fields[index : index + 3]
        if attribute != "filter":
            continue
        if value not in {"unspecified", "unset", ""}:
            active.append(f"{path} ({value})")
    if active:
        raise GitTransportError(
            "refusing durable snapshot because a Git filter attribute is active for durable content: "
            + ", ".join(active)
        )


def stage_durable_paths(workspace: Path, durable_paths: list[str]) -> None:
    require_transport_repo(workspace)
    selected = selected_durable_roots(workspace, durable_paths)
    if not selected:
        return
    run_git(workspace, "add", "-A", "--", *selected)


def git_identity(workspace: Path) -> tuple[str | None, str | None]:
    require_transport_repo(workspace)
    name = run_git(workspace, "config", "--local", "user.name", check=False).stdout.strip() or None
    email = run_git(workspace, "config", "--local", "user.email", check=False).stdout.strip() or None
    return name, email


def configure_identity(workspace: Path, name: str | None, email: str | None) -> None:
    require_transport_repo(workspace)
    if bool(name) != bool(email):
        raise GitTransportError("provide both --author-name and --author-email, or neither")
    if name and email:
        run_git(workspace, "config", "--local", "user.name", name)
        run_git(workspace, "config", "--local", "user.email", email)


def current_branch(workspace: Path) -> str | None:
    require_transport_repo(workspace)
    result = run_git(workspace, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None


def current_head(workspace: Path) -> str | None:
    require_transport_repo(workspace)
    result = run_git(workspace, "rev-parse", "HEAD", check=False)
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None


def durable_status_count(workspace: Path, durable_paths: list[str]) -> int:
    require_transport_repo(workspace)
    selected = [normalize_rule_path(rule).rstrip("/") for rule in durable_paths]
    result = run_git(workspace, "status", "--porcelain=v1", "--untracked-files=all", "--", *selected)
    return sum(1 for line in result.stdout.splitlines() if line.strip())


def init_transport(workspace: Path, author_name: str | None, author_email: str | None) -> int:
    require_workspace(workspace)
    require_git()
    discovered = discovered_repo_root(workspace)
    if discovered is not None and discovered != workspace.resolve():
        raise GitTransportError(
            f"refusing unrelated enclosing Git repository; Brain root is {workspace.resolve()} but Git top-level is {discovered}"
        )
    if discovered is None:
        # An explicit empty template prevents user/system init.templateDir settings from
        # silently copying executable hooks into a Brain repository created by this tool.
        with tempfile.TemporaryDirectory(prefix="aham-git-template-") as template_dir:
            try:
                result = subprocess.run(
                    [
                        "git",
                        "-c",
                        "core.autocrlf=false",
                        "-c",
                        "core.safecrlf=false",
                        "init",
                        f"--template={template_dir}",
                        str(workspace),
                    ],
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=GIT_TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired as exc:
                raise GitTransportError(f"Git init timed out after {GIT_TIMEOUT_SECONDS} seconds") from exc
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "git init failed"
            raise GitTransportError(message)
    require_transport_repo(workspace)
    configure_identity(workspace, author_name, author_email)
    name, email = git_identity(workspace)
    print("GIT TRANSPORT INITIALIZED")
    print("Remote required: no")
    print("Git hooks during transport commits: disabled")
    print(f"Commit identity: {'configured' if name and email else 'not configured'}")
    if not (name and email):
        print("A commit identity is required before the first snapshot.")
    return 0


def status_transport(workspace: Path) -> int:
    require_workspace(workspace)
    require_git()
    contract = load_contract()
    discovered = discovered_repo_root(workspace)
    if discovered is None:
        print("GIT TRANSPORT STATUS")
        print("Initialized: no")
        print("Remote required: no")
        return 0
    require_transport_repo(workspace)
    durable_paths = list(contract["durable_paths"])
    print("GIT TRANSPORT STATUS")
    print("Initialized: yes")
    print(f"Branch: {current_branch(workspace) or '(detached/no branch yet)'}")
    print(f"Head: {current_head(workspace) or '(no commits yet)'}")
    print(f"Durable changes: {durable_status_count(workspace, durable_paths)}")
    remote_lines = run_git(workspace, "remote", check=False).stdout.splitlines()
    print(f"Configured remotes: {len([line for line in remote_lines if line.strip()])}")
    return 0


def snapshot_transport(workspace: Path, message: str | None) -> int:
    require_workspace(workspace)
    require_git()
    contract = load_contract()
    require_transport_repo(workspace)

    durable_paths = list(contract["durable_paths"])
    ensure_staged_paths_are_allowed(workspace, durable_paths)
    ensure_no_git_filters(workspace, durable_paths)

    head_before = current_head(workspace)
    if head_before and current_branch(workspace) is None:
        raise GitTransportError(
            "refusing durable snapshot on detached HEAD; switch to a named branch before creating another snapshot"
        )

    if durable_status_count(workspace, durable_paths) == 0:
        print("GIT SNAPSHOT: no durable changes")
        print(f"Head: {head_before or '(no commits yet)'}")
        return 0

    name, email = git_identity(workspace)
    if not (name and email):
        raise GitTransportError(
            "Git commit identity is not configured; initialize with --author-name and --author-email or configure Git identity yourself"
        )

    # Re-check attributes immediately before staging so a later status/stage operation is
    # never the first point at which a configured clean filter can execute.
    ensure_no_git_filters(workspace, durable_paths)
    stage_durable_paths(workspace, durable_paths)
    ensure_staged_paths_are_allowed(workspace, durable_paths)
    staged = staged_paths(workspace)
    if not staged:
        print("GIT SNAPSHOT: no durable changes")
        print(f"Head: {current_head(workspace) or '(no commits yet)'}")
        return 0

    commit_message = message.strip() if isinstance(message, str) and message.strip() else f"Brain durable snapshot {utc_now()}"
    run_commit_without_hooks(workspace, commit_message)
    head = current_head(workspace)
    if not head:
        raise GitTransportError("Git reported a successful commit but no HEAD could be verified")

    print("GIT SNAPSHOT SAVED")
    print(f"Head: {head}")
    print(f"Files: {len(staged)}")
    print("Remote push: not performed")
    print("Git hooks: not executed by transport commit")
    return 0


def main() -> int:
    args = parse_args()
    workspace = resolve_workspace(args.workspace)
    try:
        if args.command == "init":
            return init_transport(workspace, args.author_name, args.author_email)
        if args.command == "status":
            return status_transport(workspace)
        if args.command == "snapshot":
            return snapshot_transport(workspace, args.message)
        raise GitTransportError("unsupported Git transport command")
    except (GitTransportError, StateError, OSError) as exc:
        print(f"GIT TRANSPORT FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
