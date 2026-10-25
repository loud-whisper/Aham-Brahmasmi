from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "scripts" / "setup_workspace.py"
SANDBOX = ROOT / "scripts" / "rehearsal_sandbox.py"
SANDBOX_HOME = "/" + "home/aham"


@unittest.skipUnless(sys.platform.startswith("linux"), "M5 OS isolation is currently a Linux gate")
class M5RehearsalSandboxTests(unittest.TestCase):
    def run_script(self, script: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(script), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            env=env,
            timeout=30,
        )

    def make_sandbox_fixture(self, root: Path) -> tuple[Path, Path]:
        workspace = root / "workspace"
        project = root / "project"
        project.mkdir()
        setup = self.run_script(SETUP, "--workspace", str(workspace))
        self.assertEqual(setup.returncode, 0, setup.stderr + setup.stdout)
        return workspace, project

    def sandbox_prefix(self, workspace: Path, project: Path, env: dict[str, str]) -> list[str]:
        args = ["run", "--workspace", str(workspace), "--project", str(project)]
        if env.get("AHAM_TEST_BWRAP_SUDO_HELPER") == "1":
            args.append("--sudo-namespace-helper")
        return args

    def test_os_enforced_sandbox_launcher_exists(self) -> None:
        self.assertTrue(
            SANDBOX.is_file(),
            "M5 requires an OS-enforced rehearsal launcher; prompt/path instructions are not isolation",
        )

    def test_extra_bind_cannot_replace_control_plane_or_parent_work_mount(self) -> None:
        if not SANDBOX.is_file():
            self.skipTest("sandbox launcher is not implemented yet")
        if shutil.which("bwrap") is None:
            self.skipTest("bubblewrap is not installed in this test environment")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace, project = self.make_sandbox_fixture(root)
            env = dict(os.environ)
            contract_override = root / "attacker-contract.json"
            contract_override.write_text("{}\n", encoding="utf-8")
            shadow_work = root / "shadow-work"
            shadow_work.mkdir()

            control = self.run_script(
                SANDBOX,
                *self.sandbox_prefix(workspace, project, env),
                "--ro-bind",
                f"{contract_override}:/control/task.json",
                "--",
                "/usr/bin/true",
                env=env,
            )
            self.assertNotEqual(control.returncode, 0, control.stdout + control.stderr)
            self.assertIn("task contract", control.stderr.lower())

            work_parent = self.run_script(
                SANDBOX,
                *self.sandbox_prefix(workspace, project, env),
                "--rw-bind",
                f"{shadow_work}:/work",
                "--",
                "/usr/bin/true",
                env=env,
            )
            self.assertNotEqual(work_parent.returncode, 0, work_parent.stdout + work_parent.stderr)
            self.assertIn("protected", work_parent.stderr.lower())

    def test_extra_bind_refuses_entire_real_home(self) -> None:
        if not SANDBOX.is_file():
            self.skipTest("sandbox launcher is not implemented yet")
        if shutil.which("bwrap") is None:
            self.skipTest("bubblewrap is not installed in this test environment")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace, project = self.make_sandbox_fixture(root)
            env = dict(os.environ)
            result = self.run_script(
                SANDBOX,
                *self.sandbox_prefix(workspace, project, env),
                "--ro-bind",
                f"{Path.home()}:/opt/host-home",
                "--",
                "/usr/bin/true",
                env=env,
            )
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("broad host bind", result.stderr.lower())

    def test_sandbox_hides_host_state_and_preserves_only_explicit_writes(self) -> None:
        if not SANDBOX.is_file():
            self.skipTest("sandbox launcher is not implemented yet")
        if shutil.which("bwrap") is None:
            self.skipTest("bubblewrap is not installed in this test environment")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace, project = self.make_sandbox_fixture(root)

            sentinel = root / "outside-sandbox-sentinel.txt"
            sentinel.write_text("M5 SENTINEL MUST REMAIN PRIVATE\n", encoding="utf-8")
            unrelated = root / "unrelated-project"
            unrelated.mkdir()
            unrelated_secret = unrelated / "private.txt"
            unrelated_secret.write_text("UNRELATED PRIVATE DATA\n", encoding="utf-8")

            probe = r'''
import json, os
from pathlib import Path

sentinel = Path(os.environ["AHAM_TEST_HOST_SENTINEL"])
unrelated = Path(os.environ["AHAM_TEST_HOST_UNRELATED"])
real_home = Path(os.environ["AHAM_TEST_REAL_HOME"])
framework_write = True
try:
    Path("/framework/.m5-write-probe").write_text("should fail\n", encoding="utf-8")
except OSError:
    framework_write = False
results = {
    "uid": os.getuid(),
    "home": os.environ.get("HOME"),
    "ssh_auth_sock": os.environ.get("SSH_AUTH_SOCK"),
    "docker_socket_visible": Path("/var/run/docker.sock").exists(),
    "sentinel_readable": sentinel.exists() and os.access(sentinel, os.R_OK),
    "sentinel_writable": sentinel.exists() and os.access(sentinel, os.W_OK),
    "unrelated_readable": unrelated.exists() and os.access(unrelated, os.R_OK),
    "real_home_visible": real_home.exists(),
    "framework_writable": framework_write,
}
sandbox_home = Path("/" + "home/aham")
Path("/work/project/agent-write.txt").write_text("project write ok\n", encoding="utf-8")
Path("/work/workspace/agent-write.txt").write_text("workspace write ok\n", encoding="utf-8")
(sandbox_home / "home-write.txt").write_text("synthetic home write ok\n", encoding="utf-8")
print(json.dumps(results, sort_keys=True))
'''
            env = dict(os.environ)
            env["AHAM_TEST_HOST_SENTINEL"] = str(sentinel)
            env["AHAM_TEST_HOST_UNRELATED"] = str(unrelated_secret)
            env["AHAM_TEST_REAL_HOME"] = str(Path.home())
            env["SSH_AUTH_SOCK"] = str(root / "fake-agent.sock")

            sandbox_args = self.sandbox_prefix(workspace, project, env)
            sandbox_args += [
                "--pass-env",
                "AHAM_TEST_HOST_SENTINEL",
                "--pass-env",
                "AHAM_TEST_HOST_UNRELATED",
                "--pass-env",
                "AHAM_TEST_REAL_HOME",
                "--",
                "/usr/bin/python3",
                "-c",
                probe,
            ]
            result = self.run_script(SANDBOX, *sandbox_args, env=env)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            observed = json.loads(result.stdout.strip().splitlines()[-1])
            self.assertEqual(observed["uid"], os.getuid())
            self.assertEqual(observed["home"], SANDBOX_HOME)
            self.assertIsNone(observed["ssh_auth_sock"])
            self.assertFalse(observed["docker_socket_visible"])
            self.assertFalse(observed["sentinel_readable"])
            self.assertFalse(observed["sentinel_writable"])
            self.assertFalse(observed["unrelated_readable"])
            self.assertFalse(observed["real_home_visible"])
            self.assertFalse(observed["framework_writable"])
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "M5 SENTINEL MUST REMAIN PRIVATE\n")
            self.assertEqual(unrelated_secret.read_text(encoding="utf-8"), "UNRELATED PRIVATE DATA\n")
            self.assertEqual((project / "agent-write.txt").read_text(encoding="utf-8"), "project write ok\n")
            self.assertEqual((workspace / "agent-write.txt").read_text(encoding="utf-8"), "workspace write ok\n")


if __name__ == "__main__":
    unittest.main()
