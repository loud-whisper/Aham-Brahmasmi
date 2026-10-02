from __future__ import annotations

import shutil
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "scripts" / "release_audit.py"


@unittest.skipIf(shutil.which("git") is None, "git is not available")
class ReleaseAuditTests(unittest.TestCase):
    def test_offline_release_rehearsal_passes_in_isolation(self) -> None:
        result = subprocess.run(
            [sys.executable, str(AUDIT)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=90,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("RELEASE REHEARSAL PASSED", result.stdout)
        self.assertIn("fresh private workspace setup and verification", result.stdout)
        self.assertIn("checkpoint, crash recovery", result.stdout)
        self.assertIn("caller-bound runtime authority", result.stdout)
        self.assertIn("host-neutral local Git snapshot without a remote", result.stdout)


if __name__ == "__main__":
    unittest.main()
