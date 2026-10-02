from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts" / "runtime_negative_path_rehearsal.py"
EVIDENCE = ROOT / "scripts" / "runtime_evidence.py"
STARTUP = ROOT / "scripts" / "startup.py"
WRAP_UP = ROOT / "scripts" / "wrap_up.py"


def namespace_helper_args() -> list[str]:
    if os.environ.get("AHAM_TEST_BWRAP_SUDO_HELPER") == "1":
        return ["--sudo-namespace-helper"]
    return []


class RuntimeNegativePathRegressionTests(unittest.TestCase):
    def run_tool(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(TOOL), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def run_script(self, script: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(script), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def prepare_and_exercise(self, root: Path) -> dict[str, object]:
        prepared = self.run_tool("prepare", "--root", str(root))
        self.assertEqual(prepared.returncode, 0, prepared.stdout + prepared.stderr)
        exercised = self.run_tool("exercise", "--root", str(root))
        self.assertEqual(exercised.returncode, 0, exercised.stdout + exercised.stderr)
        return json.loads((root / "negative_manifest.json").read_text(encoding="utf-8"))

    def complete_target_recovery(self, root: Path, manifest: dict[str, object]) -> dict[str, object]:
        workspace = str(root / "workspace")
        startup = self.run_script(
            STARTUP,
            "--workspace",
            workspace,
            "--runtime",
            "local",
            "--mode",
            "wrap_up",
            "--capability",
            "read_files",
            "--capability",
            "write_files",
            "--capability",
            "run_commands",
            "--harness",
            f"negative-target:{manifest['rehearsal_id']}",
            "--json",
        )
        self.assertEqual(startup.returncode, 0, startup.stdout + startup.stderr)
        report = json.loads(startup.stdout)
        session_id = str(report["session_authority"]["session_id"])
        recovered = self.run_script(
            WRAP_UP,
            "--workspace",
            workspace,
            "--recover-pending",
            "--session-id",
            session_id,
        )
        self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
        controller = json.loads((root / "controller_verified.json").read_text(encoding="utf-8"))
        return controller

    def test_controller_probes_reject_malformed_and_denied_then_preserve_interruption(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "negative"
            manifest = self.prepare_and_exercise(root)
            verified = json.loads((root / "controller_verified.json").read_text(encoding="utf-8"))
            self.assertTrue(verified["malformed_rejected"])
            self.assertTrue(verified["malformed_zero_mutation"])
            self.assertTrue(verified["denied_rejected"])
            self.assertTrue(verified["denied_zero_mutation"])
            self.assertEqual(verified["writer_crash_exit_code"], 86)
            self.assertEqual(verified["crash_point"], "wrap_up_after_commit_record")
            self.assertEqual(verified["interrupted_operation_id"], manifest["interrupted_operation_id"])
            self.assertEqual(verified["source_revision"], 2)
            self.assertTrue((root / "workspace" / "state" / "pending_wrap_up.json").is_file())

    def test_fresh_target_recovery_is_independently_verified(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "negative"
            manifest = self.prepare_and_exercise(root)
            target = self.run_tool(
                "run-target",
                "--root",
                str(root),
                *namespace_helper_args(),
                "--non-interactive",
                "--model",
                "example-model",
                "--harness",
                "target-harness",
                "--harness-version",
                "2.0",
                "--context-tokens",
                "4096",
                "--quantization",
                "Q4",
                "--",
                "/bin/true",
            )
            self.assertEqual(target.returncode, 0, target.stdout + target.stderr)
            controller = self.complete_target_recovery(root, manifest)
            result = {
                "format": "aham-brahmasmi-runtime-negative-path-result",
                "version": 1,
                "rehearsal_id": manifest["rehearsal_id"],
                "recovered_fact": manifest["interrupted_fact"],
                "recovered_revision": controller["source_revision"],
                "recovered_checkpoint_id": controller["source_checkpoint_id"],
                "resume_verified": True,
            }
            (root / "result" / "recovered.json").write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            verified = self.run_tool("verify", "--root", str(root), "--json")
            self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
            report = json.loads(verified.stdout)
            self.assertTrue(report["verified"])
            self.assertTrue(report["runtime_evidence"]["fresh_target_session"])
            self.assertEqual(report["runtime_evidence"]["writer_crash_exit_code"], 86)
            self.assertEqual(report["runtime_evidence"]["source_revision"], report["runtime_evidence"]["recovered_revision"])
            self.assertEqual(report["runtime_evidence"]["claim_scope"], "single_failure_path_rehearsal")


class RuntimeNegativePathEvidenceTests(unittest.TestCase):
    def run_evidence(self, register: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(EVIDENCE), "validate", "--register", str(register)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def entry(self) -> dict[str, object]:
        return {
            "entry_id": "negative-example",
            "evidence_type": "runtime_failure_paths",
            "rehearsal_id": "negative-123",
            "framework_commit": "a" * 40,
            "malformed_exit_code": 1,
            "malformed_stderr_sha256": "1" * 64,
            "malformed_zero_mutation": True,
            "denied_exit_code": 1,
            "denied_stderr_sha256": "2" * 64,
            "denied_zero_mutation": True,
            "interrupted_operation_id": "negative-interrupt-123",
            "crash_point": "wrap_up_after_commit_record",
            "writer_crash_exit_code": 86,
            "source_revision": 1,
            "recovered_revision": 1,
            "source_checkpoint_id": "wrap-negative-interrupt-123",
            "recovered_checkpoint_id": "wrap-negative-interrupt-123",
            "state_digest": "3" * 64,
            "target_runtime_profile": "local",
            "target_model": "example-model",
            "target_harness": "target-harness",
            "target_harness_version": "2.0",
            "target_context_tokens": 4096,
            "target_quantization": "Q4",
            "target_os_platform": "Linux-test",
            "target_permission_mode": "bubblewrap;stdin=closed",
            "target_human_intervention": False,
            "target_runtime_command_sha256": "4" * 64,
            "fresh_target_session": True,
            "result": "pass",
            "verified_at": "2026-09-19T20:30:00Z",
            "independently_verified": True,
            "claim_scope": "single_failure_path_rehearsal",
            "source": "verified_negative_report.json",
            "limitations": ["Single negative-path rehearsal is not a reliability estimate."],
        }

    def write_register(self, path: Path, entry: dict[str, object]) -> None:
        path.write_text(
            json.dumps(
                {
                    "format": "aham-brahmasmi-runtime-evidence-register",
                    "version": 1,
                    "entries": [entry],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    def test_runtime_failure_paths_are_a_distinct_valid_evidence_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            register = Path(temp) / "register.json"
            self.write_register(register, self.entry())
            result = self.run_evidence(register)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_passing_failure_paths_require_exact_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            register = Path(temp) / "register.json"
            entry = self.entry()
            entry["recovered_revision"] = 2
            self.write_register(register, entry)
            result = self.run_evidence(register)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("recovered_revision", result.stderr)


if __name__ == "__main__":
    unittest.main()
