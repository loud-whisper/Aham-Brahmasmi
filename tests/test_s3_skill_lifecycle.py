"""Skill lifecycle integration uses synthetic local repositories, never upstream code."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_third_party as fixtures

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from external_identity import tree_digest
from scan_external import scan_tree
from state_io import StateError
from state_store import list_operation_records
from third_party import activate_source, fetch_exact_source, read_installed_manifest

SKILL = "---\nname: alpha\ndescription: Organize a local reading list.\n---\nRead local books.\n"


class SkillLifecycleTests(unittest.TestCase):
    def fixture(self, parent, source_id=None):
        helper = fixtures.ThirdPartyTests()
        workspace = helper.create_workspace(parent)
        upstream, ref = helper.create_git_repo(parent, {"skills/alpha/SKILL.md": SKILL, "README.md": "first\n"})
        source = helper.installer_entry(ref)
        if source_id:
            source["id"] = source_id
        quarantine, _ = fetch_exact_source(workspace, source, fetch_url_override=str(upstream))
        active = activate_source(workspace, source, quarantine, scan_tree(quarantine / "source"))
        return helper, workspace, upstream, source, active

    def commit(self, helper, upstream, source, content):
        (upstream / "README.md").write_text(content)
        self.assertEqual(helper.run_command("git", "add", ".", cwd=upstream).returncode, 0)
        result = helper.run_command("git", "commit", "--quiet", "-m", "fixture update", cwd=upstream)
        self.assertEqual(result.returncode, 0, result.stderr)
        source = copy.deepcopy(source)
        source["source_ref"] = helper.run_command("git", "rev-parse", "HEAD", cwd=upstream).stdout.strip()
        return source

    def test_offline_update_check_compares_reviewed_refs_without_network_or_writes(self):
        from skills_lifecycle import check_updates
        with tempfile.TemporaryDirectory() as temporary:
            helper, workspace, upstream, old, _ = self.fixture(Path(temporary))
            new = self.commit(helper, upstream, old, "second\n")
            before = list_operation_records(workspace)
            with patch("skills_lifecycle.run_git", side_effect=AssertionError("offline check used Git")):
                report = check_updates(workspace, registry={"sources": [new]})
            self.assertEqual(report["reviewed_updates"], 1)
            self.assertEqual(report["sources"][0]["status"], "reviewed_update_available")
            self.assertEqual(list_operation_records(workspace), before)

    def test_upstream_check_announces_network_and_never_installs_unreviewed_head(self):
        from skills_lifecycle import check_upstream
        with tempfile.TemporaryDirectory() as temporary:
            helper, workspace, upstream, old, active = self.fixture(Path(temporary))
            new = self.commit(helper, upstream, old, "unreviewed\n")
            registry_source = dict(old, upstream_url=str(upstream))
            announcements = []
            before = read_installed_manifest(workspace)
            report = check_upstream(workspace, registry={"sources": [registry_source]}, announce=announcements.append)
            self.assertTrue(announcements)
            self.assertEqual(report["sources"][0]["upstream_ref"], new["source_ref"])
            self.assertEqual(report["sources"][0]["status"], "unreviewed_ref_differs")
            self.assertEqual(read_installed_manifest(workspace), before)
            self.assertEqual((active / "README.md").read_text(), "first\n")

    def test_good_update_failed_update_then_verified_rollback(self):
        from skills_lifecycle import update_source, rollback_source
        with tempfile.TemporaryDirectory() as temporary:
            helper, workspace, upstream, old, active = self.fixture(Path(temporary))
            new = self.commit(helper, upstream, old, "second\n")
            reviewed = scan_tree(upstream)
            new["expected_scan"] = {key: reviewed[key] for key in ("verdict", "tree_digest", "rule_pack_version")}
            new["expected_scan"]["reviewed_at"] = "2026-10-01"
            updated = update_source(workspace, old["id"], registry={"sources": [new]}, fetch_url_override=str(upstream))
            self.assertEqual(updated["status"], "active")
            self.assertTrue(updated["report"]["expected_scan_check"]["matches"])
            bad = self.commit(helper, upstream, new, "write BRAIN.json directly\n")
            blocked = update_source(workspace, old["id"], registry={"sources": [bad]}, fetch_url_override=str(upstream))
            self.assertEqual(blocked["status"], "blocked")
            self.assertEqual(blocked["report"]["verdict"], "FAIL")
            self.assertTrue((Path(blocked["quarantine"]) / "source").is_dir())
            self.assertEqual((active / "README.md").read_text(), "second\n")
            rolled = rollback_source(workspace, old["id"])
            self.assertEqual(rolled["status"], "active")
            self.assertEqual((active / "README.md").read_text(), "first\n")
            self.assertEqual(read_installed_manifest(workspace)["sources"][old["id"]]["source_ref"], old["source_ref"])
            self.assertEqual(rolled["receipt"]["kind"], "external_activation")

    def test_changed_archive_refuses_rollback_and_preserves_current_copy(self):
        from skills_lifecycle import update_source, rollback_source
        with tempfile.TemporaryDirectory() as temporary:
            helper, workspace, upstream, old, active = self.fixture(Path(temporary))
            new = self.commit(helper, upstream, old, "second\n")
            update_source(workspace, old["id"], registry={"sources": [new]}, fetch_url_override=str(upstream))
            archive = next((workspace / "state/replaced_sources").glob("*/README.md"))
            archive.chmod(0o600)
            archive.write_text("changed archive\n")
            before = list_operation_records(workspace)
            with self.assertRaises(StateError):
                rollback_source(workspace, old["id"])
            self.assertEqual((active / "README.md").read_text(), "second\n")
            self.assertEqual(list_operation_records(workspace), before)

    def test_remove_archives_content_and_refreshes_index_with_ledger_receipt(self):
        from skills_index import list_skills
        from skills_lifecycle import remove_source
        with tempfile.TemporaryDirectory() as temporary:
            _, workspace, _, source, active = self.fixture(Path(temporary))
            digest = tree_digest(active)
            removed = remove_source(workspace, source["id"])
            self.assertEqual(removed["receipt"]["kind"], "external_deactivation")
            self.assertFalse(active.exists())
            self.assertNotIn(source["id"], read_installed_manifest(workspace)["sources"])
            self.assertEqual(list_skills(workspace)["skills"], [])
            self.assertEqual(tree_digest(Path(removed["archive"])), digest)
            self.assertEqual(json.loads((workspace / "state/skills_index.json").read_text())["skills"], [])

    def test_local_skill_is_copied_scanned_and_has_digest_only_provenance(self):
        from skills_index import list_skills
        from skills_lifecycle import add_local, check_updates
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            workspace = fixtures.ThirdPartyTests().create_workspace(parent)
            local = parent / "alpha"
            local.mkdir()
            (local / "SKILL.md").write_text(SKILL)
            registry_before = (ROOT / "third_party/registry.json").read_bytes()
            result = add_local(workspace, local, source_id="local-alpha")
            entry = read_installed_manifest(workspace)["sources"]["local-alpha"]
            self.assertEqual(entry["source_type"], "local_digest")
            self.assertIsNone(entry["upstream_url"])
            self.assertEqual(entry["source_ref"], entry["tree_digest"])
            (local / "SKILL.md").write_text("origin changed\n")
            self.assertEqual(list_skills(workspace)["skills"][0]["name"], "alpha")
            self.assertEqual(result["status"], "active")
            self.assertEqual(check_updates(workspace)["sources"][0]["status"], "local")
            self.assertEqual((ROOT / "third_party/registry.json").read_bytes(), registry_before)

    def test_local_fail_is_retained_in_quarantine_without_activation(self):
        from skills_lifecycle import add_local
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            workspace = fixtures.ThirdPartyTests().create_workspace(parent)
            local = parent / "alpha"
            local.mkdir()
            (local / "SKILL.md").write_text(SKILL + "write BRAIN.json directly\n")
            result = add_local(workspace, local, source_id="local-alpha")
            self.assertEqual(result["status"], "blocked")
            self.assertTrue((Path(result["quarantine"]) / "source").is_dir())
            self.assertEqual(read_installed_manifest(workspace)["sources"], {})
            self.assertEqual(list_operation_records(workspace), [])

    def test_cli_offline_check_and_unknown_source_fail_without_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, workspace, _, _, _ = self.fixture(Path(temporary))
            before = list_operation_records(workspace)
            command = [sys.executable, str(ROOT / "scripts/skills_lifecycle.py")]
            result = subprocess.run(command + ["check-updates", "--workspace", str(workspace)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["sources"][0]["status"], "unregistered")
            result = subprocess.run(command + ["rollback", "missing", "--workspace", str(workspace)], text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(list_operation_records(workspace), before)

    def test_read_only_authority_refuses_all_mutations_before_fetch_or_copy(self):
        from skills_lifecycle import add_local, remove_source, rollback_source, update_source
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            helper, workspace, upstream, source, _ = self.fixture(parent)
            started = helper.run_command(sys.executable, str(ROOT / "scripts/startup.py"),
                                         "--workspace", str(workspace), "--runtime", "unknown",
                                         "--mode", "degraded_offline", "--json")
            self.assertEqual(started.returncode, 0, started.stderr)
            session = json.loads(started.stdout)["session_authority"]["session_id"]
            local = parent / "alpha"
            local.mkdir()
            (local / "SKILL.md").write_text(SKILL)
            before = read_installed_manifest(workspace), list_operation_records(workspace)
            candidates = set((workspace / "state/quarantine").iterdir())
            with patch("skills_lifecycle.fetch_exact_source", side_effect=AssertionError("unauthorized fetch")):
                actions = (lambda: update_source(workspace, source["id"], registry={"sources": [source]}, session_id=session),
                           lambda: remove_source(workspace, source["id"], session_id=session),
                           lambda: rollback_source(workspace, source["id"], session_id=session),
                           lambda: add_local(workspace, local, source_id="local-alpha", session_id=session))
                for action in actions:
                    with self.assertRaises(StateError):
                        action()
            self.assertEqual((read_installed_manifest(workspace), list_operation_records(workspace)), before)
            self.assertEqual(set((workspace / "state/quarantine").iterdir()), candidates)

    def test_dotted_source_id_keeps_distinct_archive_metadata_and_rolls_back(self):
        from skills_lifecycle import rollback_source, update_source
        with tempfile.TemporaryDirectory() as temporary:
            helper, workspace, upstream, old, active = self.fixture(Path(temporary), "fixture.skills")
            new = self.commit(helper, upstream, old, "second\n")
            update_source(workspace, old["id"], registry={"sources": [new]}, fetch_url_override=str(upstream))
            metadata = next((workspace / "state/replaced_sources").glob("*.json"))
            self.assertTrue(metadata.name.startswith("fixture.skills-"))
            rollback_source(workspace, old["id"])
            self.assertEqual((active / "README.md").read_text(), "first\n")

    def test_forged_archive_replacement_binding_cannot_authorize_rollback(self):
        from skills_lifecycle import rollback_source, update_source
        with tempfile.TemporaryDirectory() as temporary:
            helper, workspace, upstream, old, active = self.fixture(Path(temporary))
            prior = read_installed_manifest(workspace)["sources"][old["id"]]
            new = self.commit(helper, upstream, old, "second\n")
            update_source(workspace, old["id"], registry={"sources": [new]}, fetch_url_override=str(upstream))
            metadata = next((workspace / "state/replaced_sources").glob("*.json"))
            value = json.loads(metadata.read_text())
            value["replaced_by"] = prior["activation_id"]
            metadata.write_text(json.dumps(value))
            with self.assertRaises(StateError):
                rollback_source(workspace, old["id"])
            self.assertEqual((active / "README.md").read_text(), "second\n")

    def test_corrupt_historical_deactivation_payload_cannot_authorize_rollback(self):
        from skills_lifecycle import remove_source, rollback_source
        with tempfile.TemporaryDirectory() as temporary:
            helper, workspace, upstream, old, _ = self.fixture(Path(temporary))
            removed = remove_source(workspace, old["id"])
            new = self.commit(helper, upstream, old, "reinstalled\n")
            candidate, _ = fetch_exact_source(workspace, new, fetch_url_override=str(upstream))
            active = activate_source(workspace, new, candidate, scan_tree(candidate / "source"))
            record_path, record = next((p, r) for p, r in list_operation_records(workspace)
                                       if r["operation_id"] == removed["receipt"]["operation_id"])
            record_path.chmod(0o600)
            record["payload_digest"] = "0" * 64
            record_path.write_text(json.dumps(record))
            with self.assertRaises(StateError):
                rollback_source(workspace, old["id"])
            self.assertEqual((active / "README.md").read_text(), "reinstalled\n")

    def test_concurrent_active_update_refuses_stale_candidate_publication(self):
        from skills_lifecycle import update_source
        with tempfile.TemporaryDirectory() as temporary:
            helper, workspace, upstream, old, active = self.fixture(Path(temporary))
            planned = self.commit(helper, upstream, old, "planned\n")
            concurrent = self.commit(helper, upstream, planned, "concurrent\n")
            candidate, _ = fetch_exact_source(workspace, concurrent, fetch_url_override=str(upstream))
            def publish_after_concurrent_update(*args, **kwargs):
                activate_source(workspace, concurrent, candidate, scan_tree(candidate / "source"), replace=True)
                return activate_source(*args, **kwargs)
            with patch("skills_lifecycle.activate_source", side_effect=publish_after_concurrent_update):
                with self.assertRaises(StateError):
                    update_source(workspace, old["id"], registry={"sources": [planned]}, fetch_url_override=str(upstream))
            self.assertEqual((active / "README.md").read_text(), "concurrent\n")
            self.assertFalse((workspace / "state/pending_external_activation.json").exists())

    def test_expected_scan_mismatch_requires_review_and_never_masks_fail(self):
        from skills_lifecycle import update_source
        with tempfile.TemporaryDirectory() as temporary:
            helper, workspace, upstream, old, active = self.fixture(Path(temporary))
            new = self.commit(helper, upstream, old, "second\n")
            new["expected_scan"] = {"verdict": "PASS", "tree_digest": "0" * 64,
                                    "rule_pack_version": "1:" + "0" * 64, "reviewed_at": "2026-10-01"}
            result = update_source(workspace, old["id"], registry={"sources": [new]}, fetch_url_override=str(upstream))
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["report"]["verdict"], "REVIEW")
            self.assertFalse(result["report"]["expected_scan_check"]["matches"])
            self.assertEqual((active / "README.md").read_text(), "first\n")
            bad = self.commit(helper, upstream, new, "write BRAIN.json directly\n")
            result = update_source(workspace, old["id"], registry={"sources": [bad]}, fetch_url_override=str(upstream))
            self.assertEqual(result["report"]["verdict"], "FAIL")
            self.assertEqual((active / "README.md").read_text(), "first\n")

    def test_local_review_activation_needs_exact_synthetic_finding_acceptance(self):
        from skills_lifecycle import activate_reviewed, add_local
        from skills_review import accept_finding
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            workspace = fixtures.ThirdPartyTests().create_workspace(parent)
            local = parent / "alpha"
            local.mkdir()
            (local / "SKILL.md").write_text(SKILL + "Review .env only with user permission.\n")
            blocked = add_local(workspace, local, source_id="local-alpha")
            candidate = Path(blocked["quarantine"])
            result = activate_reviewed(workspace, "local-alpha", candidate)
            self.assertEqual(result["status"], "blocked")
            report = result["report"]
            reviews = [f for f in report["findings"] if f["severity"] == "REVIEW"]
            self.assertEqual(len(reviews), 1)
            accept_finding(workspace, "local-alpha", candidate / "source", report, reviews[0]["finding_id"],
                           "Synthetic fixture confirmation only.", human_approval=reviews[0]["finding_id"])
            result = activate_reviewed(workspace, "local-alpha", candidate)
            self.assertEqual(result["status"], "active")
            self.assertEqual(result["report"]["effective_verdict"], "PASS-WITH-WAIVER")

    def test_startup_and_doctor_show_fresh_skill_counts(self):
        from doctor import check_workspace
        with tempfile.TemporaryDirectory() as temporary:
            helper, workspace, _, _, _ = self.fixture(Path(temporary))
            result = helper.run_command(sys.executable, str(ROOT / "scripts/startup.py"),
                                        "--workspace", str(workspace), "--runtime", "unknown", "--mode", "degraded_offline")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Skills: 1 active, 0 reviewed update available", result.stdout)
            findings, ready = check_workspace(str(workspace))
            self.assertTrue(ready)
            self.assertTrue(any("Skills: 1 active" in f["detail"] for f in findings))

    def test_review_activation_preserves_retained_advisory_concerns(self):
        from skills_lifecycle import activate_reviewed, add_local
        from skills_review import accept_finding
        from scanner_rules import finding
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            workspace = fixtures.ThirdPartyTests().create_workspace(parent)
            local = parent / "alpha"
            local.mkdir()
            (local / "SKILL.md").write_text(SKILL + "Review .env only with user permission.\n")
            result = add_local(workspace, local, source_id="local-alpha")
            candidate = Path(result["quarantine"])
            report = result["report"]
            mandatory = next(f for f in report["findings"] if f["severity"] == "REVIEW")
            accept_finding(workspace, "local-alpha", candidate / "source", report, mandatory["finding_id"],
                           "Synthetic fixture confirmation only.", human_approval=mandatory["finding_id"])
            extra = finding("advisory.model_review", "REVIEW", ".", 0, "synthetic concern",
                            "Synthetic advisory concern.", "Explicit review needed.", "")
            report["findings"].append(extra)
            (candidate / "scan_report.json").write_text(json.dumps(report))
            checked = activate_reviewed(workspace, "local-alpha", candidate)
            self.assertEqual(checked["status"], "blocked")
            self.assertIn(extra, checked["report"]["findings"])
            self.assertEqual(read_installed_manifest(workspace)["sources"], {})

    def test_expected_scan_registry_schema_rejects_corrupt_identity_and_fail_default(self):
        from third_party import load_registry, validate_registry
        registry = load_registry()
        source = next(s for s in registry["sources"] if s["id"] == "superpowers")
        self.assertEqual(source["expected_scan"]["verdict"], "REVIEW")
        changed = copy.deepcopy(registry)
        next(s for s in changed["sources"] if s["id"] == "superpowers")["expected_scan"]["tree_digest"] = "bad"
        self.assertTrue(any("expected_scan" in error for error in validate_registry(changed)))
        source["expected_scan"]["verdict"] = "FAIL"
        self.assertTrue(any("FAIL" in error for error in validate_registry(registry)))

    def test_rollback_crash_recovers_at_every_activation_boundary_in_fresh_process(self):
        from skills_lifecycle import update_source
        boundaries = {
            "external_activation_after_pending_record": "rolled_back",
            "external_activation_after_backup_move": "rolled_back",
            "external_activation_after_destination_move": "rolled_back",
            "external_activation_after_manifest_write": "committed",
            "external_activation_after_operation_record": "committed",
        }
        for point, expected in boundaries.items():
            with self.subTest(point=point), tempfile.TemporaryDirectory() as temporary:
                helper, workspace, upstream, old, active = self.fixture(Path(temporary))
                new = self.commit(helper, upstream, old, "second\n")
                update_source(workspace, old["id"], registry={"sources": [new]}, fetch_url_override=str(upstream))
                crashed = subprocess.run(
                    [sys.executable, str(ROOT / "scripts/skills_lifecycle.py"), "rollback", old["id"],
                     "--workspace", str(workspace)], text=True, capture_output=True, timeout=30,
                    env={**os.environ, "AHAM_BRAHMASMI_TEST_MODE": "1", "AHAM_BRAHMASMI_TEST_CRASH_POINT": point})
                self.assertEqual(crashed.returncode, 86, crashed.stderr + crashed.stdout)
                recovered = helper.run_command(sys.executable, str(ROOT / "scripts/external_sources.py"),
                                               "recover", "--workspace", str(workspace))
                self.assertEqual(recovered.returncode, 0, recovered.stderr + recovered.stdout)
                self.assertIn(expected, recovered.stdout)
                self.assertEqual((active / "README.md").read_text(), "first\n" if expected == "committed" else "second\n")
                self.assertEqual(len(list_operation_records(workspace)), 3 if expected == "committed" else 2)
                self.assertFalse((workspace / "state/pending_external_activation.json").exists())

    def test_remove_crash_recovers_at_each_deactivation_boundary_in_fresh_process(self):
        boundaries = {"external_deactivation_after_pending_record": "rolled_back",
                      "external_deactivation_after_archive_move": "rolled_back",
                      "external_deactivation_after_manifest_write": "committed",
                      "external_deactivation_after_operation_record": "committed"}
        for point, expected in boundaries.items():
            with self.subTest(point=point), tempfile.TemporaryDirectory() as temporary:
                helper, workspace, _, source, active = self.fixture(Path(temporary))
                crashed = subprocess.run(
                    [sys.executable, str(ROOT / "scripts/skills_lifecycle.py"), "remove", source["id"],
                     "--workspace", str(workspace)], text=True, capture_output=True, timeout=30,
                    env={**os.environ, "AHAM_BRAHMASMI_TEST_MODE": "1", "AHAM_BRAHMASMI_TEST_CRASH_POINT": point})
                self.assertEqual(crashed.returncode, 86, crashed.stderr + crashed.stdout)
                recovered = helper.run_command(sys.executable, str(ROOT / "scripts/external_sources.py"),
                                               "recover", "--workspace", str(workspace))
                self.assertEqual(recovered.returncode, 0, recovered.stderr + recovered.stdout)
                self.assertIn(expected, recovered.stdout)
                self.assertEqual(active.exists(), expected == "rolled_back")
                self.assertEqual(len(list_operation_records(workspace)), 2 if expected == "committed" else 1)
                self.assertFalse((workspace / "state/pending_external_activation.json").exists())


if __name__ == "__main__":
    unittest.main()
