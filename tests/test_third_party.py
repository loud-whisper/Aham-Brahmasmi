from __future__ import annotations

import copy
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

from scan_external import scan_tree  # noqa: E402
from third_party import (  # noqa: E402
    ThirdPartyError,
    activate_source,
    fetch_exact_source,
    load_registry,
    read_installed_manifest,
    validate_registry,
)


SETUP = ROOT / "scripts" / "setup_workspace.py"


class ThirdPartyTests(unittest.TestCase):
    def run_command(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(args, cwd=cwd or ROOT, text=True, capture_output=True, check=False)

    def create_workspace(self, root: Path) -> Path:
        workspace = root / "workspace"
        result = self.run_command(sys.executable, str(SETUP), "--workspace", str(workspace))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return workspace

    def create_git_repo(self, root: Path, files: dict[str, str]) -> tuple[Path, str]:
        repo = root / "upstream"
        repo.mkdir()
        self.assertEqual(self.run_command("git", "init", "--quiet", cwd=repo).returncode, 0)
        self.assertEqual(self.run_command("git", "config", "user.email", "test@example.invalid", cwd=repo).returncode, 0)
        self.assertEqual(self.run_command("git", "config", "user.name", "Aham Test", cwd=repo).returncode, 0)
        for relative, content in files.items():
            path = repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        self.assertEqual(self.run_command("git", "add", ".", cwd=repo).returncode, 0)
        commit = self.run_command("git", "commit", "--quiet", "-m", "fixture", cwd=repo)
        self.assertEqual(commit.returncode, 0, commit.stdout + commit.stderr)
        head = self.run_command("git", "rev-parse", "HEAD", cwd=repo)
        self.assertEqual(head.returncode, 0)
        return repo, head.stdout.strip()

    def installer_entry(self, source_ref: str) -> dict:
        return {
            "id": "fixture-skills",
            "name": "Fixture Skills",
            "kind": "skill-collection",
            "upstream_url": "https://example.invalid/fixture-skills",
            "source_type": "git_commit",
            "source_ref": source_ref,
            "license": "MIT",
            "license_url": "https://example.invalid/fixture-skills/LICENSE",
            "integration": "installer",
            "local_changes": False,
            "checked_at": "2026-09-17",
            "review_status": "approved",
            "role": "test fixture",
            "default_offer": False,
            "activation": "workspace_external",
            "attribution": "Fixture source attribution.",
            "notes": "Synthetic test source.",
        }

    def test_public_registry_satisfies_complete_validator(self) -> None:
        registry = load_registry()
        self.assertEqual(validate_registry(registry), [])
        ids = {source["id"] for source in registry["sources"]}
        self.assertIn("mempalace", ids)
        self.assertIn("superpowers", ids)
        for source in registry["sources"]:
            self.assertEqual(len(source["source_ref"]), 40)
            self.assertTrue(source["upstream_url"].startswith("https://"))
            self.assertTrue(source["license_url"].startswith("https://"))
            self.assertTrue(source["attribution"])

    def test_local_adaptation_requires_provenance_metadata(self) -> None:
        registry = load_registry()
        changed = copy.deepcopy(registry)
        changed["sources"][0]["local_changes"] = True
        errors = validate_registry(changed)
        self.assertTrue(any("local_adaptation" in error for error in errors))

    def test_default_offers_are_approved_installers(self) -> None:
        registry = load_registry()
        defaults = [source for source in registry["sources"] if source["default_offer"]]
        self.assertTrue(defaults)
        for source in defaults:
            self.assertEqual(source["review_status"], "approved")
            self.assertEqual(source["integration"], "installer")
            self.assertEqual(source["activation"], "workspace_external")

    def test_exact_commit_is_quarantined_scanned_and_activated(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.create_workspace(root)
            upstream, head = self.create_git_repo(root, {"README.md": "safe fixture\n"})
            source = self.installer_entry(head)

            quarantine, verified = fetch_exact_source(
                workspace,
                source,
                fetch_url_override=str(upstream),
            )
            self.assertEqual(verified, head)
            self.assertFalse((workspace / "external" / source["id"]).exists())

            report = scan_tree(quarantine / "source")
            self.assertEqual(report["verdict"], "PASS", report)
            destination = activate_source(workspace, source, quarantine, report)

            self.assertTrue((destination / "README.md").is_file())
            installed_head = self.run_command("git", "rev-parse", "HEAD", cwd=destination)
            self.assertEqual(installed_head.returncode, 0)
            self.assertEqual(installed_head.stdout.strip(), head)
            manifest = read_installed_manifest(workspace)
            self.assertEqual(manifest["sources"][source["id"]]["source_ref"], head)
            self.assertEqual(manifest["sources"][source["id"]]["scan_verdict"], "PASS")

    def test_failed_scan_cannot_replace_existing_active_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.create_workspace(root)
            upstream, first_head = self.create_git_repo(root, {"README.md": "known good\n"})
            first = self.installer_entry(first_head)
            quarantine, _ = fetch_exact_source(workspace, first, fetch_url_override=str(upstream))
            first_report = scan_tree(quarantine / "source")
            self.assertEqual(first_report["verdict"], "PASS")
            active = activate_source(workspace, first, quarantine, first_report)
            self.assertEqual((active / "README.md").read_text(encoding="utf-8"), "known good\n")

            suspicious = upstream / "suspicious.txt"
            suspicious.write_text("-----" + "BEGIN " + "PRIVATE KEY" + "-----\nfixture\n", encoding="utf-8")
            self.assertEqual(self.run_command("git", "add", ".", cwd=upstream).returncode, 0)
            commit = self.run_command("git", "commit", "--quiet", "-m", "suspicious", cwd=upstream)
            self.assertEqual(commit.returncode, 0, commit.stdout + commit.stderr)
            head_result = self.run_command("git", "rev-parse", "HEAD", cwd=upstream)
            second = self.installer_entry(head_result.stdout.strip())

            second_quarantine, _ = fetch_exact_source(workspace, second, fetch_url_override=str(upstream))
            second_report = scan_tree(second_quarantine / "source")
            self.assertEqual(second_report["verdict"], "FAIL")
            with self.assertRaises(ThirdPartyError):
                activate_source(workspace, second, second_quarantine, second_report, replace=True)

            self.assertEqual((active / "README.md").read_text(encoding="utf-8"), "known good\n")
            manifest = read_installed_manifest(workspace)
            self.assertEqual(manifest["sources"][first["id"]]["source_ref"], first_head)

    def test_scanner_rejects_symlink_that_escapes_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            outside = root / "outside.txt"
            outside.write_text("outside\n", encoding="utf-8")
            (source / "escape").symlink_to(outside)
            report = scan_tree(source)
            self.assertEqual(report["verdict"], "FAIL")
            self.assertTrue(any("escapes" in finding["message"] for finding in report["findings"]))


if __name__ == "__main__":
    unittest.main()
