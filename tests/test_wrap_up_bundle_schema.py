from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "scripts" / "setup_workspace.py"
WRAP_UP = ROOT / "scripts" / "wrap_up.py"


class WrapUpBundleSchemaTests(unittest.TestCase):
    def run_script(self, script: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(script), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def make_workspace(self, root: Path) -> Path:
        workspace = root / "workspace"
        result = self.run_script(SETUP, "--workspace", str(workspace))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return workspace

    def test_intuitive_aliases_route_without_losing_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            bundle_path = root / "bundle.json"
            bundle = {
                "session_id": "alias-session",
                "facts": ["Alias durable fact"],
                "lessons": ["Alias reusable lesson"],
                "projects": [{"name": "Alias Project", "update": "Alias project update."}],
                "history": ["Alias history item."],
                "checkpoint": {
                    "summary": "Alias bundle wrapped",
                    "completed": ["Processed alias-shaped bundle"],
                    "next": "Verify alias routing.",
                    "project": "Alias Project",
                },
            }
            bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

            wrapped = self.run_script(WRAP_UP, "--workspace", str(workspace), "--bundle", str(bundle_path))
            self.assertEqual(wrapped.returncode, 0, wrapped.stderr + wrapped.stdout)
            self.assertIn("WRAP UP VERIFIED", wrapped.stdout)
            self.assertIn("Alias durable fact", (workspace / "MEMORY.md").read_text(encoding="utf-8"))
            self.assertIn("Alias reusable lesson", (workspace / "LESSONS.md").read_text(encoding="utf-8"))
            registry = json.loads((workspace / "state" / "projects.json").read_text(encoding="utf-8"))["projects"]
            project_id = next(pid for pid, entry in registry.items() if entry["display_name"] == "Alias Project")
            self.assertIn(
                "Alias project update.",
                (workspace / "projects" / f"{project_id}.md").read_text(encoding="utf-8"),
            )

            archive = json.loads((workspace / "state" / "wrapups" / "alias-session.json").read_text(encoding="utf-8"))
            self.assertEqual(archive["bundle"]["durable_facts"], ["Alias durable fact"])
            self.assertEqual(archive["bundle"]["reusable_lessons"], ["Alias reusable lesson"])
            self.assertEqual(
                archive["bundle"]["project_updates"],
                [{"project": "Alias Project", "content": "Alias project update."}],
            )
            self.assertEqual(archive["bundle"]["checkpoint"]["next_steps"], ["Verify alias routing."])

    def test_unknown_top_level_field_is_rejected_instead_of_silently_dropped(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            bundle_path = root / "bundle.json"
            bundle = {
                "session_id": "bad-session",
                "factz": ["This must not disappear silently"],
                "checkpoint": {"summary": "Should fail"},
            }
            bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

            wrapped = self.run_script(WRAP_UP, "--workspace", str(workspace), "--bundle", str(bundle_path))
            self.assertNotEqual(wrapped.returncode, 0)
            self.assertIn("unknown field(s): factz", wrapped.stderr)
            self.assertFalse((workspace / "state" / "pending_wrap_up.json").exists())

    def test_canonical_and_alias_field_conflict_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            bundle_path = root / "bundle.json"
            bundle = {
                "session_id": "conflict-session",
                "durable_facts": ["Canonical fact"],
                "facts": ["Alias fact"],
                "checkpoint": {"summary": "Should fail"},
            }
            bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

            wrapped = self.run_script(WRAP_UP, "--workspace", str(workspace), "--bundle", str(bundle_path))
            self.assertNotEqual(wrapped.returncode, 0)
            self.assertIn("cannot contain both 'durable_facts' and alias 'facts'", wrapped.stderr)


if __name__ == "__main__":
    unittest.main()
