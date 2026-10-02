from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "scripts" / "setup_workspace.py"
VERIFY = ROOT / "scripts" / "verify_workspace.py"
MIGRATE = ROOT / "scripts" / "migrate_workspace.py"
GIT_TRANSPORT = ROOT / "scripts" / "git_transport.py"
SCHEMA_DOC = ROOT / "docs" / "SCHEMA_COMPATIBILITY.md"
SCHEMA_PATH = Path("state/schema.json")
PENDING_PATH = Path("state/pending_migration.json")
MIGRATIONS_DIR = Path("state/migrations")


class R1SchemaMigrationTests(unittest.TestCase):
    def run_script(
        self,
        script: Path,
        *args: str,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
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

    def git(self, repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def new_workspace(self, root: Path) -> Path:
        workspace = root / "workspace"
        result = self.run_script(SETUP, "--workspace", str(workspace))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return workspace

    def make_legacy_workspace(self, root: Path) -> Path:
        workspace = self.new_workspace(root)
        schema = workspace / SCHEMA_PATH
        if schema.exists():
            schema.unlink()
        migrations = workspace / MIGRATIONS_DIR
        if migrations.exists():
            for child in migrations.iterdir():
                if child.is_file():
                    child.unlink()
            migrations.rmdir()
        pending = workspace / PENDING_PATH
        if pending.exists():
            pending.unlink()
        return workspace

    def test_new_workspace_has_current_schema_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.new_workspace(Path(temp))
            manifest = json.loads((workspace / SCHEMA_PATH).read_text(encoding="utf-8"))
            self.assertEqual(manifest["format"], "aham-brahmasmi-workspace-schema")
            self.assertEqual(manifest["version"], 1)
            verify = self.run_script(VERIFY, "--workspace", str(workspace))
            self.assertEqual(verify.returncode, 0, verify.stderr + verify.stdout)

    def test_git_transport_snapshots_schema_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.new_workspace(Path(temp))
            initialized = self.run_script(
                GIT_TRANSPORT,
                "init",
                "--workspace",
                str(workspace),
                "--author-name",
                "Aham Test",
                "--author-email",
                "test@example.invalid",
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
            snapshot = self.run_script(
                GIT_TRANSPORT,
                "snapshot",
                "--workspace",
                str(workspace),
                "--message",
                "schema compatibility snapshot",
            )
            self.assertEqual(snapshot.returncode, 0, snapshot.stderr + snapshot.stdout)
            tracked = self.git(workspace, "ls-files", "--", "state/schema.json")
            self.assertEqual(tracked.returncode, 0, tracked.stderr + tracked.stdout)
            self.assertEqual(tracked.stdout.strip(), "state/schema.json")

    def test_legacy_workspace_migrates_without_changing_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.make_legacy_workspace(Path(temp))
            brain_path = workspace / "BRAIN.json"
            before_brain = brain_path.read_bytes()

            verify_before = self.run_script(VERIFY, "--workspace", str(workspace))
            self.assertNotEqual(verify_before.returncode, 0)
            self.assertIn("migration", (verify_before.stdout + verify_before.stderr).lower())

            migrated = self.run_script(MIGRATE, "--workspace", str(workspace))
            self.assertEqual(migrated.returncode, 0, migrated.stderr + migrated.stdout)
            self.assertIn("MIGRATION COMPLETE", migrated.stdout)
            self.assertEqual(brain_path.read_bytes(), before_brain)

            manifest = json.loads((workspace / SCHEMA_PATH).read_text(encoding="utf-8"))
            self.assertEqual(manifest["version"], 1)
            self.assertFalse((workspace / PENDING_PATH).exists())
            receipts = list((workspace / MIGRATIONS_DIR).glob("*.json"))
            self.assertEqual(len(receipts), 1)
            receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
            self.assertEqual(receipt["from_version"], 0)
            self.assertEqual(receipt["to_version"], 1)
            self.assertEqual(receipt["status"], "complete")

            verify_after = self.run_script(VERIFY, "--workspace", str(workspace))
            self.assertEqual(verify_after.returncode, 0, verify_after.stderr + verify_after.stdout)

    def test_current_workspace_migration_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.new_workspace(Path(temp))
            schema_path = workspace / SCHEMA_PATH
            before = schema_path.read_bytes()

            first = self.run_script(MIGRATE, "--workspace", str(workspace))
            self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
            self.assertIn("MIGRATION NOT NEEDED", first.stdout)
            self.assertEqual(schema_path.read_bytes(), before)
            self.assertFalse((workspace / PENDING_PATH).exists())

            second = self.run_script(MIGRATE, "--workspace", str(workspace))
            self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
            self.assertEqual(schema_path.read_bytes(), before)

    def test_future_schema_is_refused_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.new_workspace(Path(temp))
            schema_path = workspace / SCHEMA_PATH
            manifest = json.loads(schema_path.read_text(encoding="utf-8"))
            manifest["version"] = 2
            schema_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            before = schema_path.read_bytes()

            result = self.run_script(MIGRATE, "--workspace", str(workspace))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("newer", (result.stdout + result.stderr).lower())
            self.assertEqual(schema_path.read_bytes(), before)
            self.assertFalse((workspace / PENDING_PATH).exists())

    def test_unsupported_identity_envelope_is_refused_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.make_legacy_workspace(Path(temp))
            brain_path = workspace / "BRAIN.json"
            brain = json.loads(brain_path.read_text(encoding="utf-8"))
            brain["version"] = 2
            brain_path.write_text(json.dumps(brain, indent=2) + "\n", encoding="utf-8")
            before = brain_path.read_bytes()

            result = self.run_script(MIGRATE, "--workspace", str(workspace))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("identity", (result.stdout + result.stderr).lower())
            self.assertEqual(brain_path.read_bytes(), before)
            self.assertFalse((workspace / PENDING_PATH).exists())

    def test_interrupted_migration_recovers_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.make_legacy_workspace(Path(temp))
            brain_before = (workspace / "BRAIN.json").read_bytes()

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
            self.assertTrue((workspace / SCHEMA_PATH).exists())
            self.assertTrue((workspace / PENDING_PATH).exists())
            self.assertEqual((workspace / "BRAIN.json").read_bytes(), brain_before)
            self.assertEqual(list((workspace / MIGRATIONS_DIR).glob("*.json")), [])

            recovered = self.run_script(MIGRATE, "--workspace", str(workspace))
            self.assertEqual(recovered.returncode, 0, recovered.stderr + recovered.stdout)
            self.assertIn("MIGRATION RECOVERED", recovered.stdout)
            self.assertFalse((workspace / PENDING_PATH).exists())
            receipts = list((workspace / MIGRATIONS_DIR).glob("*.json"))
            self.assertEqual(len(receipts), 1)
            receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
            self.assertEqual(receipt["from_version"], 0)
            self.assertEqual(receipt["to_version"], 1)
            self.assertEqual(receipt["status"], "complete")

            rerun = self.run_script(MIGRATE, "--workspace", str(workspace))
            self.assertEqual(rerun.returncode, 0, rerun.stderr + rerun.stdout)
            self.assertIn("MIGRATION NOT NEEDED", rerun.stdout)
            self.assertEqual(len(list((workspace / MIGRATIONS_DIR).glob("*.json"))), 1)

    def test_schema_compatibility_policy_is_documented(self) -> None:
        text = SCHEMA_DOC.read_text(encoding="utf-8")
        lowered = text.lower()
        self.assertIn("brain.json", lowered)
        self.assertIn("identity envelope", lowered)
        self.assertIn("schema 0", lowered)
        self.assertIn("schema 1", lowered)
        self.assertIn("newer", lowered)
        self.assertIn("interrupted", lowered)
        self.assertIn("state/schema.json", lowered)


if __name__ == "__main__":
    unittest.main()
