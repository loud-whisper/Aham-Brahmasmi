from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None


ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "scripts" / "setup_workspace.py"
WRAP_UP = ROOT / "scripts" / "wrap_up.py"
PORTABLE = ROOT / "scripts" / "portable_backup.py"
VERIFY = ROOT / "scripts" / "verify_workspace.py"
DOC = ROOT / "docs" / "PORTABLE_BACKUP_RESTORE.md"


class R4PortableBackupRestoreTests(unittest.TestCase):
    def run_script(self, script: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(script), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def workspace(self, root: Path) -> Path:
        workspace = root / "workspace"
        result = self.run_script(SETUP, "--workspace", str(workspace))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return workspace

    def add_committed_state(self, workspace: Path, root: Path) -> None:
        bundle = root / "bundle.json"
        bundle.write_text(
            json.dumps(
                {
                    "session_id": "r4-export-state",
                    "durable_facts": ["portable export fact"],
                    "unfinished_work": ["portable export task"],
                    "project_updates": [{"project": "R4 Demo", "content": "portable project state"}],
                    "checkpoint": {"summary": "portable export checkpoint", "project": "R4 Demo"},
                }
            ),
            encoding="utf-8",
        )
        result = self.run_script(WRAP_UP, "--workspace", str(workspace), "--bundle", str(bundle))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def export(self, workspace: Path, bundle: Path) -> subprocess.CompletedProcess[str]:
        return self.run_script(PORTABLE, "export", "--workspace", str(workspace), "--output", str(bundle))

    def manifest(self, workspace: Path) -> dict:
        result = self.run_script(PORTABLE, "manifest", "--workspace", str(workspace), "--json")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return json.loads(result.stdout)

    def test_export_manifest_is_deterministic_and_covers_authoritative_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.workspace(root)
            self.add_committed_state(workspace, root)
            one, two = root / "export-one", root / "export-two"
            first = self.export(workspace, one)
            second = self.export(workspace, two)
            self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
            self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
            m1 = json.loads((one / "manifest.json").read_text(encoding="utf-8"))
            m2 = json.loads((two / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(m1, m2)
            paths = {item["path"] for item in m1["files"]}
            self.assertIn("BRAIN.json", paths)
            self.assertIn("state/store.json", paths)
            self.assertTrue(any(path.startswith("state/operations/") for path in paths))
            self.assertTrue(any(path.startswith("state/wrapups/") for path in paths))
            self.assertEqual(m1["claim_scope"], "portable_local_export")
            self.assertFalse(m1["replicated_backup"])

    def test_export_is_provider_independent_and_excludes_transient_authority_and_caches(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.workspace(root)
            (workspace / "external" / "provider-cache").mkdir(parents=True)
            (workspace / "external" / "provider-cache" / "cache.bin").write_bytes(b"provider cache")
            (workspace / "state" / "scan_reports" / "provider.json").write_text("{}\n", encoding="utf-8")
            bundle = root / "export"
            result = self.export(workspace, bundle)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
            paths = {item["path"] for item in manifest["files"]}
            self.assertNotIn("state/session_authority.json", paths)
            self.assertFalse(any(path.startswith("external/") for path in paths))
            self.assertFalse(any(path.startswith("state/scan_reports/") for path in paths))
            self.assertIn("state/installed_sources.json", paths)

    def test_export_refuses_pending_mutation_or_migration(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.workspace(root)
            pending = workspace / "state" / "pending_wrap_up.json"
            pending.write_text("{}\n", encoding="utf-8")
            result = self.export(workspace, root / "export")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("pending", (result.stdout + result.stderr).lower())
            self.assertFalse((root / "export").exists())

    @unittest.skipIf(fcntl is None, "POSIX advisory locking unavailable")
    def test_export_coordinates_with_authoritative_writer_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.workspace(root)
            self.add_committed_state(workspace, root)
            lock_path = workspace / "state" / ".writer.lock"
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            output = root / "export"
            with lock_path.open("a+", encoding="utf-8") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                process = subprocess.Popen(
                    [
                        sys.executable,
                        str(PORTABLE),
                        "export",
                        "--workspace",
                        str(workspace),
                        "--output",
                        str(output),
                    ],
                    cwd=ROOT,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                try:
                    time.sleep(0.8)
                    self.assertIsNone(
                        process.poll(),
                        "portable export completed while the authoritative workspace writer lock was held",
                    )
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                stdout, stderr = process.communicate(timeout=15)
            self.assertEqual(process.returncode, 0, stderr + stdout)
            self.assertTrue((output / "manifest.json").is_file())

    def test_restore_to_clean_location_round_trips_exact_portable_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.workspace(root)
            self.add_committed_state(source, root)
            bundle, restored = root / "export", root / "restored"
            exported = self.export(source, bundle)
            self.assertEqual(exported.returncode, 0, exported.stderr + exported.stdout)
            source_manifest = self.manifest(source)
            source_session = json.loads((source / "state" / "session_authority.json").read_text(encoding="utf-8"))["session_id"]
            result = self.run_script(PORTABLE, "restore", "--input", str(bundle), "--workspace", str(restored))
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            verify = self.run_script(VERIFY, "--workspace", str(restored))
            self.assertEqual(verify.returncode, 0, verify.stderr + verify.stdout)
            self.assertEqual(self.manifest(restored), source_manifest)
            restored_session = json.loads((restored / "state" / "session_authority.json").read_text(encoding="utf-8"))["session_id"]
            self.assertNotEqual(restored_session, source_session)

    def test_restore_refuses_tampered_payload_without_partial_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.workspace(root)
            bundle, restored = root / "export", root / "restored"
            exported = self.export(source, bundle)
            self.assertEqual(exported.returncode, 0, exported.stderr + exported.stdout)
            payload = bundle / "payload" / "MEMORY.md"
            payload.write_text(payload.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")
            result = self.run_script(PORTABLE, "restore", "--input", str(bundle), "--workspace", str(restored))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("digest", (result.stdout + result.stderr).lower())
            self.assertFalse(restored.exists())

    def test_restore_refuses_nonempty_destination_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.workspace(root)
            bundle, restored = root / "export", root / "restored"
            exported = self.export(source, bundle)
            self.assertEqual(exported.returncode, 0, exported.stderr + exported.stdout)
            restored.mkdir()
            sentinel = restored / "keep.txt"
            sentinel.write_text("do not overwrite\n", encoding="utf-8")
            result = self.run_script(PORTABLE, "restore", "--input", str(bundle), "--workspace", str(restored))
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "do not overwrite\n")

    def test_restore_refuses_destination_inside_framework_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory(
            dir=ROOT, prefix=".r4-restore-inside-"
        ) as destination:
            root = Path(temp)
            source = self.workspace(root)
            bundle = root / "export"
            exported = self.export(source, bundle)
            self.assertEqual(exported.returncode, 0, exported.stderr + exported.stdout)
            result = self.run_script(PORTABLE, "restore", "--input", str(bundle), "--workspace", destination)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("framework repository", (result.stdout + result.stderr).lower())
            self.assertFalse(any(Path(destination).iterdir()))

    def test_manifest_hashes_match_payload_and_documentation_distinguishes_replication(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.workspace(root)
            bundle = root / "export"
            exported = self.export(source, bundle)
            self.assertEqual(exported.returncode, 0, exported.stderr + exported.stdout)
            self.assertIn("replicated backup: no", exported.stdout.lower())
            manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
            for item in manifest["files"]:
                data = (bundle / "payload" / item["path"]).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), item["sha256"])
                self.assertEqual(len(data), item["size"])
            text = DOC.read_text(encoding="utf-8").lower()
            self.assertIn("portable export", text)
            self.assertIn("replicated backup", text)
            self.assertIn("semantic", text)
            self.assertIn("session authority", text)
            self.assertIn("clean", text)


if __name__ == "__main__":
    unittest.main()
