from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "scripts" / "setup_workspace.py"
WRAP_UP = ROOT / "scripts" / "wrap_up.py"


class AstraM6RetryReceiptTests(unittest.TestCase):
    def run_script(self, script: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(script), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def parse_receipt(self, result: subprocess.CompletedProcess[str]) -> dict[str, object]:
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return json.loads(result.stdout)

    def test_exact_wrapup_retry_reconstructs_identical_structured_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            setup = self.run_script(SETUP, "--workspace", str(workspace))
            self.assertEqual(setup.returncode, 0, setup.stderr + setup.stdout)

            bundle = root / "bundle.json"
            bundle.write_text(
                json.dumps(
                    {
                        "operation_id": "m6-retry-receipt",
                        "durable_facts": ["retry receipt fact"],
                        "checkpoint": {"summary": "retry receipt checkpoint"},
                    }
                ),
                encoding="utf-8",
            )

            first = self.parse_receipt(
                self.run_script(
                    WRAP_UP,
                    "--workspace",
                    str(workspace),
                    "--bundle",
                    str(bundle),
                    "--json",
                )
            )
            retried = self.parse_receipt(
                self.run_script(
                    WRAP_UP,
                    "--workspace",
                    str(workspace),
                    "--bundle",
                    str(bundle),
                    "--json",
                )
            )
            self.assertEqual(retried, first)
            self.assertEqual(retried["operation_id"], "m6-retry-receipt")
            self.assertEqual(retried["revision"], 1)


if __name__ == "__main__":
    unittest.main()
