from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "scripts" / "setup_workspace.py"
CHECKPOINT = ROOT / "scripts" / "checkpoint.py"
RESUME = ROOT / "scripts" / "resume.py"
WRAP_UP = ROOT / "scripts" / "wrap_up.py"


class AstraM3RegressionTests(unittest.TestCase):
    def run_script(self, script: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(script), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def make_workspace(self, root: Path) -> Path:
        workspace = root / "workspace"
        result = self.run_script(SETUP, "--workspace", str(workspace))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return workspace

    def git(self, repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            text=True,
            capture_output=True,
            check=True,
        )

    def make_git_repo(self, root: Path, name: str = "project") -> Path:
        repo = root / name
        repo.mkdir()
        self.git(repo, "init", "-b", "main")
        self.git(repo, "config", "user.email", "test@example.invalid")
        self.git(repo, "config", "user.name", "Aham Test")
        (repo / "work.txt").write_text("one\n", encoding="utf-8")
        self.git(repo, "add", "work.txt")
        self.git(repo, "commit", "-m", "first")
        return repo

    def write_wrap_bundle(self, path: Path, operation_id: str, project_name: str, content: str) -> None:
        path.write_text(
            json.dumps(
                {
                    "operation_id": operation_id,
                    "project_updates": [{"project": project_name, "content": content}],
                    "checkpoint": {"summary": f"checkpoint for {project_name}", "project": project_name},
                }
            ),
            encoding="utf-8",
        )

    def project_registry(self, workspace: Path) -> dict:
        return json.loads((workspace / "state" / "projects.json").read_text(encoding="utf-8"))

    def test_f7_distinct_names_that_slug_identically_get_distinct_project_ids_and_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            first = root / "first.json"
            second = root / "second.json"
            self.write_wrap_bundle(first, "project-a", "Alpha Project", "first project state")
            self.write_wrap_bundle(second, "project-b", "Alpha@Project", "second project state")

            one = self.run_script(WRAP_UP, "--workspace", str(workspace), "--bundle", str(first))
            two = self.run_script(WRAP_UP, "--workspace", str(workspace), "--bundle", str(second))
            self.assertEqual(one.returncode, 0, one.stderr + one.stdout)
            self.assertEqual(two.returncode, 0, two.stderr + two.stdout)

            registry = self.project_registry(workspace)
            projects = registry["projects"]
            self.assertEqual(len(projects), 2)
            by_name = {entry["display_name"]: project_id for project_id, entry in projects.items()}
            self.assertNotEqual(by_name["Alpha Project"], by_name["Alpha@Project"])
            first_file = workspace / "projects" / f"{by_name['Alpha Project']}.md"
            second_file = workspace / "projects" / f"{by_name['Alpha@Project']}.md"
            self.assertTrue(first_file.is_file())
            self.assertTrue(second_file.is_file())
            self.assertIn("first project state", first_file.read_text(encoding="utf-8"))
            self.assertNotIn("second project state", first_file.read_text(encoding="utf-8"))
            self.assertIn("second project state", second_file.read_text(encoding="utf-8"))

    def test_legacy_project_migration_collision_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            # Both display names collapse to Alpha-Project under the old slug scheme.
            legacy = workspace / "projects" / "Alpha-Project.md"
            legacy.write_text("# Alpha@Project\n\nlegacy state\n", encoding="utf-8")
            bundle = root / "bundle.json"
            self.write_wrap_bundle(bundle, "migration-collision", "Alpha Project", "new state")

            result = self.run_script(WRAP_UP, "--workspace", str(workspace), "--bundle", str(bundle))
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("migration collision", result.stderr.lower())
            self.assertEqual(list((workspace / "state" / "operations").glob("*.json")), [])
            self.assertIn("legacy state", legacy.read_text(encoding="utf-8"))

    def test_f5_corrupt_newest_checkpoint_is_reported_as_gap_not_silent_verified_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            first = self.run_script(CHECKPOINT, "--workspace", str(workspace), "--summary", "older state")
            second = self.run_script(CHECKPOINT, "--workspace", str(workspace), "--summary", "newer state")
            self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
            self.assertEqual(second.returncode, 0, second.stderr + second.stdout)

            operations = sorted((workspace / "state" / "operations").glob("*.json"))
            self.assertEqual(len(operations), 2)
            newest_record = json.loads(operations[-1].read_text(encoding="utf-8"))
            checkpoint_rel = newest_record["details"]["checkpoint_file"]
            (workspace / checkpoint_rel).write_text("{corrupt", encoding="utf-8")

            resumed = self.run_script(RESUME, "--workspace", str(workspace))
            self.assertNotEqual(resumed.returncode, 0, resumed.stdout + resumed.stderr)
            combined = resumed.stdout + resumed.stderr
            self.assertNotIn("RESUME STATE VERIFIED", combined)
            self.assertIn("DEGRADED", combined.upper())
            self.assertIn("Committed revision: 2", combined)
            self.assertIn("Recovered revision: 1", combined)
            self.assertIn("continuity gap", combined.lower())

    def test_project_heads_are_scoped_by_stable_project_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            first = root / "first.json"
            second = root / "second.json"
            self.write_wrap_bundle(first, "head-a", "Project A", "A state")
            self.write_wrap_bundle(second, "head-b", "Project B", "B state")
            self.assertEqual(self.run_script(WRAP_UP, "--workspace", str(workspace), "--bundle", str(first)).returncode, 0)
            self.assertEqual(self.run_script(WRAP_UP, "--workspace", str(workspace), "--bundle", str(second)).returncode, 0)

            registry = self.project_registry(workspace)["projects"]
            by_name = {entry["display_name"]: project_id for project_id, entry in registry.items()}
            for name, expected_revision in (("Project A", 1), ("Project B", 2)):
                project_id = by_name[name]
                head_path = workspace / "state" / "project_heads" / f"{project_id}.json"
                self.assertTrue(head_path.is_file())
                head = json.loads(head_path.read_text(encoding="utf-8"))
                self.assertEqual(head["project_id"], project_id)
                self.assertEqual(head["revision"], expected_revision)

            resume_a = self.run_script(RESUME, "--workspace", str(workspace), "--project-id", by_name["Project A"])
            resume_b = self.run_script(RESUME, "--workspace", str(workspace), "--project-id", by_name["Project B"])
            self.assertEqual(resume_a.returncode, 0, resume_a.stderr + resume_a.stdout)
            self.assertEqual(resume_b.returncode, 0, resume_b.stderr + resume_b.stdout)
            self.assertIn("Revision: 1", resume_a.stdout)
            self.assertIn("Revision: 2", resume_b.stdout)

    def test_wrong_clone_with_same_commit_and_branch_is_not_fully_verified(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("git is not available")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            repo = self.make_git_repo(root, "original")
            saved = self.run_script(
                CHECKPOINT,
                "--workspace",
                str(workspace),
                "--repo",
                str(repo),
                "--project",
                "Bound Project",
                "--summary",
                "bound checkpoint",
            )
            self.assertEqual(saved.returncode, 0, saved.stderr + saved.stdout)

            clone = root / "clone"
            subprocess.run(["git", "clone", "-q", str(repo), str(clone)], check=True)
            resumed = self.run_script(RESUME, "--workspace", str(workspace), "--repo", str(clone))
            self.assertNotEqual(resumed.returncode, 0, resumed.stdout + resumed.stderr)
            self.assertNotIn("RESUME STATE VERIFIED", resumed.stdout + resumed.stderr)
            self.assertIn("repository identity", (resumed.stdout + resumed.stderr).lower())

    def test_dirty_or_untracked_repository_state_is_outside_verified_scope(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("git is not available")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            repo = self.make_git_repo(root)
            (repo / "untracked.txt").write_text("not committed\n", encoding="utf-8")

            saved = self.run_script(
                CHECKPOINT,
                "--workspace",
                str(workspace),
                "--repo",
                str(repo),
                "--summary",
                "checkpoint with untracked work",
            )
            self.assertEqual(saved.returncode, 0, saved.stderr + saved.stdout)
            resumed = self.run_script(RESUME, "--workspace", str(workspace), "--repo", str(repo))
            combined = resumed.stdout + resumed.stderr
            self.assertNotEqual(resumed.returncode, 0, combined)
            self.assertNotIn("RESUME STATE VERIFIED", combined)
            self.assertIn("DEGRADED", combined.upper())
            self.assertIn("untracked", combined.lower())
            self.assertIn("unsaved editor buffers", combined.lower())

    def test_resume_reports_exact_committed_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            first = self.run_script(CHECKPOINT, "--workspace", str(workspace), "--summary", "revision one")
            second = self.run_script(CHECKPOINT, "--workspace", str(workspace), "--summary", "revision two")
            self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
            self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
            resumed = self.run_script(RESUME, "--workspace", str(workspace))
            self.assertEqual(resumed.returncode, 0, resumed.stderr + resumed.stdout)
            self.assertIn("Revision: 2", resumed.stdout)


if __name__ == "__main__":
    unittest.main()
