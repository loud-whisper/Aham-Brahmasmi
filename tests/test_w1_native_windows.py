"""Windows lifecycle and lock regressions; local doubles are not native evidence."""
from __future__ import annotations

import errno
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import onboarding
import state_store
from state_io import StateError, require_managed_path
from portable_backup import PortableError, ensure_portable_path_uniqueness


class WindowsTests(unittest.TestCase):
    def workspace(self, root):
        workspace = root / "Brain space Ω"
        result = subprocess.run([sys.executable, str(ROOT / "aham.py"), "setup", "--workspace", str(workspace)],
                                text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return workspace

    def test_windows_preflight_accepts_supported_python(self):
        self.assertTrue(onboarding.preflight(platform="win32", version=(3, 10))["supported"])
        self.assertTrue(onboarding.preflight(platform="win32", version=(3, 14))["supported"])
        self.assertFalse(onboarding.preflight(platform="win32", version=(3, 9))["supported"])

    def test_python_provider_script_preserves_literal_arguments_without_shell(self):
        import json
        import semantic_memory
        with tempfile.TemporaryDirectory() as temporary:
            script = Path(temporary) / "provider space.py"
            script.write_text("import json,sys; print(json.dumps(sys.argv[1:]))", encoding="utf-8")
            arguments = ["search", "literal & echo ; $HOME %PATH% Ω"]
            with patch.object(semantic_memory.shutil, "which", return_value=str(script)):
                result = semantic_memory.run_provider(*arguments)
            self.assertEqual(json.loads(result.stdout), arguments)

    def test_windows_recovery_guidance_quotes_powershell_literal_paths(self):
        import recovery_commands
        arguments = ["C:\\Program Files\\Python\\python.exe", "C:\\owner's folder\\aham.py", "save"]
        command = recovery_commands.format_command(arguments, platform="win32")
        self.assertEqual(command, "& 'C:\\Program Files\\Python\\python.exe' 'C:\\owner''s folder\\aham.py' 'save'")

    @unittest.skipUnless(os.name == "nt", "execute recovery guidance in real Windows PowerShell")
    def test_native_powershell_guidance_preserves_argument_bytes(self):
        import json
        import recovery_commands
        arguments = ["owner's folder & $HOME %PATH% Ω"]
        command = recovery_commands.format_command([sys.executable, "-c", "import json,sys; print(json.dumps(sys.argv[1:]))", *arguments])
        result = subprocess.run(["pwsh", "-NoProfile", "-Command", command], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), arguments)

    def test_portable_paths_refuse_windows_aliases_and_devices(self):
        for name in ["CON", "nul.txt", "aux", "COM1.md", "LPT9", "COM¹.txt", "name.",
                     "name ", "file:stream", "bad?name", "bad\\name", "bad\x01name"]:
            with self.subTest(name=name), self.assertRaises(PortableError):
                ensure_portable_path_uniqueness(["projects/" + name])
        ensure_portable_path_uniqueness(["projects/Ω project.md", "projects/company.md"])

    def test_windows_managed_path_refuses_stream_and_device_names_before_writing(self):
        import state_io
        with tempfile.TemporaryDirectory() as temporary:
            workspace = self.workspace(Path(temporary))
            with patch.object(state_io, "IS_WINDOWS", True, create=True):
                for path in ["projects/nul.txt", "projects/file:stream", "projects/name."]:
                    with self.subTest(path=path), self.assertRaises(StateError):
                        require_managed_path(workspace, path)
            self.assertEqual(list((workspace / "projects").glob("nul*")), [])

    def test_windows_validation_precedes_native_path_alias_normalization(self):
        import state_io
        with tempfile.TemporaryDirectory() as temporary:
            workspace = self.workspace(Path(temporary))
            absolute = state_io._absolute_without_resolving
            def normalized(path): return absolute(Path(str(path).rstrip(". ")))
            with patch.object(state_io, "IS_WINDOWS", True), patch.object(state_io, "_absolute_without_resolving", normalized):
                with self.assertRaises(StateError): require_managed_path(workspace, "projects/name.")

    def test_setup_refuses_windows_invalid_destination_before_copying(self):
        import argparse
        import contextlib
        import io
        from types import SimpleNamespace
        import setup_workspace
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            arguments = argparse.Namespace(workspace=str(root / "Brain."), trust_runtime=[])
            with patch.object(setup_workspace, "parse_args", return_value=arguments), patch.object(setup_workspace, "os", SimpleNamespace(name="nt")), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result = setup_workspace.main()
            self.assertNotEqual(result, 0)
            self.assertEqual(list(root.iterdir()), [])

    def test_windows_acl_policy_refuses_broad_or_unprotected_access(self):
        from windows_access import acl_issue
        owner = "S-1-5-21-1-2-3-1001"
        allowed = {owner: 0x1f01ff, "S-1-5-18": 0x1f01ff, "S-1-5-32-544": 0x1f01ff}
        self.assertIsNone(acl_issue(owner, owner, True, allowed))
        for actual_owner, protected, grants in [(owner, False, allowed), ("S-1-5-21-foreign", True, allowed),
            (owner, True, {**allowed, "S-1-1-0": 0x120089}), (owner, True, {"S-1-5-18": 0x1f01ff})]:
            with self.subTest(owner=actual_owner, protected=protected, grants=grants):
                self.assertIsNotNone(acl_issue(actual_owner, owner, protected, grants))

    @unittest.skipUnless(os.name == "nt", "native Windows protected ACL")
    def test_native_workspace_and_bridge_have_private_acl_and_doctor_detects_drift(self):
        from windows_access import permission_issue
        import json
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); workspace = self.workspace(root)
            self.assertIsNone(permission_issue(workspace))
            project = root / "project"; project.mkdir()
            connected = subprocess.run([sys.executable, str(ROOT / "aham.py"), "connect", "--workspace", str(workspace),
                                       "--project", str(project), "--runtime", "local"], text=True, capture_output=True)
            self.assertEqual(connected.returncode, 0, connected.stdout + connected.stderr)
            self.assertIsNone(permission_issue(project / ".aham"))
            export = root / "export"
            exported = subprocess.run([sys.executable, str(ROOT / "aham.py"), "backup", "--workspace", str(workspace),
                                       "--output", str(export)], text=True, capture_output=True)
            self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
            self.assertIsNone(permission_issue(export))
            restored = root / "restored"
            restored_result = subprocess.run([sys.executable, str(ROOT / "aham.py"), "restore", "--input", str(export),
                                              "--workspace", str(restored)], text=True, capture_output=True)
            self.assertEqual(restored_result.returncode, 0, restored_result.stdout + restored_result.stderr)
            self.assertIsNone(permission_issue(restored))
            changed = subprocess.run(["icacls.exe", str(workspace), "/grant", "*S-1-1-0:(RX)"],
                                     text=True, errors="replace", capture_output=True)
            self.assertEqual(changed.returncode, 0, changed.stdout + changed.stderr)
            self.assertIsNotNone(permission_issue(workspace))
            result = subprocess.run([sys.executable, str(ROOT / "aham.py"), "check", "--workspace", str(workspace), "--json"],
                                    text=True, capture_output=True)
            self.assertFalse(json.loads(result.stdout)["ready_for_new_work"])

    @unittest.skipUnless(os.name == "nt", "native Windows long-path filesystem")
    def test_native_long_local_paths_checkpoint_without_shortening_or_redirecting(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / ("a" * 110) / ("b" * 110) / ("c" * 60)
            workspace = self.workspace(root)
            self.assertGreater(len(str(workspace)), 260)
            result = subprocess.run([sys.executable, str(ROOT / "aham.py"), "save", "--workspace", str(workspace),
                                     "--summary", "Synthetic long path checkpoint"], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("CHECKPOINT VERIFIED", result.stdout)
            self.assertTrue((workspace / "state/store.json").is_file())

    def test_managed_reparse_component_is_refused(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as temporary:
            workspace = self.workspace(Path(temporary))
            real_lstat = Path.lstat
            def lstat(path, *args, **kwargs):
                value = real_lstat(path, *args, **kwargs)
                if path.resolve() == (workspace / "projects").resolve():
                    return SimpleNamespace(st_mode=value.st_mode, st_file_attributes=0x400)
                return value
            with patch.object(Path, "lstat", lstat), self.assertRaises(StateError):
                require_managed_path(workspace, "projects/outside.md")

    def test_bridge_and_reviewed_tree_refuse_reparse_aliases(self):
        from types import SimpleNamespace
        from runtime_bridge import safe_bridge_dir
        from external_identity import tree_digest
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary); bridge = project / ".aham"; bridge.mkdir()
            (bridge / "file.md").write_text("synthetic")
            real_lstat = Path.lstat
            def lstat(path, *args, **kwargs):
                value = real_lstat(path, *args, **kwargs)
                if path.resolve() == bridge.resolve():
                    return SimpleNamespace(st_mode=value.st_mode, st_file_attributes=0x400)
                return value
            with patch.object(Path, "lstat", lstat):
                with self.subTest(path="bridge"), self.assertRaises(StateError): safe_bridge_dir(project, create=True)
                with self.subTest(path="source"), self.assertRaises(StateError): tree_digest(project)

    def test_windows_lock_contention_times_out_without_changing_ledger(self):
        from types import SimpleNamespace
        def denied(*args): raise OSError(errno.EACCES, "synthetic busy lock")
        with tempfile.TemporaryDirectory() as temporary:
            workspace = self.workspace(Path(temporary))
            before = (workspace / "state/session_authority.json").read_bytes()
            api = SimpleNamespace(LK_NBLCK=2, LK_UNLCK=0, locking=denied)
            with patch.object(state_store, "fcntl", None), patch.object(state_store, "msvcrt", api, create=True), patch.object(state_store, "WINDOWS_LOCK_TIMEOUT", 0):
                with self.assertRaisesRegex(StateError, "timed out"):
                    with state_store.writer_lock(workspace): self.fail("contended writer entered")
            self.assertEqual((workspace / "state/session_authority.json").read_bytes(), before)

    @unittest.skipUnless(os.name == "posix", "native Windows behavior is covered by hosted concurrency")
    def test_windows_backend_releases_real_lock_on_failure_and_keeps_lock_file(self):
        import fcntl
        class WindowsAPI:
            LK_NBLCK = 2
            LK_UNLCK = 0
            @staticmethod
            def locking(descriptor, mode, count):
                if os.lseek(descriptor, 0, os.SEEK_CUR) != 0 or count != 1:
                    raise OSError(errno.EINVAL, "wrong lock region")
                fcntl.flock(descriptor, fcntl.LOCK_UN if mode == 0 else fcntl.LOCK_EX | fcntl.LOCK_NB)
        with tempfile.TemporaryDirectory() as temporary:
            workspace = self.workspace(Path(temporary))
            with patch.object(state_store, "fcntl", None), patch.object(state_store, "msvcrt", WindowsAPI, create=True):
                with self.assertRaisesRegex(RuntimeError, "synthetic"):
                    with state_store.writer_lock(workspace):
                        raise RuntimeError("synthetic")
                with state_store.writer_lock(workspace) as store:
                    self.assertEqual(store["revision"], 0)
            self.assertTrue((workspace / "state/.writer.lock").is_file())

    def test_independent_lock_is_released_after_holder_is_killed(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = self.workspace(Path(temporary))
            code = ("import sys,time; from pathlib import Path; sys.path.insert(0,sys.argv[1]); "
                    "from state_store import writer_lock\n"
                    "with writer_lock(Path(sys.argv[2])):\n print('HELD',flush=True); time.sleep(30)\n")
            holder = subprocess.Popen([sys.executable, "-c", code, str(ROOT / "scripts"), str(workspace)],
                                      text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                self.assertEqual(holder.stdout.readline().strip(), "HELD")
                holder.kill(); holder.communicate(timeout=10)
                with state_store.writer_lock(workspace) as store:
                    self.assertEqual(store["revision"], 0)
            finally:
                if holder.poll() is None: holder.kill()
                holder.communicate(timeout=10)

    @unittest.skipUnless(os.name == "nt", "real Windows junction filesystem")
    def test_native_junction_component_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); workspace = self.workspace(root)
            outside = root / "outside"; outside.mkdir()
            junction = workspace / "projects/junction"
            made = subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(outside)],
                                  text=True, errors="replace", capture_output=True)
            self.assertEqual(made.returncode, 0, made.stdout + made.stderr)
            try:
                with self.assertRaises(StateError):
                    require_managed_path(workspace, "projects/junction/escape.md")
                self.assertEqual(list(outside.iterdir()), [])
            finally:
                junction.rmdir()


if __name__ == "__main__":
    unittest.main()
