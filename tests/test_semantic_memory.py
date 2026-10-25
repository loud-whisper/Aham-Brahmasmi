from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "scripts" / "setup_workspace.py"
SEMANTIC = ROOT / "scripts" / "semantic_memory.py"


class SemanticMemoryTests(unittest.TestCase):
    def run_command(
        self,
        *args: str,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args,
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )

    def make_workspace(self, root: Path) -> Path:
        workspace = root / "workspace"
        result = self.run_command(sys.executable, str(SETUP), "--workspace", str(workspace))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return workspace

    def fake_mempalace(self, root: Path) -> tuple[dict[str, str], Path]:
        bin_dir = root / "bin"
        bin_dir.mkdir()
        log = root / "mempalace-args.jsonl"
        script = bin_dir / ("mempalace.py" if os.name == "nt" else "mempalace")
        script.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "from pathlib import Path\n"
            "log = Path(os.environ['FAKE_MEMPALACE_LOG'])\n"
            "with log.open('a', encoding='utf-8') as h: h.write(json.dumps(sys.argv[1:]) + '\\n')\n"
            "args = sys.argv[1:]\n"
            "if args == ['--version']:\n"
            "    print('MemPalace 3.10.0')\n"
            "elif args == ['status']:\n"
            "    print('Palace ready')\n"
            "elif args and args[0] == 'search':\n"
            "    print('SEARCH RESULT: ' + args[1])\n"
            "elif args and args[0] == 'wake-up':\n"
            "    print('WAKE CONTEXT')\n"
            "else:\n"
            "    print('unexpected arguments', file=sys.stderr)\n"
            "    raise SystemExit(7)\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
        env = dict(os.environ)
        env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
        if os.name == "nt": env["PATHEXT"] = env.get("PATHEXT", ".EXE;.CMD") + ";.PY"
        env["FAKE_MEMPALACE_LOG"] = str(log)
        return env, log

    def test_unconfigured_status_is_nonblocking_without_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.make_workspace(Path(temp))
            env = dict(os.environ)
            env["PATH"] = str(Path(temp) / "empty-bin")
            result = self.run_command(
                sys.executable,
                str(SEMANTIC),
                "status",
                "--workspace",
                str(workspace),
                "--json",
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["configured"])
            self.assertFalse(payload["available"])
            self.assertEqual(payload["reason"], "not_configured")

    def test_configure_verifies_live_cli_and_records_no_provider_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            env, _ = self.fake_mempalace(root)
            result = self.run_command(
                sys.executable,
                str(SEMANTIC),
                "configure",
                "--workspace",
                str(workspace),
                "--provider",
                "mempalace",
                "--wing",
                "example-project",
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            brain = json.loads((workspace / "BRAIN.json").read_text(encoding="utf-8"))
            config = brain["optional_integrations"]["semantic_memory"]
            self.assertEqual(config["provider"], "mempalace")
            self.assertEqual(config["wing"], "example-project")
            self.assertEqual(config["verified_cli"], "MemPalace 3.10.0")
            self.assertNotIn("path", config)
            self.assertNotIn("url", config)

    def test_search_and_wake_up_use_configured_wing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            env, log = self.fake_mempalace(root)
            configured = self.run_command(
                sys.executable,
                str(SEMANTIC),
                "configure",
                "--workspace",
                str(workspace),
                "--wing",
                "project-wing",
                env=env,
            )
            self.assertEqual(configured.returncode, 0, configured.stdout + configured.stderr)

            searched = self.run_command(
                sys.executable,
                str(SEMANTIC),
                "search",
                "--workspace",
                str(workspace),
                "--query",
                "where did we stop",
                "--results",
                "3",
                env=env,
            )
            self.assertEqual(searched.returncode, 0, searched.stdout + searched.stderr)
            self.assertIn("SEARCH RESULT: where did we stop", searched.stdout)

            wake = self.run_command(
                sys.executable,
                str(SEMANTIC),
                "wake-up",
                "--workspace",
                str(workspace),
                env=env,
            )
            self.assertEqual(wake.returncode, 0, wake.stdout + wake.stderr)
            self.assertIn("SEARCH RESULT: project context for the current session", wake.stdout)
            self.assertNotIn("WAKE CONTEXT", wake.stdout)

            calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
            self.assertIn(
                ["search", "where did we stop", "--results", "3", "--wing", "project-wing"],
                calls,
            )
            self.assertIn(["search", "project context for the current session", "--results", "5",
                           "--wing", "project-wing"], calls)
            self.assertNotIn(["wake-up", "--wing", "project-wing"], calls)

    def test_configured_provider_failure_does_not_modify_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            env, _ = self.fake_mempalace(root)
            configured = self.run_command(
                sys.executable,
                str(SEMANTIC),
                "configure",
                "--workspace",
                str(workspace),
                env=env,
            )
            self.assertEqual(configured.returncode, 0, configured.stdout + configured.stderr)
            before = (workspace / "BRAIN.json").read_text(encoding="utf-8")

            missing_env = dict(os.environ)
            missing_env["PATH"] = str(root / "missing-bin")
            status = self.run_command(
                sys.executable,
                str(SEMANTIC),
                "status",
                "--workspace",
                str(workspace),
                "--json",
                env=missing_env,
            )
            self.assertEqual(status.returncode, 2)
            payload = json.loads(status.stdout)
            self.assertTrue(payload["configured"])
            self.assertFalse(payload["available"])
            self.assertEqual((workspace / "BRAIN.json").read_text(encoding="utf-8"), before)

    def test_disable_only_removes_adapter_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            env, _ = self.fake_mempalace(root)
            configured = self.run_command(
                sys.executable,
                str(SEMANTIC),
                "configure",
                "--workspace",
                str(workspace),
                env=env,
            )
            self.assertEqual(configured.returncode, 0)
            memory_before = (workspace / "MEMORY.md").read_text(encoding="utf-8")
            disabled = self.run_command(
                sys.executable,
                str(SEMANTIC),
                "disable",
                "--workspace",
                str(workspace),
            )
            self.assertEqual(disabled.returncode, 0, disabled.stdout + disabled.stderr)
            brain = json.loads((workspace / "BRAIN.json").read_text(encoding="utf-8"))
            self.assertIsNone(brain["optional_integrations"]["semantic_memory"])
            self.assertEqual((workspace / "MEMORY.md").read_text(encoding="utf-8"), memory_before)

    def test_semantic_contract_keeps_provider_replaceable_and_optional(self) -> None:
        contract = json.loads((ROOT / "core" / "semantic_memory.json").read_text(encoding="utf-8"))
        provider = contract["providers"]["mempalace"]
        self.assertFalse(provider["required"])
        self.assertEqual(provider["failure_policy"], "continue_without_semantic_memory")
        self.assertIn("search", contract["operations"])
        self.assertIn("wake_up", contract["operations"])


if __name__ == "__main__":
    unittest.main()
