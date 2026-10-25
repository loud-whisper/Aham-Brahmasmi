from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from external_sources import verify_quarantine_integrity  # noqa: E402
from scan_external import scan_tree  # noqa: E402
from third_party import ThirdPartyError, fetch_exact_source  # noqa: E402


SETUP = ROOT / "scripts" / "setup_workspace.py"


class ExternalSourceIntegrityTests(unittest.TestCase):
    def run_command(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(args, cwd=cwd or ROOT, text=True, capture_output=True, check=False)

    def create_workspace(self, root: Path) -> Path:
        workspace = root / "workspace"
        result = self.run_command(sys.executable, str(SETUP), "--workspace", str(workspace))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return workspace

    def create_upstream(self, root: Path) -> tuple[Path, str]:
        repo = root / "upstream"
        repo.mkdir()
        self.assertEqual(self.run_command("git", "init", "--quiet", cwd=repo).returncode, 0)
        self.assertEqual(self.run_command("git", "config", "user.email", "test@example.invalid", cwd=repo).returncode, 0)
        self.assertEqual(self.run_command("git", "config", "user.name", "Aham Test", cwd=repo).returncode, 0)
        (repo / "README.md").write_text("reviewed content\n", encoding="utf-8")
        self.assertEqual(self.run_command("git", "add", ".", cwd=repo).returncode, 0)
        commit = self.run_command("git", "commit", "--quiet", "-m", "fixture", cwd=repo)
        self.assertEqual(commit.returncode, 0, commit.stdout + commit.stderr)
        head = self.run_command("git", "rev-parse", "HEAD", cwd=repo)
        self.assertEqual(head.returncode, 0)
        return repo, head.stdout.strip()

    def source_entry(self, source_ref: str) -> dict:
        return {
            "id": "fixture-integrity",
            "name": "Fixture Integrity",
            "kind": "skill-collection",
            "upstream_url": "https://example.invalid/fixture-integrity",
            "source_type": "git_commit",
            "source_ref": source_ref,
            "license": "MIT",
            "license_url": "https://example.invalid/fixture-integrity/LICENSE",
            "integration": "installer",
            "local_changes": False,
            "checked_at": "2026-09-17",
            "review_status": "approved",
            "role": "test fixture",
            "default_offer": False,
            "activation": "workspace_external",
            "attribution": "Fixture attribution.",
            "notes": "Synthetic integrity test source.",
        }

    def fetch_fixture(self, root: Path) -> tuple[Path, dict]:
        workspace = self.create_workspace(root)
        upstream, head = self.create_upstream(root)
        source = self.source_entry(head)
        quarantine, _ = fetch_exact_source(workspace, source, fetch_url_override=str(upstream))
        report = scan_tree(quarantine / "source")
        self.assertEqual(report["verdict"], "PASS", report)
        return quarantine, source

    def test_clean_exact_quarantine_revalidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            quarantine, source = self.fetch_fixture(Path(temp))
            verify_quarantine_integrity(quarantine, source)

    def test_tracked_change_after_scan_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            quarantine, source = self.fetch_fixture(Path(temp))
            (quarantine / "source" / "README.md").write_text("changed after scan\n", encoding="utf-8")
            with self.assertRaises(ThirdPartyError):
                verify_quarantine_integrity(quarantine, source)

    def test_untracked_change_after_scan_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            quarantine, source = self.fetch_fixture(Path(temp))
            (quarantine / "source" / "new-file.txt").write_text("added after scan\n", encoding="utf-8")
            with self.assertRaises(ThirdPartyError):
                verify_quarantine_integrity(quarantine, source)

    def test_provenance_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            quarantine, source = self.fetch_fixture(Path(temp))
            provenance_path = quarantine / "provenance.json"
            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
            provenance["source_id"] = "different-source"
            provenance_path.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
            with self.assertRaises(ThirdPartyError):
                verify_quarantine_integrity(quarantine, source)


if __name__ == "__main__":
    unittest.main()
