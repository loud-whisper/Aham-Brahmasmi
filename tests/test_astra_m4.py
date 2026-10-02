from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from project_state import checkpoint_file_from_record
from state_io import StateError, require_managed_path
from windows_access import create_private_directory

SETUP = ROOT / "scripts" / "setup_workspace.py"
WRAP_UP = ROOT / "scripts" / "wrap_up.py"
GIT_TRANSPORT = ROOT / "scripts" / "git_transport.py"
RUNTIME_BRIDGE = ROOT / "scripts" / "runtime_bridge.py"


class AstraM4RegressionTests(unittest.TestCase):
    def run_script(self, script: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(script), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def git(self, repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            text=True,
            capture_output=True,
            check=check,
        )

    def make_workspace(self, path: Path) -> Path:
        result = self.run_script(SETUP, "--workspace", str(path))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return path

    def init_git_repo(self, repo: Path) -> None:
        repo.mkdir(parents=True, exist_ok=True)
        self.git(repo, "init", "-b", "main")
        self.git(repo, "config", "user.email", "test@example.invalid")
        self.git(repo, "config", "user.name", "Aham Test")

    def test_f8_symlinked_managed_projects_directory_cannot_redirect_writes_outside_workspace(self) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks are unavailable on this platform")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root / "workspace")
            outside = root / "outside"
            outside.mkdir()

            projects = workspace / "projects"
            shutil.rmtree(projects)
            projects.symlink_to(outside, target_is_directory=True)

            bundle = root / "bundle.json"
            bundle.write_text(
                json.dumps(
                    {
                        "operation_id": "m4-f8-symlink",
                        "project_updates": [{"project": "Escaped Project", "content": "must stay contained"}],
                        "checkpoint": {"summary": "F8 containment regression", "project": "Escaped Project"},
                    }
                ),
                encoding="utf-8",
            )

            result = self.run_script(WRAP_UP, "--workspace", str(workspace), "--bundle", str(bundle))
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(list(outside.iterdir()), [], "managed symlink redirected a durable write outside the workspace")
            self.assertEqual(list((workspace / "state" / "operations").glob("*.json")), [])

    def test_dynamic_project_leaf_symlink_is_refused_without_consuming_target(self) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks are unavailable on this platform")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root / "workspace")
            outside = root / "outside-project.md"
            outside.write_text("# Leaf Project\n\noutside sentinel\n", encoding="utf-8")
            legacy = workspace / "projects" / "Leaf-Project.md"
            legacy.symlink_to(outside)
            before = outside.read_text(encoding="utf-8")

            bundle = root / "bundle.json"
            bundle.write_text(
                json.dumps(
                    {
                        "operation_id": "m4-leaf-symlink",
                        "project_updates": [{"project": "Leaf Project", "content": "must not follow leaf symlink"}],
                        "checkpoint": {"summary": "leaf symlink containment", "project": "Leaf Project"},
                    }
                ),
                encoding="utf-8",
            )
            result = self.run_script(WRAP_UP, "--workspace", str(workspace), "--bundle", str(bundle))
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(outside.read_text(encoding="utf-8"), before)
            self.assertTrue(legacy.is_symlink(), "refusal should not migrate or consume the symlink")
            self.assertEqual(list((workspace / "state" / "operations").glob("*.json")), [])

    def test_managed_path_rejects_parent_traversal_and_absolute_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root / "workspace")
            with self.assertRaises(StateError):
                require_managed_path(workspace, "../outside.txt", label="traversal fixture")
            with self.assertRaises(StateError):
                require_managed_path(workspace, root / "outside.txt", label="absolute escape fixture")

    def test_committed_checkpoint_reference_rejects_traversal_shape(self) -> None:
        bad = {
            "kind": "checkpoint",
            "details": {"checkpoint_file": "state/checkpoints/../../outside.json"},
        }
        self.assertIsNone(checkpoint_file_from_record(bad))
        nested = {
            "kind": "wrap_up",
            "details": {"receipt": {"checkpoint_file": "state/checkpoints/nested/escape.json"}},
        }
        self.assertIsNone(checkpoint_file_from_record(nested))

    def test_f9_git_transport_refuses_unrelated_enclosing_repository_before_mutation(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("git is not available")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            parent = root / "parent"
            self.init_git_repo(parent)
            self.git(parent, "config", "user.name", "Parent Sentinel")
            self.git(parent, "config", "user.email", "parent@example.invalid")

            workspace = self.make_workspace(parent / "brain")
            before_name = self.git(parent, "config", "--local", "user.name").stdout.strip()
            before_email = self.git(parent, "config", "--local", "user.email").stdout.strip()

            result = self.run_script(
                GIT_TRANSPORT,
                "init",
                "--workspace",
                str(workspace),
                "--author-name",
                "Brain Identity",
                "--author-email",
                "brain@example.invalid",
            )

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(self.git(parent, "config", "--local", "user.name").stdout.strip(), before_name)
            self.assertEqual(self.git(parent, "config", "--local", "user.email").stdout.strip(), before_email)
            top = self.git(workspace, "rev-parse", "--show-toplevel").stdout.strip()
            self.assertEqual(Path(top).resolve(), parent.resolve(), "test setup no longer exercises an enclosing repository")

    def test_git_transport_explicitly_refuses_linked_worktree_brain(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("git is not available")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.make_workspace(root / "source")
            init = self.run_script(
                GIT_TRANSPORT,
                "init",
                "--workspace",
                str(source),
                "--author-name",
                "Aham Test",
                "--author-email",
                "test@example.invalid",
            )
            self.assertEqual(init.returncode, 0, init.stdout + init.stderr)
            snap = self.run_script(GIT_TRANSPORT, "snapshot", "--workspace", str(source), "--message", "seed")
            self.assertEqual(snap.returncode, 0, snap.stdout + snap.stderr)

            linked = root / "linked"
            added = self.git(source, "worktree", "add", "-b", "linked-test", str(linked), check=False)
            self.assertEqual(added.returncode, 0, added.stdout + added.stderr)
            status = self.run_script(GIT_TRANSPORT, "status", "--workspace", str(linked))
            self.assertNotEqual(status.returncode, 0, status.stdout + status.stderr)
            self.assertIn("linked Git worktrees are not supported", status.stderr)

    def test_f10_tracked_runtime_config_is_refused_before_private_paths_are_written(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("git is not available")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root / "workspace")
            project = root / "project"
            self.init_git_repo(project)

            aham = project / ".aham"
            create_private_directory(aham)
            config = aham / "runtime.json"
            original = '{"placeholder": "safe"}\n'
            config.write_text(original, encoding="utf-8")
            self.git(project, "add", ".aham/runtime.json")
            self.git(project, "commit", "-m", "track placeholder runtime config")
            before_status = self.git(project, "status", "--porcelain=v1", "--untracked-files=all").stdout

            result = self.run_script(
                RUNTIME_BRIDGE,
                "install",
                "--runtime",
                "local",
                "--workspace",
                str(workspace),
                "--project",
                str(project),
            )

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(config.read_text(encoding="utf-8"), original)
            self.assertNotIn(str(workspace), config.read_text(encoding="utf-8"))
            self.assertNotIn(str(project), config.read_text(encoding="utf-8"))
            after_status = self.git(project, "status", "--porcelain=v1", "--untracked-files=all").stdout
            self.assertEqual(after_status, before_status, "refusal must happen before any project mutation")

    def test_effective_git_ignore_is_verified_not_inferred_from_text(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("git is not available")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root / "workspace")
            project = root / "project"
            self.init_git_repo(project)
            aham = project / ".aham"
            create_private_directory(aham)
            ignore = aham / ".gitignore"
            original = "runtime.json\n!runtime.json\n"
            ignore.write_text(original, encoding="utf-8")

            result = self.run_script(
                RUNTIME_BRIDGE,
                "install",
                "--runtime",
                "local",
                "--workspace",
                str(workspace),
                "--project",
                str(project),
            )
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("effective Git ignore rules", result.stderr)
            self.assertFalse((aham / "runtime.json").exists())
            self.assertFalse((aham / "runtime.md").exists())
            self.assertEqual(ignore.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
