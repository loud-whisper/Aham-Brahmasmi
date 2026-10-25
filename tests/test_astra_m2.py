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
WRAP_UP = ROOT / "scripts" / "wrap_up.py"
CHECKPOINT = ROOT / "scripts" / "checkpoint.py"


class AstraM2RegressionTests(unittest.TestCase):
    def run_script(
        self,
        script: Path,
        *args: str,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        return subprocess.run(
            [sys.executable, str(script), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            env=merged_env,
        )

    def make_workspace(self, root: Path) -> Path:
        workspace = root / "workspace"
        result = self.run_script(SETUP, "--workspace", str(workspace))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return workspace

    def write_bundle(self, path: Path, operation_id: str, fact: str) -> None:
        path.write_text(
            json.dumps(
                {
                    "operation_id": operation_id,
                    "durable_facts": [fact],
                    "checkpoint": {"summary": f"commit {operation_id}"},
                }
            ),
            encoding="utf-8",
        )

    def store(self, workspace: Path) -> dict:
        return json.loads((workspace / "state" / "store.json").read_text(encoding="utf-8"))

    def operations(self, workspace: Path) -> list[dict]:
        return [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((workspace / "state" / "operations").glob("*.json"))
        ]

    def test_f4_independent_concurrent_wrapups_are_serialized_without_lost_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            bundles: list[Path] = []
            for index in range(6):
                path = root / f"bundle-{index}.json"
                self.write_bundle(path, f"parallel-{index}", f"parallel fact {index}")
                bundles.append(path)

            processes = [
                subprocess.Popen(
                    [sys.executable, str(WRAP_UP), "--workspace", str(workspace), "--bundle", str(bundle)],
                    cwd=ROOT,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                for bundle in bundles
            ]
            results = [process.communicate(timeout=30) + (process.returncode,) for process in processes]
            for stdout, stderr, code in results:
                self.assertEqual(code, 0, stderr + stdout)

            memory = (workspace / "MEMORY.md").read_text(encoding="utf-8")
            for index in range(6):
                self.assertEqual(memory.count(f"parallel fact {index}"), 1)

            operations = self.operations(workspace)
            self.assertEqual(len(operations), 6)
            self.assertEqual([item["revision"] for item in operations], [1, 2, 3, 4, 5, 6])
            self.assertEqual(self.store(workspace)["revision"], 6)
            self.assertEqual(
                {item["operation_id"] for item in operations},
                {f"parallel-{index}" for index in range(6)},
            )

    def test_expected_revision_conflict_fails_before_durable_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            first_bundle = root / "first.json"
            second_bundle = root / "second.json"
            self.write_bundle(first_bundle, "revision-first", "first revision fact")
            self.write_bundle(second_bundle, "revision-stale", "stale revision fact")

            first = self.run_script(
                WRAP_UP,
                "--workspace",
                str(workspace),
                "--bundle",
                str(first_bundle),
                "--expected-revision",
                "0",
            )
            self.assertEqual(first.returncode, 0, first.stderr + first.stdout)

            before = (workspace / "MEMORY.md").read_text(encoding="utf-8")
            stale = self.run_script(
                WRAP_UP,
                "--workspace",
                str(workspace),
                "--bundle",
                str(second_bundle),
                "--expected-revision",
                "0",
            )
            self.assertNotEqual(stale.returncode, 0, stale.stdout + stale.stderr)
            self.assertIn("revision", (stale.stdout + stale.stderr).lower())
            self.assertEqual((workspace / "MEMORY.md").read_text(encoding="utf-8"), before)
            self.assertNotIn("stale revision fact", before)
            self.assertEqual(self.store(workspace)["revision"], 1)
            self.assertEqual(len(self.operations(workspace)), 1)

    def test_checkpoint_and_wrapup_share_one_monotonic_revision_stream(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            checkpoint = self.run_script(
                CHECKPOINT,
                "--workspace",
                str(workspace),
                "--summary",
                "standalone checkpoint",
                "--expected-revision",
                "0",
            )
            self.assertEqual(checkpoint.returncode, 0, checkpoint.stderr + checkpoint.stdout)

            bundle = root / "bundle.json"
            self.write_bundle(bundle, "after-checkpoint", "fact after checkpoint")
            wrapped = self.run_script(
                WRAP_UP,
                "--workspace",
                str(workspace),
                "--bundle",
                str(bundle),
                "--expected-revision",
                "1",
            )
            self.assertEqual(wrapped.returncode, 0, wrapped.stderr + wrapped.stdout)

            operations = self.operations(workspace)
            self.assertEqual([(item["revision"], item["kind"]) for item in operations], [(1, "checkpoint"), (2, "wrap_up")])
            self.assertEqual(self.store(workspace)["revision"], 2)

    def test_wrapup_crash_recovery_conserves_state_at_each_commit_boundary(self) -> None:
        crash_points = (
            "wrap_up_after_pending",
            "wrap_up_after_projection",
            "wrap_up_after_commit_record",
            "wrap_up_after_head",
            "wrap_up_after_receipt",
        )
        for crash_point in crash_points:
            with self.subTest(crash_point=crash_point), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                workspace = self.make_workspace(root)
                bundle = root / "bundle.json"
                operation_id = crash_point.replace("wrap_up_", "crash-")
                fact = f"fact for {crash_point}"
                self.write_bundle(bundle, operation_id, fact)

                crashed = self.run_script(
                    WRAP_UP,
                    "--workspace",
                    str(workspace),
                    "--bundle",
                    str(bundle),
                    env={
                        "AHAM_BRAHMASMI_TEST_MODE": "1",
                        "AHAM_BRAHMASMI_TEST_CRASH_POINT": crash_point,
                    },
                )
                self.assertEqual(crashed.returncode, 86, crashed.stderr + crashed.stdout)
                self.assertTrue((workspace / "state" / "pending_wrap_up.json").exists())

                status = self.run_script(
                    WRAP_UP,
                    "--workspace",
                    str(workspace),
                    "--status",
                    operation_id,
                )
                self.assertEqual(status.returncode, 0, status.stderr + status.stdout)
                if crash_point in {"wrap_up_after_pending", "wrap_up_after_projection"}:
                    self.assertIn("Status: pending", status.stdout)
                else:
                    self.assertIn("Status: complete", status.stdout)

                recovered = self.run_script(
                    WRAP_UP,
                    "--workspace",
                    str(workspace),
                    "--recover-pending",
                )
                self.assertEqual(recovered.returncode, 0, recovered.stderr + recovered.stdout)
                self.assertFalse((workspace / "state" / "pending_wrap_up.json").exists())
                self.assertEqual((workspace / "MEMORY.md").read_text(encoding="utf-8").count(fact), 1)
                self.assertEqual(self.store(workspace)["revision"], 1)
                operations = self.operations(workspace)
                self.assertEqual(len(operations), 1)
                self.assertEqual(operations[0]["operation_id"], operation_id)
                self.assertEqual(operations[0]["revision"], 1)

    def test_checkpoint_crash_recovery_conserves_state_at_each_commit_boundary(self) -> None:
        crash_points = (
            "checkpoint_after_pending",
            "checkpoint_after_projection",
            "checkpoint_after_commit_record",
            "checkpoint_after_head",
        )
        for crash_point in crash_points:
            with self.subTest(crash_point=crash_point), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                workspace = self.make_workspace(root)
                crashed = self.run_script(
                    CHECKPOINT,
                    "--workspace",
                    str(workspace),
                    "--summary",
                    f"checkpoint fixture {crash_point}",
                    env={
                        "AHAM_BRAHMASMI_TEST_MODE": "1",
                        "AHAM_BRAHMASMI_TEST_CRASH_POINT": crash_point,
                    },
                )
                self.assertEqual(crashed.returncode, 86, crashed.stderr + crashed.stdout)
                pending = workspace / "state" / "pending_checkpoint.json"
                self.assertTrue(pending.exists())
                records_before = self.operations(workspace)
                if crash_point in {"checkpoint_after_pending", "checkpoint_after_projection"}:
                    self.assertEqual(records_before, [])
                else:
                    self.assertEqual(len(records_before), 1)
                    self.assertEqual(records_before[0]["revision"], 1)

                recovered = self.run_script(
                    CHECKPOINT,
                    "--workspace",
                    str(workspace),
                    "--recover-pending",
                )
                self.assertEqual(recovered.returncode, 0, recovered.stderr + recovered.stdout)
                self.assertFalse(pending.exists())
                records = self.operations(workspace)
                self.assertEqual(len(records), 1)
                self.assertEqual(records[0]["kind"], "checkpoint")
                self.assertEqual(records[0]["revision"], 1)
                self.assertEqual(self.store(workspace)["revision"], 1)
                latest = json.loads((workspace / "state" / "latest_checkpoint.json").read_text(encoding="utf-8"))
                self.assertEqual(latest["revision"], 1)
                checkpoint_file = workspace / latest["file"]
                self.assertTrue(checkpoint_file.is_file())
                checkpoint_payload = json.loads(checkpoint_file.read_text(encoding="utf-8"))
                self.assertEqual(checkpoint_payload["revision"], 1)
                self.assertEqual(checkpoint_payload["summary"], f"checkpoint fixture {crash_point}")

    def test_fresh_process_can_identify_last_committed_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            for index in range(3):
                bundle = root / f"bundle-{index}.json"
                self.write_bundle(bundle, f"fresh-{index}", f"fresh fact {index}")
                result = self.run_script(WRAP_UP, "--workspace", str(workspace), "--bundle", str(bundle))
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

            status = self.run_script(
                WRAP_UP,
                "--workspace",
                str(workspace),
                "--status",
                "fresh-2",
            )
            self.assertEqual(status.returncode, 0, status.stderr + status.stdout)
            self.assertIn("Revision: 3", status.stdout)
            self.assertEqual(self.store(workspace)["revision"], 3)


if __name__ == "__main__":
    unittest.main()
