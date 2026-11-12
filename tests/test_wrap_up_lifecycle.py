from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def run(script: str, *args: str, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args], cwd=ROOT, text=True,
                          capture_output=True, check=False, env=env)


def aham(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(ROOT / "aham.py"), *args], cwd=ROOT, text=True,
                          capture_output=True, check=False)


def item(identity: str, status: str = "verified", routes=(), reason: str | None = None) -> dict:
    return {"id": identity, "summary": f"Summary of {identity}", "evidence_status": status,
            "evidence": "Test suite passed." if status == "verified" else "", "next_action": None,
            "routes": [{"field": field, "index": index} for field, index in routes],
            "nothing_durable_reason": reason}


class WrapUpLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.workspace = self.root / "workspace"
        self.assertEqual(run("setup_workspace.py", "--workspace", str(self.workspace)).returncode, 0)
        self.pending = self.workspace / "state/pending_wrap_up.json"
        origin = self.wrap(self.bundle("origin", durable_facts=["Alpha runs on port 8080."],
                                       unfinished_work=["Finish the alpha migration.", "Write the release note."]))
        self.assertEqual(origin.returncode, 0, origin.stdout + origin.stderr)
        state = self.state()
        self.fact = state["facts"][0]["fact_id"]
        self.tasks = [task["task_id"] for task in state["tasks"]]

    def bundle(self, operation_id: str, **fields) -> dict:
        value = {"operation_id": operation_id, "durable_facts": [], "unfinished_work": [],
                 "reusable_lessons": [], "project_updates": [], "history": [],
                 "checkpoint": {"summary": "State after " + operation_id, "next_steps": ["Continue"]}}
        value.update(fields)
        return value

    def wrap(self, bundle: dict, *extra: str, env: dict | None = None) -> subprocess.CompletedProcess[str]:
        path = self.root / (bundle["operation_id"] + ".json")
        path.write_text(json.dumps(bundle), encoding="utf-8")
        return run("wrap_up.py", "--workspace", str(self.workspace), "--bundle", str(path), *extra, env=env)

    def state(self) -> dict:
        return json.loads(run("record_lifecycle.py", "list", "--workspace", str(self.workspace), "--json").stdout)

    def revision(self) -> int:
        return json.loads((self.workspace / "state/store.json").read_text(encoding="utf-8"))["revision"]

    def status_of(self, identity: str) -> str:
        state = self.state()
        for record in state["tasks"]:
            if record["task_id"] == identity:
                return record["status"]
        for record in state["facts"]:
            if record["fact_id"] == identity:
                return record["status"]
        raise AssertionError("unknown record " + identity)

    def closing(self, operation_id: str, status: str = "verified") -> dict:
        return self.bundle(operation_id, inventory=[item("alpha-migration", status)], lifecycle=[
            {"action": "task_complete", "id": self.tasks[0], "reason": "Migration verified.",
             "item": "alpha-migration"}])

    def test_task_complete_requires_verified_item(self) -> None:
        before = self.revision()
        result = self.wrap(self.closing("unverified-close", "unverified"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("keep the task open", result.stderr)
        self.assertEqual(self.revision(), before)
        self.assertFalse(self.pending.exists())

    def test_unknown_or_terminal_id_rejects_whole_bundle_before_mutation(self) -> None:
        before = self.revision()
        memory = (self.workspace / "MEMORY.md").read_text(encoding="utf-8")
        unknown = self.bundle("unknown-id", durable_facts=["Beta is new."], inventory=[
            item("beta", routes=[("durable_facts", 0)]), item("ghost")], lifecycle=[
            {"action": "task_complete", "id": "task_" + "0" * 32, "reason": "Done.", "item": "ghost"}])
        result = self.wrap(unknown)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("task_" + "0" * 32, result.stderr)
        self.assertEqual(self.wrap(self.closing("first-close")).returncode, 0)
        after_close = self.revision()
        terminal = self.wrap(self.closing("second-close"))
        self.assertNotEqual(terminal.returncode, 0)
        self.assertIn(self.tasks[0], terminal.stderr)
        self.assertEqual(self.revision(), after_close)
        self.assertGreater(after_close, before)
        self.assertNotIn("Beta is new.", (self.workspace / "MEMORY.md").read_text(encoding="utf-8"))
        self.assertTrue((self.workspace / "MEMORY.md").read_text(encoding="utf-8").startswith(memory))
        self.assertFalse(self.pending.exists())

    def test_wrap_up_closes_task(self) -> None:
        result = self.wrap(self.closing("close-alpha"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        listing = aham("tasks", "list", "--workspace", str(self.workspace), "--json")
        self.assertEqual(listing.returncode, 0, listing.stdout + listing.stderr)
        tasks = {task["task_id"]: task["status"] for task in json.loads(listing.stdout)["tasks"]}
        self.assertEqual(tasks[self.tasks[0]], "completed")
        self.assertEqual(tasks[self.tasks[1]], "open")
        self.assertNotIn("facts", json.loads(listing.stdout))
        from startup_packet import build_startup_packet
        packet = build_startup_packet(self.workspace, "regular")
        open_ids = [entry["id"] for part in packet["parts"] if part["section"] == "open_tasks"
                    for entry in part["items"]]
        self.assertEqual(open_ids, [self.tasks[1]])
        self.assertFalse(self.pending.exists())

    def test_crash_between_commit_and_closure_replays_once(self) -> None:
        env = dict(os.environ, AHAM_BRAHMASMI_TEST_MODE="1", AHAM_BRAHMASMI_TEST_CRASH_POINT="wrap_up_after_receipt")
        crashed = self.wrap(self.closing("crash-close"), env=env)
        self.assertEqual(crashed.returncode, 86, crashed.stdout + crashed.stderr)
        self.assertTrue(self.pending.exists())
        self.assertEqual(self.status_of(self.tasks[0]), "open")
        committed = self.revision()
        recovered = run("wrap_up.py", "--workspace", str(self.workspace), "--recover-pending")
        self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
        self.assertEqual(self.status_of(self.tasks[0]), "completed")
        self.assertEqual(self.revision(), committed + 1)
        self.assertFalse(self.pending.exists())
        second = run("wrap_up.py", "--workspace", str(self.workspace), "--recover-pending")
        self.assertNotEqual(second.returncode, 0)
        rerun = self.wrap(self.closing("crash-close"))
        self.assertEqual(rerun.returncode, 0, rerun.stdout + rerun.stderr)
        self.assertEqual(self.revision(), committed + 1)

    def test_crash_between_two_closures_applies_each_once(self) -> None:
        bundle = self.bundle("two-closes", inventory=[item("alpha-migration"), item("release-note")], lifecycle=[
            {"action": "task_complete", "id": self.tasks[0], "reason": "Verified.", "item": "alpha-migration"},
            {"action": "task_cancel", "id": self.tasks[1], "reason": "No longer needed.", "item": "release-note"}])
        base = self.revision()
        env = dict(os.environ, AHAM_BRAHMASMI_TEST_MODE="1",
                   AHAM_BRAHMASMI_TEST_CRASH_POINT="wrap_up_after_lifecycle_operation")
        crashed = self.wrap(bundle, env=env)
        self.assertEqual(crashed.returncode, 86, crashed.stdout + crashed.stderr)
        self.assertEqual(self.status_of(self.tasks[0]), "completed")
        self.assertEqual(self.status_of(self.tasks[1]), "open")
        self.assertEqual(self.revision(), base + 2)
        progress = json.loads(self.pending.read_text(encoding="utf-8"))["progress"]
        self.assertEqual(progress["step"], "apply_lifecycle")
        recovered = run("wrap_up.py", "--workspace", str(self.workspace), "--recover-pending")
        self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
        self.assertEqual(self.status_of(self.tasks[1]), "cancelled")
        self.assertEqual(self.revision(), base + 3)
        self.assertFalse(self.pending.exists())

    def test_supersede_links_both_facts(self) -> None:
        bundle = self.bundle("move-port", inventory=[item("port-change")], lifecycle=[
            {"action": "fact_supersede", "id": self.fact, "reason": "Port changed.", "item": "port-change",
             "replacement": "Alpha runs on port 9090."}])
        result = self.wrap(bundle)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        facts = {fact["fact_id"]: fact for fact in self.state()["facts"]}
        old = facts[self.fact]
        new = facts[old["superseded_by"]]
        self.assertEqual(old["status"], "superseded")
        self.assertEqual(new["supersedes"], self.fact)
        self.assertEqual(new["statement"], "Alpha runs on port 9090.")
        self.assertEqual(new["status"], "active")
        listing = aham("facts", "list", "--workspace", str(self.workspace), "--json")
        self.assertEqual(listing.returncode, 0, listing.stdout + listing.stderr)
        self.assertNotIn("tasks", json.loads(listing.stdout))

    def test_lifecycle_needs_an_inventory_item(self) -> None:
        missing = self.bundle("no-inventory", lifecycle=[
            {"action": "task_cancel", "id": self.tasks[1], "reason": "Dropped.", "item": "x"}])
        self.assertNotEqual(self.wrap(missing).returncode, 0)
        wrong = self.bundle("wrong-item", inventory=[item("other", reason="Discussion only.")], lifecycle=[
            {"action": "task_cancel", "id": self.tasks[1], "reason": "Dropped.", "item": "absent"}])
        result = self.wrap(wrong)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("absent", result.stderr)

    def test_session_can_save_after_a_closing_wrap_up(self) -> None:
        from confirm_context import read_all_and_confirm
        self.assertEqual(run("runtime_trust.py", "trust", "local", "--workspace", str(self.workspace),
                             "--confirm", "local").returncode, 0)
        started = run("startup.py", "--workspace", str(self.workspace), "--runtime", "local", "--mode", "regular",
                      "--capability", "read_files", "--capability", "write_files", "--json")
        session = json.loads(started.stdout)["session_authority"]["session_id"]
        read_all_and_confirm(self.workspace, session)
        wrapped = self.wrap(self.closing("session-close"), "--session-id", session)
        self.assertEqual(wrapped.returncode, 0, wrapped.stdout + wrapped.stderr)
        saved = run("checkpoint.py", "--workspace", str(self.workspace), "--summary", "after closing",
                    "--session-id", session)
        self.assertEqual(saved.returncode, 0, saved.stdout + saved.stderr)


if __name__ == "__main__":
    unittest.main()
