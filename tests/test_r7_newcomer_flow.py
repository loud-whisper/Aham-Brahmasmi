"""Synthetic newcomer diagnostics; real human walkthrough outcomes are separate."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import doctor


class NewcomerFlowTests(unittest.TestCase):
    def run_aham(self, *arguments):
        return subprocess.run([sys.executable, str(ROOT / "aham.py"), *arguments],
                              text=True, capture_output=True, cwd=ROOT, check=False)

    def workspace(self, root):
        destination = root / "workspace"
        result = self.run_aham("setup", "--workspace", str(destination))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Next: run aham.py check --workspace", result.stdout)
        return destination

    def snapshot(self, workspace):
        return {str(path.relative_to(workspace)): (stat.S_IMODE(path.stat().st_mode),
                path.read_bytes() if path.is_file() else None) for path in [workspace, *workspace.rglob("*")]}

    @unittest.skipUnless(os.name == "posix", "POSIX permission modes; Windows ACL gate is W1")
    def test_setup_owner_only_modes_under_permissive_umask(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            parent_mode = stat.S_IMODE(root.stat().st_mode)
            result = subprocess.run([sys.executable, "-c", "import os,runpy,sys; from pathlib import Path; os.umask(0); sys.path.insert(0,str(Path(sys.argv[1]).parent)); sys.argv=sys.argv[1:]; runpy.run_path(sys.argv[0],run_name='__main__')",
                                     str(ROOT / "scripts/setup_workspace.py"), "--workspace", str(workspace)],
                                    text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            for path in [workspace, *workspace.rglob("*")]:
                with self.subTest(path=path.relative_to(workspace)):
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700 if path.is_dir() else 0o600)
            self.assertEqual(stat.S_IMODE(root.stat().st_mode), parent_mode)

    def test_no_selected_workspace_is_not_ready(self):
        result = self.run_aham("check", "--json")
        self.assertNotEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertFalse(report["ready_for_new_work"])
        self.assertTrue(any("--workspace" in item.get("action", "") for item in report["findings"]))

    def test_simulated_windows_without_native_backend_is_not_verified(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = self.workspace(Path(temporary))
            with patch.object(doctor.sys, "platform", "win32"), patch.object(doctor, "os", SimpleNamespace(name="posix")), patch.object(doctor, "permission_issue", return_value=None), patch.object(doctor.shutil, "which", return_value=None):
                findings, _ = doctor.check_workspace(workspace)
            finding = next(item for item in findings if item["name"] == "Workspace permissions")
            self.assertEqual(finding["status"], "not_checked")

    def test_stale_session_pending_recovery_requests_owner_access(self):
        from session_authority import load_session
        with tempfile.TemporaryDirectory() as temporary:
            workspace = self.workspace(Path(temporary))
            (workspace / "state/pending_checkpoint.json").write_text("{}")
            session = load_session(workspace)
            session["current_revision"] += 1
            with patch.object(doctor, "load_session", return_value=session):
                findings, _ = doctor.check_workspace(workspace)
            finding = next(item for item in findings if item["name"] == "Interrupted checkpoint")
            self.assertIn("recover-access", finding["action"])

    def test_legacy_pending_recovery_has_confirmed_owner_access_without_granting_new_work(self):
        from session_authority import issue_session, require_operation_authority
        from state_io import StateError
        with tempfile.TemporaryDirectory() as temporary:
            workspace = self.workspace(Path(temporary))
            interrupted = subprocess.run([sys.executable, str(ROOT / "aham.py"), "save", "--workspace", str(workspace),
                "--summary", "Synthetic pre-trust interrupted checkpoint"], text=True, capture_output=True,
                env={**os.environ, "AHAM_BRAHMASMI_TEST_MODE": "1", "AHAM_BRAHMASMI_TEST_CRASH_POINT": "checkpoint_after_pending"})
            self.assertEqual(interrupted.returncode, 86, interrupted.stderr)
            issue_session(workspace, source="startup_controller", requested_runtime="local", runtime="local", mode="regular",
                          capabilities=["write_files"], allowed_operations=["checkpoint", "recover_checkpoint", "wrap_up", "recover_wrap_up"])
            identity = json.loads((workspace / "BRAIN.json").read_text())["workspace_id"]
            before = self.snapshot(workspace)
            bad = self.run_aham("recover-access", "--workspace", str(workspace), "--confirm", "wrong")
            self.assertNotEqual(bad.returncode, 0)
            self.assertEqual(self.snapshot(workspace), before)
            granted = self.run_aham("recover-access", "--workspace", str(workspace), "--confirm", identity)
            self.assertEqual(granted.returncode, 0, granted.stdout + granted.stderr)
            session = json.loads(granted.stdout)
            self.assertEqual(session["allowed_operations"], ["recover_checkpoint", "recover_wrap_up"])
            with self.assertRaises(StateError):
                require_operation_authority(workspace, "recover_checkpoint")
            with self.assertRaises(StateError):
                require_operation_authority(workspace, "checkpoint", session_id=session["session_id"])
            recovered = self.run_aham("save", "--workspace", str(workspace), "--recover-pending", "--session-id", session["session_id"])
            self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
            self.assertIn("CHECKPOINT VERIFIED", recovered.stdout)
            self.assertFalse((workspace / "state/pending_checkpoint.json").exists())

    def test_pending_checkpoint_reports_plain_recovery_and_changes_nothing(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = self.workspace(Path(temporary))
            (workspace / "state/pending_checkpoint.json").write_text("{}")
            before = self.snapshot(workspace)
            result = self.run_aham("check", "--workspace", str(workspace), "--json")
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            self.assertFalse(report["ready_for_new_work"])
            finding = next(item for item in report["findings"] if item["name"] == "Interrupted checkpoint")
            self.assertIn("aham.py", finding["action"])
            self.assertIn("--recover-pending", finding["action"])
            self.assertIn("--session-id", finding["action"])
            self.assertEqual(self.snapshot(workspace), before)

    @unittest.skipUnless(os.name == "posix", "POSIX mode check")
    def test_doctor_detects_open_workspace_permissions_without_chmod(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = self.workspace(Path(temporary)); workspace.chmod(0o755)
            before = self.snapshot(workspace)
            result = self.run_aham("check", "--workspace", str(workspace), "--json")
            self.assertNotEqual(result.returncode, 0)
            report = json.loads(result.stdout)
            permission = next(item for item in report["findings"] if item["name"] == "Workspace permissions")
            self.assertEqual(permission["status"], "action_needed")
            self.assertIn("0700", permission["action"])
            self.assertEqual(self.snapshot(workspace), before)

    def test_doctor_reports_corrupt_store_as_action_not_traceback(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = self.workspace(Path(temporary))
            (workspace / "state/store.json").write_text("not JSON")
            before = self.snapshot(workspace)
            result = self.run_aham("check", "--workspace", str(workspace), "--json")
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("Traceback", result.stderr)
            report = json.loads(result.stdout)
            self.assertFalse(report["ready_for_new_work"])
            self.assertEqual(self.snapshot(workspace), before)

    def test_doctor_refuses_store_ahead_of_missing_ledger(self):
        from state_store import STORE_FORMAT, STORE_VERSION
        with tempfile.TemporaryDirectory() as temporary:
            workspace = self.workspace(Path(temporary))
            (workspace / "state/store.json").write_text(json.dumps({"format": STORE_FORMAT, "version": STORE_VERSION,
                "revision": 1, "last_operation_id": "missing", "last_record": "state/operations/missing.json"}))
            before = self.snapshot(workspace)
            result = self.run_aham("check", "--workspace", str(workspace), "--json")
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(json.loads(result.stdout)["ready_for_new_work"])
            self.assertEqual(self.snapshot(workspace), before)

    def test_requested_invalid_bridge_blocks_readiness(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = self.workspace(Path(temporary))
            project = Path(temporary) / "project"; project.mkdir()
            result = self.run_aham("connect", "--workspace", str(workspace), "--project", str(project), "--runtime", "local")
            self.assertEqual(result.returncode, 0, result.stderr)
            (project / ".aham/runtime.json").write_text("{}")
            before = self.snapshot(workspace)
            result = self.run_aham("check", "--workspace", str(workspace), "--project", str(project), "--json")
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(json.loads(result.stdout)["ready_for_new_work"])
            self.assertEqual(self.snapshot(workspace), before)

    def test_bridge_status_refuses_configuration_selected_instruction_path(self):
        from runtime_bridge import load_status
        from state_io import StateError
        with tempfile.TemporaryDirectory() as temporary:
            workspace = self.workspace(Path(temporary))
            project = Path(temporary) / "project"; project.mkdir()
            result = self.run_aham("connect", "--workspace", str(workspace), "--project", str(project), "--runtime", "local")
            self.assertEqual(result.returncode, 0, result.stderr)
            outside = Path(temporary) / "outside.md"; outside.write_text("Synthetic outside instruction data")
            path = project / ".aham/runtime.json"; config = json.loads(path.read_text())
            config["instruction_file"] = "../outside.md"; path.write_text(json.dumps(config))
            with self.assertRaises(StateError):
                load_status(project)
            self.assertEqual(outside.read_text(), "Synthetic outside instruction data")

    def test_recovery_access_without_pending_work_is_read_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = self.workspace(Path(temporary))
            identity = json.loads((workspace / "BRAIN.json").read_text())["workspace_id"]
            before = self.snapshot(workspace)
            result = self.run_aham("recover-access", "--workspace", str(workspace), "--confirm", identity)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(self.snapshot(workspace), before)

    @unittest.skipUnless(os.name == "posix", "POSIX directory permissions")
    def test_setup_permission_refusal_has_no_traceback_or_parent_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary) / "blocked"; parent.mkdir(); parent.chmod(0)
            try:
                result = self.run_aham("setup", "--workspace", str(parent / "workspace"))
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(stat.S_IMODE(parent.stat().st_mode), 0)
            finally:
                parent.chmod(0o700)

    def test_linked_destination_is_refused_without_changing_target(self):
        if os.name != "posix": self.skipTest("POSIX symlink fixture")
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "target"; target.mkdir()
            alias = Path(temporary) / "alias"; alias.symlink_to(target, target_is_directory=True)
            before = self.snapshot(target)
            result = self.run_aham("setup", "--workspace", str(alias))
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(self.snapshot(target), before)

    def test_default_location_and_sync_root_containment(self):
        from onboarding import default_workspace, sync_root_warning
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            for platform in ("linux", "darwin"):
                default = default_workspace(platform=platform, home=home)
                self.assertIsNone(sync_root_warning(default, platform=platform, home=home, environ={}))
                self.assertNotIn("Desktop", default.parts)
                self.assertNotIn("Documents", default.parts)
            root = home / "Library/CloudStorage/Dropbox-Test"
            root.mkdir(parents=True)
            warning = sync_root_warning(root / "workspace", platform="darwin", home=home, environ={})
            self.assertIsNotNone(warning)
            self.assertIsNone(sync_root_warning(home / "Library/CloudStorage-adjacent/workspace", platform="darwin", home=home, environ={}))
            self.assertIsNotNone(sync_root_warning(home / "sync/workspace", platform="win32", home=home,
                                                  environ={"OneDrive": str(home / "sync")}))

    def test_unsupported_platform_and_python_are_actionable(self):
        from onboarding import preflight
        for platform, version in (("unsupported-os", (3, 14)), ("linux", (3, 9)), ("darwin", (3, 15))):
            with self.subTest(platform=platform, version=version):
                report = preflight(platform=platform, version=version)
                self.assertFalse(report["supported"])
                self.assertTrue(report["action"])

    def test_readme_is_short_and_generated_status_has_new_home(self):
        readme = (ROOT / "README.md").read_text()
        status = ROOT / "docs/STATUS.md"
        self.assertTrue(status.is_file())
        self.assertNotIn("<!-- runtime-evidence-status:start -->", readme)
        self.assertIn("<!-- runtime-evidence-status:start -->", status.read_text())
        self.assertIn("https://github.com/loud-whisper/Aham-Brahmasmi", readme)
        self.assertIn("docs/GET_AN_ASSISTANT.md", readme)
        self.assertLessEqual(len(readme.encode()), 9000)

    def test_walkthrough_protocol_preserves_pending_human_gate(self):
        protocol = ROOT / "docs/dev/WALKTHROUGH_PROTOCOL.md"
        self.assertTrue(protocol.is_file())
        text = protocol.read_text()
        for term in ("two or three", "synthetic", "switch", "interrupted", "no Git or Python"):
            self.assertIn(term, text)
        self.assertIn("- [ ] Fresh user completes setup", (ROOT / "docs/ARCHITECTURE_REMEDIATION_CHECKLIST.md").read_text())


if __name__ == "__main__":
    unittest.main()
