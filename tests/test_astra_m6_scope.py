from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "scripts" / "setup_workspace.py"
CHECKPOINT = ROOT / "scripts" / "checkpoint.py"
WRAP_UP = ROOT / "scripts" / "wrap_up.py"
RESUME = ROOT / "scripts" / "resume.py"


class AstraM6SuccessScopeRegressionTests(unittest.TestCase):
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

    def test_checkpoint_human_success_is_qualified_and_states_exclusions(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.make_workspace(Path(temp))
            result = self.run_script(
                CHECKPOINT,
                "--workspace",
                str(workspace),
                "--summary",
                "precise checkpoint semantics",
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            lines = result.stdout.splitlines()
            self.assertNotIn("CHECKPOINT VERIFIED", lines)
            self.assertIn("CHECKPOINT VERIFIED: local durable checkpoint state", lines)
            self.assertIn("Persistence: committed local durable state", lines)
            self.assertIn("Verification scope: durable workspace checkpoint data", lines)
            excluded = next((line for line in lines if line.startswith("Excluded scope: ")), "")
            self.assertIn("repository state", excluded)
            self.assertIn("unsaved editor buffers", excluded)
            self.assertIn("replicated backup", excluded)
            self.assertIn("runtime instruction compliance", excluded)
            self.assertIn("end-to-end recovery", excluded)

    def test_wrapup_human_success_is_qualified_and_states_exclusions(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            bundle = root / "bundle.json"
            bundle.write_text(
                json.dumps(
                    {
                        "operation_id": "m6-scope-wrap",
                        "durable_facts": ["scope fact"],
                        "checkpoint": {"summary": "precise wrap-up semantics"},
                    }
                ),
                encoding="utf-8",
            )
            result = self.run_script(
                WRAP_UP,
                "--workspace",
                str(workspace),
                "--bundle",
                str(bundle),
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            lines = result.stdout.splitlines()
            self.assertNotIn("WRAP UP VERIFIED", lines)
            self.assertIn("WRAP UP VERIFIED: routed durable workspace state and final checkpoint", lines)
            self.assertIn("Persistence: committed local durable state", lines)
            self.assertIn("Verification scope: routed durable workspace content and final checkpoint", lines)
            excluded = next((line for line in lines if line.startswith("Excluded scope: ")), "")
            self.assertIn("unrelated project artifacts", excluded)
            self.assertIn("repository state", excluded)
            self.assertIn("unsaved editor buffers", excluded)
            self.assertIn("replicated backup", excluded)
            self.assertIn("runtime instruction compliance", excluded)
            self.assertIn("end-to-end recovery", excluded)

    def test_resume_success_is_qualified_and_states_excluded_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.make_workspace(Path(temp))
            created = self.run_script(
                CHECKPOINT,
                "--workspace",
                str(workspace),
                "--summary",
                "resume scope fixture",
            )
            self.assertEqual(created.returncode, 0, created.stderr + created.stdout)

            resumed = self.run_script(RESUME, "--workspace", str(workspace))
            self.assertEqual(resumed.returncode, 0, resumed.stderr + resumed.stdout)
            lines = resumed.stdout.splitlines()
            self.assertNotIn("RESUME STATE VERIFIED", lines)
            self.assertIn("RESUME STATE VERIFIED: durable checkpoint continuation", lines)
            self.assertIn("Verification scope: durable workspace checkpoint data only.", lines)
            excluded = next((line for line in lines if line.startswith("Excluded scope: ")), "")
            self.assertIn("repository state", excluded)
            self.assertIn("unsaved editor buffers", excluded)
            self.assertIn("replicated backup", excluded)
            self.assertIn("runtime instruction compliance", excluded)
            self.assertIn("end-to-end recovery", excluded)

    def test_degraded_resume_states_exact_recovery_action(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.make_workspace(Path(temp))
            for summary in ("older good checkpoint", "newest checkpoint"):
                created = self.run_script(
                    CHECKPOINT,
                    "--workspace",
                    str(workspace),
                    "--summary",
                    summary,
                )
                self.assertEqual(created.returncode, 0, created.stderr + created.stdout)

            latest = json.loads((workspace / "state" / "latest_checkpoint.json").read_text(encoding="utf-8"))
            newest = workspace / str(latest["file"])
            newest.write_text("{not valid json\n", encoding="utf-8")

            resumed = self.run_script(RESUME, "--workspace", str(workspace))
            self.assertEqual(resumed.returncode, 10, resumed.stderr + resumed.stdout)
            text = resumed.stderr
            self.assertIn("Committed revision: 2", text)
            self.assertIn("Recovered revision: 1", text)
            self.assertIn("Continuity gap:", text)
            self.assertIn("Recovery action:", text)
            self.assertIn("repair or restore the newest committed checkpoint before continuing", text)


if __name__ == "__main__":
    unittest.main()
