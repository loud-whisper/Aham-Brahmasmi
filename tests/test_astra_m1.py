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
sys.path.insert(0, str(ROOT / "scripts"))
from state_io import workspace_fingerprint  # noqa: E402


class AstraM1RegressionTests(unittest.TestCase):
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

    def write_bundle(self, path: Path, operation_id: str, fact: str, summary: str = "done") -> None:
        path.write_text(
            json.dumps(
                {
                    "session_id": operation_id,
                    "durable_facts": [fact],
                    "checkpoint": {"summary": summary},
                }
            ),
            encoding="utf-8",
        )

    def test_f1_reused_identity_with_different_payload_is_rejected_before_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            first_bundle = root / "first.json"
            second_bundle = root / "second.json"
            self.write_bundle(first_bundle, "reused", "original fact", "first")
            self.write_bundle(second_bundle, "reused", "replacement fact", "second")

            first = self.run_script(WRAP_UP, "--workspace", str(workspace), "--bundle", str(first_bundle))
            self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
            archive = workspace / "state" / "wrapups" / "reused.json"
            before_archive = archive.read_text(encoding="utf-8")
            before_memory = (workspace / "MEMORY.md").read_text(encoding="utf-8")

            second = self.run_script(WRAP_UP, "--workspace", str(workspace), "--bundle", str(second_bundle))
            self.assertNotEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertIn("different payload", (second.stdout + second.stderr).lower())
            self.assertEqual(archive.read_text(encoding="utf-8"), before_archive)
            self.assertEqual((workspace / "MEMORY.md").read_text(encoding="utf-8"), before_memory)
            self.assertNotIn("replacement fact", before_memory)

    def test_f2_free_form_marker_text_cannot_suppress_real_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            bundle = root / "bundle.json"
            bundle.write_text(
                json.dumps(
                    {
                        "session_id": "quoted",
                        "durable_facts": [
                            "A lesson can quote <!-- aham:quoted:memory:1 --> without becoming control metadata.",
                            "important second fact",
                        ],
                        "checkpoint": {"summary": "quoted marker test"},
                    }
                ),
                encoding="utf-8",
            )

            result = self.run_script(WRAP_UP, "--workspace", str(workspace), "--bundle", str(bundle))
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            memory = (workspace / "MEMORY.md").read_text(encoding="utf-8")
            self.assertIn("important second fact", memory)
            self.assertEqual(memory.count("important second fact"), 1)

    def test_f3_recovery_rejects_alias_shaped_persisted_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            brain = json.loads((workspace / "BRAIN.json").read_text(encoding="utf-8"))
            pending = {
                "format": "aham-brahmasmi-wrap-up",
                "version": 1,
                "status": "pending",
                "session_id": "damaged",
                "created_at": "2026-09-18T00:00:00Z",
                "workspace_fingerprint": workspace_fingerprint(brain),
                "repository": None,
                "bundle": {
                    "session_id": "damaged",
                    "facts": ["must not be silently dropped"],
                    "unfinished_work": [],
                    "reusable_lessons": [],
                    "project_updates": [],
                    "history": [],
                    "checkpoint": {
                        "summary": "damaged pending state",
                        "completed": [],
                        "next_steps": [],
                        "artifacts": [],
                        "project": None,
                    },
                },
            }
            pending_path = workspace / "state" / "pending_wrap_up.json"
            pending_path.write_text(json.dumps(pending), encoding="utf-8")
            before = (workspace / "MEMORY.md").read_text(encoding="utf-8")

            result = self.run_script(WRAP_UP, "--workspace", str(workspace), "--recover-pending")
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("WRAP UP VERIFIED", result.stdout)
            self.assertEqual((workspace / "MEMORY.md").read_text(encoding="utf-8"), before)
            self.assertFalse((workspace / "state" / "wrapups" / "damaged.json").exists())

    def test_exact_retry_reuses_receipt_and_status_is_queryable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            bundle = root / "bundle.json"
            self.write_bundle(bundle, "retryable", "one durable fact")

            first = self.run_script(WRAP_UP, "--workspace", str(workspace), "--bundle", str(bundle))
            self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
            receipt_path = workspace / "state" / "wrapups" / "retryable.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            digest = receipt.get("payload_digest")
            self.assertIsInstance(digest, str)
            self.assertEqual(len(digest), 64)

            retry = self.run_script(WRAP_UP, "--workspace", str(workspace), "--bundle", str(bundle))
            self.assertEqual(retry.returncode, 0, retry.stderr + retry.stdout)
            self.assertIn("RECEIPT", retry.stdout.upper())
            self.assertEqual((workspace / "MEMORY.md").read_text(encoding="utf-8").count("one durable fact"), 1)
            self.assertEqual(json.loads(receipt_path.read_text(encoding="utf-8"))["payload_digest"], digest)

            status = self.run_script(
                WRAP_UP,
                "--workspace",
                str(workspace),
                "--status",
                "retryable",
            )
            self.assertEqual(status.returncode, 0, status.stderr + status.stdout)
            self.assertIn("complete", status.stdout.lower())
            self.assertIn(digest, status.stdout)

    def test_completed_receipt_uses_only_canonical_persisted_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            bundle = root / "bundle.json"
            bundle.write_text(
                json.dumps(
                    {
                        "session_id": "canonical",
                        "facts": ["fact via request alias"],
                        "lessons": ["lesson via request alias"],
                        "projects": [{"name": "Demo", "update": "project via request alias"}],
                        "checkpoint": {"summary": "canonical persisted state", "next": "continue"},
                    }
                ),
                encoding="utf-8",
            )

            result = self.run_script(WRAP_UP, "--workspace", str(workspace), "--bundle", str(bundle))
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            receipt = json.loads((workspace / "state" / "wrapups" / "canonical.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["operation_id"], "canonical")
            self.assertNotIn("session_id", receipt)
            self.assertNotIn("facts", receipt["bundle"])
            self.assertNotIn("lessons", receipt["bundle"])
            self.assertNotIn("projects", receipt["bundle"])
            self.assertNotIn("next", receipt["bundle"]["checkpoint"])
            self.assertEqual(receipt["bundle"]["checkpoint"]["next_steps"], ["continue"])


if __name__ == "__main__":
    unittest.main()
