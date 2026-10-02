from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from state_io import StateError, require_workspace

SETUP = SCRIPTS / "setup_workspace.py"
MIGRATE = SCRIPTS / "migrate_workspace.py"
VERIFY = SCRIPTS / "verify_workspace.py"


class R1PendingMigrationGateTests(unittest.TestCase):
    def run_script(
        self,
        script: Path,
        *args: str,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        import os

        merged = os.environ.copy()
        if env:
            merged.update(env)
        return subprocess.run(
            [sys.executable, str(script), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            env=merged,
        )

    def test_schema_written_but_pending_migration_blocks_normal_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp) / "workspace"
            setup = self.run_script(SETUP, "--workspace", str(workspace))
            self.assertEqual(setup.returncode, 0, setup.stderr + setup.stdout)

            # Convert the current fixture into the real pre-R1 schema-0 shape.
            (workspace / "state" / "schema.json").unlink()

            crashed = self.run_script(
                MIGRATE,
                "--workspace",
                str(workspace),
                env={
                    "AHAM_BRAHMASMI_TEST_MODE": "1",
                    "AHAM_BRAHMASMI_TEST_CRASH_POINT": "migration_after_schema_write",
                },
            )
            self.assertEqual(crashed.returncode, 86, crashed.stderr + crashed.stdout)
            self.assertTrue((workspace / "state" / "schema.json").is_file())
            self.assertTrue((workspace / "state" / "pending_migration.json").is_file())

            with self.assertRaisesRegex(StateError, "pending migration"):
                require_workspace(workspace)

            verify = self.run_script(VERIFY, "--workspace", str(workspace))
            self.assertNotEqual(verify.returncode, 0)
            self.assertIn("pending migration", (verify.stdout + verify.stderr).lower())

            recovered = self.run_script(MIGRATE, "--workspace", str(workspace))
            self.assertEqual(recovered.returncode, 0, recovered.stderr + recovered.stdout)
            self.assertIn("MIGRATION RECOVERED", recovered.stdout)
            self.assertFalse((workspace / "state" / "pending_migration.json").exists())

            require_workspace(workspace)
            verify_after = self.run_script(VERIFY, "--workspace", str(workspace))
            self.assertEqual(verify_after.returncode, 0, verify_after.stderr + verify_after.stdout)


if __name__ == "__main__":
    unittest.main()
