from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "scripts" / "setup_workspace.py"
STARTUP = ROOT / "scripts" / "startup.py"
CHECKPOINT = ROOT / "scripts" / "checkpoint.py"


class RuntimeStartupTests(unittest.TestCase):
    def run_command(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)

    def create_workspace(self, root: Path) -> Path:
        workspace = root / "workspace"
        result = self.run_command(sys.executable, str(SETUP), "--workspace", str(workspace))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return workspace

    def startup_report(
        self,
        workspace: Path,
        *,
        runtime: str = "unknown",
        mode: str = "regular",
        capabilities: tuple[str, ...] = (),
        context_loaded: bool = False,
    ) -> tuple[subprocess.CompletedProcess[str], dict]:
        command = [
            sys.executable,
            str(STARTUP),
            "--workspace",
            str(workspace),
            "--runtime",
            runtime,
            "--mode",
            mode,
            "--json",
        ]
        for capability in capabilities:
            command.extend(["--capability", capability])
        if context_loaded:
            command.append("--context-loaded")
        result = self.run_command(*command)
        payload = json.loads(result.stdout) if result.stdout.strip().startswith("{") else {}
        return result, payload

    def test_named_profiles_do_not_imply_capabilities(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.create_workspace(Path(temp))
            for runtime in ("claude", "gemini", "codex", "local"):
                with self.subTest(runtime=runtime):
                    result, report = self.startup_report(workspace, runtime=runtime)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertTrue(report["ready"])
                    self.assertEqual(report["runtime"], runtime)
                    self.assertTrue(report["runtime_profile_exact_match"])
                    self.assertEqual(report["capabilities"], [])
                    self.assertFalse(report["write_policy"]["effective_runtime_write_ready"])
                    self.assertFalse(report["native_skill_loader_required"])
                    self.assertFalse(report["semantic_memory_required"])

    def test_unknown_runtime_uses_safe_fallback_without_fabricating_tools(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.create_workspace(Path(temp))
            result, report = self.startup_report(workspace, runtime="future-runtime")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(report["ready"])
            self.assertEqual(report["requested_runtime"], "future-runtime")
            self.assertEqual(report["runtime"], "unknown")
            self.assertFalse(report["runtime_profile_exact_match"])
            self.assertEqual(report["capabilities"], [])
            self.assertFalse(report["write_policy"]["effective_runtime_write_ready"])

    def test_quick_mode_requires_verified_loaded_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.create_workspace(Path(temp))
            blocked, report = self.startup_report(workspace, runtime="claude", mode="quick")
            self.assertEqual(blocked.returncode, 2)
            self.assertFalse(report["ready"])
            self.assertEqual(report["state_freshness"], "unverified")
            self.assertTrue(any("Quick mode" in blocker for blocker in report["blockers"]))

            ready, report = self.startup_report(
                workspace,
                runtime="claude",
                mode="quick",
                context_loaded=True,
            )
            self.assertEqual(ready.returncode, 0, ready.stdout + ready.stderr)
            self.assertTrue(report["ready"])
            self.assertEqual(report["state_freshness"], "verified_loaded_context")

    def test_runtime_switch_reads_the_same_durable_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.create_workspace(Path(temp))
            checkpoint = self.run_command(
                sys.executable,
                str(CHECKPOINT),
                "--workspace",
                str(workspace),
                "--summary",
                "portable state fixture",
                "--completed",
                "milestone one",
                "--next-step",
                "continue elsewhere",
            )
            self.assertEqual(checkpoint.returncode, 0, checkpoint.stdout + checkpoint.stderr)

            first_result, first = self.startup_report(
                workspace,
                runtime="claude",
                capabilities=("read_files",),
            )
            second_result, second = self.startup_report(
                workspace,
                runtime="gemini",
                capabilities=("read_files",),
            )
            self.assertEqual(first_result.returncode, 0)
            self.assertEqual(second_result.returncode, 0)
            self.assertEqual(first["latest_checkpoint"], second["latest_checkpoint"])
            self.assertEqual(first["latest_checkpoint"]["summary"], "portable state fixture")
            self.assertNotEqual(first["runtime"], second["runtime"])

    def test_missing_skill_loader_and_semantic_memory_do_not_block_core_startup(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.create_workspace(Path(temp))
            trust = self.run_command(sys.executable, str(ROOT / "scripts/runtime_trust.py"),
                                     "trust", "local", "--workspace", str(workspace), "--confirm", "local")
            self.assertEqual(trust.returncode, 0, trust.stdout + trust.stderr)
            result, report = self.startup_report(
                workspace,
                runtime="local",
                capabilities=("read_files", "write_files"),
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(report["ready"])
            self.assertNotIn("skill_loader", report["capabilities"])
            self.assertNotIn("semantic_memory", report["capabilities"])
            self.assertEqual(report["semantic_memory_status"], "not_configured")
            self.assertTrue(report["write_policy"]["effective_runtime_write_ready"])

    def test_configured_but_unverified_semantic_memory_is_nonblocking(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.create_workspace(Path(temp))
            brain_path = workspace / "BRAIN.json"
            brain = json.loads(brain_path.read_text(encoding="utf-8"))
            brain["optional_integrations"]["semantic_memory"] = {"provider": "fixture"}
            brain_path.write_text(json.dumps(brain, indent=2) + "\n", encoding="utf-8")

            result, report = self.startup_report(workspace, runtime="codex", capabilities=("read_files",))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(report["ready"])
            self.assertEqual(report["semantic_memory_status"], "configured_not_verified")

    def test_pending_wrap_up_blocks_new_regular_work(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.create_workspace(Path(temp))
            (workspace / "state" / "pending_wrap_up.json").write_text("{}\n", encoding="utf-8")
            result, report = self.startup_report(workspace, runtime="claude")
            self.assertEqual(result.returncode, 2)
            self.assertFalse(report["ready"])
            self.assertTrue(report["pending_wrap_up"])
            self.assertTrue(any("unfinished wrap-up" in blocker for blocker in report["blockers"]))

    def test_degraded_mode_never_reports_runtime_writes_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.create_workspace(Path(temp))
            result, report = self.startup_report(
                workspace,
                runtime="claude",
                mode="degraded_offline",
                capabilities=("write_files",),
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(report["state_freshness"], "stale_by_mode")
            self.assertFalse(report["write_policy"]["core_allows_writes"])
            self.assertFalse(report["write_policy"]["effective_runtime_write_ready"])

    def test_unknown_capability_name_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.create_workspace(Path(temp))
            result = self.run_command(
                sys.executable,
                str(STARTUP),
                "--workspace",
                str(workspace),
                "--runtime",
                "claude",
                "--capability",
                "telepathy",
                "--json",
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("unrecognized capability", result.stderr)


if __name__ == "__main__":
    unittest.main()
