from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from windows_access import create_private_directory
SETUP = ROOT / "scripts" / "setup_workspace.py"
BRIDGE = ROOT / "scripts" / "runtime_bridge.py"
START = "<!-- aham-brahmasmi:runtime-instructions:start -->"
END = "<!-- aham-brahmasmi:runtime-instructions:end -->"


class RuntimeBridgeTests(unittest.TestCase):
    def run_tool(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(BRIDGE), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def make_workspace(self, root: Path) -> Path:
        workspace = root / "workspace"
        result = subprocess.run(
            [sys.executable, str(SETUP), "--workspace", str(workspace)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return workspace

    def install(self, runtime: str, workspace: Path, project: Path) -> subprocess.CompletedProcess[str]:
        return self.run_tool(
            "install",
            "--runtime",
            runtime,
            "--workspace",
            str(workspace),
            "--project",
            str(project),
        )

    def test_claude_bridge_creates_import_and_lifecycle_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            project = root / "project"
            project.mkdir()

            result = self.install("claude", workspace, project)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            claude = (project / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertIn("@.aham/runtime.md", claude)
            self.assertEqual(claude.count(START), 1)
            bridge = (project / ".aham" / "runtime.md").read_text(encoding="utf-8")
            self.assertIn("aham.py start", bridge)
            self.assertIn("aham.py save", bridge)
            self.assertIn("aham.py resume", bridge)
            self.assertIn("aham.py wrap-up", bridge)
            self.assertIn("capabilities actually verified", bridge)
            self.assertIn("Never record intended work as completed work", bridge)
            self.assertIn("CHECKPOINT VERIFIED", bridge)
            self.assertIn("WRAP UP VERIFIED", bridge)
            self.assertIn("Never invent, paraphrase, or simulate successful tool output", bridge)

    def test_local_paths_are_kept_in_git_ignored_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            project = root / "project"
            project.mkdir()
            result = self.install("claude", workspace, project)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            bridge = (project / ".aham" / "runtime.md").read_text(encoding="utf-8")
            self.assertNotIn(str(workspace), bridge)
            self.assertNotIn(str(ROOT), bridge)
            config = json.loads((project / ".aham" / "runtime.json").read_text(encoding="utf-8"))
            self.assertEqual(config["workspace"], str(workspace.resolve()))
            self.assertEqual(config["framework_root"], str(ROOT.resolve()))
            ignore = (project / ".aham" / ".gitignore").read_text(encoding="utf-8")
            self.assertIn("runtime.json", ignore.splitlines())

    def test_gemini_bridge_preserves_existing_instructions_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            project = root / "project"
            project.mkdir()
            gemini_path = project / "GEMINI.md"
            gemini_path.write_text("# Existing rules\n\nKeep this text.\n", encoding="utf-8")

            first = self.install("gemini", workspace, project)
            second = self.install("gemini", workspace, project)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            text = gemini_path.read_text(encoding="utf-8")
            self.assertIn("Keep this text.", text)
            self.assertIn("@.aham/runtime.md", text)
            self.assertEqual(text.count(START), 1)
            self.assertEqual(text.count(END), 1)

    def test_codex_bridge_preserves_existing_agents_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            project = root / "project"
            project.mkdir()
            agents = project / "AGENTS.md"
            agents.write_text("# Project instructions\n\nNever edit generated files.\n", encoding="utf-8")

            result = self.install("codex", workspace, project)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            text = agents.read_text(encoding="utf-8")
            self.assertIn("Never edit generated files.", text)
            self.assertIn("Read and follow .aham/runtime.md", text)
            self.assertEqual(text.count(START), 1)

    def test_local_bridge_requires_manual_read_and_modifies_no_native_instruction_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            project = root / "project"
            project.mkdir()

            result = self.install("local", workspace, project)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Automatic instruction-file activation: unavailable", result.stdout)
            self.assertIn("Read and follow .aham/runtime.md", result.stdout)
            self.assertTrue((project / ".aham" / "runtime.md").is_file())
            self.assertFalse((project / "CLAUDE.md").exists())
            self.assertFalse((project / "GEMINI.md").exists())
            self.assertFalse((project / "AGENTS.md").exists())

    def test_status_reports_installed_bridge(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            project = root / "project"
            project.mkdir()
            result = self.install("claude", workspace, project)
            self.assertEqual(result.returncode, 0)

            status = self.run_tool("status", "--project", str(project), "--json")
            self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
            payload = json.loads(status.stdout)
            self.assertTrue(payload["installed"])
            self.assertTrue(payload["managed_bridge"])
            self.assertTrue(payload["runtime_instruction"])
            self.assertTrue(payload["local_config_ignored"])
            self.assertEqual(payload["configuration"]["runtime"], "claude")

    def test_remove_deletes_only_managed_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            project = root / "project"
            project.mkdir()
            agents = project / "AGENTS.md"
            agents.write_text("# Existing\n\nKeep me.\n", encoding="utf-8")
            self.assertEqual(self.install("codex", workspace, project).returncode, 0)

            removed = self.run_tool("remove", "--project", str(project))
            self.assertEqual(removed.returncode, 0, removed.stdout + removed.stderr)
            text = agents.read_text(encoding="utf-8")
            self.assertIn("Keep me.", text)
            self.assertNotIn(START, text)
            self.assertNotIn("Read and follow .aham/runtime.md", text)
            self.assertFalse((project / ".aham" / "runtime.md").exists())
            self.assertFalse((project / ".aham" / "runtime.json").exists())

    def test_refuses_unmanaged_runtime_bridge_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            project = root / "project"
            project.mkdir()
            create_private_directory(project / ".aham")
            unmanaged = project / ".aham" / "runtime.md"
            unmanaged.write_text("someone else's file\n", encoding="utf-8")

            result = self.install("claude", workspace, project)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unmanaged", result.stderr.lower())
            self.assertEqual(unmanaged.read_text(encoding="utf-8"), "someone else's file\n")

    def test_refuses_symlinked_bridge_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            project = root / "project"
            project.mkdir()
            elsewhere = root / "elsewhere"
            elsewhere.mkdir()
            try:
                (project / ".aham").symlink_to(elsewhere, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")

            result = self.install("claude", workspace, project)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("symlinked", result.stderr.lower())
            self.assertFalse((elsewhere / "runtime.md").exists())

    def test_malformed_managed_markers_block_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            project = root / "project"
            project.mkdir()
            claude = project / "CLAUDE.md"
            claude.write_text(f"Existing\n{START}\nunterminated\n", encoding="utf-8")

            result = self.install("claude", workspace, project)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("malformed", result.stderr.lower())
            self.assertIn("unterminated", claude.read_text(encoding="utf-8"))

    def test_contract_keeps_unknown_and_local_manual(self) -> None:
        contract = json.loads((ROOT / "core" / "runtime_adapter.json").read_text(encoding="utf-8"))
        self.assertEqual(contract["runtimes"]["local"]["mode"], "manual")
        self.assertEqual(contract["runtimes"]["unknown"]["mode"], "manual")
        self.assertIn("never record intended work as completed work", [s.lower() for s in contract["required_behaviors"]])
        self.assertIn(".aham/runtime.json", contract["local_configuration"])


if __name__ == "__main__":
    unittest.main()
