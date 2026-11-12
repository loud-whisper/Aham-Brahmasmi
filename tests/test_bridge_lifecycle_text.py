from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import runtime_bridge  # noqa: E402

RUNTIMES = ("claude", "gemini", "codex", "local", "unknown")


class BridgeLifecycleTextTests(unittest.TestCase):
    def test_start_section_covers_modes_reading_and_confirmation(self) -> None:
        for runtime in RUNTIMES:
            with self.subTest(runtime=runtime):
                text = runtime_bridge.render_bridge(runtime)
                for required in ("--mode quick", "--mode regular", "--upgrade-from", "context --startup",
                                 "--part", "part_sha256", "confirm-context", "CONTEXT CONFIRMED",
                                 "startup is incomplete", "open tasks", "last session"):
                    self.assertIn(required, text)
                self.assertNotIn("context\nalready loaded", text)
                self.assertNotIn("already loaded and verified", text)

    def test_upgrade_conditions_match_the_startup_contract(self) -> None:
        contract = json.loads((ROOT / "core/startup.json").read_text(encoding="utf-8"))
        self.assertEqual(contract["mode_selection"]["default_when_no_phrase"], "quick")
        text = " ".join(runtime_bridge.render_bridge("unknown").split())
        for phrase in ("resume earlier work", "tasks, earlier sessions or lessons", "save or wrap-up",
                       "pending recovery"):
            self.assertIn(phrase, text)

    def test_wrap_up_section_covers_inventory_closure_and_outcome(self) -> None:
        text = " ".join(runtime_bridge.render_bridge("unknown").split())
        for required in ("inventory", "every independent piece of work", "evidence_status", "verified",
                         "owner_reported", "inferred", "unverified", "not_done", "lifecycle", "task_complete",
                         "summary", "outcome", "blocked", "snapshot", "next action"):
            self.assertIn(required, text)

    def test_quick_start_fits_the_quick_ceiling_for_every_profile(self) -> None:
        ceiling = json.loads((ROOT / "core/startup.json").read_text(encoding="utf-8"))["quick_budget_bytes"]
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp) / "workspace"
            setup = subprocess.run([sys.executable, str(SCRIPTS / "setup_workspace.py"), "--workspace",
                                    str(workspace)], capture_output=True, text=True, check=False)
            self.assertEqual(setup.returncode, 0, setup.stdout + setup.stderr)
            for runtime in RUNTIMES:
                with self.subTest(runtime=runtime):
                    result = subprocess.run([sys.executable, str(SCRIPTS / "startup.py"), "--workspace",
                                             str(workspace), "--runtime", runtime, "--mode", "quick", "--json"],
                                            capture_output=True, text=True, check=False)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    accounting = json.loads(result.stdout)["startup_context"]
                    self.assertLessEqual(accounting["total_bytes"], ceiling)
                    # Leave room for the owner's own standing files and facts.
                    self.assertLessEqual(accounting["total_bytes"], ceiling - 4096)

    def test_done_for_the_day_is_a_default_wrap_up_phrase(self) -> None:
        import owner_phrases
        self.assertEqual(owner_phrases.DEFAULTS["wrap_up"], ("wrap up", "done for the day"))


if __name__ == "__main__":
    unittest.main()
