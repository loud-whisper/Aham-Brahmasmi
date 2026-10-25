from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "scripts" / "setup_workspace.py"
DOCTOR = ROOT / "scripts" / "doctor.py"
BRIDGE = ROOT / "scripts" / "runtime_bridge.py"


class DoctorTests(unittest.TestCase):
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
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return workspace

    def test_verified_workspace_is_ready_without_optional_tools(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.make_workspace(Path(temp))
            result = self.run_script(DOCTOR, "--workspace", str(workspace), "--json")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            self.assertTrue(report["ready_for_new_work"])
            statuses = {item["name"]: item["status"] for item in report["findings"]}
            self.assertEqual(statuses["Private Brain workspace"], "ok")
            self.assertEqual(statuses["Interrupted wrap up"], "ok")
            self.assertEqual(statuses["Semantic memory"], "not_configured")

    def test_pending_wrap_up_blocks_new_work_with_next_action(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.make_workspace(Path(temp))
            (workspace / "state" / "pending_wrap_up.json").write_text("{}\n", encoding="utf-8")
            result = self.run_script(DOCTOR, "--workspace", str(workspace), "--json")
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            self.assertFalse(report["ready_for_new_work"])
            pending = next(item for item in report["findings"] if item["name"] == "Interrupted wrap up")
            self.assertEqual(pending["status"], "action_needed")
            self.assertIn("--recover-pending", pending["action"])

    def test_invalid_workspace_explains_recovery_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            missing = Path(temp) / "missing"
            result = self.run_script(DOCTOR, "--workspace", str(missing), "--json")
            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            workspace = next(item for item in report["findings"] if item["name"] == "Private Brain workspace")
            self.assertEqual(workspace["status"], "action_needed")
            self.assertIn("verify_workspace.py", workspace["action"])

    def test_project_bridge_is_reported_after_install(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            project = root / "project"
            project.mkdir()
            installed = self.run_script(
                BRIDGE,
                "install",
                "--runtime",
                "codex",
                "--workspace",
                str(workspace),
                "--project",
                str(project),
            )
            self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
            result = self.run_script(
                DOCTOR,
                "--workspace",
                str(workspace),
                "--project",
                str(project),
                "--json",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            bridge = next(item for item in report["findings"] if item["name"] == "Project bridge")
            self.assertEqual(bridge["status"], "ok")
            self.assertIn("codex", bridge["detail"])


if __name__ == "__main__":
    unittest.main()
