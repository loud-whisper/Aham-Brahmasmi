#!/usr/bin/env python3
"""Owner-facing outcome of a wrap-up, and what optional Git history says about it.

Everything here reads local state only. No function contacts a remote, creates one,
chooses one or pushes. A comparison with an upstream-tracking ref describes the copy
of that ref already on this machine, not the remote's current state.
"""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

from state_io import StateError

ROUTED_FIELDS = ("durable_facts", "unfinished_work", "reusable_lessons", "project_updates", "history")
APPLIED_STATUS = {"task_complete": "completed", "task_cancel": "cancelled",
                  "fact_supersede": "superseded", "fact_retract": "retracted"}
UPSTREAM_RELATIONS = ("matches_upstream_ref", "behind_upstream_ref", "ahead_of_upstream_ref",
                      "diverged_from_upstream_ref")


def _transport_ready(workspace: Path) -> bool:
    """True when the workspace is itself an initialized Git transport repository."""
    import git_transport

    try:
        git_transport.require_git()
        if git_transport.discovered_repo_root(workspace) is None:
            return False
        git_transport.require_transport_repo(workspace)
        return True
    except (StateError, OSError):
        return False


def upstream_relation(workspace: Path) -> str:
    """Relation of HEAD to the local upstream-tracking ref, or ``not_configured``.

    Derived only from refs already present. Nothing is fetched, so a result of
    ``matches_upstream_ref`` does not show the remote has no newer commits.
    """
    import git_transport

    if not _transport_ready(workspace):
        return "not_configured"
    try:
        if git_transport.run_git(workspace, "rev-parse", "--verify", "--quiet", "@{upstream}",
                                 check=False).returncode != 0:
            return "not_configured"
        counts = git_transport.run_git(workspace, "rev-list", "--left-right", "--count",
                                       "HEAD...@{upstream}").stdout.split()
        ahead, behind = int(counts[0]), int(counts[1])
    except (StateError, OSError, ValueError, IndexError):
        return "not_configured"
    if ahead and behind:
        return "diverged_from_upstream_ref"
    if behind:
        return "behind_upstream_ref"
    return "ahead_of_upstream_ref" if ahead else "matches_upstream_ref"


def snapshot_state(workspace: Path) -> dict[str, Any]:
    """Whether the durable workspace state is contained in a local Git commit."""
    import git_transport

    if not _transport_ready(workspace):
        return {"status": "not_configured", "commit": None}
    try:
        durable_paths = list(git_transport.load_contract()["durable_paths"])
        if git_transport.durable_status_count(workspace, durable_paths) == 0:
            head = git_transport.current_head(workspace)
            if head:
                return {"status": "committed", "commit": head}
    except (StateError, OSError):
        return {"status": "failed", "commit": None}
    return {"status": "not_requested", "commit": None}


def take_snapshot(workspace: Path, operation_id: str) -> dict[str, Any]:
    """Commit a local snapshot through the existing transport. Never pushes.

    A failure is reported, not raised: the wrap-up is already committed to the
    workspace ledger and an optional snapshot cannot invalidate it.
    """
    import git_transport

    if not _transport_ready(workspace):
        return {"status": "not_configured", "commit": None}
    try:
        with redirect_stdout(io.StringIO()):
            git_transport.snapshot_transport(workspace, f"Wrap-up {operation_id}")
    except (StateError, OSError):
        return {"status": "failed", "commit": None}
    state = snapshot_state(workspace)
    return state if state["status"] == "committed" else {"status": "failed", "commit": None}


def replication_state(workspace: Path, snapshot: dict[str, Any]) -> dict[str, str]:
    """Whether the snapshot is contained in the local upstream-tracking ref."""
    relation = upstream_relation(workspace)
    if relation == "not_configured":
        return {"status": "not_configured"}
    if snapshot["status"] != "committed":
        return {"status": "not_checked"}
    if relation in {"ahead_of_upstream_ref", "diverged_from_upstream_ref"}:
        return {"status": "ahead_of_upstream_ref"}
    return {"status": "contained_in_upstream_ref"}


def _next_action(next_steps: list[str], outcome: str, snapshot: dict[str, Any], replication: dict[str, str]) -> str:
    if outcome == "blocked":
        return "Recover this wrap-up before new work: a recorded task or fact change has not been applied."
    parts = [next_steps[0] if next_steps else "No next step was recorded."]
    if snapshot["status"] == "not_requested":
        parts.append("This wrap-up is not yet in the workspace Git history; take a Git snapshot to capture it.")
    elif snapshot["status"] == "failed":
        parts.append("The Git snapshot failed; check the Git transport status and take the snapshot again.")
    if replication["status"] == "ahead_of_upstream_ref":
        parts.append("The snapshot exists only on this machine; the owner may push the workspace repository. "
                     "Aham never pushes.")
    return " ".join(parts)


def wrap_up_summary(workspace: Path, record: dict[str, Any], snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    """Summarize a committed wrap-up: what was routed, closed and left open."""
    from record_lifecycle import replay

    completed = record["details"]["receipt"]
    bundle = completed["bundle"]
    state = replay(workspace)
    statuses = {task["task_id"]: task["status"] for task in state["tasks"]}
    statuses.update({fact["fact_id"]: fact["status"] for fact in state["facts"]})
    lifecycle = [{"id": entry["id"], "action": entry["action"],
                  "status": "applied" if statuses.get(entry["id"]) == APPLIED_STATUS[entry["action"]] else "pending"}
                 for entry in completed.get("lifecycle") or []]
    outcome = "complete" if all(entry["status"] == "applied" for entry in lifecycle) else "blocked"
    snapshot = snapshot if snapshot is not None else snapshot_state(workspace)
    replication = replication_state(workspace, snapshot)
    return {
        "outcome": outcome,
        "routed": {field: len(bundle[field]) for field in ROUTED_FIELDS},
        "tasks_completed": [entry["id"] for entry in lifecycle
                            if entry["action"] == "task_complete" and entry["status"] == "applied"],
        "tasks_open": sum(1 for task in state["tasks"] if task["status"] == "open"),
        "lifecycle": lifecycle,
        "snapshot": snapshot,
        "replication": replication,
        "next_action": _next_action(bundle["checkpoint"]["next_steps"], outcome, snapshot, replication),
    }


def pending_summary(recovery_action: str) -> dict[str, Any]:
    """Summary of a wrap-up that has not committed: nothing is done yet."""
    return {
        "outcome": "blocked",
        "routed": {field: 0 for field in ROUTED_FIELDS},
        "tasks_completed": [],
        "tasks_open": None,
        "lifecycle": [],
        "snapshot": {"status": "not_requested", "commit": None},
        "replication": {"status": "not_checked"},
        "next_action": "Recover the pending wrap-up: " + recovery_action,
    }


def summary_lines(summary: dict[str, Any]) -> list[str]:
    routed = ", ".join(f"{field} {count}" for field, count in summary["routed"].items() if count) or "nothing"
    lines = [
        f"Outcome: {summary['outcome']}",
        f"Routed: {routed}",
        "Tasks completed: " + (", ".join(summary["tasks_completed"]) or "none"),
        "Tasks still open: " + ("unknown" if summary["tasks_open"] is None else str(summary["tasks_open"])),
    ]
    for entry in summary["lifecycle"]:
        lines.append(f"Record change: {entry['action']} {entry['id']} ({entry['status']})")
    snapshot = summary["snapshot"]
    lines.append("Git snapshot: " + snapshot["status"] + (f" ({snapshot['commit']})" if snapshot["commit"] else ""))
    lines.append("Copy off this machine: " + summary["replication"]["status"])
    lines.append("Next action: " + summary["next_action"])
    return lines
