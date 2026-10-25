from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROVENANCE = ROOT / "scripts" / "provenance.py"


@unittest.skipIf(shutil.which("git") is None, "git is not available")
class ProvenanceTests(unittest.TestCase):
    def run_tool(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(PROVENANCE), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def git(self, repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            text=True,
            capture_output=True,
            check=True,
        )

    def make_repo(self, root: Path) -> Path:
        repo = root / "source"
        repo.mkdir()
        self.git(repo, "init")
        self.git(repo, "config", "user.email", "test@example.invalid")
        self.git(repo, "config", "user.name", "Aham Test")
        (repo / "work.txt").write_text("reviewed source tree\n", encoding="utf-8")
        self.git(repo, "add", "work.txt")
        self.git(repo, "commit", "-m", "reviewed state")
        return repo

    def test_create_and_verify_commitment_without_exposing_secret(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = self.make_repo(root)
            secret = root / "secret.bin"
            secret_bytes = b"correct horse battery staple plus release provenance secret"
            secret.write_bytes(secret_bytes)
            output = root / "commitment.json"

            created = self.run_tool(
                "create",
                "--secret-file",
                str(secret),
                "--repo",
                str(repo),
                "--output",
                str(output),
            )
            self.assertEqual(created.returncode, 0, created.stdout + created.stderr)
            self.assertIn("PROVENANCE COMMITMENT CREATED", created.stdout)
            self.assertNotIn(secret_bytes.decode("utf-8"), created.stdout)
            value = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(value["format"], "aham-brahmasmi-provenance-commitment")
            self.assertEqual(value["hash_algorithm"], "SHA-256")
            self.assertEqual(len(value["tree_sha"]), 40)
            self.assertEqual(len(value["commitment"]), 64)
            self.assertNotIn("secret", value)

            verified = self.run_tool(
                "verify",
                "--secret-file",
                str(secret),
                "--commitment-file",
                str(output),
                "--repo",
                str(repo),
            )
            self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
            self.assertIn("PROVENANCE VERIFIED", verified.stdout)

    def test_wrong_secret_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = self.make_repo(root)
            secret = root / "secret.bin"
            secret.write_bytes(b"a" * 40)
            wrong = root / "wrong.bin"
            wrong.write_bytes(b"b" * 40)
            output = root / "commitment.json"
            self.assertEqual(
                self.run_tool(
                    "create",
                    "--secret-file",
                    str(secret),
                    "--repo",
                    str(repo),
                    "--output",
                    str(output),
                ).returncode,
                0,
            )
            verified = self.run_tool(
                "verify",
                "--secret-file",
                str(wrong),
                "--commitment-file",
                str(output),
            )
            self.assertNotEqual(verified.returncode, 0)
            self.assertIn("does not match", verified.stderr)

    def test_commitment_is_bound_to_exact_git_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = self.make_repo(root)
            secret = root / "secret.bin"
            secret.write_bytes(b"c" * 48)
            first = root / "first.json"
            self.assertEqual(
                self.run_tool(
                    "create",
                    "--secret-file",
                    str(secret),
                    "--repo",
                    str(repo),
                    "--output",
                    str(first),
                ).returncode,
                0,
            )
            first_value = json.loads(first.read_text(encoding="utf-8"))

            (repo / "work.txt").write_text("changed source tree\n", encoding="utf-8")
            self.git(repo, "add", "work.txt")
            self.git(repo, "commit", "-m", "changed state")
            second = root / "second.json"
            self.assertEqual(
                self.run_tool(
                    "create",
                    "--secret-file",
                    str(secret),
                    "--repo",
                    str(repo),
                    "--output",
                    str(second),
                ).returncode,
                0,
            )
            second_value = json.loads(second.read_text(encoding="utf-8"))
            self.assertNotEqual(first_value["tree_sha"], second_value["tree_sha"])
            self.assertNotEqual(first_value["commitment"], second_value["commitment"])

    def test_short_secret_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = self.make_repo(root)
            secret = root / "secret.bin"
            secret.write_bytes(b"too short")
            result = self.run_tool(
                "create",
                "--secret-file",
                str(secret),
                "--repo",
                str(repo),
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("at least 32 bytes", result.stderr)

    def test_create_refuses_to_overwrite_public_commitment(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = self.make_repo(root)
            secret = root / "secret.bin"
            secret.write_bytes(b"d" * 48)
            output = root / "commitment.json"
            output.write_text("keep me\n", encoding="utf-8")
            result = self.run_tool(
                "create",
                "--secret-file",
                str(secret),
                "--repo",
                str(repo),
                "--output",
                str(output),
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("refusing to overwrite", result.stderr)
            self.assertEqual(output.read_text(encoding="utf-8"), "keep me\n")


if __name__ == "__main__":
    unittest.main()
