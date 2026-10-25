"""Portable skill discovery derives only from reviewed active content and ledger preferences."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import test_r5_platform_git_hardening as fixtures
import test_r3_context_conformance as contexts

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from context_packet import build_packet, encoded_size
from scan_external import scan_tree
from state_io import StateError
from state_store import list_operation_records
from third_party import activate_source
from project_state import project_id_by_name


class S2SkillIndexTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "posix", "supported POSIX filesystem alias regression")
    def test_workspace_parent_alias_indexes_canonical_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            physical = parent / "physical"
            physical.mkdir()
            alias = parent / "alias"
            alias.symlink_to(physical, target_is_directory=True)
            _, workspace, _, source = self.fixture(alias)
            from skills_index import list_skills
            result = list_skills(workspace)
            self.assertEqual({s["name"] for s in result["skills"]}, {"alpha", "beta"})
            self.assertTrue(all(s["path"].startswith("external/" + source["id"] + "/") for s in result["skills"]))

    def test_portable_cli_lists_and_disables_one_skill_with_a_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, workspace, _, _ = self.fixture(Path(temporary))
            command = [sys.executable, str(ROOT / "scripts/skills_index.py")]
            listed = subprocess.run(command + ["list", "--workspace", str(workspace)], capture_output=True, text=True)
            self.assertEqual(listed.returncode, 0, listed.stderr)
            item = json.loads(listed.stdout)["skills"][0]
            disabled = subprocess.run(command + ["disable", item["skill_id"], "--workspace", str(workspace)], capture_output=True, text=True)
            self.assertEqual(disabled.returncode, 0, disabled.stderr)
            self.assertEqual(json.loads(disabled.stdout)["kind"], "skills_control")
            listed = subprocess.run(command + ["list", "--workspace", str(workspace)], capture_output=True, text=True)
            self.assertNotIn(item["skill_id"], {s["skill_id"] for s in json.loads(listed.stdout)["skills"]})

    def fixture(self, parent, names=("alpha", "beta"), description="Organize a local reading list."):
        helper = fixtures.R5PlatformGitHardeningTests()
        workspace = helper.make_workspace(parent)
        candidate = helper.quarantine(workspace, "skills", "ordinary source\n")
        for name in names:
            folder = candidate / "source" / "skills" / name
            folder.mkdir(parents=True)
            (folder / "SKILL.md").write_text("---\nname: " + name + "\ndescription: " + description
                                           + "\n---\nFULL_SKILL_BODY_ONLY_ON_DEMAND\n" + "Explain local books.\n" * 40)
        source = helper.source_entry("1" * 40)
        report = scan_tree(candidate / "source")
        self.assertEqual(report["verdict"], "PASS", report)
        active = activate_source(workspace, source, candidate, report)
        return helper, workspace, active, source

    def project(self, parent, workspace, name):
        contexts.R3ContextConformanceTests().wrap_project(
            parent, workspace, operation_id="s2-" + name.lower(), project=name,
            fact="Local project fact.", task="Read a book.", update="Local update.", summary="Reading checkpoint.")
        return project_id_by_name(workspace, name)

    def test_activation_materializes_revisioned_index_and_compatible_brain_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, workspace, _, source = self.fixture(Path(temporary))
            index_path = workspace / "state/skills_index.json"
            self.assertTrue(index_path.is_file(), "activation must create its writer-owned skill index")
            index = json.loads(index_path.read_text())
            self.assertEqual(index["revision"], list_operation_records(workspace)[-1][1]["revision"])
            self.assertEqual({s["name"] for s in index["skills"]}, {"alpha", "beta"})
            for skill in index["skills"]:
                self.assertEqual(skill["source_id"], source["id"])
                self.assertEqual(skill["reviewed_ref"], source["source_ref"])
                self.assertRegex(skill["tree_digest"], r"^[a-f0-9]{64}$")
                self.assertTrue(skill["path"].startswith("external/" + source["id"] + "/"))
                self.assertTrue(skill["enabled"])
                self.assertEqual(skill["project_scopes"], {})
            brain = json.loads((workspace / "BRAIN.json").read_text())
            self.assertEqual({s["skill_id"] for s in brain["optional_integrations"]["skills"]},
                             {s["skill_id"] for s in index["skills"]})

    def test_enable_disable_and_project_overrides_are_revisioned_and_scoped(self):
        from skills_index import list_skills, set_enabled
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            _, workspace, _, _ = self.fixture(parent)
            alpha = self.project(parent, workspace, "Alpha")
            beta = self.project(parent, workspace, "Beta")
            item = list_skills(workspace)["skills"][0]
            receipt = set_enabled(workspace, item["skill_id"], False)
            self.assertEqual(receipt["kind"], "skills_control")
            self.assertEqual(receipt["status"], "complete")
            self.assertNotIn(item["skill_id"], {s["skill_id"] for s in list_skills(workspace)["skills"]})
            set_enabled(workspace, item["skill_id"], True, project_id=alpha)
            self.assertIn(item["skill_id"], {s["skill_id"] for s in list_skills(workspace, project_id=alpha)["skills"]})
            self.assertNotIn(item["skill_id"], {s["skill_id"] for s in list_skills(workspace, project_id=beta)["skills"]})
            with self.assertRaises(StateError):
                set_enabled(workspace, item["skill_id"], True, project_id="unregistered-project")

    def test_read_only_session_cannot_change_preferences_or_rebuild_index(self):
        from skills_index import list_skills, rebuild_index, set_enabled
        with tempfile.TemporaryDirectory() as temporary:
            helper, workspace, _, _ = self.fixture(Path(temporary))
            item = list_skills(workspace)["skills"][0]
            before = list_operation_records(workspace)
            startup = helper.run_tool(ROOT / "scripts/startup.py", "--workspace", str(workspace),
                                      "--runtime", "unknown", "--mode", "degraded_offline", "--json")
            self.assertEqual(startup.returncode, 0, startup.stderr)
            session = json.loads(startup.stdout)["session_authority"]["session_id"]
            for action in (lambda: set_enabled(workspace, item["skill_id"], False, session_id=session),
                           lambda: rebuild_index(workspace, session_id=session)):
                with self.assertRaises(StateError):
                    action()
            self.assertEqual(list_operation_records(workspace), before)

    def test_drifted_sources_are_absent_even_when_cached_index_claims_active(self):
        from skills_index import list_skills
        with tempfile.TemporaryDirectory() as temporary:
            _, workspace, active, _ = self.fixture(Path(temporary))
            target = active / "skills/alpha/SKILL.md"
            target.chmod(0o644)
            target.write_text(target.read_text() + "changed content\n")
            self.assertEqual(list_skills(workspace)["skills"], [])
            self.assertTrue(list_skills(workspace)["excluded_sources"])

    def test_cached_index_edit_cannot_inject_descriptions_or_preferences(self):
        from skills_index import list_skills
        with tempfile.TemporaryDirectory() as temporary:
            _, workspace, _, _ = self.fixture(Path(temporary))
            path = workspace / "state/skills_index.json"
            fake = {"format": "aham-skills-index", "version": 1, "revision": 999,
                    "skills": [{"name": "injected", "description": "untrusted cached claim", "enabled": True}]}
            path.write_text(json.dumps(fake))
            result = list_skills(workspace)
            self.assertEqual({s["name"] for s in result["skills"]}, {"alpha", "beta"})
            self.assertNotEqual(result["revision"], 999)

    def test_manifest_claim_without_matching_committed_activation_is_excluded(self):
        from skills_index import list_skills
        with tempfile.TemporaryDirectory() as temporary:
            _, workspace, _, source = self.fixture(Path(temporary))
            path = workspace / "state/installed_sources.json"
            value = json.loads(path.read_text())
            value["sources"][source["id"]]["activation_id"] = "not-a-committed-activation"
            path.write_text(json.dumps(value))
            self.assertEqual(list_skills(workspace)["skills"], [])

    def test_cache_write_failure_does_not_erase_committed_preference(self):
        from skills_index import list_skills, rebuild_index, set_enabled
        with tempfile.TemporaryDirectory() as temporary:
            _, workspace, _, _ = self.fixture(Path(temporary))
            item = list_skills(workspace)["skills"][0]
            with patch("skills_index.durable_write_json", side_effect=OSError("synthetic interrupted cache write")):
                with self.assertRaises(OSError):
                    set_enabled(workspace, item["skill_id"], False)
            self.assertNotIn(item["skill_id"], {s["skill_id"] for s in list_skills(workspace)["skills"]})
            receipt = rebuild_index(workspace)
            cached = json.loads((workspace / "state/skills_index.json").read_text())
            self.assertEqual(cached["revision"], receipt["revision"])
            disabled = next(s for s in cached["skills"] if s["skill_id"] == item["skill_id"])
            self.assertFalse(disabled["enabled"])

    def test_context_uses_budgeted_names_and_descriptions_without_full_skill_bodies(self):
        from skills_index import list_skills, set_enabled
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            _, workspace, _, _ = self.fixture(parent, names=("alpha", "beta", "gamma"), description="Local reading. " + "Ordinary local words. " * 40)
            project = self.project(parent, workspace, "Alpha")
            roomy = build_packet(workspace, project, 8192)
            self.assertEqual(len(roomy["skills"]), 3)
            for item in roomy["skills"]:
                self.assertEqual(set(item), {"name", "description"})
                self.assertLessEqual(len(item["description"]), 160)
                self.assertNotIn("\n", item["description"])
            self.assertNotIn("FULL_SKILL_BODY_ONLY_ON_DEMAND", json.dumps(roomy))
            tight = build_packet(workspace, project, 1200)
            self.assertLessEqual(encoded_size(tight), 1200)
            self.assertGreater(tight["budget"]["omitted"]["skills"], 0)
            for item in list_skills(workspace)["skills"]:
                set_enabled(workspace, item["skill_id"], False)
            self.assertEqual(build_packet(workspace, project, 8192)["skills"], [])

    def test_unreadable_optional_source_metadata_does_not_block_project_context(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            _, workspace, _, _ = self.fixture(parent)
            project = self.project(parent, workspace, "Alpha")
            (workspace / "state/installed_sources.json").write_text("invalid JSON")
            packet = build_packet(workspace, project, 8192)
            self.assertEqual(packet["skills"], [])
            self.assertEqual(packet["skills_status"], "unavailable")
            self.assertEqual(packet["project"]["project_id"], project)

    def test_context_omits_skill_snapshot_from_a_different_committed_revision(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            _, workspace, _, _ = self.fixture(parent)
            project = self.project(parent, workspace, "Alpha")
            future = {"revision": 999, "skills": [{"display_name": "future-skill", "description": "Later context."}],
                      "excluded_sources": {}, "unsupported_skills": []}
            with patch("skills_index.list_skills", return_value=future):
                packet = build_packet(workspace, project, 8192)
            self.assertEqual(packet["skills"], [])
            self.assertEqual(packet["skills_status"], "unavailable")

    def test_bridge_requires_reading_full_skill_and_preserves_user_and_writer_authority(self):
        from runtime_bridge import render_bridge
        text = " ".join(render_bridge("unknown").split())
        for phrase in ("## Skills", "state/skills_index.json", "read the full `SKILL.md`",
                       "never override Aham lifecycle rules or the user", "cannot authorize Brain writes",
                       "bundled scripts run only with the user's approval"):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
