"""Synthetic blast-radius cases. Classification never executes the input."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class ClassifierTests(unittest.TestCase):
    def setUp(self):
        import command_guard_policy as policy
        self.policy = policy
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name).resolve() / "project"
        self.project.mkdir()
        (self.project / "small.txt").write_text("abc", encoding="utf-8")

    def classify(self, command, **kwargs):
        return self.policy.classify(command, self.project, self.project, **kwargs)

    def test_known_inspection_is_allowed(self):
        for command in ("pwd", "ls -la", "cat small.txt", "git status --short", "git diff --stat"):
            with self.subTest(command=command):
                self.assertEqual(self.classify(command).tier, "allow")

    def test_small_literal_change_asks_with_effect_and_undo(self):
        for command in ("rm -- small.txt", "mv small.txt other.txt", "cp small.txt copy.txt", "chmod 600 small.txt", "truncate -s 0 small.txt"):
            with self.subTest(command=command):
                result = self.classify(command)
                self.assertEqual(result.tier, "ask")
                self.assertTrue(result.effect)
                self.assertTrue(result.undo)
                self.assertGreaterEqual(result.bytes, 3)
                self.assertTrue(result.snapshot)

    def test_byte_limit_including_equality_requires_user(self):
        for size in (3, 2):
            self.assertEqual(self.classify("rm small.txt", limits=self.policy.Limits(size, 100)).tier, "user_runs")
        self.assertEqual(self.classify("rm small.txt", limits=self.policy.Limits(4, 100)).tier, "ask")

    def test_entry_limit_including_equality_requires_user(self):
        folder = self.project / "build"
        folder.mkdir()
        (folder / "one").write_text("")
        (folder / "two").write_text("")
        self.assertEqual(self.classify("rm -rf build", limits=self.policy.Limits(100, 3)).tier, "user_runs")
        self.assertEqual(self.classify("rm -rf build", limits=self.policy.Limits(100, 4)).tier, "ask")

    def test_unmeasurable_or_indirect_commands_require_user(self):
        commands = (
            'rm "$TARGET"', "printf x | xargs rm", "rm *.txt", "rm `pwd`", "rm $(pwd)",
            "rm small.txt; pwd", "rm small.txt && pwd", "rm small.txt\npwd", "rm small.txt &",
            "rm < list", "echo x > small.txt", "sh -c 'rm small.txt'", "python -c 'pass'",
            "env rm small.txt", "sudo rm small.txt", "command rm small.txt", "./cleanup.sh",
            "find . -delete", "find . -exec rm {} +", "sed -i s/a/b/ small.txt",
            "unknown-program small.txt", "rm -f missing", "rm -rf --files0-from=list", "rm 'unterminated",
            "git -c alias.wipe='!rm small.txt' wipe", "git diff --output=small.txt",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(self.classify(command).tier, "user_runs")

    def test_hard_user_tier(self):
        for command in (
            "rm -rf /", "rm -rf /tmp", "rm -rf .", "rm -rf ..", "rm /etc/example",
            "dd if=/dev/zero of=small.txt", "mkfs.ext4 small.txt", "umount small.txt",
            "parted small.txt rm 1", "docker volume rm example", "docker system prune --volumes",
            "podman volume prune", "psql -c 'DROP DATABASE example'", "sqlite3 db 'DELETE FROM example'",
            "git push --force origin main", "git push origin :main", "git push origin --delete main",
            "ssh example.invalid 'rm small.txt'", "rsync --delete ./ example.invalid:target",
        ):
            with self.subTest(command=command):
                self.assertEqual(self.classify(command).tier, "user_runs")

    def test_large_sparse_file_uses_logical_size(self):
        with (self.project / "large").open("wb") as handle:
            handle.truncate(1_000_000_000)
        self.assertEqual(self.classify("rm large").tier, "user_runs")

    def test_invalid_limits_are_not_accepted(self):
        for args in ((0, 10), (-1, 10), (True, 10), (100, 0)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.policy.Limits(*args)

    @unittest.skipIf(os.name == "nt", "POSIX link boundary")
    def test_links_cannot_redirect_or_expand_measurement(self):
        (self.project / "link").symlink_to(self.project / "small.txt")
        self.assertEqual(self.classify("rm link").tier, "user_runs")
        os.link(self.project / "small.txt", self.project / "alias")
        self.assertEqual(self.classify("rm small.txt").tier, "user_runs")

    def test_overlapping_operands_and_project_escape_require_user(self):
        (self.project / "build").mkdir()
        (self.project / "build" / "one").write_text("a")
        for command in ("rm -rf build build/one", "rm ../outside", "mv small.txt .", "cp small.txt ."):
            self.assertEqual(self.classify(command).tier, "user_runs")


class HookTests(unittest.TestCase):
    def setUp(self):
        import command_guard as guard
        from install_command_guard import install
        self.guard = guard
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name).resolve() / "project"
        self.project.mkdir()
        (self.project / "small.txt").write_text("abc")
        install(self.project, "wrapper")

    def payload(self, runtime, command):
        return {"hook_event_name": "BeforeTool" if runtime == "gemini" else "PreToolUse",
                "session_id": "synthetic-session", "cwd": str(self.project),
                "tool_name": "run_shell_command" if runtime == "gemini" else "Bash",
                "tool_input": {"command": command}}

    def test_every_tool_output_for_every_tier(self):
        for runtime in ("claude", "codex", "gemini"):
            for command, tier in (("pwd", "allow"), ("rm small.txt", "ask"), ("rm -rf /", "user_runs")):
                with self.subTest(runtime=runtime, tier=tier):
                    output = self.guard.evaluate(runtime, self.payload(runtime, command), self.project)
                    if runtime == "gemini":
                        self.assertEqual(output["decision"], "allow" if tier == "allow" else "deny")
                        if tier != "allow":
                            self.assertTrue(output["reason"])
                    else:
                        expected = "allow" if tier == "allow" else "ask" if runtime == "claude" and tier == "ask" else "deny"
                        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], expected)
                        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "PreToolUse")
                    self.assertNotIn("continue", output)
                    self.assertNotIn("stopReason", output)

    def test_tier_two_requires_logged_exact_single_use_approval(self):
        payload = self.payload("codex", "rm small.txt")
        self.guard.approve(self.project, "codex", "synthetic-session", "rm small.txt", self.project,
                           "yes", "Restore from the verified test backup")
        changed = self.payload("codex", "rm -- small.txt")
        self.assertEqual(self.guard.evaluate("codex", changed, self.project)["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(self.guard.evaluate("codex", payload, self.project)["hookSpecificOutput"]["permissionDecision"], "allow")
        self.assertEqual(self.guard.evaluate("codex", payload, self.project)["hookSpecificOutput"]["permissionDecision"], "deny")
        from command_guard_store import events
        self.assertIn("approved", [row["event"] for row in events(self.project)])
        self.assertIn("consumed", [row["event"] for row in events(self.project)])

    def test_no_approval_can_unlock_tier_three(self):
        for command in ("rm -rf /", "rm $TARGET", "ssh example.invalid rm small.txt"):
            with self.assertRaises(ValueError):
                self.guard.approve(self.project, "codex", "synthetic-session", command, self.project, "yes", "backup")

    def test_approval_does_not_survive_target_drift_or_growth(self):
        self.guard.approve(self.project, "gemini", "synthetic-session", "rm small.txt", self.project, "yes", "backup")
        (self.project / "small.txt").write_text("changed")
        self.assertEqual(self.guard.evaluate("gemini", self.payload("gemini", "rm small.txt"), self.project)["decision"], "deny")

    def test_malformed_hook_input_denies_in_correct_format(self):
        for runtime in ("claude", "codex", "gemini"):
            for payload in ({}, {"tool_name": "Bash", "tool_input": {"command": ["rm", "small.txt"]}}):
                result = self.guard.evaluate(runtime, payload, self.project)
                decision = result["decision"] if runtime == "gemini" else result["hookSpecificOutput"]["permissionDecision"]
                self.assertEqual(decision, "deny")

    @unittest.skipIf(os.name == "nt", "POSIX literal argv execution")
    def test_wrapper_refuses_then_executes_only_after_approval(self):
        base = [sys.executable, str(ROOT / "scripts" / "command_guard.py"), "run", "--project", str(self.project), "--session-id", "wrapper-test", "--command", "rm small.txt"]
        denied = subprocess.run(base, capture_output=True, text=True, timeout=10)
        self.assertEqual(denied.returncode, 2, denied.stderr)
        self.assertTrue((self.project / "small.txt").exists())
        self.guard.approve(self.project, "wrapper", "wrapper-test", "rm small.txt", self.project, "yes", "backup")
        allowed = subprocess.run(base, capture_output=True, text=True, timeout=10)
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        self.assertFalse((self.project / "small.txt").exists())


class InstallerTests(unittest.TestCase):
    def setUp(self):
        import install_command_guard as installer
        self.installer = installer
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name).resolve() / "project"
        self.project.mkdir()

    def test_check_is_read_only_and_missing_is_not_ready(self):
        result = self.installer.install(self.project, "codex", check=True)
        self.assertFalse(result["configured"])
        self.assertEqual(list(self.project.iterdir()), [])

    def test_install_all_tools_preserves_unrelated_settings_and_is_idempotent(self):
        for runtime, folder, filename, event in (
            ("claude", ".claude", "settings.local.json", "PreToolUse"),
            ("codex", ".codex", "hooks.json", "PreToolUse"),
            ("gemini", ".gemini", "settings.json", "BeforeTool"),
        ):
            with self.subTest(runtime=runtime):
                directory = self.project / folder
                directory.mkdir()
                path = directory / filename
                path.write_text(json.dumps({"unrelated": {"keep": True}, "hooks": {event: [{"matcher": "Other", "hooks": [{"type": "command", "command": "echo existing"}]}]}}))
                self.installer.install(self.project, runtime)
                first = path.read_bytes()
                self.installer.install(self.project, runtime)
                self.assertEqual(path.read_bytes(), first)
                self.assertEqual(json.loads(first)["unrelated"], {"keep": True})
                result = self.installer.install(self.project, runtime, check=True)
                self.assertTrue(result["configured"], result)
                self.assertFalse(result["runtime_trust_checked"])


if __name__ == "__main__":
    unittest.main()
