from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "scripts" / "setup_workspace.py"
WRAP_UP = ROOT / "scripts" / "wrap_up.py"
STARTUP = ROOT / "scripts" / "startup.py"
LIFECYCLE = ROOT / "scripts" / "record_lifecycle.py"


class R2FactTaskLifecycleTests(unittest.TestCase):
    def run_script(self, script: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(script), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def make_workspace(self, root: Path) -> Path:
        workspace = root / "workspace"
        result = self.run_script(SETUP, "--workspace", str(workspace))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return workspace

    def write_json(self, path: Path, value: dict) -> Path:
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def initial_wrap(self, root: Path, workspace: Path) -> None:
        bundle = {
            "operation_id": "r2-origin",
            "durable_facts": ["Alpha is enabled."],
            "unfinished_work": ["Finish alpha migration.", "Write release note."],
            "reusable_lessons": [],
            "project_updates": [],
            "history": [],
            "checkpoint": {
                "summary": "R2 origin state",
                "completed": [],
                "next_steps": ["Continue R2 lifecycle testing"],
            },
        }
        result = self.run_script(
            WRAP_UP,
            "--workspace",
            str(workspace),
            "--bundle",
            str(self.write_json(root / "origin.json", bundle)),
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def list_state(self, workspace: Path) -> dict:
        result = self.run_script(LIFECYCLE, "list", "--workspace", str(workspace), "--json")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return json.loads(result.stdout)

    def apply(self, root: Path, workspace: Path, name: str, request: dict, *extra: str) -> subprocess.CompletedProcess[str]:
        request_path = self.write_json(root / f"{name}.json", request)
        return self.run_script(
            LIFECYCLE,
            "apply",
            "--workspace",
            str(workspace),
            "--request",
            str(request_path),
            *extra,
        )

    def test_wrap_up_records_have_stable_ids_status_and_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            self.initial_wrap(root, workspace)

            first = self.list_state(workspace)
            second = self.list_state(workspace)
            self.assertEqual(first, second)
            self.assertEqual(first["revision"], 1)
            self.assertEqual(len(first["facts"]), 1)
            self.assertEqual(len(first["tasks"]), 2)

            fact = first["facts"][0]
            self.assertRegex(fact["fact_id"], r"^fact_[0-9a-f]{32}$")
            self.assertEqual(fact["statement"], "Alpha is enabled.")
            self.assertEqual(fact["status"], "active")
            self.assertEqual(fact["provenance"]["operation_id"], "r2-origin")
            self.assertEqual(fact["provenance"]["revision"], 1)
            self.assertEqual(fact["provenance"]["source_type"], "wrap_up")
            self.assertRegex(fact["provenance"]["content_digest"], r"^[0-9a-f]{64}$")

            task = first["tasks"][0]
            self.assertRegex(task["task_id"], r"^task_[0-9a-f]{32}$")
            self.assertEqual(task["status"], "open")
            self.assertEqual(task["provenance"]["operation_id"], "r2-origin")
            self.assertEqual(task["provenance"]["revision"], 1)

    def test_conflicting_facts_remain_distinct_with_explicit_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            self.initial_wrap(root, workspace)
            existing = self.list_state(workspace)["facts"][0]

            applied = self.apply(
                root,
                workspace,
                "conflict",
                {
                    "operation_id": "r2-conflict",
                    "action": "fact_assert",
                    "statement": "Alpha is disabled.",
                    "source": "operator-note-2026-09-19",
                    "conflicts_with": [existing["fact_id"]],
                },
            )
            self.assertEqual(applied.returncode, 0, applied.stderr + applied.stdout)

            state = self.list_state(workspace)
            self.assertEqual(state["revision"], 2)
            self.assertEqual(len(state["facts"]), 2)
            by_id = {item["fact_id"]: item for item in state["facts"]}
            newer = next(item for item in state["facts"] if item["statement"] == "Alpha is disabled.")
            self.assertEqual(newer["status"], "active")
            self.assertEqual(newer["provenance"]["source"], "operator-note-2026-09-19")
            self.assertEqual(newer["conflicts_with"], [existing["fact_id"]])
            self.assertIn(newer["fact_id"], by_id[existing["fact_id"]]["conflicts_with"])
            self.assertEqual(by_id[existing["fact_id"]]["statement"], "Alpha is enabled.")

    def test_fact_supersede_and_retract_preserve_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            self.initial_wrap(root, workspace)
            original = self.list_state(workspace)["facts"][0]

            superseded = self.apply(
                root,
                workspace,
                "supersede",
                {
                    "operation_id": "r2-supersede",
                    "action": "fact_supersede",
                    "fact_id": original["fact_id"],
                    "statement": "Alpha is enabled in production only.",
                    "source": "deployment-record-42",
                    "reason": "Scope was clarified.",
                },
            )
            self.assertEqual(superseded.returncode, 0, superseded.stderr + superseded.stdout)
            state = self.list_state(workspace)
            by_id = {item["fact_id"]: item for item in state["facts"]}
            old = by_id[original["fact_id"]]
            self.assertEqual(old["status"], "superseded")
            self.assertIsNotNone(old["superseded_by"])
            replacement = by_id[old["superseded_by"]]
            self.assertEqual(replacement["status"], "active")
            self.assertEqual(replacement["supersedes"], original["fact_id"])
            self.assertEqual(replacement["provenance"]["source"], "deployment-record-42")
            self.assertEqual(old["statement"], "Alpha is enabled.")
            self.assertTrue(any(event["action"] == "superseded" for event in old["events"]))

            retracted = self.apply(
                root,
                workspace,
                "retract",
                {
                    "operation_id": "r2-retract",
                    "action": "fact_retract",
                    "fact_id": replacement["fact_id"],
                    "reason": "Deployment was rolled back.",
                },
            )
            self.assertEqual(retracted.returncode, 0, retracted.stderr + retracted.stdout)
            final = {item["fact_id"]: item for item in self.list_state(workspace)["facts"]}
            self.assertEqual(final[replacement["fact_id"]]["status"], "retracted")
            self.assertEqual(final[replacement["fact_id"]]["statement"], "Alpha is enabled in production only.")
            self.assertTrue(any(event["action"] == "retracted" for event in final[replacement["fact_id"]]["events"]))

    def test_task_complete_cancel_and_invalid_second_transition(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            self.initial_wrap(root, workspace)
            tasks = self.list_state(workspace)["tasks"]
            first, second = tasks

            completed = self.apply(
                root,
                workspace,
                "complete",
                {
                    "operation_id": "r2-task-complete",
                    "action": "task_complete",
                    "task_id": first["task_id"],
                    "reason": "Verified complete.",
                },
            )
            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
            cancelled = self.apply(
                root,
                workspace,
                "cancel",
                {
                    "operation_id": "r2-task-cancel",
                    "action": "task_cancel",
                    "task_id": second["task_id"],
                    "reason": "No longer required.",
                },
            )
            self.assertEqual(cancelled.returncode, 0, cancelled.stderr + cancelled.stdout)

            state = self.list_state(workspace)
            by_id = {item["task_id"]: item for item in state["tasks"]}
            self.assertEqual(by_id[first["task_id"]]["status"], "completed")
            self.assertEqual(by_id[second["task_id"]]["status"], "cancelled")
            revision_before = state["revision"]

            invalid = self.apply(
                root,
                workspace,
                "invalid-transition",
                {
                    "operation_id": "r2-invalid-transition",
                    "action": "task_cancel",
                    "task_id": first["task_id"],
                    "reason": "Should be rejected.",
                },
            )
            self.assertNotEqual(invalid.returncode, 0)
            self.assertEqual(self.list_state(workspace)["revision"], revision_before)

    def test_exact_retry_is_idempotent_and_conflicting_retry_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            self.initial_wrap(root, workspace)
            fact_id = self.list_state(workspace)["facts"][0]["fact_id"]
            request = {
                "operation_id": "r2-idempotent",
                "action": "fact_retract",
                "fact_id": fact_id,
                "reason": "Retire old fact.",
            }
            first = self.apply(root, workspace, "retry-1", request)
            self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
            after_first = self.list_state(workspace)
            second = self.apply(root, workspace, "retry-2", request)
            self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
            self.assertIn("EXISTING RECEIPT REUSED", second.stdout)
            self.assertEqual(self.list_state(workspace), after_first)

            changed = dict(request)
            changed["reason"] = "Different payload under same operation ID."
            conflict = self.apply(root, workspace, "retry-conflict", changed)
            self.assertNotEqual(conflict.returncode, 0)
            self.assertEqual(self.list_state(workspace), after_first)

    def test_degraded_read_only_session_cannot_mutate_record_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            self.initial_wrap(root, workspace)
            fact_id = self.list_state(workspace)["facts"][0]["fact_id"]

            startup = self.run_script(
                STARTUP,
                "--workspace",
                str(workspace),
                "--runtime",
                "local",
                "--mode",
                "degraded_offline",
                "--capability",
                "read_files",
                "--json",
            )
            self.assertEqual(startup.returncode, 0, startup.stderr + startup.stdout)
            report = json.loads(startup.stdout)
            self.assertEqual(report["session_authority"]["authority"], "read_only")
            revision_before = self.list_state(workspace)["revision"]

            denied = self.apply(
                root,
                workspace,
                "denied",
                {
                    "operation_id": "r2-denied",
                    "action": "fact_retract",
                    "fact_id": fact_id,
                    "reason": "Must be denied.",
                },
                "--session-id",
                report["session_authority"]["session_id"],
            )
            self.assertNotEqual(denied.returncode, 0)
            self.assertIn("denies operation", denied.stderr.lower())
            self.assertEqual(self.list_state(workspace)["revision"], revision_before)

    def test_lifecycle_status_receipt_is_restart_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            self.initial_wrap(root, workspace)
            task_id = self.list_state(workspace)["tasks"][0]["task_id"]
            applied = self.apply(
                root,
                workspace,
                "status",
                {
                    "operation_id": "r2-status",
                    "action": "task_complete",
                    "task_id": task_id,
                    "reason": "Done.",
                },
            )
            self.assertEqual(applied.returncode, 0, applied.stderr + applied.stdout)

            status = self.run_script(
                LIFECYCLE,
                "status",
                "--workspace",
                str(workspace),
                "--operation-id",
                "r2-status",
                "--json",
            )
            self.assertEqual(status.returncode, 0, status.stderr + status.stdout)
            receipt = json.loads(status.stdout)
            self.assertEqual(receipt["status"], "complete")
            self.assertEqual(receipt["kind"], "record_lifecycle")
            self.assertEqual(receipt["operation_id"], "r2-status")
            self.assertEqual(receipt["revision"], 2)
            self.assertEqual(receipt["action"], "task_complete")
            self.assertEqual(receipt["target_id"], task_id)
            self.assertTrue(receipt["independently_verified"])


if __name__ == "__main__":
    unittest.main()
