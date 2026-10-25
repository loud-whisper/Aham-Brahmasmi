from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_live_runtime_rehearsal import LiveRuntimeRehearsalTests


ROOT = Path(__file__).resolve().parents[1]
REGISTER_TOOL = ROOT / "scripts" / "runtime_evidence.py"


def namespace_helper_args() -> list[str]:
    if os.environ.get("AHAM_TEST_BWRAP_SUDO_HELPER") == "1":
        return ["--sudo-namespace-helper"]
    return []


class AstraM6LiveEvidenceEmissionRegressionTests(unittest.TestCase):
    def test_independent_verifier_emits_register_compatible_evidence(self) -> None:
        helper = LiveRuntimeRehearsalTests()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "rehearsal"
            manifest = helper.prepare(root)
            helper.complete_synthetic_runtime(root)

            result = helper.run_tool("verify", "--root", str(root), "--json")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            entry = report["runtime_evidence"]

            self.assertEqual(entry["evidence_type"], "live_runtime_rehearsal")
            self.assertEqual(entry["runtime_profile"], manifest["runtime"])
            self.assertEqual(entry["rehearsal_id"], manifest["rehearsal_id"])
            self.assertEqual(entry["result"], "pass")
            self.assertTrue(entry["independently_verified"])
            self.assertEqual(entry["claim_scope"], "single_run_smoke_test")
            self.assertIsInstance(manifest["framework_commit"], str)
            self.assertEqual(len(manifest["framework_commit"]), 40)
            self.assertEqual(entry["framework_commit"], manifest["framework_commit"])

            register = root / "emitted-register.json"
            register.write_text(
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
            validated = subprocess.run(
                [sys.executable, str(REGISTER_TOOL), "validate", "--register", str(register)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(validated.returncode, 0, validated.stderr + validated.stdout)
            self.assertIn("RUNTIME EVIDENCE REGISTER VERIFIED", validated.stdout)

    def test_run_binds_rich_runtime_metadata_for_independent_verification(self) -> None:
        helper = LiveRuntimeRehearsalTests()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "rehearsal"
            manifest = helper.prepare(root)

            run_result = helper.run_tool(
                "run",
                "--root",
                str(root),
                *namespace_helper_args(),
                "--non-interactive",
                "--model",
                "unsloth/Qwen3.8-27B-GGUF",
                "--harness",
                "DeepSeek Harness",
                "--harness-version",
                "0.1.5-rc.2",
                "--context-tokens",
                "65536",
                "--quantization",
                "UD-Q4_K_XL",
                "--",
                "/bin/true",
            )
            self.assertEqual(run_result.returncode, 0, run_result.stdout + run_result.stderr)

            execution_path = root / "runtime_execution.json"
            self.assertTrue(execution_path.is_file())
            execution = json.loads(execution_path.read_text(encoding="utf-8"))
            self.assertEqual(execution["runtime"], manifest["runtime"])
            self.assertEqual(execution["rehearsal_id"], manifest["rehearsal_id"])
            self.assertEqual(execution["model"], "unsloth/Qwen3.8-27B-GGUF")
            self.assertEqual(execution["harness"], "DeepSeek Harness")
            self.assertEqual(execution["harness_version"], "0.1.5-rc.2")
            self.assertEqual(execution["context_tokens"], 65536)
            self.assertEqual(execution["quantization"], "UD-Q4_K_XL")
            self.assertIsInstance(execution["os_platform"], str)
            self.assertTrue(execution["os_platform"])
            self.assertIsInstance(execution["permission_mode"], str)
            self.assertTrue(execution["permission_mode"])
            self.assertFalse(execution["human_intervention"])
            self.assertRegex(execution["runtime_command_sha256"], r"^[0-9a-f]{64}$")

            helper.complete_synthetic_runtime(root)
            verified = helper.run_tool("verify", "--root", str(root), "--json")
            self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
            entry = json.loads(verified.stdout)["runtime_evidence"]
            self.assertEqual(entry["model"], execution["model"])
            self.assertEqual(entry["harness"], execution["harness"])
            self.assertEqual(entry["harness_version"], execution["harness_version"])
            self.assertEqual(entry["context_tokens"], execution["context_tokens"])
            self.assertEqual(entry["quantization"], execution["quantization"])
            self.assertEqual(entry["os_platform"], execution["os_platform"])
            self.assertEqual(entry["permission_mode"], execution["permission_mode"])
            self.assertEqual(entry["human_intervention"], execution["human_intervention"])
            self.assertNotIn("does not capture the exact model", " ".join(entry["limitations"]))

    def test_run_refuses_to_overwrite_existing_execution_evidence(self) -> None:
        helper = LiveRuntimeRehearsalTests()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "rehearsal"
            helper.prepare(root)
            args = (
                "run",
                "--root",
                str(root),
                *namespace_helper_args(),
                "--non-interactive",
                "--model",
                "test-model",
                "--harness",
                "test-harness",
                "--harness-version",
                "1.0",
                "--context-tokens",
                "4096",
                "--quantization",
                "test-quant",
                "--",
                "/bin/true",
            )
            first = helper.run_tool(*args)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            execution_path = root / "runtime_execution.json"
            original = execution_path.read_text(encoding="utf-8")

            second = helper.run_tool(*args)
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("runtime execution record already exists", second.stderr)
            self.assertEqual(execution_path.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
