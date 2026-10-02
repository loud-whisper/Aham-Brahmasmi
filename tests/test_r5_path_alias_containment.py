from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from state_io import StateError, require_managed_path  # noqa: E402


SETUP = ROOT / "scripts" / "setup_workspace.py"


class R5PathAliasContainmentTests(unittest.TestCase):
    def test_ancestor_alias_is_canonicalized_without_weakening_inner_symlink_guard(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            real_parent = root / "real-parent"
            real_parent.mkdir()
            alias_parent = root / "alias-parent"
            try:
                alias_parent.symlink_to(real_parent, target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"directory symlinks unavailable: {exc}")

            workspace = alias_parent / "workspace"
            result = subprocess.run(
                [sys.executable, str(SETUP), "--workspace", str(workspace)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

            managed = require_managed_path(workspace, workspace / "state" / "store.json")
            self.assertEqual(managed, (real_parent / "workspace" / "state" / "store.json").resolve())

            real_leaf = real_parent / "workspace" / "projects" / "real-leaf"
            real_leaf.mkdir()
            managed_alias = real_parent / "workspace" / "projects" / "managed-alias"
            managed_alias.symlink_to(real_leaf, target_is_directory=True)
            with self.assertRaises(StateError):
                require_managed_path(
                    real_parent / "workspace",
                    managed_alias / "should-not-be-reached.txt",
                    label="R5 inner symlink fixture",
                )


if __name__ == "__main__":
    unittest.main()
