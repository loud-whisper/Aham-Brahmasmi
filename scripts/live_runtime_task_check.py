#!/usr/bin/env python3
"""Verify live-rehearsal task state before a runtime may checkpoint it."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


FORMAT = "aham-brahmasmi-live-runtime-rehearsal"
CONTRACT_FORMAT = "aham-brahmasmi-agent-task-contract"
EVIDENCE_FORMAT = "aham-brahmasmi-live-runtime-evidence"
VERSION = 1
EVIDENCE_FILE = "LIVE_RUNTIME_EVIDENCE.json"
REQUIRED_TASK_FILES = {"task.txt", EVIDENCE_FILE}
SUPPORTED = {"claude", "gemini", "codex", "local"}
CONTRACT_FIELDS = {
    "format",
    "version",
    "runtime",
    "rehearsal_id",
    "task_marker",
    "commit_message",
}


class TaskCheckError(RuntimeError):
    """Raised when required live-rehearsal task state is not verified."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify the exact live-runtime rehearsal task state before checkpointing."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--root", help="Trusted prepared live-runtime rehearsal root")
    source.add_argument("--contract", help="Read-only minimal task contract exposed to an isolated runtime")
    parser.add_argument(
        "--project",
        help="Project path to verify when --contract is used; ignored for trusted --root verification",
    )
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TaskCheckError(f"could not read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise TaskCheckError(f"expected a JSON object in {path}")
    return value


def run_git(project: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(project), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise TaskCheckError(f"git command failed: {detail}")
    return result.stdout.strip()


def resolve_root(value: str) -> Path:
    raw = Path(value).expanduser()
    if raw.is_symlink():
        raise TaskCheckError("the rehearsal root may not be a symlink")
    root = raw.resolve()
    if not root.is_dir():
        raise TaskCheckError("the rehearsal root does not exist")
    return root


def trusted_expectations(root: Path) -> tuple[Path, dict[str, Any]]:
    manifest = read_json(root / "rehearsal.json")
    if manifest.get("format") != FORMAT or manifest.get("version") != VERSION:
        raise TaskCheckError("rehearsal manifest format is not recognized")

    project = Path(str(manifest.get("project", ""))).expanduser().resolve()
    if project.parent != root or not project.is_dir():
        raise TaskCheckError("rehearsal manifest project path no longer points inside the rehearsal root")
    return project, manifest


def contract_expectations(contract_value: str, project_value: str | None) -> tuple[Path, dict[str, Any]]:
    if not project_value:
        raise TaskCheckError("--project is required with --contract")
    contract_path = Path(contract_value).expanduser()
    if contract_path.is_symlink() or not contract_path.is_file():
        raise TaskCheckError("task contract is missing or is not a regular file")
    contract = read_json(contract_path)
    if set(contract) != CONTRACT_FIELDS:
        raise TaskCheckError("task contract fields do not exactly match the minimal contract schema")
    if contract.get("format") != CONTRACT_FORMAT or contract.get("version") != VERSION:
        raise TaskCheckError("task contract format is not recognized")

    project = Path(project_value).expanduser().resolve()
    if not project.is_dir():
        raise TaskCheckError("project does not exist")
    return project, contract


def verify_task(project: Path, expected: dict[str, Any]) -> tuple[str, str]:
    runtime = expected.get("runtime")
    if runtime not in SUPPORTED:
        raise TaskCheckError("rehearsal identity has an unsupported runtime")
    rehearsal_id = expected.get("rehearsal_id")
    if not isinstance(rehearsal_id, str) or not rehearsal_id:
        raise TaskCheckError("rehearsal identity has no rehearsal ID")

    task_marker = expected.get("task_marker")
    if not isinstance(task_marker, str) or not task_marker:
        raise TaskCheckError("rehearsal identity has no task marker")
    commit_message = expected.get("commit_message")
    if not isinstance(commit_message, str) or not commit_message:
        raise TaskCheckError("rehearsal identity has no commit message")

    task_path = project / "task.txt"
    if task_path.is_symlink() or not task_path.is_file():
        raise TaskCheckError("task.txt is missing or is not a regular file")
    task_text = task_path.read_text(encoding="utf-8")
    if task_text not in {task_marker, task_marker + "\n"}:
        raise TaskCheckError("task.txt does not contain only the exact live rehearsal completion marker")

    current_head = run_git(project, "rev-parse", "HEAD")
    latest_message = run_git(project, "log", "-1", "--pretty=%s")
    if latest_message != commit_message:
        raise TaskCheckError("latest project commit does not have the expected live rehearsal message")

    changed_files = {
        line
        for line in run_git(project, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").splitlines()
        if line
    }
    if changed_files != REQUIRED_TASK_FILES:
        expected_files = ", ".join(sorted(REQUIRED_TASK_FILES))
        found = ", ".join(sorted(changed_files)) or "(none)"
        raise TaskCheckError(
            f"latest live task commit must change only {expected_files}; found: {found}"
        )

    for required in REQUIRED_TASK_FILES:
        run_git(project, "ls-files", "--error-unmatch", required)

    required_dirty = run_git(
        project,
        "diff",
        "--name-only",
        "HEAD",
        "--",
        "task.txt",
        EVIDENCE_FILE,
    )
    if required_dirty:
        raise TaskCheckError("required rehearsal files changed after the live task commit")

    status = run_git(project, "status", "--porcelain=v1", "--untracked-files=all")
    if status:
        raise TaskCheckError(
            f"project contains uncommitted or untracked files before checkpointing: {status}"
        )

    evidence_path = project / EVIDENCE_FILE
    if evidence_path.is_symlink() or not evidence_path.is_file():
        raise TaskCheckError("live runtime evidence is missing or is not a regular file")
    evidence = read_json(evidence_path)
    expected_evidence = {
        "format": EVIDENCE_FORMAT,
        "version": 1,
        "runtime": runtime,
        "rehearsal_id": rehearsal_id,
        "startup_ready": True,
    }
    if evidence != expected_evidence:
        raise TaskCheckError("live runtime evidence does not exactly match the prepared rehearsal identity")

    return runtime, current_head


def main() -> int:
    args = parse_args()
    try:
        if args.root is not None:
            root = resolve_root(args.root)
            project, expected = trusted_expectations(root)
        else:
            project, expected = contract_expectations(args.contract, args.project)
        runtime, current_head = verify_task(project, expected)
    except (TaskCheckError, OSError) as exc:
        print(f"TASK STATE FAILED: {exc}", file=sys.stderr)
        return 1

    print("TASK STATE VERIFIED")
    print(f"Runtime: {runtime}")
    print(f"Project commit: {current_head}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
