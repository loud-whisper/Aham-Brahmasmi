"""Unavailable-backend refusal preserves state on every supported platform.

Both lock backends are explicitly removed in the child. W1's native process
tests and hosted portability suite separately establish Windows lifecycle scope.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class WindowsBoundaryTests(unittest.TestCase):
    def run_tool(self, script: str, *arguments: str, unsupported_lock: bool = False):
        path = SCRIPTS / script
        if unsupported_lock:
            command = [sys.executable, "-c", (
                "import runpy,sys; from pathlib import Path; "
                "sys.path.insert(0,str(Path(sys.argv[1]).parent)); "
                "import state_store; state_store.fcntl=None; state_store.msvcrt=None; "
                "sys.argv=sys.argv[1:]; runpy.run_path(sys.argv[0],run_name='__main__')"
            ), str(path), *arguments]
        else:
            command = [sys.executable, str(path), *arguments]
        return subprocess.run(command, text=True, encoding="utf-8", capture_output=True,
                              timeout=30, env={**os.environ, "PYTHONUTF8": "1"})

    def snapshot(self, workspace: Path):
        return {path.relative_to(workspace).as_posix():
                ("file", path.read_bytes()) if path.is_file() else ("directory", None)
                for path in workspace.rglob("*")}

    def test_structure_verification_and_unsupported_operations_preserve_workspace(self):
        # Removing the writer's unsupported-platform refusal must fail this test:
        # no session, revision, pending operation or export may appear after denial.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "Brain space Ω"
            setup = self.run_tool("setup_workspace.py", "--workspace", str(workspace))
            self.assertEqual(setup.returncode, 0, setup.stdout + setup.stderr)
            verified = self.run_tool("verify_workspace.py", "--workspace", str(workspace))
            self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
            self.assertIn("WORKSPACE VERIFIED", verified.stdout)
            before = self.snapshot(workspace)
            cases = [
                ("startup.py", "--runtime", "codex", "--mode", "regular",
                 "--capability", "write_files", "--json"),
                ("startup.py", "--runtime", "unknown", "--mode", "degraded_offline", "--json"),
                ("checkpoint.py", "--summary", "Synthetic refused checkpoint"),
                ("portable_backup.py", "export", "--output", str(root / "export")),
            ]
            for script, *arguments in cases:
                with self.subTest(script=script, arguments=arguments):
                    result = self.run_tool(script, *arguments, "--workspace", str(workspace),
                                           unsupported_lock=True)
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn("writer coordination is unavailable", result.stderr)
                    self.assertNotIn("BRAIN READY", result.stdout)
                    self.assertNotIn("CHECKPOINT VERIFIED", result.stdout)
                    self.assertEqual(self.snapshot(workspace), before)
                    self.assertFalse((root / "export").exists())


if __name__ == "__main__":
    unittest.main()
