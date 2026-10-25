from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SWITCH_TOOL = ROOT / "scripts" / "runtime_switch_rehearsal.py"
EVIDENCE_TOOL = ROOT / "scripts" / "runtime_evidence.py"
STARTUP = ROOT / "scripts" / "startup.py"
WRAP_UP = ROOT / "scripts" / "wrap_up.py"


def namespace_helper_args() -> list[str]:
    if os.environ.get("AHAM_TEST_BWRAP_SUDO_HELPER") == "1":
        return ["--sudo-namespace-helper"]
    return []


class RuntimeSwitchRecoveryRegressionTests(unittest.TestCase):
    def run_switch(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SWITCH_TOOL), *args],
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

    def prepare(self, root: Path) -> dict[str, object]:
        result = self.run_switch("prepare", "--root", str(root))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("RUNTIME SWITCH REHEARSAL PREPARED", result.stdout)
        return json.loads((root / "switch_manifest.json").read_text(encoding="utf-8"))

    def complete_source_state(self, root: Path, manifest: dict[str, object]) -> None:
        workspace = str(root / "workspace")
        startup = self.run_script(
            STARTUP,
            "--workspace",
            workspace,
            "--runtime",
            "local",
            "--mode",
            "regular",
            "--capability",
            "read_files",
            "--capability",
            "write_files",
            "--capability",
            "run_commands",
            "--harness",
            f"runtime-switch-source:{manifest['switch_id']}",
            "--json",
        )
        self.assertEqual(startup.returncode, 0, startup.stdout + startup.stderr)
        session = json.loads(startup.stdout)["session_authority"]["session_id"]
        bundle = root / "source-bundle.json"
        bundle.write_text(
            json.dumps(
                {
                    "operation_id": manifest["source_operation_id"],
                    "durable_facts": [manifest["durable_fact"]],
                    "unfinished_work": [manifest["unfinished_task"]],
                    "reusable_lessons": [],
                    "project_updates": [
                        {
                            "project": manifest["project_name"],
                            "content": manifest["project_update"],
                        }
                    ],
                    "history": [],
                    "checkpoint": {
                        "summary": manifest["checkpoint_summary"],
                        "completed": ["Runtime A committed the switch-source state."],
                        "next_steps": [manifest["checkpoint_next_step"]],
                        "artifacts": [],
                        "project": manifest["project_name"],
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
            workspace,
            "--bundle",
            str(bundle),
            "--session-id",
            session,
        )
        self.assertEqual(wrapped.returncode, 0, wrapped.stdout + wrapped.stderr)
        self.assertIn("WRAP UP VERIFIED", wrapped.stdout)

    def test_prepare_keeps_source_markers_out_of_target_contract_and_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "switch"
            manifest = self.prepare(root)
            source = (root / "control" / "source_task.md").read_text(encoding="utf-8")
            target = (root / "control" / "target_task.md").read_text(encoding="utf-8")
            project_text = "\n".join(
                path.read_text(encoding="utf-8", errors="replace")
                for path in (root / "project").rglob("*")
                if path.is_file() and ".git" not in path.parts
            )
            for field in ("durable_fact", "unfinished_task", "project_update"):
                marker = str(manifest[field])
                self.assertIn(marker, source)
                self.assertNotIn(marker, target)
                self.assertNotIn(marker, project_text)

    def test_source_and_fresh_target_can_be_independently_verified(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "switch"
            manifest = self.prepare(root)

            source_run = self.run_switch(
                "run-source",
                "--root",
                str(root),
                *namespace_helper_args(),
                "--non-interactive",
                "--model",
                "example-model",
                "--harness",
                "source-harness",
                "--harness-version",
                "1.0",
                "--context-tokens",
                "4096",
                "--quantization",
                "Q4",
                "--",
                "/bin/true",
            )
            self.assertEqual(source_run.returncode, 0, source_run.stdout + source_run.stderr)
            self.complete_source_state(root, manifest)

            source_verify = self.run_switch("verify-source", "--root", str(root))
            self.assertEqual(source_verify.returncode, 0, source_verify.stdout + source_verify.stderr)
            self.assertIn("SWITCH SOURCE STATE VERIFIED", source_verify.stdout)
            source_state = json.loads((root / "source_verified.json").read_text(encoding="utf-8"))

            target_run = self.run_switch(
                "run-target",
                "--root",
                str(root),
                *namespace_helper_args(),
                "--non-interactive",
                "--model",
                "example-model",
                "--harness",
                "target-harness",
                "--harness-version",
                "2.0",
                "--context-tokens",
                "4096",
                "--quantization",
                "Q4",
                "--",
                "/bin/true",
            )
            self.assertEqual(target_run.returncode, 0, target_run.stdout + target_run.stderr)

            result = {
                "format": "aham-brahmasmi-runtime-switch-recovery-result",
                "version": 1,
                "switch_id": manifest["switch_id"],
                "recovered_fact": manifest["durable_fact"],
                "recovered_unfinished_task": manifest["unfinished_task"],
                "recovered_project_update": manifest["project_update"],
                "recovered_revision": source_state["revision"],
                "recovered_checkpoint_id": source_state["checkpoint_id"],
                "startup_state_freshness": "verified_local",
                "resume_verified": True,
            }
            (root / "result" / "recovered.json").write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )

            verified = self.run_switch("verify", "--root", str(root), "--json")
            self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
            report = json.loads(verified.stdout)
            self.assertTrue(report["verified"])
            self.assertEqual(report["source_revision"], report["recovered_revision"])
            self.assertEqual(report["source_checkpoint_id"], report["recovered_checkpoint_id"])
            self.assertTrue(report["runtime_evidence"]["fresh_target_session"])
            self.assertEqual(report["runtime_evidence"]["claim_scope"], "single_switch_recovery")

    def test_target_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "switch"
            manifest = self.prepare(root)
            source_run = self.run_switch(
                "run-source", "--root", str(root), *namespace_helper_args(), "--non-interactive", "--", "/bin/true"
            )
            self.assertEqual(source_run.returncode, 0, source_run.stdout + source_run.stderr)
            self.complete_source_state(root, manifest)
            self.assertEqual(self.run_switch("verify-source", "--root", str(root)).returncode, 0)
            target_run = self.run_switch(
                "run-target", "--root", str(root), *namespace_helper_args(), "--non-interactive", "--", "/bin/true"
            )
            self.assertEqual(target_run.returncode, 0, target_run.stdout + target_run.stderr)
            source_state = json.loads((root / "source_verified.json").read_text(encoding="utf-8"))
            bad = {
                "format": "aham-brahmasmi-runtime-switch-recovery-result",
                "version": 1,
                "switch_id": manifest["switch_id"],
                "recovered_fact": "wrong fact",
                "recovered_unfinished_task": manifest["unfinished_task"],
                "recovered_project_update": manifest["project_update"],
                "recovered_revision": source_state["revision"],
                "recovered_checkpoint_id": source_state["checkpoint_id"],
                "startup_state_freshness": "verified_local",
                "resume_verified": True,
            }
            (root / "result" / "recovered.json").write_text(json.dumps(bad) + "\n", encoding="utf-8")
            verified = self.run_switch("verify", "--root", str(root))
            self.assertNotEqual(verified.returncode, 0)
            self.assertIn("recovered durable fact", verified.stderr)

    def test_target_rejects_known_session_continuation_flags(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "switch"
            manifest = self.prepare(root)
            source_run = self.run_switch(
                "run-source", "--root", str(root), *namespace_helper_args(), "--non-interactive", "--", "/bin/true"
            )
            self.assertEqual(source_run.returncode, 0, source_run.stdout + source_run.stderr)
            self.complete_source_state(root, manifest)
            self.assertEqual(self.run_switch("verify-source", "--root", str(root)).returncode, 0)
            target = self.run_switch(
                "run-target",
                "--root",
                str(root),
                *namespace_helper_args(),
                "--non-interactive",
                "--",
                "/bin/true",
                "--continue",
            )
            self.assertNotEqual(target.returncode, 0)
            self.assertIn("fresh target session", target.stderr.lower())


class RuntimeSwitchEvidenceRegisterRegressionTests(unittest.TestCase):
    def run_evidence(self, register: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(EVIDENCE_TOOL), "validate", "--register", str(register)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def switch_entry(self) -> dict[str, object]:
        return {
            "entry_id": "switch-example",
            "evidence_type": "runtime_switch_recovery",
            "switch_id": "switch-123",
            "framework_commit": "a" * 40,
            "from_runtime_profile": "local",
            "from_model": "example-model",
            "from_harness": "source-harness",
            "from_harness_version": "1.0",
            "from_context_tokens": 4096,
            "from_quantization": "Q4",
            "from_os_platform": "Linux-test",
            "from_permission_mode": "bubblewrap;stdin=closed",
            "from_human_intervention": False,
            "from_runtime_command_sha256": "1" * 64,
            "to_runtime_profile": "local",
            "to_model": "example-model",
            "to_harness": "target-harness",
            "to_harness_version": "2.0",
            "to_context_tokens": 4096,
            "to_quantization": "Q4",
            "to_os_platform": "Linux-test",
            "to_permission_mode": "bubblewrap;stdin=closed",
            "to_human_intervention": False,
            "to_runtime_command_sha256": "2" * 64,
            "source_operation_id": "switch-source-switch-123",
            "source_revision": 1,
            "recovered_revision": 1,
            "source_checkpoint_id": "wrap-switch-source-switch-123",
            "recovered_checkpoint_id": "wrap-switch-source-switch-123",
            "state_digest": "3" * 64,
            "fresh_target_session": True,
            "result": "pass",
            "verified_at": "2026-09-19T20:00:00Z",
            "independently_verified": True,
            "claim_scope": "single_switch_recovery",
            "source": "verified_switch_report.json",
            "limitations": ["Single switch recovery is not a reliability estimate."],
        }

    def write_register(self, path: Path, entry: dict[str, object]) -> None:
        path.write_text(
            json.dumps(
                {
                    "format": "aham-brahmasmi-runtime-evidence-register",
                    "version": 1,
                    "entries": [entry],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    def test_switch_recovery_is_a_distinct_valid_evidence_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            register = Path(temp) / "register.json"
            self.write_register(register, self.switch_entry())
            result = self.run_evidence(register)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("RUNTIME EVIDENCE REGISTER VERIFIED", result.stdout)

    def test_passing_switch_requires_same_source_and_recovered_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            register = Path(temp) / "register.json"
            entry = self.switch_entry()
            entry["recovered_revision"] = 2
            self.write_register(register, entry)
            result = self.run_evidence(register)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("recovered_revision", result.stderr)


if __name__ == "__main__":
    unittest.main()
