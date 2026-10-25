from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts" / "runtime_evidence.py"
REGISTER = ROOT / "evidence" / "runtime_harness_register.json"
STATUS = ROOT / "docs" / "STATUS.md"
CHECKLIST = ROOT / "PROJECT_CHECKLIST.md"
LIVE_DOC = ROOT / "docs" / "LIVE_RUNTIME_REHEARSAL.md"


class AstraM6DocumentationReconciliationRegressionTests(unittest.TestCase):
    def run_tool(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(TOOL), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_status_and_project_checklist_match_canonical_generated_status(self) -> None:
        result = self.run_tool(
            "check-docs",
            "--register",
            str(REGISTER),
            "--document",
            str(STATUS),
            "--document",
            str(CHECKLIST),
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("RUNTIME EVIDENCE DOCUMENTATION VERIFIED", result.stdout)

    def test_readme_no_longer_lists_already_verified_gemini_and_codex_as_remaining(self) -> None:
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("run the real Gemini live-runtime rehearsal and independently verify it", text)
        self.assertNotIn("run the real Codex live-runtime rehearsal and independently verify it", text)

    def test_project_checklist_uses_generated_status_instead_of_manual_live_result_summary(self) -> None:
        text = CHECKLIST.read_text(encoding="utf-8")
        self.assertIn("<!-- runtime-evidence-status:start -->", text)
        self.assertIn("<!-- runtime-evidence-status:end -->", text)
        self.assertNotIn("Live results recorded 2026-09-18:", text)

    def test_live_rehearsal_document_names_register_and_single_run_scope(self) -> None:
        text = LIVE_DOC.read_text(encoding="utf-8")
        self.assertIn("evidence/runtime_harness_register.json", text)
        self.assertIn("single-run smoke test", text)
        self.assertIn("framework/profile", text.lower())


if __name__ == "__main__":
    unittest.main()
