from __future__ import annotations

import datetime
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
FRESHNESS = {"verified_local", "matches_upstream_ref", "behind_upstream_ref", "ahead_of_upstream_ref",
             "diverged_from_upstream_ref"}


def run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args], cwd=ROOT, text=True,
                          capture_output=True, check=False)


def item(identity: str, status: str = "verified", routes=(), reason: str | None = None) -> dict:
    return {"id": identity, "summary": f"Summary of {identity}", "evidence_status": status,
            "evidence": "Test suite passed." if status == "verified" else "", "next_action": None,
            "routes": [{"field": field, "index": index} for field, index in routes],
            "nothing_durable_reason": reason}


@unittest.skipIf(shutil.which("git") is None, "git is not available")
class WrapUpOutcomeTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.workspace = self.root / "workspace"
        self.assertEqual(run("setup_workspace.py", "--workspace", str(self.workspace)).returncode, 0)

    def git(self, where: Path, *args: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(["git", "-C", str(where), *args], text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def init_git(self) -> None:
        result = run("git_transport.py", "init", "--workspace", str(self.workspace),
                     "--author-name", "Aham Test", "--author-email", "test@example.invalid")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        snapshot = run("git_transport.py", "snapshot", "--workspace", str(self.workspace))
        self.assertEqual(snapshot.returncode, 0, snapshot.stdout + snapshot.stderr)

    def add_upstream(self) -> Path:
        """Give the workspace a remote and an upstream-tracking ref, as an owner would."""
        remote = self.root / "remote.git"
        subprocess.run(["git", "init", "--bare", "--quiet", str(remote)], check=True)
        branch = self.git(self.workspace, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        self.git(self.workspace, "remote", "add", "origin", str(remote))
        self.git(self.workspace, "push", "--quiet", "--set-upstream", "origin", branch)
        self.branch = branch
        return remote

    def bundle(self, operation_id: str, **fields) -> dict:
        value = {"operation_id": operation_id, "durable_facts": [], "unfinished_work": [],
                 "reusable_lessons": [], "project_updates": [], "history": [],
                 "checkpoint": {"summary": "State after " + operation_id, "next_steps": ["Review the release note."]}}
        value.update(fields)
        return value

    def wrap(self, bundle: dict, *extra: str) -> tuple[subprocess.CompletedProcess[str], dict]:
        path = self.root / (bundle["operation_id"] + ".json")
        path.write_text(json.dumps(bundle), encoding="utf-8")
        result = run("wrap_up.py", "--workspace", str(self.workspace), "--bundle", str(path), "--json", *extra)
        receipt = json.loads(result.stdout) if result.stdout.strip().startswith("{") else {}
        return result, receipt

    def start(self, mode: str = "regular") -> dict:
        self.assertEqual(run("runtime_trust.py", "trust", "local", "--workspace", str(self.workspace),
                             "--confirm", "local").returncode, 0)
        result = run("startup.py", "--workspace", str(self.workspace), "--runtime", "local", "--mode", mode,
                     "--capability", "read_files", "--capability", "write_files", "--json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_summary_counts_match_committed_items(self) -> None:
        _, first = self.wrap(self.bundle("origin", unfinished_work=["Finish alpha.", "Write the release note."]))
        tasks = json.loads(run("record_lifecycle.py", "list", "--workspace", str(self.workspace), "--json").stdout)["tasks"]
        self.assertEqual(first["summary"]["tasks_open"], 2)
        result, receipt = self.wrap(self.bundle(
            "second", durable_facts=["Alpha is enabled.", "Beta is disabled."], history=["Enabled alpha."],
            inventory=[item("alpha", routes=[("durable_facts", 0), ("durable_facts", 1), ("history", 0)])],
            lifecycle=[{"action": "task_complete", "id": tasks[0]["task_id"], "reason": "Verified.", "item": "alpha"}]))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        summary = receipt["summary"]
        self.assertEqual(summary["outcome"], "complete")
        self.assertEqual(summary["routed"], {"durable_facts": 2, "unfinished_work": 0, "reusable_lessons": 0,
                                             "project_updates": 0, "history": 1})
        self.assertEqual(sum(summary["routed"].values()), receipt["accepted_item_count"])
        self.assertEqual(summary["tasks_completed"], [tasks[0]["task_id"]])
        self.assertEqual(summary["tasks_open"], 1)
        self.assertEqual(summary["lifecycle"], [{"id": tasks[0]["task_id"], "action": "task_complete",
                                                 "status": "applied"}])
        self.assertEqual(summary["snapshot"], {"status": "not_configured", "commit": None})
        self.assertEqual(summary["replication"], {"status": "not_configured"})
        self.assertIn("Review the release note.", summary["next_action"])
        text = run("wrap_up.py", "--workspace", str(self.workspace), "--status", "second")
        self.assertIn("Outcome: complete", text.stdout)
        self.assertIn("Tasks still open: 1", text.stdout)

    def test_snapshot_flag_commits_and_reports_commit(self) -> None:
        self.init_git()
        before = self.git(self.workspace, "rev-parse", "HEAD").stdout.strip()
        _, plain = self.wrap(self.bundle("plain", durable_facts=["Alpha is enabled."]))
        self.assertEqual(plain["summary"]["snapshot"], {"status": "not_requested", "commit": None})
        self.assertEqual(self.git(self.workspace, "rev-parse", "HEAD").stdout.strip(), before)
        result, receipt = self.wrap(self.bundle("snap", durable_facts=["Beta is disabled."]), "--snapshot")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        head = self.git(self.workspace, "rev-parse", "HEAD").stdout.strip()
        self.assertNotEqual(head, before)
        self.assertEqual(receipt["summary"]["snapshot"], {"status": "committed", "commit": head})
        self.assertEqual(self.git(self.workspace, "status", "--porcelain", "--", "MEMORY.md").stdout, "")

    def test_snapshot_failure_does_not_invalidate_receipt(self) -> None:
        self.init_git()
        self.git(self.workspace, "checkout", "--quiet", "--detach")
        result, receipt = self.wrap(self.bundle("detached", durable_facts=["Alpha is enabled."]), "--snapshot")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(receipt["summary"]["snapshot"]["status"], "failed")
        self.assertIsNone(receipt["summary"]["snapshot"]["commit"])
        self.assertEqual(receipt["status"], "complete")
        status = run("wrap_up.py", "--workspace", str(self.workspace), "--status", "detached", "--json")
        self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
        self.assertEqual(json.loads(status.stdout)["status"], "complete")

    def test_no_push_ever(self) -> None:
        self.init_git()
        remote = self.add_upstream()
        remote_before = self.git(remote, "rev-parse", self.branch).stdout.strip()
        result, receipt = self.wrap(self.bundle("snap", durable_facts=["Alpha is enabled."]), "--snapshot")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(receipt["summary"]["snapshot"]["status"], "committed")
        self.assertEqual(self.git(remote, "rev-parse", self.branch).stdout.strip(), remote_before)
        self.assertEqual(receipt["summary"]["replication"], {"status": "ahead_of_upstream_ref"})
        self.assertIn("push", receipt["summary"]["next_action"])
        self.git(self.workspace, "push", "--quiet")
        status = json.loads(run("wrap_up.py", "--workspace", str(self.workspace), "--status", "snap", "--json").stdout)
        self.assertEqual(status["summary"]["replication"], {"status": "contained_in_upstream_ref"})

    def test_replication_never_claimed_without_upstream_ref(self) -> None:
        _, no_git = self.wrap(self.bundle("no-git", durable_facts=["Alpha is enabled."]))
        self.assertEqual(no_git["summary"]["replication"], {"status": "not_configured"})
        self.init_git()
        _, local_only = self.wrap(self.bundle("local-only", durable_facts=["Beta is disabled."]), "--snapshot")
        self.assertEqual(local_only["summary"]["snapshot"]["status"], "committed")
        self.assertEqual(local_only["summary"]["replication"], {"status": "not_configured"})
        self.add_upstream()
        _, unsaved = self.wrap(self.bundle("unsaved", durable_facts=["Gamma is new."]))
        self.assertEqual(unsaved["summary"]["snapshot"]["status"], "not_requested")
        self.assertEqual(unsaved["summary"]["replication"], {"status": "not_checked"})

    def other_clone_pushes(self, remote: Path) -> None:
        clone = self.root / "clone"
        subprocess.run(["git", "clone", "--quiet", str(remote), str(clone)], check=True)
        (clone / "README.md").write_text("changed elsewhere\n", encoding="utf-8")
        self.git(clone, "-c", "user.name=Other", "-c", "user.email=other@example.invalid", "commit", "--quiet",
                 "-am", "Change from another machine")
        self.git(clone, "push", "--quiet")

    def test_behind_upstream_ref_blocks_writes_not_reads(self) -> None:
        self.init_git()
        remote = self.add_upstream()
        matching = self.start()
        self.assertEqual(matching["state_freshness"], "matches_upstream_ref")
        self.assertTrue(matching["session_authority"]["allowed_operations"])
        self.other_clone_pushes(remote)
        self.git(self.workspace, "fetch", "--quiet")
        report = self.start()
        self.assertEqual(report["state_freshness"], "behind_upstream_ref")
        self.assertTrue(report["ready"])
        self.assertEqual(report["session_authority"]["allowed_operations"], [])
        self.assertFalse(report["write_policy"]["core_allows_writes"])
        packet = run("startup_packet.py", "--workspace", str(self.workspace), "--part", "1")
        self.assertEqual(packet.returncode, 0, packet.stdout + packet.stderr)
        self.assertIn(report["state_freshness"], FRESHNESS)

    def test_startup_never_fetches(self) -> None:
        self.init_git()
        remote = self.add_upstream()
        tracking = "refs/remotes/origin/" + self.branch
        before = self.git(self.workspace, "rev-parse", tracking).stdout.strip()
        self.other_clone_pushes(remote)
        report = self.start()
        self.assertEqual(report["state_freshness"], "matches_upstream_ref")
        self.assertEqual(self.git(self.workspace, "rev-parse", tracking).stdout.strip(), before)
        self.assertNotEqual(self.git(remote, "rev-parse", self.branch).stdout.strip(), before)

    def test_workspace_without_git_stays_verified_local(self) -> None:
        self.assertEqual(self.start()["state_freshness"], "verified_local")

    def test_old_checkpoint_marked_stale(self) -> None:
        import argparse
        import startup
        self.wrap(self.bundle("origin", durable_facts=["Alpha is enabled."]))
        arguments = argparse.Namespace(workspace=str(self.workspace), runtime="unknown", mode="regular",
                                       capability=[], project_id=None, harness=None, context_loaded=False,
                                       upgrade_from=None, json=True)
        fresh = startup.build_report(arguments)["latest_checkpoint"]
        self.assertEqual(fresh["age_days"], 0)
        self.assertIs(fresh["stale"], False)
        later = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=46)
        with mock.patch.object(startup, "current_time", return_value=later):
            old = startup.build_report(arguments)["latest_checkpoint"]
        self.assertEqual(old["age_days"], 46)
        self.assertIs(old["stale"], True)
        contract = json.loads((ROOT / "core/lifecycle.json").read_text(encoding="utf-8"))
        self.assertEqual(contract["checkpoint"]["stale_after_days"], 45)


if __name__ == "__main__":
    unittest.main()
