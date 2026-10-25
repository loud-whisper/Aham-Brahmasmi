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
GIT_TRANSPORT = ROOT / "scripts" / "git_transport.py"


@unittest.skipIf(shutil.which("git") is None, "git is not available")
class GitTransportTests(unittest.TestCase):
    def run_command(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args,
            cwd=cwd or ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def run_tool(self, *args: str) -> subprocess.CompletedProcess[str]:
        return self.run_command(sys.executable, str(GIT_TRANSPORT), *args)

    def git(self, workspace: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return self.run_command("git", "-C", str(workspace), *args)

    def make_workspace(self, root: Path) -> Path:
        workspace = root / "workspace"
        result = self.run_command(sys.executable, str(SETUP), "--workspace", str(workspace))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return workspace

    def init_transport(self, workspace: Path) -> None:
        result = self.run_tool(
            "init",
            "--workspace",
            str(workspace),
            "--author-name",
            "Aham Test",
            "--author-email",
            "test@example.invalid",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Remote required: no", result.stdout)
        self.assertIn("Git hooks during transport commits: disabled", result.stdout)

    def test_status_is_nonblocking_before_git_initialization(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.make_workspace(Path(temp))
            result = self.run_tool("status", "--workspace", str(workspace))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Initialized: no", result.stdout)
            self.assertIn("Remote required: no", result.stdout)

    def test_snapshot_versions_only_durable_allowlist_and_never_requires_remote(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.make_workspace(Path(temp))
            self.init_transport(workspace)

            (workspace / "MEMORY.md").write_text("# Memory\n\nDurable fixture.\n", encoding="utf-8")
            (workspace / "external" / "do-not-version.txt").write_text("external fixture\n", encoding="utf-8")
            (workspace / "state" / "quarantine" / "do-not-version.txt").write_text(
                "quarantine fixture\n", encoding="utf-8"
            )
            (workspace / "state" / "pending_wrap_up.json").write_text("{\"fixture\": true}\n", encoding="utf-8")

            snap = self.run_tool(
                "snapshot",
                "--workspace",
                str(workspace),
                "--message",
                "First durable snapshot",
            )
            self.assertEqual(snap.returncode, 0, snap.stdout + snap.stderr)
            self.assertIn("GIT SNAPSHOT SAVED", snap.stdout)
            self.assertIn("Remote push: not performed", snap.stdout)
            self.assertIn("Git hooks: not executed", snap.stdout)

            tracked = self.git(workspace, "ls-files")
            self.assertEqual(tracked.returncode, 0, tracked.stdout + tracked.stderr)
            tracked_paths = set(tracked.stdout.splitlines())
            self.assertIn("BRAIN.json", tracked_paths)
            self.assertIn("MEMORY.md", tracked_paths)
            self.assertNotIn("external/do-not-version.txt", tracked_paths)
            self.assertNotIn("state/quarantine/do-not-version.txt", tracked_paths)
            self.assertNotIn("state/pending_wrap_up.json", tracked_paths)

            remotes = self.git(workspace, "remote")
            self.assertEqual(remotes.returncode, 0)
            self.assertEqual(remotes.stdout.strip(), "")

            status = self.run_tool("status", "--workspace", str(workspace))
            self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
            self.assertIn("Configured remotes: 0", status.stdout)
            self.assertIn("Durable changes: 0", status.stdout)

    def test_transport_commit_does_not_execute_configured_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            self.init_transport(workspace)

            hooks = workspace / ".git" / "hooks"
            hooks.mkdir(parents=True, exist_ok=True)
            marker = root / "hook-ran.txt"
            hook = hooks / "pre-commit"
            hook.write_text(
                "#!/bin/sh\n"
                f"touch \"{marker}\"\n"
                "exit 1\n",
                encoding="utf-8",
            )
            hook.chmod(0o755)
            configured = self.git(workspace, "config", "--local", "core.hooksPath", str(hooks))
            self.assertEqual(configured.returncode, 0, configured.stdout + configured.stderr)

            snap = self.run_tool("snapshot", "--workspace", str(workspace), "--message", "Hook isolation fixture")
            self.assertEqual(snap.returncode, 0, snap.stdout + snap.stderr)
            self.assertFalse(marker.exists(), "configured pre-commit hook unexpectedly ran")

    def test_missing_identity_fails_before_transport_stages_anything(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.make_workspace(Path(temp))
            initialized = self.run_tool("init", "--workspace", str(workspace))
            self.assertEqual(initialized.returncode, 0, initialized.stdout + initialized.stderr)
            self.git(workspace, "config", "--local", "--unset-all", "user.name")
            self.git(workspace, "config", "--local", "--unset-all", "user.email")

            environment_name = self.git(workspace, "config", "--global", "user.name").stdout.strip()
            environment_email = self.git(workspace, "config", "--global", "user.email").stdout.strip()
            if environment_name or environment_email:
                self.skipTest("test environment has a global Git identity")

            blocked = self.run_tool("snapshot", "--workspace", str(workspace), "--message", "Needs identity")
            self.assertNotEqual(blocked.returncode, 0)
            self.assertIn("identity is not configured", blocked.stderr)
            staged = self.git(workspace, "diff", "--cached", "--name-only")
            self.assertEqual(staged.returncode, 0)
            self.assertEqual(staged.stdout.strip(), "")

    def test_second_snapshot_versions_changed_durable_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.make_workspace(Path(temp))
            self.init_transport(workspace)
            first = self.run_tool("snapshot", "--workspace", str(workspace), "--message", "Initial Brain state")
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            first_head = self.git(workspace, "rev-parse", "HEAD").stdout.strip()

            with (workspace / "TODO.md").open("a", encoding="utf-8") as handle:
                handle.write("\n- Durable next action\n")

            second = self.run_tool("snapshot", "--workspace", str(workspace), "--message", "Update tasks")
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            second_head = self.git(workspace, "rev-parse", "HEAD").stdout.strip()
            self.assertNotEqual(first_head, second_head)

            show = self.git(workspace, "show", "--name-only", "--format=", "HEAD")
            self.assertEqual(show.returncode, 0)
            self.assertIn("TODO.md", show.stdout.splitlines())

    def test_unrelated_prestaged_path_blocks_snapshot_without_committing_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.make_workspace(Path(temp))
            self.init_transport(workspace)
            initial = self.run_tool("snapshot", "--workspace", str(workspace), "--message", "Initial Brain state")
            self.assertEqual(initial.returncode, 0, initial.stdout + initial.stderr)
            head_before = self.git(workspace, "rev-parse", "HEAD").stdout.strip()

            excluded = workspace / "external" / "manual-stage.txt"
            excluded.write_text("must not be committed by Brain snapshot\n", encoding="utf-8")
            staged = self.git(workspace, "add", "external/manual-stage.txt")
            self.assertEqual(staged.returncode, 0, staged.stdout + staged.stderr)
            with (workspace / "MEMORY.md").open("a", encoding="utf-8") as handle:
                handle.write("\nDurable change waiting to be committed.\n")

            blocked = self.run_tool("snapshot", "--workspace", str(workspace), "--message", "Should be blocked")
            self.assertNotEqual(blocked.returncode, 0)
            self.assertIn("unrelated paths are already staged", blocked.stderr)
            self.assertIn("external/manual-stage.txt", blocked.stderr)
            head_after = self.git(workspace, "rev-parse", "HEAD").stdout.strip()
            self.assertEqual(head_before, head_after)

    def test_contract_explicitly_excludes_transient_and_third_party_trees(self) -> None:
        contract = json.loads((ROOT / "core" / "git_transport.json").read_text(encoding="utf-8"))
        durable = set(contract["durable_paths"])
        excluded = set(contract["excluded_paths"])
        self.assertIn("projects/", durable)
        self.assertIn("state/checkpoints/", durable)
        self.assertIn("external/", excluded)
        self.assertIn("state/quarantine/", excluded)
        self.assertIn("state/pending_wrap_up.json", excluded)
        self.assertTrue(durable.isdisjoint(excluded))

    def test_memory_contract_points_to_optional_host_neutral_git_transport(self) -> None:
        memory = json.loads((ROOT / "core" / "memory.json").read_text(encoding="utf-8"))
        providers = {item["id"]: item for item in memory["optional_backends"]}
        git = providers["git"]
        self.assertFalse(git["required"])
        self.assertFalse(git["remote_required"])
        self.assertFalse(git["automatic_push"])
        self.assertEqual(git["contract"], "core/git_transport.json")
        self.assertEqual(git["failure_policy"], "continue_with_local_verified_files")


if __name__ == "__main__":
    unittest.main()
