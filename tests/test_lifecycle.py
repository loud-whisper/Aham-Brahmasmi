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


class LifecycleTests(unittest.TestCase):
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

    def make_git_repo(self, root: Path) -> Path:
        repo = root / "project"
        repo.mkdir()
        self.git(repo, "init")
        self.git(repo, "config", "user.email", "test@example.invalid")
        self.git(repo, "config", "user.name", "Aham Test")
        (repo / "work.txt").write_text("one\n", encoding="utf-8")
        self.git(repo, "add", "work.txt")
        self.git(repo, "commit", "-m", "first")
        return repo

    def test_checkpoint_and_resume_without_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.make_workspace(Path(temp))
            saved = self.run_script(
                CHECKPOINT,
                "--workspace",
                str(workspace),
                "--summary",
                "Completed the first milestone",
                "--completed",
                "Created durable state",
                "--next-step",
                "Continue from here",
            )
            self.assertEqual(saved.returncode, 0, saved.stderr + saved.stdout)
            self.assertIn("CHECKPOINT SAVED", saved.stdout)
            self.assertIn("CHECKPOINT VERIFIED", saved.stdout)

            latest = json.loads((workspace / "state" / "latest_checkpoint.json").read_text(encoding="utf-8"))
            checkpoint = json.loads((workspace / latest["file"]).read_text(encoding="utf-8"))
            self.assertEqual(checkpoint["id"], latest["id"])
            self.assertEqual(checkpoint["summary"], "Completed the first milestone")

            resumed = self.run_script(RESUME, "--workspace", str(workspace))
            self.assertEqual(resumed.returncode, 0, resumed.stderr + resumed.stdout)
            self.assertIn("RESUME STATE VERIFIED", resumed.stdout)
            self.assertIn("Completed the first milestone", resumed.stdout)
            self.assertIn("Continue from here", resumed.stdout)

    def test_resume_accepts_newer_commit_on_same_branch(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("git is not available")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            repo = self.make_git_repo(root)

            saved = self.run_script(
                CHECKPOINT,
                "--workspace",
                str(workspace),
                "--repo",
                str(repo),
                "--summary",
                "Repository milestone",
            )
            self.assertEqual(saved.returncode, 0, saved.stderr + saved.stdout)
            self.assertIn("CHECKPOINT VERIFIED", saved.stdout)

            (repo / "work.txt").write_text("two\n", encoding="utf-8")
            self.git(repo, "add", "work.txt")
            self.git(repo, "commit", "-m", "second")

            resumed = self.run_script(RESUME, "--workspace", str(workspace), "--repo", str(repo))
            self.assertEqual(resumed.returncode, 0, resumed.stderr + resumed.stdout)
            self.assertIn("RESUME STATE VERIFIED", resumed.stdout)

    def test_resume_rejects_branch_mismatch(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("git is not available")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            repo = self.make_git_repo(root)

            saved = self.run_script(
                CHECKPOINT,
                "--workspace",
                str(workspace),
                "--repo",
                str(repo),
                "--summary",
                "Branch-sensitive milestone",
            )
            self.assertEqual(saved.returncode, 0, saved.stderr + saved.stdout)
            self.git(repo, "checkout", "-b", "other-branch")

            resumed = self.run_script(RESUME, "--workspace", str(workspace), "--repo", str(repo))
            self.assertNotEqual(resumed.returncode, 0)
            self.assertIn("branch mismatch", resumed.stderr.lower())

    def test_wrap_up_routes_state_and_replay_does_not_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            bundle_path = root / "bundle.json"
            bundle = {
                "session_id": "session-001",
                "durable_facts": ["The durable fact"],
                "unfinished_work": ["The unfinished task"],
                "reusable_lessons": ["The reusable lesson"],
                "project_updates": [{"project": "Example Project", "content": "Project state changed."}],
                "history": ["Finished a meaningful milestone."],
                "checkpoint": {
                    "summary": "Wrapped the test session",
                    "completed": ["Routed durable state"],
                    "next_steps": ["Start the next milestone"],
                    "project": "Example Project",
                },
            }
            bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

            wrapped = self.run_script(WRAP_UP, "--workspace", str(workspace), "--bundle", str(bundle_path))
            self.assertEqual(wrapped.returncode, 0, wrapped.stderr + wrapped.stdout)
            self.assertIn("WRAP UP COMPLETE", wrapped.stdout)
            self.assertIn("WRAP UP VERIFIED", wrapped.stdout)
            self.assertFalse((workspace / "state" / "pending_wrap_up.json").exists())
            archive = workspace / "state" / "wrapups" / "session-001.json"
            self.assertTrue(archive.is_file())

            registry = json.loads((workspace / "state" / "projects.json").read_text(encoding="utf-8"))["projects"]
            project_id = next(pid for pid, entry in registry.items() if entry["display_name"] == "Example Project")
            project_path = workspace / "projects" / f"{project_id}.md"
            memory = (workspace / "MEMORY.md").read_text(encoding="utf-8")
            todo = (workspace / "TODO.md").read_text(encoding="utf-8")
            lessons = (workspace / "LESSONS.md").read_text(encoding="utf-8")
            project = project_path.read_text(encoding="utf-8")
            self.assertEqual(memory.count("The durable fact"), 1)
            self.assertEqual(todo.count("The unfinished task"), 1)
            self.assertEqual(lessons.count("The reusable lesson"), 1)
            self.assertEqual(project.count("Project state changed."), 1)

            replay = self.run_script(WRAP_UP, "--workspace", str(workspace), "--bundle", str(bundle_path))
            self.assertEqual(replay.returncode, 0, replay.stderr + replay.stdout)
            self.assertIn("WRAP UP VERIFIED", replay.stdout)
            self.assertIn("EXISTING RECEIPT REUSED", replay.stdout)
            self.assertEqual((workspace / "MEMORY.md").read_text(encoding="utf-8").count("The durable fact"), 1)
            self.assertEqual((workspace / "TODO.md").read_text(encoding="utf-8").count("The unfinished task"), 1)
            self.assertEqual((workspace / "LESSONS.md").read_text(encoding="utf-8").count("The reusable lesson"), 1)
            self.assertEqual(project_path.read_text(encoding="utf-8").count("Project state changed."), 1)

            resumed = self.run_script(RESUME, "--workspace", str(workspace))
            self.assertEqual(resumed.returncode, 0, resumed.stderr + resumed.stdout)
            self.assertIn("Wrapped the test session", resumed.stdout)

    def test_resume_stops_for_pending_wrap_up(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            saved = self.run_script(CHECKPOINT, "--workspace", str(workspace), "--summary", "Existing milestone")
            self.assertEqual(saved.returncode, 0, saved.stderr + saved.stdout)
            (workspace / "state" / "pending_wrap_up.json").write_text("{}", encoding="utf-8")

            resumed = self.run_script(RESUME, "--workspace", str(workspace))
            self.assertNotEqual(resumed.returncode, 0)
            self.assertIn("unfinished wrap-up", resumed.stderr.lower())

    def test_memory_contract_keeps_mempalace_optional(self) -> None:
        memory = json.loads((ROOT / "core" / "memory.json").read_text(encoding="utf-8"))
        providers = {item["id"]: item for item in memory["optional_backends"]}
        self.assertFalse(providers["mempalace"]["required"])
        self.assertEqual(providers["mempalace"]["failure_policy"], "continue_without_semantic_memory")
        self.assertTrue(memory["default_backend"]["required"])


if __name__ == "__main__":
    unittest.main()
