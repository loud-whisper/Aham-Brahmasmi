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
LIFECYCLE = ROOT / "scripts" / "record_lifecycle.py"
CONTEXT = ROOT / "scripts" / "context_packet.py"
CONFORMANCE = ROOT / "scripts" / "runtime_conformance.py"
POLICY = ROOT / "core" / "runtime_conformance.json"
REGISTER = ROOT / "evidence" / "runtime_harness_register.json"


class R3ContextConformanceTests(unittest.TestCase):
    def run_script(self, script: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(script), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def write_json(self, path: Path, value: dict) -> Path:
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def make_workspace(self, root: Path) -> Path:
        workspace = root / "workspace"
        result = self.run_script(SETUP, "--workspace", str(workspace))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return workspace

    def wrap_project(
        self,
        root: Path,
        workspace: Path,
        *,
        operation_id: str,
        project: str,
        fact: str,
        task: str,
        update: str,
        summary: str,
    ) -> None:
        bundle = {
            "operation_id": operation_id,
            "durable_facts": [fact],
            "unfinished_work": [task],
            "reusable_lessons": [],
            "project_updates": [{"project": project, "content": update}],
            "history": [],
            "checkpoint": {
                "summary": summary,
                "completed": [f"Completed work for {project}."],
                "next_steps": [f"Continue work for {project}."],
                "project": project,
            },
        }
        result = self.run_script(
            WRAP_UP,
            "--workspace",
            str(workspace),
            "--bundle",
            str(self.write_json(root / f"{operation_id}.json", bundle)),
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def project_id(self, workspace: Path, display_name: str) -> str:
        registry = json.loads((workspace / "state" / "projects.json").read_text(encoding="utf-8"))
        return next(project_id for project_id, entry in registry["projects"].items() if entry["display_name"] == display_name)

    def lifecycle_state(self, workspace: Path) -> dict:
        result = self.run_script(LIFECYCLE, "list", "--workspace", str(workspace), "--json")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return json.loads(result.stdout)

    def apply_lifecycle(self, root: Path, workspace: Path, name: str, request: dict) -> subprocess.CompletedProcess[str]:
        return self.run_script(
            LIFECYCLE,
            "apply",
            "--workspace",
            str(workspace),
            "--request",
            str(self.write_json(root / f"{name}.json", request)),
            "--json",
        )

    def packet(self, workspace: Path, project_id: str, max_bytes: int = 8192) -> subprocess.CompletedProcess[str]:
        return self.run_script(
            CONTEXT,
            "--workspace",
            str(workspace),
            "--project-id",
            project_id,
            "--max-bytes",
            str(max_bytes),
            "--json",
        )

    def test_packet_is_bounded_project_scoped_and_revision_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            self.wrap_project(
                root,
                workspace,
                operation_id="r3-alpha",
                project="Alpha",
                fact="Alpha fact must remain private to Alpha.",
                task="Alpha open task.",
                update="Alpha project update.",
                summary="Alpha checkpoint summary",
            )
            self.wrap_project(
                root,
                workspace,
                operation_id="r3-beta",
                project="Beta",
                fact="Beta secret must never enter Alpha packet.",
                task="Beta secret task.",
                update="Beta secret project update.",
                summary="Beta secret checkpoint",
            )

            alpha_id = self.project_id(workspace, "Alpha")
            result = self.packet(workspace, alpha_id, 8192)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertLessEqual(len(result.stdout.encode("utf-8")), 8192)
            packet = json.loads(result.stdout)

            self.assertEqual(packet["format"], "aham-brahmasmi-context-packet")
            self.assertEqual(packet["version"], 1)
            self.assertEqual(packet["source_revision"], 2)
            self.assertEqual(packet["project"]["project_id"], alpha_id)
            self.assertEqual(packet["project"]["display_name"], "Alpha")
            self.assertEqual(packet["checkpoint"]["revision"], 1)
            self.assertEqual(packet["checkpoint"]["summary"], "Alpha checkpoint summary")
            rendered = json.dumps(packet, sort_keys=True)
            self.assertIn("Alpha fact must remain private to Alpha.", rendered)
            self.assertIn("Alpha open task.", rendered)
            self.assertIn("Alpha project update.", rendered)
            self.assertNotIn("Beta secret", rendered)
            self.assertFalse(packet["budget"]["token_equivalence_claimed"])
            self.assertEqual(packet["budget"]["max_bytes"], 8192)

    def test_packet_reflects_current_lifecycle_state_not_stale_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            self.wrap_project(
                root,
                workspace,
                operation_id="r3-current",
                project="Current",
                fact="Current fact v1.",
                task="Current task remains open.",
                update="Current update.",
                summary="Current checkpoint",
            )
            project_id = self.project_id(workspace, "Current")
            state = self.lifecycle_state(workspace)
            old_fact = state["facts"][0]
            task = state["tasks"][0]

            supersede = self.apply_lifecycle(
                root,
                workspace,
                "supersede",
                {
                    "operation_id": "r3-current-supersede",
                    "action": "fact_supersede",
                    "fact_id": old_fact["fact_id"],
                    "statement": "Current fact v2.",
                    "source": "authoritative-update",
                    "reason": "The earlier value became stale.",
                },
            )
            self.assertEqual(supersede.returncode, 0, supersede.stderr + supersede.stdout)
            complete = self.apply_lifecycle(
                root,
                workspace,
                "complete",
                {
                    "operation_id": "r3-current-complete",
                    "action": "task_complete",
                    "task_id": task["task_id"],
                    "reason": "Work finished.",
                },
            )
            self.assertEqual(complete.returncode, 0, complete.stderr + complete.stdout)

            result = self.packet(workspace, project_id, 8192)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            packet = json.loads(result.stdout)
            statements = [item["statement"] for item in packet["facts"]]
            descriptions = [item["description"] for item in packet["tasks"]]
            self.assertEqual(statements, ["Current fact v2."])
            self.assertNotIn("Current fact v1.", statements)
            self.assertNotIn("Current task remains open.", descriptions)
            self.assertEqual(packet["source_revision"], 3)

    def test_packet_budget_truncation_is_deterministic_and_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            bundle = {
                "operation_id": "r3-large",
                "durable_facts": [f"Fact {index}: " + ("x" * 220) for index in range(12)],
                "unfinished_work": [f"Task {index}: " + ("y" * 220) for index in range(12)],
                "reusable_lessons": [],
                "project_updates": [{"project": "Large", "content": "Latest project state " + ("z" * 300)}],
                "history": [],
                "checkpoint": {
                    "summary": "Large checkpoint",
                    "completed": [],
                    "next_steps": ["Continue Large."],
                    "project": "Large",
                },
            }
            wrapped = self.run_script(
                WRAP_UP,
                "--workspace",
                str(workspace),
                "--bundle",
                str(self.write_json(root / "large.json", bundle)),
            )
            self.assertEqual(wrapped.returncode, 0, wrapped.stderr + wrapped.stdout)
            project_id = self.project_id(workspace, "Large")

            first = self.packet(workspace, project_id, 2200)
            second = self.packet(workspace, project_id, 2200)
            self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
            self.assertEqual(first.stdout, second.stdout)
            self.assertLessEqual(len(first.stdout.encode("utf-8")), 2200)
            packet = json.loads(first.stdout)
            omitted = packet["budget"]["omitted"]
            self.assertGreater(omitted["facts"] + omitted["tasks"] + omitted["project_updates"], 0)
            self.assertTrue(packet["budget"]["truncated"])
            self.assertRegex(packet["packet_sha256"], r"^[0-9a-f]{64}$")

    def test_packet_refuses_budget_too_small_for_required_core(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            self.wrap_project(
                root,
                workspace,
                operation_id="r3-small",
                project="Small",
                fact="Small fact.",
                task="Small task.",
                update="Small update.",
                summary="Small checkpoint",
            )
            project_id = self.project_id(workspace, "Small")
            result = self.packet(workspace, project_id, 128)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("budget", result.stderr.lower())
            self.assertEqual(result.stdout, "")

    def test_conformance_policy_is_capability_based_not_vendor_based(self) -> None:
        policy = json.loads(POLICY.read_text(encoding="utf-8"))
        self.assertEqual(policy["version"], 1)
        self.assertEqual(
            [tier["id"] for tier in policy["tiers"]],
            ["context_packet", "lifecycle_reader", "lifecycle_writer", "recovery_verified"],
        )
        rendered = json.dumps(policy).lower()
        for vendor in ("claude", "gemini", "codex", "opencode", "deepseek"):
            self.assertNotIn(vendor, rendered)
        for tier in policy["tiers"]:
            self.assertIn("demonstrated_requirements", tier)
            self.assertIsInstance(tier["demonstrated_requirements"], list)

    def test_retained_evidence_matrix_reuses_verified_runs_without_new_live_cost(self) -> None:
        result = self.run_script(
            CONFORMANCE,
            "matrix",
            "--register",
            str(REGISTER),
            "--context-budget-bytes",
            "8192",
            "--json",
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        matrix = json.loads(result.stdout)
        self.assertEqual(matrix["context_budget_bytes"], 8192)
        self.assertFalse(matrix["token_equivalence_claimed"])
        self.assertEqual(matrix["new_live_runs_required"], 0)

        rich = {(item["harness"], item["harness_version"]): item for item in matrix["selected_rich_evidence"]}
        self.assertEqual(rich[("DeepSeek Harness", "0.1.5-rc.2")]["tier"], "lifecycle_writer")
        self.assertEqual(rich[("OpenCode", "1.14.25")]["tier"], "recovery_verified")
        self.assertEqual(rich[("DeepSeek Harness", "0.1.5-rc.2")]["context_tokens"], 65536)
        self.assertEqual(rich[("OpenCode", "1.14.25")]["context_tokens"], 65536)

        legacy = {item["runtime_profile"]: item for item in matrix["legacy_unclassified"]}
        self.assertIn("gemini", legacy)
        self.assertIn("codex", legacy)
        self.assertIn("insufficient metadata", legacy["gemini"]["reason"].lower())

    def test_unknown_runtime_name_alone_never_grants_conformance(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            register = Path(temp) / "register.json"
            register.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "entries": [
                            {
                                "entry_id": "name-only",
                                "evidence_type": "framework_profile_test",
                                "runtime_profile": "future-super-runtime",
                                "result": "pass",
                                "independently_verified": True,
                                "claim_scope": "framework_profile_only",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            result = self.run_script(
                CONFORMANCE,
                "matrix",
                "--register",
                str(register),
                "--context-budget-bytes",
                "8192",
                "--json",
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            matrix = json.loads(result.stdout)
            self.assertEqual(matrix["selected_rich_evidence"], [])
            self.assertEqual(matrix["legacy_unclassified"][0]["runtime_profile"], "future-super-runtime")
            self.assertIn("insufficient", matrix["legacy_unclassified"][0]["reason"].lower())


if __name__ == "__main__":
    unittest.main()
