from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts" / "live_runtime_rehearsal.py"
TASK_CHECK = ROOT / "scripts" / "live_runtime_task_check.py"
CHECKPOINT = ROOT / "scripts" / "checkpoint.py"
WRAP_UP = ROOT / "scripts" / "wrap_up.py"


class LiveRuntimeRehearsalTests(unittest.TestCase):
    def run_tool(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(TOOL), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def run_script(self, script: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(script), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def git(self, repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def prepare(self, root: Path, runtime: str = "local") -> dict:
        result = self.run_tool("prepare", "--runtime", runtime, "--root", str(root))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("LIVE RUNTIME REHEARSAL PREPARED", result.stdout)
        return json.loads((root / "rehearsal.json").read_text(encoding="utf-8"))

    def complete_task_commit(self, root: Path) -> dict:
        manifest = json.loads((root / "rehearsal.json").read_text(encoding="utf-8"))
        project = Path(manifest["project"])
        runtime = manifest["runtime"]
        rehearsal_id = manifest["rehearsal_id"]

        (project / "task.txt").write_text(manifest["task_marker"] + "\n", encoding="utf-8")
        evidence = {
            "format": "aham-brahmasmi-live-runtime-evidence",
            "version": 1,
            "runtime": runtime,
            "rehearsal_id": rehearsal_id,
            "startup_ready": True,
        }
        (project / "LIVE_RUNTIME_EVIDENCE.json").write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        added = self.git(project, "add", "task.txt", "LIVE_RUNTIME_EVIDENCE.json")
        self.assertEqual(added.returncode, 0, added.stderr)
        committed = self.git(project, "commit", "-m", manifest["commit_message"])
        self.assertEqual(committed.returncode, 0, committed.stdout + committed.stderr)
        return manifest

    def complete_synthetic_runtime(self, root: Path) -> dict:
        manifest = self.complete_task_commit(root)
        workspace = Path(manifest["workspace"])
        project = Path(manifest["project"])
        runtime = manifest["runtime"]
        rehearsal_id = manifest["rehearsal_id"]

        task_check = self.run_script(TASK_CHECK, "--root", str(root))
        self.assertEqual(task_check.returncode, 0, task_check.stdout + task_check.stderr)
        self.assertIn("TASK STATE VERIFIED", task_check.stdout)

        checkpoint = self.run_script(
            CHECKPOINT,
            "--workspace",
            str(workspace),
            "--repo",
            str(project),
            "--summary",
            manifest["milestone_summary"],
            "--completed",
            "Live runtime updated and committed the rehearsal task.",
            "--next-step",
            "Complete the wrap-up rehearsal.",
            "--project",
            "Live Runtime Rehearsal",
        )
        self.assertEqual(checkpoint.returncode, 0, checkpoint.stdout + checkpoint.stderr)
        self.assertIn("CHECKPOINT SAVED", checkpoint.stdout)
        self.assertIn("CHECKPOINT VERIFIED", checkpoint.stdout)

        bundle = workspace / "live-runtime-wrap-up.json"
        bundle.write_text(
            json.dumps(
                {
                    "session_id": f"live-runtime-{rehearsal_id}",
                    "durable_facts": [
                        f"Live runtime {runtime} completed rehearsal {rehearsal_id}."
                    ],
                    "unfinished_work": [],
                    "reusable_lessons": [
                        "Live runtime lifecycle commands were verified through the Aham Brahmasmi bridge."
                    ],
                    "project_updates": [
                        {
                            "project": "Live Runtime Rehearsal",
                            "content": f"Runtime {runtime} completed rehearsal {rehearsal_id}.",
                        }
                    ],
                    "history": [
                        f"Completed live runtime rehearsal {rehearsal_id} using {runtime}."
                    ],
                    "checkpoint": {
                        "summary": manifest["final_summary"],
                        "completed": [
                            "Verified startup, project work, milestone checkpoint and wrap up in the live runtime."
                        ],
                        "next_steps": [
                            "Verify the rehearsal with scripts/live_runtime_rehearsal.py."
                        ],
                        "artifacts": [],
                        "project": "Live Runtime Rehearsal",
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        wrapped = self.run_script(
            WRAP_UP,
            "--workspace",
            str(workspace),
            "--bundle",
            str(bundle),
            "--repo",
            str(project),
        )
        self.assertEqual(wrapped.returncode, 0, wrapped.stdout + wrapped.stderr)
        self.assertIn("WRAP UP COMPLETE", wrapped.stdout)
        self.assertIn("WRAP UP VERIFIED", wrapped.stdout)

        final_task_check = self.run_script(TASK_CHECK, "--root", str(root))
        self.assertEqual(
            final_task_check.returncode,
            0,
            final_task_check.stdout + final_task_check.stderr,
        )
        self.assertIn("TASK STATE VERIFIED", final_task_check.stdout)
        return manifest

    def test_prepare_creates_isolated_clean_project_and_ignored_local_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "rehearsal"
            manifest = self.prepare(root, "claude")
            workspace = Path(manifest["workspace"])
            project = Path(manifest["project"])

            self.assertTrue((workspace / "BRAIN.json").is_file())
            self.assertTrue((project / "LIVE_REHEARSAL.md").is_file())
            self.assertTrue((project / ".aham" / "runtime.md").is_file())
            self.assertTrue((project / ".aham" / "runtime.json").is_file())
            self.assertIn("runtime.json", (project / ".aham" / ".gitignore").read_text(encoding="utf-8"))

            prompt = (project / "LIVE_REHEARSAL.md").read_text(encoding="utf-8")
            self.assertIn("TASK STATE VERIFIED", prompt)
            self.assertIn("CHECKPOINT VERIFIED", prompt)
            self.assertIn("WRAP UP VERIFIED", prompt)
            self.assertIn("Your own prose is not evidence of tool execution", prompt)

            tracked = self.git(project, "ls-files").stdout.splitlines()
            self.assertNotIn(".aham/runtime.json", tracked)
            status = self.git(project, "status", "--porcelain=v1", "--untracked-files=all")
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertEqual(status.stdout.strip(), "")

    def test_prepare_refuses_non_empty_root_without_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "rehearsal"
            root.mkdir()
            sentinel = root / "keep.txt"
            sentinel.write_text("keep me\n", encoding="utf-8")

            result = self.run_tool("prepare", "--runtime", "local", "--root", str(root))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("must be empty", result.stderr)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep me\n")
            self.assertFalse((root / "workspace").exists())

    def test_task_check_rejects_appended_completion_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "rehearsal"
            manifest = self.prepare(root)
            project = Path(manifest["project"])
            runtime = manifest["runtime"]
            rehearsal_id = manifest["rehearsal_id"]

            (project / "task.txt").write_text(
                "Rehearsal task has not been completed yet.\n" + manifest["task_marker"] + "\n",
                encoding="utf-8",
            )
            (project / "LIVE_RUNTIME_EVIDENCE.json").write_text(
                json.dumps(
                    {
                        "format": "aham-brahmasmi-live-runtime-evidence",
                        "version": 1,
                        "runtime": runtime,
                        "rehearsal_id": rehearsal_id,
                        "startup_ready": True,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            self.assertEqual(self.git(project, "add", "task.txt", "LIVE_RUNTIME_EVIDENCE.json").returncode, 0)
            committed = self.git(project, "commit", "-m", manifest["commit_message"])
            self.assertEqual(committed.returncode, 0, committed.stdout + committed.stderr)

            result = self.run_script(TASK_CHECK, "--root", str(root))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("TASK STATE FAILED", result.stderr)
            self.assertIn("only the exact", result.stderr)

    def test_task_check_accepts_exact_committed_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "rehearsal"
            self.prepare(root)
            self.complete_task_commit(root)

            result = self.run_script(TASK_CHECK, "--root", str(root))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("TASK STATE VERIFIED", result.stdout)

    def test_task_check_rejects_untracked_project_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "rehearsal"
            self.prepare(root)
            manifest = self.complete_task_commit(root)
            project = Path(manifest["project"])
            (project / "bundle.json").write_text("{}\n", encoding="utf-8")

            result = self.run_script(TASK_CHECK, "--root", str(root))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("TASK STATE FAILED", result.stderr)
            self.assertIn("uncommitted or untracked files", result.stderr)
            self.assertIn("bundle.json", result.stderr)

    def test_task_check_rejects_extra_file_hidden_in_task_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "rehearsal"
            self.prepare(root)
            manifest = self.complete_task_commit(root)
            project = Path(manifest["project"])
            (project / "bundle.json").write_text("{}\n", encoding="utf-8")
            self.assertEqual(self.git(project, "add", "bundle.json").returncode, 0)
            amended = self.git(project, "commit", "--amend", "--no-edit")
            self.assertEqual(amended.returncode, 0, amended.stdout + amended.stderr)

            result = self.run_script(TASK_CHECK, "--root", str(root))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("TASK STATE FAILED", result.stderr)
            self.assertIn("must change only", result.stderr)
            self.assertIn("bundle.json", result.stderr)

    def test_verify_before_live_runtime_work_fails_at_task_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "rehearsal"
            self.prepare(root)

            result = self.run_tool("verify", "--root", str(root))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("TASK STATE FAILED", result.stderr)
            self.assertIn("completion marker", result.stderr)

    def test_complete_rehearsal_verifies_durable_runtime_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "rehearsal"
            manifest = self.prepare(root)
            self.complete_synthetic_runtime(root)

            result = self.run_tool("verify", "--root", str(root), "--json")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            self.assertTrue(report["verified"])
            self.assertEqual(report["runtime"], manifest["runtime"])
            self.assertEqual(report["rehearsal_id"], manifest["rehearsal_id"])
            self.assertIn("task state machine verification passed", report["checks"])
            self.assertTrue((root / "verified_report.json").is_file())

    def test_tampered_evidence_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "rehearsal"
            self.prepare(root)
            manifest = self.complete_synthetic_runtime(root)
            project = Path(manifest["project"])
            evidence_path = project / "LIVE_RUNTIME_EVIDENCE.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["runtime"] = "gemini"
            evidence_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

            result = self.run_tool("verify", "--root", str(root))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("TASK STATE FAILED", result.stderr)
            self.assertIn("required rehearsal files changed", result.stderr)


if __name__ == "__main__":
    unittest.main()
