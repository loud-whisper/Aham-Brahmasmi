from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "scripts" / "setup_workspace.py"
CHECKPOINT = ROOT / "scripts" / "checkpoint.py"
WRAP_UP = ROOT / "scripts" / "wrap_up.py"

RECEIPT_FORMAT = "aham-brahmasmi-operation-receipt"
RECEIPT_VERSION = 1


class AstraM6ReceiptRegressionTests(unittest.TestCase):
    def run_script(
        self,
        script: Path,
        *args: str,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        return subprocess.run(
            [sys.executable, str(script), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            env=merged_env,
        )

    def make_workspace(self, root: Path) -> Path:
        workspace = root / "workspace"
        setup = self.run_script(SETUP, "--workspace", str(workspace))
        self.assertEqual(setup.returncode, 0, setup.stderr + setup.stdout)
        return workspace

    def parse_receipt(self, result: subprocess.CompletedProcess[str]) -> dict[str, object]:
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        try:
            value = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            self.fail(f"expected one JSON receipt on stdout, got: {result.stdout!r}; {exc}")
        self.assertIsInstance(value, dict)
        return value

    def assert_common_complete_receipt(self, receipt: dict[str, object], *, kind: str) -> None:
        self.assertEqual(receipt["format"], RECEIPT_FORMAT)
        self.assertEqual(receipt["version"], RECEIPT_VERSION)
        self.assertEqual(receipt["status"], "complete")
        self.assertEqual(receipt["kind"], kind)
        self.assertIsInstance(receipt["operation_id"], str)
        self.assertTrue(str(receipt["operation_id"]))
        self.assertIsInstance(receipt["revision"], int)
        self.assertGreaterEqual(int(receipt["revision"]), 1)
        self.assertIsInstance(receipt["payload_digest"], str)
        self.assertEqual(len(str(receipt["payload_digest"])), 64)
        self.assertIsInstance(receipt["accepted_items"], list)
        self.assertEqual(receipt["accepted_item_count"], len(receipt["accepted_items"]))
        self.assertIsInstance(receipt["checkpoint"], dict)
        self.assertIsInstance(receipt["verification_scope"], dict)
        scope = receipt["verification_scope"]
        self.assertIsInstance(scope["verified"], list)
        self.assertIsInstance(scope["excluded"], list)
        self.assertIn("unsaved_editor_buffers", scope["excluded"])
        self.assertIsInstance(receipt["warnings"], list)
        self.assertIsNone(receipt["recovery_action"])

    def assert_pending_receipt(self, receipt: dict[str, object], *, kind: str, operation_id: str) -> None:
        self.assertEqual(receipt["format"], RECEIPT_FORMAT)
        self.assertEqual(receipt["version"], RECEIPT_VERSION)
        self.assertEqual(receipt["status"], "pending")
        self.assertEqual(receipt["kind"], kind)
        self.assertEqual(receipt["operation_id"], operation_id)
        self.assertIsNone(receipt["revision"])
        self.assertEqual(receipt["target_revision"], 1)
        self.assertIsInstance(receipt["payload_digest"], str)
        self.assertEqual(len(str(receipt["payload_digest"])), 64)
        self.assertEqual(receipt["accepted_items"], [])
        self.assertEqual(receipt["accepted_item_count"], 0)
        self.assertIsNone(receipt["checkpoint"])
        self.assertIn("operation_not_committed", receipt["warnings"])
        self.assertIsInstance(receipt["recovery_action"], str)
        self.assertIn("--recover-pending", receipt["recovery_action"])

    def test_checkpoint_json_receipt_is_complete_and_status_reconstructs_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.make_workspace(Path(temp))
            created = self.parse_receipt(
                self.run_script(
                    CHECKPOINT,
                    "--workspace",
                    str(workspace),
                    "--summary",
                    "M6 checkpoint receipt",
                    "--completed",
                    "Verified receipt contract",
                    "--next-step",
                    "Reconstruct after restart",
                    "--json",
                )
            )
            self.assert_common_complete_receipt(created, kind="checkpoint")
            self.assertEqual(created["accepted_item_count"], 1)
            item = created["accepted_items"][0]
            self.assertEqual(item["kind"], "checkpoint")
            self.assertEqual(item["content_digest"], created["payload_digest"])
            self.assertIn("durable_workspace_checkpoint_data", created["verification_scope"]["verified"])
            self.assertIn("repository_state", created["verification_scope"]["excluded"])

            operation_id = str(created["operation_id"])
            status = self.parse_receipt(
                self.run_script(
                    CHECKPOINT,
                    "--workspace",
                    str(workspace),
                    "--status",
                    operation_id,
                    "--json",
                )
            )
            self.assertEqual(status, created)

    def test_wrapup_json_receipt_enumerates_accepted_items_and_status_reconstructs_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            bundle = root / "bundle.json"
            bundle.write_text(
                json.dumps(
                    {
                        "operation_id": "m6-wrap-receipt",
                        "durable_facts": ["M6 receipt fact"],
                        "unfinished_work": ["M6 receipt task"],
                        "reusable_lessons": ["M6 receipt lesson"],
                        "checkpoint": {"summary": "M6 wrap-up receipt"},
                    }
                ),
                encoding="utf-8",
            )

            created = self.parse_receipt(
                self.run_script(
                    WRAP_UP,
                    "--workspace",
                    str(workspace),
                    "--bundle",
                    str(bundle),
                    "--json",
                )
            )
            self.assert_common_complete_receipt(created, kind="wrap_up")
            self.assertEqual(created["operation_id"], "m6-wrap-receipt")
            self.assertEqual(created["accepted_item_count"], 3)
            item_ids = {item["item_id"] for item in created["accepted_items"]}
            self.assertEqual(item_ids, {"memory-0", "todo-0", "lesson-0"})
            destinations = {item["destination"] for item in created["accepted_items"]}
            self.assertEqual(destinations, {"MEMORY.md", "TODO.md", "LESSONS.md"})
            self.assertIn("durable_workspace_routed_content", created["verification_scope"]["verified"])
            self.assertIn("durable_workspace_checkpoint_data", created["verification_scope"]["verified"])
            self.assertIn("repository_state", created["verification_scope"]["excluded"])

            status = self.parse_receipt(
                self.run_script(
                    WRAP_UP,
                    "--workspace",
                    str(workspace),
                    "--status",
                    "m6-wrap-receipt",
                    "--json",
                )
            )
            self.assertEqual(status, created)

    def test_wrapup_pending_json_status_states_recovery_action_and_recovery_becomes_complete(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            bundle = root / "bundle.json"
            bundle.write_text(
                json.dumps(
                    {
                        "operation_id": "m6-wrap-pending",
                        "durable_facts": ["pending receipt fact"],
                        "checkpoint": {"summary": "pending wrap-up receipt"},
                    }
                ),
                encoding="utf-8",
            )
            crashed = self.run_script(
                WRAP_UP,
                "--workspace",
                str(workspace),
                "--bundle",
                str(bundle),
                env={
                    "AHAM_BRAHMASMI_TEST_MODE": "1",
                    "AHAM_BRAHMASMI_TEST_CRASH_POINT": "wrap_up_after_pending",
                },
            )
            self.assertEqual(crashed.returncode, 86, crashed.stderr + crashed.stdout)

            pending = self.parse_receipt(
                self.run_script(
                    WRAP_UP,
                    "--workspace",
                    str(workspace),
                    "--status",
                    "m6-wrap-pending",
                    "--json",
                )
            )
            self.assert_pending_receipt(pending, kind="wrap_up", operation_id="m6-wrap-pending")

            recovered = self.parse_receipt(
                self.run_script(
                    WRAP_UP,
                    "--workspace",
                    str(workspace),
                    "--recover-pending",
                    "--json",
                )
            )
            self.assert_common_complete_receipt(recovered, kind="wrap_up")
            self.assertEqual(recovered["operation_id"], "m6-wrap-pending")
            self.assertEqual(recovered["revision"], 1)

    def test_checkpoint_pending_json_status_states_recovery_action_and_recovery_becomes_complete(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.make_workspace(Path(temp))
            crashed = self.run_script(
                CHECKPOINT,
                "--workspace",
                str(workspace),
                "--summary",
                "pending checkpoint receipt",
                env={
                    "AHAM_BRAHMASMI_TEST_MODE": "1",
                    "AHAM_BRAHMASMI_TEST_CRASH_POINT": "checkpoint_after_pending",
                },
            )
            self.assertEqual(crashed.returncode, 86, crashed.stderr + crashed.stdout)
            pending_state = json.loads((workspace / "state" / "pending_checkpoint.json").read_text(encoding="utf-8"))
            operation_id = str(pending_state["operation_id"])

            pending = self.parse_receipt(
                self.run_script(
                    CHECKPOINT,
                    "--workspace",
                    str(workspace),
                    "--status",
                    operation_id,
                    "--json",
                )
            )
            self.assert_pending_receipt(pending, kind="checkpoint", operation_id=operation_id)

            recovered = self.parse_receipt(
                self.run_script(
                    CHECKPOINT,
                    "--workspace",
                    str(workspace),
                    "--recover-pending",
                    "--json",
                )
            )
            self.assert_common_complete_receipt(recovered, kind="checkpoint")
            self.assertEqual(recovered["operation_id"], operation_id)
            self.assertEqual(recovered["revision"], 1)


if __name__ == "__main__":
    unittest.main()
