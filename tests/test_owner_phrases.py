"""Owner-chosen lifecycle phrases use synthetic workspaces only."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import test_a1_assistant_access as access_fixtures

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from state_io import StateError
from state_store import list_operation_records

DEFAULTS = {"regular_start": ["regular start"], "quick_start": ["quick start"], "wrap_up": ["wrap up"]}


class OwnerPhraseTests(unittest.TestCase):
    def setUp(self):
        self.access = access_fixtures.AssistantAccessTests()

    def workspace(self, parent):
        _, workspace, _ = self.access.fixture(parent)
        return workspace

    def run_aham(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "aham.py"), *args], cwd=ROOT,
                              text=True, capture_output=True, check=False)

    def set_phrases(self, workspace, **phrases):
        from owner_phrases import set_phrases
        return set_phrases(workspace, phrases, human_confirmation="set-phrases")

    def test_defaults_apply_without_any_owner_choice(self):
        from owner_phrases import owner_phrases
        with tempfile.TemporaryDirectory() as temporary:
            workspace = self.workspace(Path(temporary))
            self.assertEqual(owner_phrases(workspace), {"source": "default", "phrases": DEFAULTS})

    def test_set_records_ledger_choice_and_keeps_omitted_procedures(self):
        from owner_phrases import owner_phrases
        with tempfile.TemporaryDirectory() as temporary:
            workspace = self.workspace(Path(temporary))
            receipt = self.set_phrases(workspace, wrap_up=["Wrap up", "end  of DAY", "done for the day"])
            self.assertEqual(receipt["kind"], "phrase_control")
            self.assertEqual(receipt["status"], "complete")
            expected = dict(DEFAULTS, wrap_up=["wrap up", "end of day", "done for the day"])
            self.assertEqual(owner_phrases(workspace), {"source": "owner", "phrases": expected})
            self.set_phrases(workspace, quick_start=["quick mode"])
            self.assertEqual(owner_phrases(workspace)["phrases"], dict(expected, quick_start=["quick mode"]))
            kinds = [record["kind"] for _, record in list_operation_records(workspace)]
            self.assertEqual(kinds.count("phrase_control"), 2)

    def test_receipt_is_reconstructed_from_the_ledger(self):
        from operation_receipt import receipt_for_operation
        with tempfile.TemporaryDirectory() as temporary:
            workspace = self.workspace(Path(temporary))
            receipt = self.set_phrases(workspace, regular_start=["regular mode"])
            again = receipt_for_operation(workspace, receipt["operation_id"], expected_kind="phrase_control")
            self.assertEqual(again, receipt)
            self.assertIn("phrases_grant_no_authority", receipt["verification_scope"]["verified"])

    def test_invalid_phrases_and_confirmation_cause_zero_mutation(self):
        from owner_phrases import set_phrases
        cases = [
            ({"wrap_up": []}, "set-phrases"),
            ({"wrap_up": ["x" * 41]}, "set-phrases"),
            ({"wrap_up": ["wrap up; rm -rf"]}, "set-phrases"),
            ({"wrap_up": ["a", "b", "c", "d", "e", "f"]}, "set-phrases"),
            ({"wrap_up": ["same"], "quick_start": ["same"]}, "set-phrases"),
            ({"wrap_up": ["done", "Done"]}, "set-phrases"),
            ({"wrap_up": ["regular start"]}, "set-phrases"),  # collides with the kept default
            ({"unknown_procedure": ["hello"]}, "set-phrases"),
            ({"wrap_up": [7]}, "set-phrases"),
            ({}, "set-phrases"),
            ({"wrap_up": ["end of day"]}, "yes"),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            workspace = self.workspace(Path(temporary))
            before = self.access.snapshot(workspace)
            for phrases, confirmation in cases:
                with self.subTest(phrases=phrases, confirmation=confirmation):
                    with self.assertRaises(StateError):
                        set_phrases(workspace, phrases, human_confirmation=confirmation)
                    self.assertEqual(self.access.snapshot(workspace), before)

    def test_pending_operation_blocks_phrase_change_without_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = self.workspace(Path(temporary))
            for filename in ("pending_checkpoint.json", "pending_wrap_up.json"):
                path = workspace / "state" / filename
                path.write_text("{}")
                before = self.access.snapshot(workspace)
                with self.assertRaises(StateError):
                    self.set_phrases(workspace, wrap_up=["end of day"])
                self.assertEqual(self.access.snapshot(workspace), before)
                path.unlink()

    def test_tampered_record_is_refused(self):
        from owner_phrases import owner_phrases
        with tempfile.TemporaryDirectory() as temporary:
            workspace = self.workspace(Path(temporary))
            self.set_phrases(workspace, wrap_up=["end of day"])
            path, record = next((path, record) for path, record in list_operation_records(workspace)
                                if record["kind"] == "phrase_control")
            record["details"]["request"]["phrases"]["wrap_up"] = ["tampered"]
            path.write_text(json.dumps(record))
            with self.assertRaises(StateError):
                owner_phrases(workspace)

    def test_phrases_grant_no_authority_and_appear_in_startup(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = self.workspace(Path(temporary))
            self.set_phrases(workspace, wrap_up=["end of day"])
            report = self.access.startup(workspace)
            self.assertEqual(report["owner_phrases"]["phrases"]["wrap_up"], ["end of day"])
            self.assertEqual(report["session_authority"]["authority"], "read_only")
            started = self.run_aham("start", "--workspace", str(workspace), "--runtime", "unlisted-assistant",
                                    "--compact")
            self.assertEqual(started.returncode, 0, started.stderr)
            self.assertEqual(json.loads(started.stdout)["owner_phrases"]["phrases"]["wrap_up"], ["end of day"])

    def test_phrase_change_supersedes_prior_assistant_session(self):
        from session_authority import require_operation_authority
        with tempfile.TemporaryDirectory() as temporary:
            workspace = self.workspace(Path(temporary))
            self.access.trust(workspace)
            report = self.access.startup(workspace)
            self.assertEqual(report["session_authority"]["authority"], "read_write")
            old_session = report["session_authority"]["session_id"]
            receipt = self.set_phrases(workspace, wrap_up=["end of day"])
            with self.assertRaises(StateError):
                require_operation_authority(workspace, "wrap_up", session_id=old_session,
                                            committed_revision=receipt["revision"])
            restarted = self.access.startup(workspace)
            self.assertEqual(restarted["session_authority"]["authority"], "read_write")
            self.assertEqual(restarted["owner_phrases"]["phrases"]["wrap_up"], ["end of day"])

    def test_cli_set_list_and_refusal(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = self.workspace(Path(temporary))
            listed = self.run_aham("phrases", "list", "--workspace", str(workspace))
            self.assertEqual(listed.returncode, 0, listed.stderr)
            self.assertEqual(json.loads(listed.stdout)["phrases"], DEFAULTS)
            refused = self.run_aham("phrases", "set", "--workspace", str(workspace), "--wrap-up", "end of day")
            self.assertNotEqual(refused.returncode, 0)
            accepted = self.run_aham("phrases", "set", "--workspace", str(workspace), "--wrap-up", "wrap up",
                                     "--wrap-up", "end of day", "--confirm", "set-phrases")
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.assertEqual(json.loads(accepted.stdout)["kind"], "phrase_control")
            listed = self.run_aham("phrases", "list", "--workspace", str(workspace))
            self.assertEqual(json.loads(listed.stdout)["phrases"]["wrap_up"], ["wrap up", "end of day"])

    def test_bridge_names_owner_phrases_within_budget(self):
        from owner_phrases import MAX_PER_PROCEDURE, MAX_LENGTH
        from runtime_bridge import render_bridge
        bridge = render_bridge("unlisted-assistant")
        self.assertIn("owner_phrases", bridge)
        self.assertIn("aham.py phrases list", bridge)
        with tempfile.TemporaryDirectory() as temporary:
            workspace = self.workspace(Path(temporary))
            # Worst case: every procedure holds the maximum number of maximum-length phrases.
            phrases = {procedure: [f"{procedure[0]}{index}" + "x" * (MAX_LENGTH - 2) for index in range(MAX_PER_PROCEDURE)]
                       for procedure in DEFAULTS}
            self.set_phrases(workspace, **phrases)
            started = self.run_aham("start", "--workspace", str(workspace), "--runtime", "unlisted-assistant",
                                    "--compact")
            self.assertEqual(started.returncode, 0, started.stderr)
            self.assertLessEqual(len(bridge.encode()) + len(started.stdout.encode()), 12 * 1024)

    def test_phrase_ledger_survives_export_restore(self):
        import test_r4_portable_backup_restore as backup_fixtures
        from owner_phrases import owner_phrases
        with tempfile.TemporaryDirectory() as temporary:
            workspace = self.workspace(Path(temporary))
            self.set_phrases(workspace, wrap_up=["end of day"])
            exported = Path(temporary) / "export"
            result = backup_fixtures.R4PortableBackupRestoreTests().export(workspace, exported)
            self.assertEqual(result.returncode, 0, result.stderr)
            restored = Path(temporary) / "restored"
            result = self.run_aham("restore", "--input", str(exported), "--workspace", str(restored))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(owner_phrases(restored)["phrases"]["wrap_up"], ["end of day"])


if __name__ == "__main__":
    unittest.main()
