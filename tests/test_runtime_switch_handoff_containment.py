from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from test_runtime_switch_recovery import RuntimeSwitchRecoveryRegressionTests, namespace_helper_args


class RuntimeSwitchHandoffContainmentRegressionTests(unittest.TestCase):
    def helper(self) -> RuntimeSwitchRecoveryRegressionTests:
        return RuntimeSwitchRecoveryRegressionTests()

    def prepare_committed_source(self, root: Path) -> tuple[RuntimeSwitchRecoveryRegressionTests, dict[str, object]]:
        helper = self.helper()
        manifest = helper.prepare(root)
        source_run = helper.run_switch(
            "run-source",
            "--root",
            str(root),
            *namespace_helper_args(),
            "--non-interactive",
            "--",
            "/bin/true",
        )
        self.assertEqual(source_run.returncode, 0, source_run.stdout + source_run.stderr)
        helper.complete_source_state(root, manifest)
        return helper, manifest

    def test_verify_source_rejects_project_handoff_created_after_prepare(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "switch"
            helper, manifest = self.prepare_committed_source(root)
            handoff = root / "project" / "HANDOFF.md"
            handoff.write_text(str(manifest["durable_fact"]) + "\n", encoding="utf-8")

            verified = helper.run_switch("verify-source", "--root", str(root))
            self.assertNotEqual(verified.returncode, 0)
            self.assertIn("project", verified.stderr.lower())
            self.assertIn("handoff", verified.stderr.lower())

    def test_verify_source_rejects_workspace_marker_outside_canonical_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "switch"
            helper, manifest = self.prepare_committed_source(root)
            handoff = root / "workspace" / "runtime-a-handoff.txt"
            handoff.write_text(
                str(manifest["unfinished_task"]) + "\n" + str(manifest["project_update"]) + "\n",
                encoding="utf-8",
            )

            verified = helper.run_switch("verify-source", "--root", str(root))
            self.assertNotEqual(verified.returncode, 0)
            self.assertIn("workspace", verified.stderr.lower())
            self.assertIn("handoff", verified.stderr.lower())

    def test_target_rejects_opencode_short_session_flag(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "switch"
            helper, manifest = self.prepare_committed_source(root)
            source_verify = helper.run_switch("verify-source", "--root", str(root))
            self.assertEqual(source_verify.returncode, 0, source_verify.stdout + source_verify.stderr)

            target = helper.run_switch(
                "run-target",
                "--root",
                str(root),
                *namespace_helper_args(),
                "--non-interactive",
                "--",
                "/bin/true",
                "-s",
                "existing-session",
            )
            self.assertNotEqual(target.returncode, 0)
            self.assertIn("fresh target session", target.stderr.lower())


if __name__ == "__main__":
    unittest.main()
