from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "scripts" / "setup_workspace.py"
VERIFY = ROOT / "scripts" / "verify_workspace.py"


class FirstRunTests(unittest.TestCase):
    def run_script(self, script: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(script), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_setup_and_verify_clean_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp) / "workspace"
            setup = self.run_script(SETUP, "--workspace", str(workspace))
            self.assertEqual(setup.returncode, 0, setup.stderr + setup.stdout)
            self.assertIn("WORKSPACE CREATED", setup.stdout)

            verify = self.run_script(VERIFY, "--workspace", str(workspace))
            self.assertEqual(verify.returncode, 0, verify.stderr + verify.stdout)
            self.assertIn("WORKSPACE VERIFIED", verify.stdout)

            for relative in (
                "BRAIN.json",
                "README.md",
                "MEMORY.md",
                "TODO.md",
                "LESSONS.md",
                "projects",
                "history",
                "state/checkpoints",
                "state/wrapups",
            ):
                self.assertTrue((workspace / relative).exists(), relative)

            brain = json.loads((workspace / "BRAIN.json").read_text(encoding="utf-8"))
            self.assertRegex(brain["workspace_id"], r"^[0-9a-f]{32}$")

    def test_separate_workspaces_receive_different_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = root / "first"
            second = root / "second"
            self.assertEqual(self.run_script(SETUP, "--workspace", str(first)).returncode, 0)
            self.assertEqual(self.run_script(SETUP, "--workspace", str(second)).returncode, 0)
            first_id = json.loads((first / "BRAIN.json").read_text(encoding="utf-8"))["workspace_id"]
            second_id = json.loads((second / "BRAIN.json").read_text(encoding="utf-8"))["workspace_id"]
            self.assertNotEqual(first_id, second_id)

    def test_setup_refuses_to_overwrite_nonempty_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp) / "workspace"
            workspace.mkdir()
            sentinel = workspace / "keep-me.txt"
            sentinel.write_text("do not replace", encoding="utf-8")

            result = self.run_script(SETUP, "--workspace", str(workspace))
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "do not replace")
            self.assertFalse((workspace / "BRAIN.json").exists())

    def test_setup_refuses_workspace_inside_public_repo(self) -> None:
        candidate = ROOT / "should-never-be-created-workspace"
        self.assertFalse(candidate.exists())
        result = self.run_script(SETUP, "--workspace", str(candidate))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(candidate.exists())

    def test_verifier_rejects_corrupt_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp) / "workspace"
            setup = self.run_script(SETUP, "--workspace", str(workspace))
            self.assertEqual(setup.returncode, 0)
            (workspace / "BRAIN.json").write_text("not json", encoding="utf-8")

            verify = self.run_script(VERIFY, "--workspace", str(workspace))
            self.assertNotEqual(verify.returncode, 0)
            self.assertIn("WORKSPACE VERIFICATION FAILED", verify.stdout)

    def test_verifier_rejects_missing_workspace_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp) / "workspace"
            setup = self.run_script(SETUP, "--workspace", str(workspace))
            self.assertEqual(setup.returncode, 0)
            brain_path = workspace / "BRAIN.json"
            brain = json.loads(brain_path.read_text(encoding="utf-8"))
            brain["workspace_id"] = None
            brain_path.write_text(json.dumps(brain), encoding="utf-8")

            verify = self.run_script(VERIFY, "--workspace", str(workspace))
            self.assertNotEqual(verify.returncode, 0)
            self.assertIn("workspace_id", verify.stdout)


class CoreContractTests(unittest.TestCase):
    def load_json(self, relative: str) -> dict:
        return json.loads((ROOT / relative).read_text(encoding="utf-8"))

    def test_core_modes_are_defined(self) -> None:
        core = self.load_json("core/brain.json")
        self.assertEqual(set(core["modes"]), {"quick", "regular", "degraded_offline", "wrap_up"})
        self.assertFalse(core["modes"]["quick"]["refresh_durable_context"])
        self.assertTrue(core["modes"]["regular"]["refresh_durable_context"])
        self.assertFalse(core["modes"]["degraded_offline"]["allow_validated_writes"])

    def test_unknown_runtime_has_safe_fallback(self) -> None:
        core = self.load_json("core/brain.json")
        behavior = core["unknown_runtime"]["behavior"].lower()
        self.assertIn("unavailable", behavior)
        self.assertIn("avoid writes", behavior)

    def test_startup_detects_capabilities_before_optional_integrations(self) -> None:
        startup = self.load_json("core/startup.json")
        ids = [phase["id"] for phase in startup["phases"]]
        self.assertLess(ids.index("detect_capabilities"), ids.index("discover_optional_integrations"))

    def test_state_routes_cover_required_destinations(self) -> None:
        routes = self.load_json("core/state_routes.json")["routes"]
        self.assertEqual(routes["durable_fact"]["destination"], "MEMORY.md")
        self.assertEqual(routes["unfinished_work"]["destination"], "TODO.md")
        self.assertEqual(routes["reusable_lesson"]["destination"], "LESSONS.md")
        self.assertEqual(routes["project_state"]["destination"], "projects/")
        self.assertEqual(routes["session_history"]["destination"], "history/")
        self.assertEqual(routes["recovery_checkpoint"]["destination"], "state/checkpoints/")


if __name__ == "__main__":
    unittest.main()
