from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFORMANCE = ROOT / "scripts" / "runtime_conformance.py"


class R3ConformanceIntegrityTests(unittest.TestCase):
    def test_recovery_evidence_does_not_upgrade_a_different_model_on_same_harness(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            register = Path(temp) / "register.json"
            register.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "entries": [
                            {
                                "entry_id": "live-model-a",
                                "evidence_type": "live_runtime_rehearsal",
                                "runtime_profile": "local",
                                "result": "pass",
                                "independently_verified": True,
                                "claim_scope": "single_run_smoke_test",
                                "framework_commit": "abc",
                                "model": "model-a",
                                "harness": "Harness X",
                                "harness_version": "1.0",
                                "context_tokens": 65536,
                                "quantization": "Q4",
                                "permission_mode": "sandbox",
                                "human_intervention": False,
                                "verified_at": "2026-01-01T00:00:00Z",
                            },
                            {
                                "entry_id": "recovery-model-b",
                                "evidence_type": "runtime_switch_recovery",
                                "result": "pass",
                                "independently_verified": True,
                                "fresh_target_session": True,
                                "to_harness": "Harness X",
                                "to_harness_version": "1.0",
                                "to_model": "model-b",
                                "to_context_tokens": 65536,
                                "to_quantization": "Q4",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(CONFORMANCE),
                    "matrix",
                    "--register",
                    str(register),
                    "--context-budget-bytes",
                    "8192",
                    "--json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            matrix = json.loads(result.stdout)
            self.assertEqual(len(matrix["selected_rich_evidence"]), 1)
            self.assertEqual(matrix["selected_rich_evidence"][0]["model"], "model-a")
            self.assertEqual(matrix["selected_rich_evidence"][0]["tier"], "lifecycle_writer")


if __name__ == "__main__":
    unittest.main()
