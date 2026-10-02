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
STARTUP = ROOT / "scripts" / "startup.py"
CHECKPOINT = ROOT / "scripts" / "checkpoint.py"
WRAP_UP = ROOT / "scripts" / "wrap_up.py"


class AstraM5RegressionTests(unittest.TestCase):
    def run_script(
        self,
        script: Path,
        *args: str,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(script), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )

    def make_workspace(self, root: Path) -> Path:
        workspace = root / "workspace"
        setup = self.run_script(SETUP, "--workspace", str(workspace))
        self.assertEqual(setup.returncode, 0, setup.stderr + setup.stdout)
        return workspace

    def start_write_session(
        self,
        workspace: Path,
        *,
        harness: str | None = None,
        project_id: str | None = None,
    ) -> dict[str, object]:
        trust = self.run_script(ROOT / "scripts/runtime_trust.py", "trust", "local",
                                "--workspace", str(workspace), "--confirm", "local")
        self.assertEqual(trust.returncode, 0, trust.stdout + trust.stderr)
        args = [
            "--workspace",
            str(workspace),
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
        ]
        if harness is not None:
            args.extend(["--harness", harness])
        if project_id is not None:
            args.extend(["--project-id", project_id])
        args.append("--json")
        startup = self.run_script(STARTUP, *args)
        self.assertEqual(startup.returncode, 0, startup.stderr + startup.stdout)
        return json.loads(startup.stdout)

    def write_bundle(self, root: Path, operation_id: str = "m5-wrap") -> Path:
        path = root / f"{operation_id}.json"
        path.write_text(
            json.dumps(
                {
                    "operation_id": operation_id,
                    "durable_facts": ["M5 authority durable fact"],
                    "unfinished_work": [],
                    "reusable_lessons": [],
                    "project_updates": [],
                    "history": [],
                    "checkpoint": {
                        "summary": f"M5 wrap {operation_id}",
                        "completed": ["authority checked"],
                        "next_steps": [],
                        "artifacts": [],
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    def test_f11_degraded_session_cannot_checkpoint_through_supported_writer(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.make_workspace(Path(temp))
            startup = self.run_script(
                STARTUP,
                "--workspace",
                str(workspace),
                "--runtime",
                "local",
                "--mode",
                "degraded_offline",
                "--json",
            )
            self.assertEqual(startup.returncode, 0, startup.stderr + startup.stdout)
            report = json.loads(startup.stdout)
            self.assertFalse(report["write_policy"]["core_allows_writes"])
            self.assertFalse(report["write_policy"]["effective_runtime_write_ready"])

            checkpoint = self.run_script(
                CHECKPOINT,
                "--workspace",
                str(workspace),
                "--summary",
                "must be denied by degraded authority",
            )
            self.assertNotEqual(checkpoint.returncode, 0, checkpoint.stdout + checkpoint.stderr)
            self.assertIn("authority", checkpoint.stderr.lower())
            self.assertEqual(list((workspace / "state" / "operations").glob("*.json")), [])
            self.assertFalse((workspace / "state" / "pending_checkpoint.json").exists())

    def test_unknown_runtime_without_verified_write_capability_cannot_mutate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.make_workspace(Path(temp))
            startup = self.run_script(
                STARTUP,
                "--workspace",
                str(workspace),
                "--runtime",
                "unrecognized-harness",
                "--mode",
                "regular",
                "--json",
            )
            self.assertEqual(startup.returncode, 0, startup.stderr + startup.stdout)
            report = json.loads(startup.stdout)
            self.assertEqual(report["runtime"], "unknown")
            self.assertFalse(report["write_policy"]["effective_runtime_write_ready"])

            checkpoint = self.run_script(
                CHECKPOINT,
                "--workspace",
                str(workspace),
                "--summary",
                "unknown runtime must remain read only",
            )
            self.assertNotEqual(checkpoint.returncode, 0, checkpoint.stdout + checkpoint.stderr)
            self.assertIn("authority", checkpoint.stderr.lower())
            self.assertEqual(list((workspace / "state" / "operations").glob("*.json")), [])

    def test_runtime_mutation_requires_exact_issued_session_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.make_workspace(Path(temp))
            report = self.start_write_session(workspace)
            before = {p.name: p.read_bytes() for p in (workspace / "state/operations").glob("*.json")}
            session_id = str(report["session_authority"]["session_id"])

            omitted = self.run_script(
                CHECKPOINT,
                "--workspace",
                str(workspace),
                "--summary",
                "session id must be presented",
            )
            self.assertNotEqual(omitted.returncode, 0, omitted.stdout + omitted.stderr)
            self.assertIn("session", omitted.stderr.lower())
            self.assertEqual({p.name: p.read_bytes() for p in (workspace / "state/operations").glob("*.json")}, before)

            wrong = self.run_script(
                CHECKPOINT,
                "--workspace",
                str(workspace),
                "--summary",
                "wrong session must be denied",
                "--session-id",
                "ses_00000000000000000000000000000000",
            )
            self.assertNotEqual(wrong.returncode, 0, wrong.stdout + wrong.stderr)
            self.assertIn("session", wrong.stderr.lower())
            self.assertEqual({p.name: p.read_bytes() for p in (workspace / "state/operations").glob("*.json")}, before)

            accepted = self.run_script(
                CHECKPOINT,
                "--workspace",
                str(workspace),
                "--summary",
                "exact session is accepted",
                "--session-id",
                session_id,
            )
            self.assertEqual(accepted.returncode, 0, accepted.stderr + accepted.stdout)
            self.assertIn("CHECKPOINT VERIFIED", accepted.stdout)

    def test_stale_session_revision_is_refused_before_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.make_workspace(Path(temp))
            report = self.start_write_session(workspace)
            session_id = str(report["session_authority"]["session_id"])

            first = self.run_script(
                CHECKPOINT,
                "--workspace",
                str(workspace),
                "--summary",
                "advance committed revision",
                "--session-id",
                session_id,
            )
            self.assertEqual(first.returncode, 0, first.stderr + first.stdout)

            authority_path = workspace / "state" / "session_authority.json"
            authority = json.loads(authority_path.read_text(encoding="utf-8"))
            self.assertEqual(authority["current_revision"], report["session_authority"]["current_revision"] + 1)
            authority["current_revision"] = 0
            authority_path.write_text(json.dumps(authority, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            stale = self.run_script(
                CHECKPOINT,
                "--workspace",
                str(workspace),
                "--summary",
                "stale authority must not advance state",
                "--session-id",
                session_id,
            )
            self.assertNotEqual(stale.returncode, 0, stale.stdout + stale.stderr)
            self.assertIn("revision", stale.stderr.lower())
            store = json.loads((workspace / "state" / "store.json").read_text(encoding="utf-8"))
            self.assertEqual(store["revision"], report["session_authority"]["current_revision"] + 1)

    def test_startup_binds_explicit_harness_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.make_workspace(Path(temp))
            report = self.start_write_session(workspace, harness="live-runtime-rehearsal:test-123")
            authority = report["session_authority"]
            self.assertEqual(authority["harness"], "live-runtime-rehearsal:test-123")
            persisted = json.loads((workspace / "state" / "session_authority.json").read_text(encoding="utf-8"))
            self.assertEqual(persisted["harness"], "live-runtime-rehearsal:test-123")

    def test_project_bound_session_requires_matching_project_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.make_workspace(Path(temp))
            seeded = self.run_script(
                CHECKPOINT,
                "--workspace",
                str(workspace),
                "--summary",
                "seed stable project identity",
                "--project",
                "Bound Project",
            )
            self.assertEqual(seeded.returncode, 0, seeded.stderr + seeded.stdout)
            registry = json.loads((workspace / "state" / "projects.json").read_text(encoding="utf-8"))["projects"]
            project_id = next(pid for pid, entry in registry.items() if entry["display_name"] == "Bound Project")

            report = self.start_write_session(workspace, project_id=project_id)
            session_id = str(report["session_authority"]["session_id"])

            matching = self.run_script(
                CHECKPOINT,
                "--workspace",
                str(workspace),
                "--summary",
                "matching project authority",
                "--project",
                "Bound Project",
                "--session-id",
                session_id,
            )
            self.assertEqual(matching.returncode, 0, matching.stderr + matching.stdout)

            mismatched = self.run_script(
                CHECKPOINT,
                "--workspace",
                str(workspace),
                "--summary",
                "unbound project must be denied",
                "--project",
                "Different Project",
                "--session-id",
                session_id,
            )
            self.assertNotEqual(mismatched.returncode, 0, mismatched.stdout + mismatched.stderr)
            self.assertIn("project", mismatched.stderr.lower())

    def test_wrap_up_requires_exact_runtime_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            bundle = self.write_bundle(root, "m5-wrap-session")
            report = self.start_write_session(workspace)
            session_id = str(report["session_authority"]["session_id"])

            omitted = self.run_script(
                WRAP_UP,
                "--workspace",
                str(workspace),
                "--bundle",
                str(bundle),
            )
            self.assertNotEqual(omitted.returncode, 0, omitted.stdout + omitted.stderr)
            self.assertIn("session", omitted.stderr.lower())

            accepted = self.run_script(
                WRAP_UP,
                "--workspace",
                str(workspace),
                "--bundle",
                str(bundle),
                "--session-id",
                session_id,
            )
            self.assertEqual(accepted.returncode, 0, accepted.stderr + accepted.stdout)
            self.assertIn("WRAP UP VERIFIED", accepted.stdout)

    def test_checkpoint_recovery_requires_same_runtime_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.make_workspace(Path(temp))
            report = self.start_write_session(workspace)
            session_id = str(report["session_authority"]["session_id"])
            crash_env = dict(os.environ)
            crash_env["AHAM_BRAHMASMI_TEST_MODE"] = "1"
            crash_env["AHAM_BRAHMASMI_TEST_CRASH_POINT"] = "checkpoint_after_pending"
            interrupted = self.run_script(
                CHECKPOINT,
                "--workspace",
                str(workspace),
                "--summary",
                "recover under same authority",
                "--session-id",
                session_id,
                env=crash_env,
            )
            self.assertEqual(interrupted.returncode, 86, interrupted.stderr + interrupted.stdout)
            self.assertTrue((workspace / "state" / "pending_checkpoint.json").is_file())

            denied = self.run_script(CHECKPOINT, "--workspace", str(workspace), "--recover-pending")
            self.assertNotEqual(denied.returncode, 0, denied.stdout + denied.stderr)
            self.assertIn("session", denied.stderr.lower())

            recovered = self.run_script(
                CHECKPOINT,
                "--workspace",
                str(workspace),
                "--recover-pending",
                "--session-id",
                session_id,
            )
            self.assertEqual(recovered.returncode, 0, recovered.stderr + recovered.stdout)
            self.assertIn("CHECKPOINT VERIFIED", recovered.stdout)

    def test_wrap_up_recovery_requires_same_runtime_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            bundle = self.write_bundle(root, "m5-wrap-recovery")
            report = self.start_write_session(workspace)
            session_id = str(report["session_authority"]["session_id"])
            crash_env = dict(os.environ)
            crash_env["AHAM_BRAHMASMI_TEST_MODE"] = "1"
            crash_env["AHAM_BRAHMASMI_TEST_CRASH_POINT"] = "wrap_up_after_pending"
            interrupted = self.run_script(
                WRAP_UP,
                "--workspace",
                str(workspace),
                "--bundle",
                str(bundle),
                "--session-id",
                session_id,
                env=crash_env,
            )
            self.assertEqual(interrupted.returncode, 86, interrupted.stderr + interrupted.stdout)
            self.assertTrue((workspace / "state" / "pending_wrap_up.json").is_file())

            denied = self.run_script(WRAP_UP, "--workspace", str(workspace), "--recover-pending")
            self.assertNotEqual(denied.returncode, 0, denied.stdout + denied.stderr)
            self.assertIn("session", denied.stderr.lower())

            recovered = self.run_script(
                WRAP_UP,
                "--workspace",
                str(workspace),
                "--recover-pending",
                "--session-id",
                session_id,
            )
            self.assertEqual(recovered.returncode, 0, recovered.stderr + recovered.stdout)
            self.assertIn("WRAP UP VERIFIED", recovered.stdout)


if __name__ == "__main__":
    unittest.main()
