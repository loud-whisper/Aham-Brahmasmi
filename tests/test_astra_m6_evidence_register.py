from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts" / "runtime_evidence.py"
REGISTER = ROOT / "evidence" / "runtime_harness_register.json"


class AstraM6EvidenceRegisterRegressionTests(unittest.TestCase):
    def run_tool(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(TOOL), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def entry(
        self,
        *,
        entry_id: str,
        evidence_type: str = "live_runtime_rehearsal",
        rehearsal_id: str | None = "rehearsal-1",
        result: str = "pass",
        historical: bool = False,
    ) -> dict[str, object]:
        return {
            "entry_id": entry_id,
            "evidence_type": evidence_type,
            "runtime_profile": "local" if evidence_type == "live_runtime_rehearsal" else "codex",
            "model": None if historical else "example-model",
            "harness": None if historical else "example-harness",
            "harness_version": None if historical else "1.2.3",
            "os_platform": None if historical else "Linux-test",
            "framework_commit": None if historical else "a" * 40,
            "rehearsal_id": rehearsal_id,
            "permission_mode": None if historical else "sandboxed-write",
            "result": result,
            "human_intervention": None if historical else False,
            "context_tokens": None if historical else 131072,
            "quantization": None if historical else "Q4_K_M",
            "verified_at": None if historical else "2026-09-19T13:30:00Z",
            "independently_verified": False if historical else True,
            "claim_scope": "single_run_smoke_test" if evidence_type == "live_runtime_rehearsal" else "framework_profile_only",
            "source": "historical checklist" if historical else "synthetic regression fixture",
            "limitations": ["Fields not recorded historically remain null."] if historical else [],
        }

    def write_register(self, path: Path, entries: list[dict[str, object]]) -> None:
        path.write_text(
            json.dumps(
                {
                    "format": "aham-brahmasmi-runtime-evidence-register",
                    "version": 1,
                    "entries": entries,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    def test_repository_has_one_versioned_register_that_validates(self) -> None:
        result = self.run_tool("validate", "--register", str(REGISTER))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("RUNTIME EVIDENCE REGISTER VERIFIED", result.stdout)

    def test_historical_evidence_can_preserve_unknown_fields_as_null(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            register = Path(temp) / "register.json"
            self.write_register(
                register,
                [
                    self.entry(
                        entry_id="historical-gemini",
                        rehearsal_id="historical-rehearsal",
                        historical=True,
                    )
                ],
            )
            result = self.run_tool("validate", "--register", str(register))
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("RUNTIME EVIDENCE REGISTER VERIFIED", result.stdout)

    def test_framework_profile_and_live_runtime_evidence_are_distinct_types(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            register = Path(temp) / "register.json"
            self.write_register(
                register,
                [
                    self.entry(entry_id="live-1", rehearsal_id="live-rehearsal"),
                    self.entry(
                        entry_id="profile-1",
                        evidence_type="framework_profile_test",
                        rehearsal_id=None,
                    ),
                ],
            )
            result = self.run_tool("validate", "--register", str(register))
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("Entries: 2", result.stdout)

    def test_duplicate_or_contradictory_live_rehearsal_identity_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            register = Path(temp) / "register.json"
            self.write_register(
                register,
                [
                    self.entry(entry_id="live-pass", rehearsal_id="same-rehearsal", result="pass"),
                    self.entry(entry_id="live-fail", rehearsal_id="same-rehearsal", result="fail"),
                ],
            )
            result = self.run_tool("validate", "--register", str(register))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("duplicate live rehearsal identity", result.stderr)

    def test_numeric_reliability_claim_is_rejected_for_single_run_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            register = Path(temp) / "register.json"
            entry = self.entry(entry_id="live-reliability", rehearsal_id="one-run")
            entry["reliability_percentage"] = 100
            self.write_register(register, [entry])
            result = self.run_tool("validate", "--register", str(register))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("reliability", result.stderr.lower())


if __name__ == "__main__":
    unittest.main()
