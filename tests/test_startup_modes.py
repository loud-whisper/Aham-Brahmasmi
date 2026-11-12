from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
WRITE_OPERATIONS = ["checkpoint", "recover_checkpoint", "wrap_up", "recover_wrap_up"]


def run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args], cwd=ROOT, text=True,
                          capture_output=True, check=False)


class StartupModeTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.workspace = self.root / "workspace"
        result = run("setup_workspace.py", "--workspace", str(self.workspace))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def trust(self, runtime: str = "local") -> None:
        result = run("runtime_trust.py", "trust", runtime, "--workspace", str(self.workspace), "--confirm", runtime)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def start(self, mode: str, *, runtime: str = "local", capabilities=("read_files", "write_files")):
        command = ["--workspace", str(self.workspace), "--runtime", runtime, "--mode", mode, "--json"]
        for capability in capabilities:
            command += ["--capability", capability]
        result = run("startup.py", *command)
        report = json.loads(result.stdout) if result.stdout.strip().startswith("{") else {}
        return result, report

    def test_quick_starts_cold_without_context_loaded_flag(self) -> None:
        result, report = self.start("quick")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(report["ready"])
        self.assertEqual(report["blockers"], [])
        self.assertEqual(report["state_freshness"], "verified_local")
        self.assertEqual(report["startup_context"]["mode"], "quick")

    def test_quick_session_has_no_write_operations(self) -> None:
        self.trust()
        result, report = self.start("quick")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(report["session_authority"]["allowed_operations"], [])
        self.assertFalse(report["write_policy"]["core_allows_writes"])
        self.assertEqual(report["upgrade"], {"required_for": ["checkpoint", "wrap_up"],
                                             "command": "start --mode regular"})

    def test_quick_session_cannot_save_or_wrap_up(self) -> None:
        self.trust()
        _, report = self.start("quick")
        session = report["session_authority"]["session_id"]
        save = run("checkpoint.py", "--workspace", str(self.workspace), "--summary", "quick save",
                   "--session-id", session)
        self.assertNotEqual(save.returncode, 0)
        self.assertIn("start --mode regular", save.stdout + save.stderr)
        bundle = self.root / "bundle.json"
        bundle.write_text(json.dumps({
            "operation_id": "quick-wrap", "durable_facts": ["A fact."], "unfinished_work": [],
            "reusable_lessons": [], "project_updates": [], "history": [],
            "checkpoint": {"summary": "quick wrap", "completed": [], "next_steps": ["Continue"]}}), encoding="utf-8")
        wrap = run("wrap_up.py", "--workspace", str(self.workspace), "--bundle", str(bundle), "--session-id", session)
        self.assertNotEqual(wrap.returncode, 0)
        self.assertIn("start --mode regular", wrap.stdout + wrap.stderr)
        self.assertFalse((self.workspace / "state/pending_wrap_up.json").exists())

    def test_regular_after_quick_issues_writing_session(self) -> None:
        self.trust()
        self.start("quick")
        result, report = self.start("regular")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(report["session_authority"]["allowed_operations"], WRITE_OPERATIONS)
        self.assertIsNone(report["upgrade"])

    def test_quick_still_reports_pending_wrap_up(self) -> None:
        (self.workspace / "state" / "pending_wrap_up.json").write_text("{}\n", encoding="utf-8")
        result, report = self.start("quick")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(report["ready"])
        self.assertTrue(any("unfinished wrap-up" in blocker for blocker in report["blockers"]))

    def test_contract_names_default_mode_and_upgrade_conditions(self) -> None:
        contract = json.loads((ROOT / "core/startup.json").read_text(encoding="utf-8"))
        selection = contract["mode_selection"]
        self.assertEqual(selection["default_when_no_phrase"], "quick")
        self.assertEqual(len(selection["upgrade_to_regular_when"]), 4)
        brain = json.loads((ROOT / "core/brain.json").read_text(encoding="utf-8"))
        self.assertIs(brain["modes"]["quick"]["allow_validated_writes"], False)

    def test_context_loaded_flag_is_still_accepted(self) -> None:
        result = run("startup.py", "--workspace", str(self.workspace), "--mode", "quick", "--context-loaded", "--json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
