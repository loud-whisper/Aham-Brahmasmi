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


class WrapUpDiagnosticTests(unittest.TestCase):
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

    def test_failed_replay_reports_exact_remaining_step_and_can_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            bundle_path = root / "bundle.json"
            bundle = {
                "session_id": "diagnostic-session",
                "durable_facts": ["Durable diagnostic fact"],
                "project_updates": [{"project": "Diagnostic Project", "content": "Durable project update."}],
                "history": ["Diagnostic history item."],
                "checkpoint": {
                    "summary": "Diagnostic wrap-up",
                    "completed": ["Prepared diagnostic fixture"],
                    "next_steps": ["Verify recovery guidance"],
                    "project": "Diagnostic Project",
                },
            }
            bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

            legacy_project_path = workspace / "projects" / "Diagnostic-Project.md"
            legacy_project_path.mkdir()

            failed = self.run_script(WRAP_UP, "--workspace", str(workspace), "--bundle", str(bundle_path))
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("Remaining step: route_projects", failed.stderr)
            self.assertIn("project update 1 of 1: Diagnostic Project", failed.stderr)
            self.assertIn("Recovery command:", failed.stderr)

            pending = workspace / "state" / "pending_wrap_up.json"
            self.assertTrue(pending.is_file())
            self.assertFalse((workspace / "state" / "wrapups" / "diagnostic-session.json").exists())
            saved_pending = json.loads(pending.read_text(encoding="utf-8"))
            self.assertEqual(saved_pending["status"], "pending")
            self.assertEqual(saved_pending["operation_id"], "diagnostic-session")
            self.assertEqual(saved_pending["progress"]["step"], "route_projects")
            self.assertIn("Diagnostic Project", saved_pending["progress"]["detail"])

            legacy_project_path.rmdir()
            recovered = self.run_script(WRAP_UP, "--workspace", str(workspace), "--recover-pending")
            self.assertEqual(recovered.returncode, 0, recovered.stderr + recovered.stdout)
            self.assertIn("WRAP UP COMPLETE", recovered.stdout)
            self.assertFalse(pending.exists())
            registry = json.loads((workspace / "state" / "projects.json").read_text(encoding="utf-8"))["projects"]
            project_id = next(pid for pid, entry in registry.items() if entry["display_name"] == "Diagnostic Project")
            project_path = workspace / "projects" / f"{project_id}.md"
            self.assertTrue(project_path.is_file())
            self.assertIn("Durable project update.", project_path.read_text(encoding="utf-8"))
            self.assertEqual((workspace / "MEMORY.md").read_text(encoding="utf-8").count("Durable diagnostic fact"), 1)

    def test_completed_archive_records_last_replay_safe_progress_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            bundle_path = root / "bundle.json"
            bundle = {
                "session_id": "archive-progress",
                "checkpoint": {"summary": "Archive progress fixture"},
            }
            bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

            result = self.run_script(WRAP_UP, "--workspace", str(workspace), "--bundle", str(bundle_path))
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            archive = json.loads((workspace / "state" / "wrapups" / "archive-progress.json").read_text(encoding="utf-8"))
            self.assertEqual(archive["status"], "complete")
            self.assertEqual(archive["progress"]["step"], "archive_transaction")


if __name__ == "__main__":
    unittest.main()
