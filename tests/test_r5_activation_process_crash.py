"""Kill activation at each journal boundary and recover in a fresh process."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import test_r5_platform_git_hardening as fixtures


ROOT = Path(__file__).resolve().parents[1]
CHILD = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from test_r5_platform_git_hardening import R5PlatformGitHardeningTests
from third_party import activate_source
from scan_external import scan_tree
fixture = R5PlatformGitHardeningTests()
activate_source(Path(sys.argv[2]), fixture.source_entry('2' * 40),
                Path(sys.argv[3]), scan_tree(Path(sys.argv[3]) / 'source'),
                replace=True)
"""


class ActivationProcessCrashTests(unittest.TestCase):
    def test_every_activation_boundary_recovers_in_a_fresh_process(self):
        from third_party import activate_source
        from scan_external import scan_tree

        boundaries = {
            "external_activation_after_pending_record": "rolled_back",
            "external_activation_after_backup_move": "rolled_back",
            "external_activation_after_destination_move": "rolled_back",
            "external_activation_after_manifest_write": "committed",
            "external_activation_after_operation_record": "committed",
        }
        for point, expected in boundaries.items():
            with self.subTest(point=point), tempfile.TemporaryDirectory() as temporary:
                fixture = fixtures.R5PlatformGitHardeningTests()
                workspace = fixture.make_workspace(Path(temporary))
                old = fixture.quarantine(workspace, "old", "old active\n")
                active = activate_source(workspace, fixture.source_entry("1" * 40), old,
                                         scan_tree(old / "source"))
                candidate = fixture.quarantine(workspace, "new", "new candidate\n")
                crashed = subprocess.run(
                    [sys.executable, "-c", CHILD, str(ROOT / "tests"), str(workspace), str(candidate)],
                    env={**os.environ, "AHAM_BRAHMASMI_TEST_MODE": "1",
                         "AHAM_BRAHMASMI_TEST_CRASH_POINT": point},
                    capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(crashed.returncode, 86, crashed.stdout + crashed.stderr)
                self.assertTrue((workspace / "state/pending_external_activation.json").is_file())
                recovered = subprocess.run(
                    [sys.executable, str(ROOT / "scripts/external_sources.py"), "recover",
                     "--workspace", str(workspace)],
                    capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
                self.assertIn(expected, recovered.stdout)
                self.assertFalse((workspace / "state/pending_external_activation.json").exists())
                manifest = json.loads((workspace / "state/installed_sources.json").read_text())
                entry = manifest["sources"]["fixture-r5-source"]
                from state_store import list_operation_records
                records = list_operation_records(workspace)
                self.assertEqual(len(records), 2 if expected == "committed" else 1)
                from operation_receipt import receipt_for_operation
                self.assertEqual(receipt_for_operation(workspace, records[-1][1]["operation_id"])["status"], "complete")
                if expected == "committed":
                    self.assertEqual(entry["source_ref"], "2" * 40)
                    self.assertEqual((active / "README.md").read_text(), "new candidate\n")
                    backups = list((workspace / "state/replaced_sources").glob("*/README.md"))
                    self.assertEqual([path.read_text() for path in backups], ["old active\n"])
                else:
                    self.assertEqual(entry["source_ref"], "1" * 40)
                    self.assertEqual((active / "README.md").read_text(), "old active\n")
                    self.assertEqual((candidate / "source/README.md").read_text(), "new candidate\n")


if __name__ == "__main__":
    unittest.main()
