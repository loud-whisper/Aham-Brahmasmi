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
CONTEXT = ROOT / "scripts" / "context_packet.py"


class R3ContextIntegrityTests(unittest.TestCase):
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

    def write_bundle(self, root: Path, workspace: Path, bundle: dict) -> None:
        path = root / "bundle.json"
        path.write_text(json.dumps(bundle), encoding="utf-8")
        result = self.run_script(WRAP_UP, "--workspace", str(workspace), "--bundle", str(path))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def project_id(self, workspace: Path, display_name: str) -> str:
        registry = json.loads((workspace / "state" / "projects.json").read_text(encoding="utf-8"))
        return next(project_id for project_id, entry in registry["projects"].items() if entry["display_name"] == display_name)

    def packet(self, workspace: Path, project_id: str) -> subprocess.CompletedProcess[str]:
        return self.run_script(
            CONTEXT,
            "--workspace",
            str(workspace),
            "--project-id",
            project_id,
            "--max-bytes",
            "8192",
            "--json",
        )

    def test_multi_project_wrap_does_not_fan_unscoped_facts_or_tasks_into_each_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            self.write_bundle(
                root,
                workspace,
                {
                    "operation_id": "r3-multi-project",
                    "durable_facts": ["Ambiguous fact must not be copied into either project packet."],
                    "unfinished_work": ["Ambiguous task must not be copied into either project packet."],
                    "reusable_lessons": [],
                    "project_updates": [
                        {"project": "Alpha", "content": "Alpha-only update."},
                        {"project": "Beta", "content": "Beta-only update."},
                    ],
                    "history": [],
                    "checkpoint": {
                        "summary": "Alpha checkpoint",
                        "completed": [],
                        "next_steps": ["Continue Alpha."],
                        "project": "Alpha",
                    },
                },
            )

            alpha = json.loads(self.packet(workspace, self.project_id(workspace, "Alpha")).stdout)
            beta_result = self.packet(workspace, self.project_id(workspace, "Beta"))

            self.assertEqual(alpha["facts"], [])
            self.assertEqual(alpha["tasks"], [])
            self.assertEqual([item["content"] for item in alpha["project_updates"]], ["Alpha-only update."])

            # Beta has no project-specific checkpoint in this operation, so a packet must fail
            # rather than borrow Alpha's checkpoint or leak ambiguous durable records.
            self.assertNotEqual(beta_result.returncode, 0)
            self.assertNotIn("Ambiguous fact", beta_result.stdout)
            self.assertNotIn("Ambiguous task", beta_result.stdout)

    def test_packet_rejects_corrupt_authoritative_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            self.write_bundle(
                root,
                workspace,
                {
                    "operation_id": "r3-corrupt-checkpoint",
                    "durable_facts": ["Valid project fact."],
                    "unfinished_work": ["Valid project task."],
                    "reusable_lessons": [],
                    "project_updates": [{"project": "Corrupt", "content": "Valid update."}],
                    "history": [],
                    "checkpoint": {
                        "summary": "Valid checkpoint",
                        "completed": [],
                        "next_steps": ["Continue."],
                        "project": "Corrupt",
                    },
                },
            )
            checkpoint = next((workspace / "state" / "checkpoints").glob("*.json"))
            value = json.loads(checkpoint.read_text(encoding="utf-8"))
            value["status"] = "corrupt"
            checkpoint.write_text(json.dumps(value), encoding="utf-8")

            result = self.packet(workspace, self.project_id(workspace, "Corrupt"))
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertIn("checkpoint", result.stderr.lower())


if __name__ == "__main__":
    unittest.main()
