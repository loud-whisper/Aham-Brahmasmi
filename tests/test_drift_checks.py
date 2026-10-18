from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import install_command_guard
import runtime_bridge


class WorkspaceDriftTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name).resolve() / "workspace"
        shutil.copytree(ROOT / "templates/private-workspace", self.workspace)
        brain = json.loads((self.workspace / "BRAIN.json").read_text())
        brain["workspace_id"] = "a" * 32
        (self.workspace / "BRAIN.json").write_text(json.dumps(brain), encoding="utf-8")
        self.index = {
            "format": "aham-brahmasmi-workspace-index", "version": 1,
            "files": ["BRAIN.json", "INDEX.json", "README.md", "MEMORY.md", "TODO.md", "LESSONS.md"],
            "projects": [], "startup_budget_bytes": 65536,
        }
        self.save_index()

    def save_index(self):
        (self.workspace / "INDEX.json").write_text(json.dumps(self.index), encoding="utf-8")

    def run_tool(self, script="verify_workspace.py", *extra):
        return subprocess.run([sys.executable, str(ROOT / "scripts" / script),
                               "--workspace", str(self.workspace), *extra],
                              capture_output=True, text=True, timeout=30)

    def assert_refused(self, phrase, script="verify_workspace.py", *extra):
        result = self.run_tool(script, *extra)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(phrase, result.stdout + result.stderr)

    def test_clean_workspace_and_indexed_project_pass(self):
        folder = self.workspace / "projects/demo"
        folder.mkdir()
        (folder / "PROJECT.md").write_text("# Demo\n", encoding="utf-8")
        self.index["projects"] = ["demo"]
        self.save_index()
        result = self.run_tool()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_setup_template_has_index(self):
        self.assertTrue((ROOT / "templates/private-workspace/INDEX.json").is_file())

    def test_unindexed_top_level_instruction_or_state_fails(self):
        for name in ("AGENTS.md", "CLAUDE.md", "GEMINI.md", "EXTRA_STATE.json", ".cursorrules"):
            with self.subTest(name=name):
                path = self.workspace / name
                path.write_text("extra context", encoding="utf-8")
                self.assert_refused("unindexed top-level file: " + name)
                path.unlink()

    def test_indexed_extra_instruction_passes(self):
        (self.workspace / "AGENTS.md").write_text("# Rules\n", encoding="utf-8")
        self.index["files"].append("AGENTS.md")
        self.save_index()
        self.assertEqual(self.run_tool().returncode, 0)

    def test_project_folder_without_record_fails(self):
        (self.workspace / "projects/demo").mkdir()
        self.index["projects"] = ["demo"]
        self.save_index()
        self.assert_refused("missing project record: projects/demo/PROJECT.md")

    def test_project_folder_missing_from_list_fails(self):
        folder = self.workspace / "projects/demo"
        folder.mkdir()
        (folder / "PROJECT.md").write_text("# Demo\n", encoding="utf-8")
        self.assert_refused("unlisted project folder: demo")

    def test_listed_missing_folder_and_file_fail(self):
        self.index["projects"] = ["missing"]
        self.index["files"].append("missing.md")
        self.save_index()
        self.assert_refused("missing indexed file: missing.md")
        self.assert_refused("missing listed project folder: missing")

    def test_missing_or_malformed_index_fails(self):
        (self.workspace / "INDEX.json").unlink()
        self.assert_refused("INDEX.json")
        for value in ([], {}, {**self.index, "startup_budget_bytes": True},
                      {**self.index, "startup_budget_bytes": 0},
                      {**self.index, "files": ["../escape.md"]},
                      {**self.index, "projects": ["../escape"]},
                      {**self.index, "files": self.index["files"] * 2}):
            with self.subTest(value=value):
                (self.workspace / "INDEX.json").write_text(json.dumps(value), encoding="utf-8")
                self.assert_refused("INDEX.json")

    def test_startup_source_budget_fails_validation_and_startup(self):
        self.index["startup_budget_bytes"] = 1
        self.save_index()
        self.assert_refused("startup context exceeds byte budget")
        self.assert_refused("startup context exceeds byte budget", "startup.py", "--json")
        self.assertFalse((self.workspace / "state/session_authority.json").exists())

    def test_utf8_bytes_count_and_exact_budget_boundary(self):
        result = self.run_tool("startup.py", "--json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        accounting = json.loads(result.stdout).get("startup_context")
        self.assertIsNotNone(accounting, "startup must report its source byte accounting")
        other_bytes = accounting["total_bytes"] - (self.workspace / "INDEX.json").stat().st_size
        # The inventory itself is a startup source; solve for its byte length.
        for _ in range(4):
            self.index["startup_budget_bytes"] = other_bytes + len(json.dumps(self.index).encode("utf-8"))
        self.save_index()
        self.assertEqual(self.run_tool().returncode, 0)
        with (self.workspace / "MEMORY.md").open("a", encoding="utf-8") as output:
            output.write("é")
        self.assert_refused("startup context exceeds byte budget")
        self.index["startup_budget_bytes"] += 1
        self.save_index()
        self.assert_refused("startup context exceeds byte budget")
        self.index["startup_budget_bytes"] += 1
        self.save_index()
        self.assertEqual(self.run_tool().returncode, 0)

    def test_doctor_rejects_workspace_drift(self):
        (self.workspace / "AGENTS.md").write_text("# Rules", encoding="utf-8")
        self.assert_refused("unindexed top-level file", "doctor.py", "--json")

    @unittest.skipUnless(os.name == "posix", "POSIX symlinks")
    def test_symlinked_project_folder_is_refused(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        (outside / "PROJECT.md").write_text("# Outside", encoding="utf-8")
        (self.workspace / "projects/demo").symlink_to(outside, target_is_directory=True)
        self.index["projects"] = ["demo"]
        self.save_index()
        self.assert_refused("symlink")

    @unittest.skipUnless(os.name == "posix", "POSIX symlinks")
    def test_symlinked_index_or_startup_source_is_refused(self):
        for name in ("INDEX.json", "MEMORY.md"):
            with self.subTest(name=name):
                path = self.workspace / name
                original = path.read_bytes()
                outside = Path(self.temp.name) / name
                outside.write_bytes(original)
                path.unlink()
                path.symlink_to(outside)
                self.assert_refused("symlink")
                path.unlink()
                path.write_bytes(original)


class GeneratedTemplateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.workspace = self.base / "workspace"
        shutil.copytree(ROOT / "templates/private-workspace", self.workspace)
        brain = json.loads((self.workspace / "BRAIN.json").read_text())
        brain["workspace_id"] = "b" * 32
        (self.workspace / "BRAIN.json").write_text(json.dumps(brain), encoding="utf-8")
        self.project = self.base / "project"
        self.project.mkdir()

    def check_bridge(self, runtime):
        return subprocess.run([sys.executable, str(ROOT / "scripts/runtime_bridge.py"), "install",
                               "--runtime", runtime, "--workspace", str(self.workspace),
                               "--project", str(self.project), "--check"],
                              capture_output=True, text=True, timeout=30)

    def install_bridge(self, runtime):
        with contextlib.redirect_stdout(io.StringIO()):
            runtime_bridge.install(runtime, str(self.workspace), str(self.project))

    def snapshot(self):
        return {str(p.relative_to(self.project)): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in self.project.rglob("*") if p.is_file()}

    def test_missing_bridge_check_is_read_only(self):
        result = self.check_bridge("codex")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing", (result.stdout + result.stderr).lower())
        self.assertEqual(list(self.project.iterdir()), [])

    def test_all_bridge_templates_install_and_check_detects_content_drift(self):
        for runtime, instruction in (("claude", "CLAUDE.md"), ("gemini", "GEMINI.md"),
                                     ("codex", "AGENTS.md"), ("local", None), ("other-tool", None)):
            with self.subTest(runtime=runtime):
                self.install_bridge(runtime)
                before = self.snapshot()
                result = self.check_bridge(runtime)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(before, self.snapshot())
                bridge = self.project / ".aham/runtime.md"
                bridge.write_text(bridge.read_text() + "\nchanged\n", encoding="utf-8")
                self.assertNotEqual(self.check_bridge(runtime).returncode, 0)
                self.install_bridge(runtime)
                if instruction:
                    path = self.project / instruction
                    path.write_text("Unrelated owner rules\n" + path.read_text(), encoding="utf-8")
                    self.assertEqual(self.check_bridge(runtime).returncode, 0)
                    path.write_text(path.read_text().replace(".aham/runtime.md", ".aham/wrong.md"), encoding="utf-8")
                    self.assertNotEqual(self.check_bridge(runtime).returncode, 0)

    def test_bridge_check_uses_current_template(self):
        self.install_bridge("codex")
        templates = self.base / "templates"
        shutil.copytree(ROOT / "templates/runtime-bridge", templates)
        (templates / "runtime.md").write_text("Changed template: $runtime\n", encoding="utf-8")
        with mock.patch.object(runtime_bridge, "TEMPLATE_DIR", templates):
            status = runtime_bridge.load_status(self.project)
        self.assertFalse(status["installed"], status)

    def test_native_instruction_check_uses_current_template(self):
        self.install_bridge("codex")
        templates = self.base / "templates"
        shutil.copytree(ROOT / "templates/runtime-bridge", templates)
        (templates / "codex.md").write_text("Changed native instructions\n", encoding="utf-8")
        with mock.patch.object(runtime_bridge, "TEMPLATE_DIR", templates):
            status = runtime_bridge.load_status(self.project)
        self.assertFalse(status["installed"], status)

    def test_bridge_check_accepts_platform_line_endings(self):
        self.install_bridge("codex")
        path = self.project / ".aham/runtime.md"
        path.write_bytes(runtime_bridge.render_bridge("codex").replace("\n", "\r\n").encode("utf-8"))
        before = self.snapshot()
        result = self.check_bridge("codex")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(before, self.snapshot())

    def test_check_rejects_different_runtime_without_writing(self):
        self.install_bridge("codex")
        before = self.snapshot()
        self.assertNotEqual(self.check_bridge("claude").returncode, 0)
        self.assertEqual(before, self.snapshot())

    @unittest.skipUnless(os.name == "posix", "POSIX hook installer")
    def test_hooks_install_from_templates_and_check_detects_template_drift(self):
        for runtime in ("claude", "codex", "gemini"):
            with self.subTest(runtime=runtime):
                self.assertTrue(install_command_guard.install(self.project, runtime)["configured"])
                before = self.snapshot()
                self.assertTrue(install_command_guard.install(self.project, runtime, check=True)["configured"])
                self.assertEqual(before, self.snapshot())
                templates = self.base / runtime
                templates.mkdir()
                (templates / "hooks.json").write_text(json.dumps({runtime: {
                    "path": install_command_guard.TARGETS[runtime][0],
                    "event": install_command_guard.TARGETS[runtime][1],
                    "group": {"matcher": "changed", "hooks": [{"type": "command", "command": "$command", "timeout": 1}]},
                }}), encoding="utf-8")
                with mock.patch.object(install_command_guard, "TEMPLATE_DIR", templates):
                    result = install_command_guard.install(self.project, runtime, check=True)
                self.assertFalse(result["configured"], result)


class FoundationDriftTests(unittest.TestCase):
    def test_foundation_checks_the_workspace_template(self):
        import verify_foundation
        with tempfile.TemporaryDirectory() as temp:
            framework = Path(temp) / "framework"
            shutil.copytree(ROOT, framework, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            with mock.patch.object(verify_foundation, "ROOT", framework), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(verify_foundation.main(), 0)
                (framework / "templates/private-workspace/AGENTS.md").write_text("Rules\n", encoding="utf-8")
                self.assertNotEqual(verify_foundation.main(), 0)

    def test_foundation_checks_template_startup_budget(self):
        import verify_foundation
        with tempfile.TemporaryDirectory() as temp:
            framework = Path(temp) / "framework"
            shutil.copytree(ROOT, framework, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            path = framework / "templates/private-workspace/INDEX.json"
            index = json.loads(path.read_text(encoding="utf-8"))
            index["startup_budget_bytes"] = 1
            path.write_text(json.dumps(index), encoding="utf-8")
            output = io.StringIO()
            with mock.patch.object(verify_foundation, "ROOT", framework), contextlib.redirect_stdout(output):
                self.assertNotEqual(verify_foundation.main(), 0)
            self.assertIn("startup context exceeds byte budget", output.getvalue())


if __name__ == "__main__":
    unittest.main()
