"""Runtime trust and any-assistant access use synthetic workspaces only."""
from __future__ import annotations

import json
import copy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_r3_context_conformance as fixtures

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from project_state import project_id_by_name
from session_authority import load_session, require_operation_authority
from state_io import StateError
from state_store import list_operation_records


class AssistantAccessTests(unittest.TestCase):
    def fixture(self, parent):
        helper = fixtures.R3ContextConformanceTests()
        workspace = helper.make_workspace(parent)
        helper.wrap_project(parent, workspace, operation_id="a1-alpha", project="Alpha",
                            fact="Synthetic Alpha fact", task="Synthetic Alpha task",
                            update="Synthetic Alpha update", summary="Synthetic checkpoint")
        return helper, workspace, project_id_by_name(workspace, "Alpha")

    def run_aham(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "aham.py"), *args], cwd=ROOT,
                              text=True, capture_output=True, check=False)

    def startup(self, workspace, *, runtime="unlisted-assistant", mode="regular", capabilities=("write_files",)):
        import argparse
        from startup import build_report
        return build_report(argparse.Namespace(workspace=str(workspace), runtime=runtime, mode=mode,
                                               capability=list(capabilities), project_id=None, harness=None,
                                               context_loaded=False, json=True))

    def trust(self, workspace, runtime="unlisted-assistant"):
        from runtime_trust import change_trust
        return change_trust(workspace, runtime, trusted=True, human_confirmation=runtime, owner_control=True)

    def snapshot(self, workspace):
        return {str(p.relative_to(workspace)): p.read_bytes() if p.is_file() else None
                for p in workspace.rglob("*")}

    def test_listed_runtime_without_owner_trust_stays_read_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, workspace, _ = self.fixture(Path(temporary))
            report = self.startup(workspace, runtime="codex")
            self.assertEqual(report["session_authority"]["authority"], "read_only")
            self.assertFalse(report["write_policy"]["runtime_trusted_for_writes"])

    def test_unlisted_runtime_trust_and_probe_grant_writer_authority(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, workspace, _ = self.fixture(Path(temporary))
            receipt = self.trust(workspace)
            self.assertEqual(receipt["kind"], "runtime_control")
            report = self.startup(workspace)
            self.assertTrue(report["write_policy"]["runtime_trusted_for_writes"])
            self.assertEqual(report["writer_self_test"]["status"], "passed")
            self.assertEqual(report["session_authority"]["authority"], "read_write")
            self.assertFalse(report["runtime_profile_exact_match"])

    def test_capability_report_without_trust_does_not_run_probe(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, workspace, _ = self.fixture(Path(temporary))
            with patch("runtime_trust.probe_writer", side_effect=AssertionError("untrusted runtime probed")):
                report = self.startup(workspace)
            self.assertEqual(report["session_authority"]["authority"], "read_only")

    def test_trust_without_write_capability_does_not_grant_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, workspace, _ = self.fixture(Path(temporary))
            self.trust(workspace)
            report = self.startup(workspace, capabilities=("read_files",))
            self.assertEqual(report["session_authority"]["authority"], "read_only")

    def test_probe_failure_keeps_trusted_runtime_read_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, workspace, _ = self.fixture(Path(temporary))
            self.trust(workspace)
            with patch("runtime_trust.probe_writer", side_effect=StateError("Synthetic probe failure")):
                report = self.startup(workspace)
            self.assertEqual(report["writer_self_test"]["status"], "failed")
            self.assertEqual(report["session_authority"]["authority"], "read_only")

    def test_degraded_mode_never_probes_or_grants_trusted_runtime_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, workspace, _ = self.fixture(Path(temporary))
            self.trust(workspace)
            with patch("runtime_trust.probe_writer", side_effect=AssertionError("degraded mode probed")):
                report = self.startup(workspace, mode="degraded_offline")
            self.assertEqual(report["session_authority"]["authority"], "read_only")

    def test_revocation_denies_existing_session_and_next_startup(self):
        from runtime_trust import change_trust
        with tempfile.TemporaryDirectory() as temporary:
            _, workspace, _ = self.fixture(Path(temporary))
            self.trust(workspace)
            report = self.startup(workspace)
            old_session = report["session_authority"]["session_id"]
            change_trust(workspace, "unlisted-assistant", trusted=False,
                         human_confirmation="unlisted-assistant", owner_control=True)
            with self.assertRaises(StateError):
                require_operation_authority(workspace, "checkpoint", session_id=old_session)
            self.assertEqual(self.startup(workspace)["session_authority"]["authority"], "read_only")

    def test_ordinary_read_only_runtime_cannot_self_trust(self):
        from runtime_trust import change_trust
        with tempfile.TemporaryDirectory() as temporary:
            _, workspace, _ = self.fixture(Path(temporary))
            report = self.startup(workspace)
            before = self.snapshot(workspace)
            with self.assertRaises(StateError):
                change_trust(workspace, "unlisted-assistant", trusted=True,
                             human_confirmation="unlisted-assistant",
                             session_id=report["session_authority"]["session_id"])
            self.assertEqual(self.snapshot(workspace), before)

    def test_owner_control_requires_exact_confirmation_before_mutation(self):
        from runtime_trust import change_trust
        with tempfile.TemporaryDirectory() as temporary:
            _, workspace, _ = self.fixture(Path(temporary))
            before = self.snapshot(workspace)
            for runtime, confirmation in (("unlisted-assistant", "wrong"), ("../escape", "../escape")):
                with self.subTest(runtime=runtime), self.assertRaises(StateError):
                    change_trust(workspace, runtime, trusted=True, human_confirmation=confirmation, owner_control=True)
            self.assertEqual(self.snapshot(workspace), before)

    def test_trust_cache_edit_cannot_grant_runtime_authority(self):
        from runtime_trust import trusted_runtimes
        with tempfile.TemporaryDirectory() as temporary:
            _, workspace, _ = self.fixture(Path(temporary))
            path = workspace / "state/runtime_trust.json"
            path.write_text(json.dumps({"trusted": ["unlisted-assistant"]}))
            self.assertNotIn("unlisted-assistant", trusted_runtimes(workspace))
            self.assertEqual(self.startup(workspace)["session_authority"]["authority"], "read_only")

    def test_probe_uses_transient_managed_path_and_cleans_it(self):
        from runtime_trust import probe_writer
        with tempfile.TemporaryDirectory() as temporary:
            _, workspace, _ = self.fixture(Path(temporary))
            before = list_operation_records(workspace)
            self.assertEqual(probe_writer(workspace)["status"], "passed")
            self.assertEqual(list_operation_records(workspace), before)
            self.assertFalse(list((workspace / "state/runtime_probes").glob("*.json")))

    def test_entry_point_help_and_offline_memory_commands(self):
        help_result = self.run_aham("--help")
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        for verb in ("setup", "check", "start", "save", "wrap-up", "connect", "trust-runtime", "context", "import-wrapup"):
            self.assertIn(verb, help_result.stdout)
        for verb in ("save", "wrap-up"):
            verb_help = self.run_aham(verb, "--help")
            self.assertEqual(verb_help.returncode, 0, verb_help.stderr)
            self.assertIn("--workspace", verb_help.stdout)
            self.assertIn("--session-id", verb_help.stdout)
        with tempfile.TemporaryDirectory() as temporary:
            _, workspace, project = self.fixture(Path(temporary))
            configured = self.run_aham("memory", "configure", "--workspace", str(workspace), "--provider", "lite")
            self.assertEqual(configured.returncode, 0, configured.stderr)
            result = self.run_aham("memory", "search", "--workspace", str(workspace), "--project-id", project, "--query", "Alpha")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Synthetic Alpha fact", result.stdout)

    def test_chat_template_round_trip_and_duplicate_import(self):
        from chat_access import chat_packet
        with tempfile.TemporaryDirectory() as temporary:
            _, workspace, project = self.fixture(Path(temporary))
            packet = chat_packet(workspace, project, max_bytes=12000)
            response = packet["wrapup_template"]
            response["operation_id"] = "a1-chat-roundtrip"
            response["bundle"]["durable_facts"] = ["Synthetic chat fact"]
            response["bundle"]["checkpoint"]["summary"] = "Synthetic chat wrap-up"
            path = Path(temporary) / "response.json"
            path.write_text(json.dumps(response))
            session = load_session(workspace)["session_id"]
            for _ in range(2):
                result = self.run_aham("import-wrapup", str(path), "--workspace", str(workspace), "--session-id", session, "--json")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["status"], "complete")
            self.assertEqual(sum(record["operation_id"] == "a1-chat-roundtrip" for _, record in list_operation_records(workspace)), 1)

    def test_malformed_chat_response_has_zero_workspace_mutation(self):
        self.assertEqual(self.run_aham("--help").returncode, 0)
        with tempfile.TemporaryDirectory() as temporary:
            _, workspace, _ = self.fixture(Path(temporary))
            before = self.snapshot(workspace)
            for text in ("not JSON", "{\"format\":1,\"format\":2}", "BEGIN AHAM WRAPUP\n{}", "{}\n{}"):
                path = Path(temporary) / "bad-response.txt"
                path.write_text(text)
                result = self.run_aham("import-wrapup", str(path), "--workspace", str(workspace),
                                       "--session-id", load_session(workspace)["session_id"])
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.snapshot(workspace), before)

    def test_bridge_and_compact_startup_obey_instruction_budget(self):
        from runtime_bridge import render_bridge
        with tempfile.TemporaryDirectory() as temporary:
            _, workspace, _ = self.fixture(Path(temporary))
            started = self.run_aham("start", "--workspace", str(workspace), "--runtime", "unlisted-assistant", "--compact")
            self.assertEqual(started.returncode, 0, started.stderr)
            bridge = render_bridge("unlisted-assistant")
            self.assertIn("aham.py", bridge)
            self.assertIn("CHECKPOINT VERIFIED", bridge)
            self.assertLessEqual(len(bridge.encode()) + len(started.stdout.encode()), 12 * 1024)

    def test_setup_explicit_trust_and_invalid_names(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "new"
            bad = self.run_aham("setup", "--workspace", str(destination), "--trust-runtime", "../escape")
            self.assertNotEqual(bad.returncode, 0)
            self.assertFalse(destination.exists())
            good = self.run_aham("setup", "--workspace", str(destination), "--trust-runtime", "New-Assistant")
            self.assertEqual(good.returncode, 0, good.stderr)
            self.assertIn(load_session(destination)["session_id"], good.stdout)
            self.assertEqual(self.startup(destination, runtime="new-assistant")["session_authority"]["authority"], "read_write")

    def test_r1_migration_preserves_identity_and_requires_new_owner_trust(self):
        import test_r1_schema_migrations as migration_fixtures
        with tempfile.TemporaryDirectory() as temporary:
            helper = migration_fixtures.R1SchemaMigrationTests()
            workspace = helper.make_legacy_workspace(Path(temporary))
            brain_before = (workspace / "BRAIN.json").read_bytes()
            migration = self.run_aham("migrate", "--workspace", str(workspace))
            self.assertEqual(migration.returncode, 0, migration.stderr)
            self.assertEqual((workspace / "BRAIN.json").read_bytes(), brain_before)
            self.assertEqual(self.startup(workspace, runtime="local")["session_authority"]["authority"], "read_only")
            self.trust(workspace, "local")
            self.assertEqual(self.startup(workspace, runtime="local")["session_authority"]["authority"], "read_write")

    def test_unlisted_bridge_is_manual_and_preserves_requested_name(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, workspace, _ = self.fixture(Path(temporary))
            project = Path(temporary) / "project"
            project.mkdir()
            result = self.run_aham("connect", "--workspace", str(workspace), "--project", str(project),
                                   "--runtime", "new-assistant")
            self.assertEqual(result.returncode, 0, result.stderr)
            config = json.loads((project / ".aham/runtime.json").read_text())
            self.assertEqual(config["runtime"], "new-assistant")
            self.assertIsNone(config["instruction_file"])
            self.assertEqual({p.name for p in project.iterdir()}, {".aham"})
            bridge = (project / ".aham/runtime.md").read_text()
            self.assertNotIn(str(workspace), bridge)
            self.assertNotIn(str(ROOT), bridge)

    def test_probe_readback_and_cleanup_errors_deny_writes(self):
        for target, replacement in (("runtime_trust.read_json", {}),
                                    ("runtime_trust.sync_directory", PermissionError("synthetic cleanup sync"))):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as temporary:
                _, workspace, _ = self.fixture(Path(temporary))
                self.trust(workspace)
                options = {"side_effect": replacement} if isinstance(replacement, Exception) else {"return_value": replacement}
                with patch(target, **options):
                    report = self.startup(workspace)
                self.assertEqual(report["writer_self_test"]["status"], "failed")
                self.assertEqual(report["session_authority"]["authority"], "read_only")

    def test_pending_checkpoint_denies_regular_startup_without_probe(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, workspace, _ = self.fixture(Path(temporary))
            self.trust(workspace)
            (workspace / "state/pending_checkpoint.json").write_text("{}")
            with patch("runtime_trust.probe_writer", side_effect=AssertionError("pending operation probed")):
                report = self.startup(workspace)
            self.assertFalse(report["ready"])
            self.assertEqual(report["session_authority"]["authority"], "read_only")

    def test_trust_cache_failure_preserves_canonical_choice_and_repairs_without_new_operation(self):
        from runtime_trust import trusted_runtimes, repair_trust_view
        with tempfile.TemporaryDirectory() as temporary:
            _, workspace, _ = self.fixture(Path(temporary))
            with patch("runtime_trust._materialize", side_effect=OSError("synthetic cache failure")):
                with self.assertRaises(OSError):
                    self.trust(workspace)
            self.assertIn("unlisted-assistant", trusted_runtimes(workspace))
            before = list_operation_records(workspace)
            repair_trust_view(workspace)
            self.assertEqual(list_operation_records(workspace), before)
            self.assertEqual(json.loads((workspace / "state/runtime_trust.json").read_text())["trusted"], ["unlisted-assistant"])

    def test_pending_operation_blocks_trust_and_repair_without_mutation(self):
        from runtime_trust import repair_trust_view
        with tempfile.TemporaryDirectory() as temporary:
            _, workspace, _ = self.fixture(Path(temporary))
            for filename in ("pending_checkpoint.json", "pending_wrap_up.json"):
                path = workspace / "state" / filename
                path.write_text("{}")
                before = self.snapshot(workspace)
                with self.assertRaises(StateError):
                    self.trust(workspace)
                with self.assertRaises(StateError):
                    repair_trust_view(workspace)
                self.assertEqual(self.snapshot(workspace), before)
                path.unlink()

    def test_chat_identity_scope_revision_artifact_and_authority_rejections_are_read_only(self):
        from chat_access import chat_packet, validate_response
        with tempfile.TemporaryDirectory() as temporary:
            _, workspace, project = self.fixture(Path(temporary))
            template = chat_packet(workspace, project)["wrapup_template"]
            session = load_session(workspace)["session_id"]
            cases = []
            for field, value in (("workspace_id", "foreign"), ("project_id", "foreign"),
                                 ("base_revision", 999), ("version", True), ("session_id", session)):
                response = copy.deepcopy(template); response[field] = value; cases.append(response)
            for field, value in (("project", "Foreign"), ("artifacts", ["MEMORY.md"])):
                response = copy.deepcopy(template); response["bundle"]["checkpoint"][field] = value; cases.append(response)
            response = copy.deepcopy(template)
            response["bundle"]["project_updates"] = [{"project": "Foreign", "content": "foreign content"}]
            cases.append(response)
            before = self.snapshot(workspace)
            for response in cases:
                with self.subTest(response=response), self.assertRaises(StateError):
                    validate_response(workspace, response, session_id=session)
                self.assertEqual(self.snapshot(workspace), before)
            with self.assertRaises(StateError):
                validate_response(workspace, template, session_id="ses_" + "0" * 32)
            self.assertEqual(self.snapshot(workspace), before)

    def test_chat_input_limits_and_duplicate_nested_fields(self):
        from chat_access import read_response
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "response"
            for data in (b"x" * 65537, b"{\"bundle\":{\"x\":1,\"x\":2}}", b"{\"x\":NaN}", b"\xff",
                         b"BEGIN AHAM WRAPUP\n{}\nEND AHAM WRAPUP\nEND AHAM WRAPUP"):
                path.write_bytes(data)
                with self.subTest(data=data[:50]), self.assertRaises((StateError, ValueError)):
                    read_response(path)

    def test_chat_project_bound_session_round_trip(self):
        import argparse
        from startup import build_report
        from chat_access import chat_packet
        with tempfile.TemporaryDirectory() as temporary:
            _, workspace, project = self.fixture(Path(temporary))
            self.trust(workspace)
            report = build_report(argparse.Namespace(workspace=str(workspace), runtime="unlisted-assistant",
                mode="regular", capability=["write_files"], project_id=project, harness=None, context_loaded=False, json=True))
            response = chat_packet(workspace, project)["wrapup_template"]
            response["bundle"]["checkpoint"]["summary"] = "Synthetic project-bound chat import"
            path = Path(temporary) / "response.json"; path.write_text(json.dumps(response))
            result = self.run_aham("import-wrapup", str(path), "--workspace", str(workspace), "--session-id",
                                   report["session_authority"]["session_id"], "--json")
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_chat_replay_rejects_changed_base_or_payload_without_mutation(self):
        from chat_access import chat_packet, validate_response
        with tempfile.TemporaryDirectory() as temporary:
            _, workspace, project = self.fixture(Path(temporary))
            response = chat_packet(workspace, project)["wrapup_template"]
            session = load_session(workspace)["session_id"]
            path = Path(temporary) / "response.json"; path.write_text(json.dumps(response))
            result = self.run_aham("import-wrapup", str(path), "--workspace", str(workspace), "--session-id", session, "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            before = self.snapshot(workspace)
            for change in ("base", "payload"):
                altered = copy.deepcopy(response)
                if change == "base": altered["base_revision"] += 1
                else: altered["bundle"]["durable_facts"] = ["Changed replay content"]
                with self.subTest(change=change), self.assertRaises(StateError):
                    validate_response(workspace, altered, session_id=session)
                self.assertEqual(self.snapshot(workspace), before)

    def test_recovery_guidance_uses_running_interpreter(self):
        import shlex
        from recovery_commands import recovery_command
        for verb in ("save", "wrap-up"):
            command = shlex.split(recovery_command(verb, platform="linux"))
            self.assertEqual(command[:3], [sys.executable, str(ROOT / "aham.py"), verb])
            self.assertIn("--session-id", command)

    def test_probe_and_trust_cache_excluded_but_trust_ledger_survives_export_restore(self):
        import test_git_transport as git_fixtures
        import test_r4_portable_backup_restore as backup_fixtures
        from runtime_trust import trusted_runtimes
        with tempfile.TemporaryDirectory() as temporary:
            _, workspace, _ = self.fixture(Path(temporary))
            self.trust(workspace)
            directory = workspace / "state/runtime_probes"; directory.mkdir()
            (directory / "stale.json").write_text("Synthetic interrupted probe")
            git = git_fixtures.GitTransportTests(); git.init_transport(workspace)
            result = git.run_tool("snapshot", "--workspace", str(workspace), "--message", "A1 fixture")
            self.assertEqual(result.returncode, 0, result.stderr)
            tracked = git.git(workspace, "ls-files").stdout
            self.assertNotIn("runtime_probes", tracked)
            self.assertNotIn("runtime_trust.json", tracked)
            backup = backup_fixtures.R4PortableBackupRestoreTests()
            exported = Path(temporary) / "export"
            result = backup.export(workspace, exported)
            self.assertEqual(result.returncode, 0, result.stderr)
            paths = {item["path"] for item in json.loads((exported / "manifest.json").read_text())["files"]}
            self.assertFalse(any("runtime_probes" in path or "runtime_trust.json" in path for path in paths))
            restored = Path(temporary) / "restored"
            result = self.run_aham("restore", "--input", str(exported), "--workspace", str(restored))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("unlisted-assistant", trusted_runtimes(restored))

    def test_corrupt_trust_record_cannot_issue_writer_authority(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, workspace, _ = self.fixture(Path(temporary))
            self.trust(workspace)
            path, record = next((path, record) for path, record in list_operation_records(workspace)
                                if record["kind"] == "runtime_control")
            record["details"]["request"]["runtime"] = "tampered"
            path.write_text(json.dumps(record))
            before = (workspace / "state/session_authority.json").read_bytes()
            with self.assertRaises(StateError):
                self.startup(workspace)
            self.assertEqual((workspace / "state/session_authority.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
