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
TOOL = ROOT / "scripts" / "live_runtime_rehearsal.py"
CONTRACT_NAME = "agent_task.json"
SENTINEL_NAME = "outside-sandbox-sentinel.txt"


@unittest.skipUnless(sys.platform.startswith("linux"), "M5 live rehearsal isolation is currently a Linux gate")
class M5LiveRehearsalIsolationTests(unittest.TestCase):
    def run_tool(
        self,
        *args: str,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(TOOL), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            env=env,
            timeout=30,
        )

    def prepare(self, root: Path) -> dict[str, object]:
        result = self.run_tool("prepare", "--runtime", "local", "--root", str(root))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads((root / "rehearsal.json").read_text(encoding="utf-8"))

    def test_prepare_separates_control_plane_from_agent_task_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "rehearsal"
            manifest = self.prepare(root)
            control = root / "control"
            contract_path = control / CONTRACT_NAME
            sentinel_path = control / SENTINEL_NAME
            project = Path(str(manifest["project"]))

            self.assertTrue(contract_path.is_file())
            self.assertTrue(sentinel_path.is_file())
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            self.assertEqual(
                set(contract),
                {"format", "version", "runtime", "rehearsal_id", "task_marker", "commit_message"},
            )
            self.assertEqual(contract["runtime"], manifest["runtime"])
            self.assertEqual(contract["rehearsal_id"], manifest["rehearsal_id"])
            self.assertEqual(contract["task_marker"], manifest["task_marker"])
            self.assertEqual(contract["commit_message"], manifest["commit_message"])

            prompt = (project / "LIVE_REHEARSAL.md").read_text(encoding="utf-8")
            self.assertIn("--contract /control/task.json", prompt)
            self.assertIn("--project /work/project", prompt)
            self.assertNotIn(str(root / "rehearsal.json"), prompt)
            self.assertFalse((project / "rehearsal.json").exists())
            self.assertFalse((project / SENTINEL_NAME).exists())

    def test_run_mounts_only_minimal_control_contract(self) -> None:
        if shutil.which("bwrap") is None:
            self.skipTest("bubblewrap is not installed in this test environment")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "rehearsal"
            manifest = self.prepare(root)
            control = root / "control"
            sentinel_path = control / SENTINEL_NAME
            authoritative_manifest = root / "rehearsal.json"

            probe = r'''
import json, os
from pathlib import Path
contract = Path("/control/task.json")
host_manifest = Path(os.environ["AHAM_TEST_HOST_MANIFEST"])
host_sentinel = Path(os.environ["AHAM_TEST_HOST_SENTINEL"])
print(json.dumps({
    "contract_visible": contract.is_file(),
    "control_manifest_visible": Path("/control/rehearsal.json").exists(),
    "host_manifest_visible": host_manifest.exists(),
    "host_sentinel_visible": host_sentinel.exists(),
    "framework_visible": Path("/framework/scripts/live_runtime_task_check.py").is_file(),
    "project_visible": Path("/work/project/LIVE_REHEARSAL.md").is_file(),
    "workspace_visible": Path("/work/workspace/BRAIN.json").is_file(),
}, sort_keys=True))
'''
            env = dict(os.environ)
            env["AHAM_TEST_HOST_MANIFEST"] = str(authoritative_manifest)
            env["AHAM_TEST_HOST_SENTINEL"] = str(sentinel_path)
            if env.get("AHAM_TEST_BWRAP_SUDO_HELPER") == "1":
                helper = ["--sudo-namespace-helper"]
            else:
                helper = []

            result = self.run_tool(
                "run",
                "--root",
                str(root),
                *helper,
                "--pass-env",
                "AHAM_TEST_HOST_MANIFEST",
                "--pass-env",
                "AHAM_TEST_HOST_SENTINEL",
                "--",
                "/usr/bin/python3",
                "-c",
                probe,
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            observed = json.loads(result.stdout.strip().splitlines()[-1])
            self.assertTrue(observed["contract_visible"])
            self.assertFalse(observed["control_manifest_visible"])
            self.assertFalse(observed["host_manifest_visible"])
            self.assertFalse(observed["host_sentinel_visible"])
            self.assertTrue(observed["framework_visible"])
            self.assertTrue(observed["project_visible"])
            self.assertTrue(observed["workspace_visible"])
            self.assertTrue(authoritative_manifest.is_file())
            self.assertTrue(sentinel_path.is_file())
            self.assertEqual(str(manifest["rehearsal_id"]), json.loads((control / CONTRACT_NAME).read_text())["rehearsal_id"])


if __name__ == "__main__":
    unittest.main()
