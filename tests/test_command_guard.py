"""Synthetic blast-radius cases. Classification never executes the input."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from concurrent.futures import ThreadPoolExecutor

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
        self.assertEqual(self.policy.Limits().max_bytes, 1_000_000_000)
        self.assertEqual(self.policy.Limits().max_files, 10_000)
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

    def test_measurement_failure_timeout_and_mount_require_user(self):
        (self.project / "build").mkdir()
        with mock.patch("command_guard_policy.os.scandir", side_effect=PermissionError("synthetic refusal")):
            self.assertEqual(self.classify("rm -r build").tier, "user_runs")
        with mock.patch("command_guard_policy.time.monotonic", side_effect=[0, 4]):
            self.assertEqual(self.classify("rm small.txt").tier, "user_runs")
        with mock.patch("command_guard_policy.os.path.ismount", return_value=True):
            self.assertEqual(self.classify("rm small.txt").tier, "user_runs")

    def test_guard_and_repository_control_paths_require_user(self):
        for directory in (".aham", ".codex", ".claude", ".gemini", ".git"):
            folder = self.project / directory
            folder.mkdir()
            (folder / "data").write_text("x")
            self.assertEqual(self.classify(f"rm -rf {directory}").tier, "user_runs")

    def test_copy_and_truncate_growth_are_bounded(self):
        self.assertEqual(self.classify("cp small.txt copy.txt", limits=self.policy.Limits(6, 10)).tier, "user_runs")
        self.assertEqual(self.classify("truncate -s 10 small.txt", limits=self.policy.Limits(10, 10)).tier, "user_runs")

    def test_database_files_and_database_trees_require_user(self):
        for filename in ("app.db", "app.sqlite3", "PG_VERSION", "ibdata1", "dump.rdb"):
            (self.project / filename).write_bytes(b"synthetic")
            self.assertEqual(self.classify(f"rm {filename}").tier, "user_runs")
        folder = self.project / "build"
        folder.mkdir()
        (folder / "storage").write_bytes(b"SQLite format 3\x00synthetic")
        self.assertEqual(self.classify("rm -rf build").tier, "user_runs")


@unittest.skipUnless(os.name == "posix", "POSIX hook installation scope")
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
        if runtime == "codex" and command == "rm small.txt":
            command = shlex.join(["rm", str(self.project / "small.txt")])
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
        self.guard.approve(self.project, "codex", "synthetic-session", payload["tool_input"]["command"], self.project,
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

    def test_codex_session_cwd_cannot_measure_relative_mutation(self):
        payload = self.payload("codex", "rm -- small.txt")
        result = self.guard.evaluate("codex", payload, self.project)
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("absolute", result["hookSpecificOutput"]["permissionDecisionReason"])
        with self.assertRaises(ValueError):
            self.guard.approve(self.project, "codex", "synthetic-session", "rm small.txt", self.project, "yes", "backup")

    def test_gemini_dir_path_is_relative_to_workspace_root(self):
        nested = self.project / "nested"
        nested.mkdir()
        (nested / "small.txt").write_text("nested")
        payload = self.payload("gemini", "rm small.txt")
        payload["tool_input"]["dir_path"] = "nested"
        result = self.guard.evaluate("gemini", payload, self.project)
        self.assertEqual(result["decision"], "deny")
        self.assertIn("6 bytes", result["reason"])

    def test_approval_binding_session_runtime_limits_and_expiry(self):
        command = shlex.join(["rm", str(self.project / "small.txt")])
        self.guard.approve(self.project, "codex", "synthetic-session", command, self.project, "yes", "backup")
        other_session = self.payload("codex", command)
        other_session["session_id"] = "different-session"
        self.assertEqual(self.guard.evaluate("codex", other_session, self.project)["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(self.guard.evaluate("gemini", self.payload("gemini", command), self.project)["decision"], "deny")
        from command_guard_store import database
        with database(self.project) as connection:
            connection.execute("UPDATE approvals SET expires=0")
        self.assertEqual(self.guard.evaluate("codex", self.payload("codex", command), self.project)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_growth_to_user_tier_cannot_consume_existing_approval(self):
        command = "rm small.txt"
        self.guard.approve(self.project, "gemini", "synthetic-session", command, self.project, "yes", "backup")
        config = self.project / ".aham/command-guard/config.json"
        config.write_text(json.dumps({"version": 1, "max_bytes": 3, "max_files": 10}))
        result = self.guard.evaluate("gemini", self.payload("gemini", command), self.project)
        self.assertEqual(result["decision"], "deny")
        self.assertIn("User runs it", result["reason"])

    def test_missing_or_corrupt_audit_denies_instead_of_proceeding(self):
        from command_guard_store import state_path
        state_path(self.project, "audit.sqlite3").write_bytes(b"invalid database")
        result = self.guard.evaluate("gemini", self.payload("gemini", "pwd"), self.project)
        self.assertEqual(result["decision"], "deny")

    def test_non_yes_and_empty_undo_do_not_create_approval(self):
        for response, undo in (("no", "backup"), ("", "backup"), ("yes", "")):
            with self.assertRaises(ValueError):
                self.guard.approve(self.project, "gemini", "synthetic-session", "rm small.txt", self.project, response, undo)

    def test_native_claude_ask_cannot_be_bypassed_by_chat_grant(self):
        with self.assertRaises(ValueError):
            self.guard.approve(self.project, "claude", "synthetic-session", "rm small.txt", self.project, "yes", "backup")

    def test_approval_recorder_can_pass_its_own_hook_but_never_for_tier_three(self):
        for nested, expected in (("rm small.txt", "allow"), ("rm $TARGET", "deny"), ("rm -rf /", "deny")):
            command = shlex.join([sys.executable, str(ROOT / "scripts/command_guard.py"), "approve",
                                  "--project", str(self.project), "--runtime", "gemini",
                                  "--session-id", "synthetic-session", "--command", nested,
                                  "--cwd", str(self.project), "--user-response", "yes", "--undo", "backup"])
            result = self.guard.evaluate("gemini", self.payload("gemini", command), self.project)
            self.assertEqual(result["decision"], expected)

    def test_denial_supplies_complete_session_bound_recorder_command(self):
        payload = self.payload("gemini", "rm small.txt")
        result = self.guard.evaluate("gemini", payload, self.project)
        recorder = result["reason"].split("\nApproval recorder, only after the user's yes:\n", 1)[1]
        args = shlex.split(recorder)
        self.assertIn("synthetic-session", args)
        self.assertIn(str(self.project), args)
        self.assertEqual(self.guard.evaluate("gemini", self.payload("gemini", recorder), self.project)["decision"], "allow")
        # Synthetic human yes: execute the supplied logging path, then retry.
        logged = subprocess.run(args, text=True, capture_output=True, timeout=10)
        self.assertEqual(logged.returncode, 0, logged.stderr)
        self.assertEqual(self.guard.evaluate("gemini", payload, self.project)["decision"], "allow")

    def test_independent_processes_cannot_replay_one_approval(self):
        self.guard.approve(self.project, "gemini", "synthetic-session", "rm small.txt", self.project, "yes", "backup")
        args = [sys.executable, str(ROOT / "scripts/command_guard.py"), "hook", "--runtime", "gemini", "--project", str(self.project)]
        def run(_):
            return subprocess.run(args, input=json.dumps(self.payload("gemini", "rm small.txt")),
                                  capture_output=True, text=True, timeout=10)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, range(2)))
        self.assertEqual(sorted(json.loads(result.stdout)["decision"] for result in results), ["allow", "deny"])

    def test_hook_cli_malformed_input_always_emits_valid_denial_json(self):
        for runtime in ("claude", "codex", "gemini"):
            args = [sys.executable, str(ROOT / "scripts/command_guard.py"), "hook", "--runtime", runtime, "--project", str(self.project)]
            for value in ("{", "null", "[]", '"text"', json.dumps({"hook_event_name": "BeforeTool" if runtime == "gemini" else "PreToolUse", "tool_name": []})):
                result = subprocess.run(args, input=value, text=True, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                data = json.loads(result.stdout)
                self.assertEqual(data["decision"] if runtime == "gemini" else data["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_unknown_shell_input_fields_do_not_change_the_measured_directory(self):
        for runtime in ("claude", "codex", "gemini"):
            payload = self.payload(runtime, "rm small.txt")
            payload["tool_input"]["workdir"] = str(self.project.parent)
            result = self.guard.evaluate(runtime, payload, self.project)
            self.assertEqual(result["decision"] if runtime == "gemini" else result["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_powershell_is_denied_with_native_format(self):
        payload = self.payload("claude", "Remove-Item small.txt")
        payload["tool_name"] = "PowerShell"
        self.assertEqual(self.guard.evaluate("claude", payload, self.project)["hookSpecificOutput"]["permissionDecision"], "deny")

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


@unittest.skipUnless(os.name == "posix", "POSIX installation scope")
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

    def test_configured_check_does_not_write_any_file(self):
        self.installer.install(self.project, "gemini")
        before = {str(p.relative_to(self.project)): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.project.rglob("*") if p.is_file()}
        self.assertTrue(self.installer.install(self.project, "gemini", check=True)["configured"])
        after = {str(p.relative_to(self.project)): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.project.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_tracked_native_settings_are_refused_before_private_write(self):
        subprocess.run(["git", "init", "-q", str(self.project)], check=True, capture_output=True)
        directory = self.project / ".codex"
        directory.mkdir()
        path = directory / "hooks.json"
        path.write_text("{}")
        subprocess.run(["git", "-C", str(self.project), "add", ".codex/hooks.json"], check=True, capture_output=True)
        with self.assertRaises((ValueError, RuntimeError)):
            self.installer.install(self.project, "codex")
        self.assertEqual(path.read_text(), "{}")
        self.assertFalse((self.project / ".aham").exists())

    def test_git_ignore_is_effective_for_all_private_paths(self):
        subprocess.run(["git", "init", "-q", str(self.project)], check=True, capture_output=True)
        self.assertTrue(self.installer.install(self.project, "codex")["configured"])
        for relative in (".codex/hooks.json", ".aham/command-guard/config.json", ".aham/command-guard/audit.sqlite3"):
            result = subprocess.run(["git", "-C", str(self.project), "check-ignore", "-q", relative], capture_output=True)
            self.assertEqual(result.returncode, 0, relative)

    def test_symlinked_state_and_settings_are_refused(self):
        outside = self.project.parent / "outside"
        outside.mkdir()
        (self.project / ".aham").symlink_to(outside, target_is_directory=True)
        with self.assertRaises((ValueError, RuntimeError)):
            self.installer.install(self.project, "codex")
        self.assertEqual(list(outside.iterdir()), [])

    def test_disabled_hooks_are_not_reported_as_configured(self):
        self.installer.install(self.project, "gemini")
        path = self.project / ".gemini/settings.json"
        value = json.loads(path.read_text())
        value["hooksConfig"] = {"enabled": False}
        path.write_text(json.dumps(value))
        self.assertFalse(self.installer.install(self.project, "gemini", check=True)["configured"])

    def test_hook_output_configuration_matches_documented_units_and_matchers(self):
        for runtime, timeout in (("claude", 10), ("codex", 10), ("gemini", 10000)):
            relative, event, group = self.installer.hook_group(self.project, runtime)
            self.assertEqual(event, "BeforeTool" if runtime == "gemini" else "PreToolUse")
            self.assertEqual(group["hooks"][0]["timeout"], timeout)
            self.assertEqual(group["hooks"][0]["type"], "command")
            if runtime == "claude":
                self.assertIn("PowerShell", group["matcher"])
                self.assertEqual(group["hooks"][0]["onFailure"], "block")

    def test_unsupported_runtime_and_public_framework_are_refused(self):
        with self.assertRaises((ValueError, RuntimeError)):
            self.installer.install(self.project, "unknown")
        with self.assertRaises((ValueError, RuntimeError)):
            self.installer.install(ROOT, "wrapper")

    def test_hook_launcher_failure_maps_to_documented_block_exit_code(self):
        with mock.patch.object(self.installer.sys, "executable", str(self.project / "missing-python")):
            for runtime in ("claude", "codex", "gemini"):
                _, _, group = self.installer.hook_group(self.project, runtime)
                result = subprocess.run(group["hooks"][0]["command"], shell=True, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 2)

    def test_check_refuses_duplicate_or_conflicting_guard_groups(self):
        self.installer.install(self.project, "codex")
        path = self.project / ".codex/hooks.json"
        value = json.loads(path.read_text())
        group = dict(value["hooks"]["PreToolUse"][0])
        group["matcher"] = "Other"
        value["hooks"]["PreToolUse"].append(group)
        path.write_text(json.dumps(value))
        self.assertFalse(self.installer.install(self.project, "codex", check=True)["configured"])


if __name__ == "__main__":
    unittest.main()
