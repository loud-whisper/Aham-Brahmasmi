from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SETUP = SCRIPTS / "setup_workspace.py"
WRAP_UP = SCRIPTS / "wrap_up.py"
CHECKPOINT = SCRIPTS / "checkpoint.py"
RESUME = SCRIPTS / "resume.py"
sys.path.insert(0, str(SCRIPTS))

from project_state import allocated_project_id  # noqa: E402


class AstraM3IdentityContractTests(unittest.TestCase):
    def run_script(self, script: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        return subprocess.run(
            [sys.executable, str(script), *args], cwd=ROOT, text=True, capture_output=True, check=False, env=merged_env
        )

    def make_workspace(self, root: Path) -> Path:
        workspace = root / "workspace"
        result = self.run_script(SETUP, "--workspace", str(workspace))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return workspace

    def test_project_id_is_allocated_from_operation_identity_not_display_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            bundle = root / "bundle.json"
            bundle.write_text(
                json.dumps(
                    {
                        "operation_id": "opaque-project-id",
                        "project_updates": [{"project": "Human Readable Name", "content": "state"}],
                        "checkpoint": {"summary": "identity contract", "project": "Human Readable Name"},
                    }
                ),
                encoding="utf-8",
            )
            result = self.run_script(WRAP_UP, "--workspace", str(workspace), "--bundle", str(bundle))
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            projects = json.loads((workspace / "state" / "projects.json").read_text(encoding="utf-8"))["projects"]
            expected = allocated_project_id(workspace, "opaque-project-id", "project-0")
            self.assertIn(expected, projects)
            self.assertEqual(projects[expected]["display_name"], "Human Readable Name")
            self.assertEqual(projects[expected]["file"], f"projects/{expected}.md")

    def test_latest_checkpoint_pointer_is_rebuilt_from_committed_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            first = self.run_script(CHECKPOINT, "--workspace", str(workspace), "--summary", "revision one")
            second = self.run_script(CHECKPOINT, "--workspace", str(workspace), "--summary", "revision two")
            self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
            self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
            pointer = workspace / "state" / "latest_checkpoint.json"
            pointer.write_text(json.dumps({"format": "aham-brahmasmi-checkpoint", "version": 1, "id": "bogus", "file": "state/checkpoints/bogus.json", "revision": 1}), encoding="utf-8")

            resumed = self.run_script(RESUME, "--workspace", str(workspace))
            self.assertEqual(resumed.returncode, 0, resumed.stderr + resumed.stdout)
            repaired = json.loads(pointer.read_text(encoding="utf-8"))
            self.assertEqual(repaired["revision"], 2)
            self.assertNotEqual(repaired["id"], "bogus")
            self.assertTrue((workspace / repaired["file"]).is_file())

    def test_precommit_project_binding_is_reconciled_before_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            bundle = root / "bundle.json"
            bundle.write_text(
                json.dumps(
                    {
                        "operation_id": "crash-project-index",
                        "project_updates": [{"project": "Crash Project", "content": "durable content"}],
                        "checkpoint": {"summary": "crash identity", "project": "Crash Project"},
                    }
                ),
                encoding="utf-8",
            )
            crashed = self.run_script(
                WRAP_UP,
                "--workspace", str(workspace),
                "--bundle", str(bundle),
                env={"AHAM_BRAHMASMI_TEST_MODE": "1", "AHAM_BRAHMASMI_TEST_CRASH_POINT": "wrap_up_after_projection"},
            )
            self.assertEqual(crashed.returncode, 86, crashed.stderr + crashed.stdout)
            provisional = json.loads((workspace / "state" / "projects.json").read_text(encoding="utf-8"))["projects"]
            self.assertEqual(len(provisional), 1)
            project_id = next(iter(provisional))
            self.assertEqual(project_id, allocated_project_id(workspace, "crash-project-index", "project-0"))
            self.assertEqual(list((workspace / "state" / "operations").glob("*.json")), [])

            recovered = self.run_script(WRAP_UP, "--workspace", str(workspace), "--recover-pending")
            self.assertEqual(recovered.returncode, 0, recovered.stderr + recovered.stdout)
            committed = json.loads((workspace / "state" / "projects.json").read_text(encoding="utf-8"))["projects"]
            self.assertEqual(list(committed), [project_id])
            self.assertTrue((workspace / "projects" / f"{project_id}.md").is_file())


if __name__ == "__main__":
    unittest.main()
