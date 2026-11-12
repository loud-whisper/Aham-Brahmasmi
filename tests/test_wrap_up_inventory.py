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


def run(script: str, *args: str, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args], cwd=ROOT, text=True,
                          capture_output=True, check=False, env=env)


def item(identity: str, status: str = "verified", routes=(), **extra) -> dict:
    value = {"id": identity, "summary": f"Summary of {identity}", "evidence_status": status,
             "evidence": "Test suite passed." if status == "verified" else "",
             "next_action": None, "routes": [{"field": field, "index": index} for field, index in routes],
             "nothing_durable_reason": None}
    value.update(extra)
    return value


class WrapUpInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.workspace = self.root / "workspace"
        result = run("setup_workspace.py", "--workspace", str(self.workspace))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.pending = self.workspace / "state/pending_wrap_up.json"

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

    def receipt(self, operation_id: str) -> dict:
        return json.loads((self.workspace / "state/wrapups" / f"{operation_id}.json").read_text(encoding="utf-8"))

    def test_v3_bundle_without_inventory_still_commits(self) -> None:
        bundle = self.bundle("plain", durable_facts=["Alpha is enabled."])
        bundle["checkpoint"]["completed"] = ["Enabled alpha."]
        result = self.wrap(bundle)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        receipt = self.receipt("plain")
        self.assertEqual(receipt["version"], 3)
        self.assertNotIn("inventory", receipt)
        self.assertEqual(receipt["bundle"]["checkpoint"]["completed"], ["Enabled alpha."])

    def test_v3_pending_transaction_recovers_after_upgrade(self) -> None:
        env = dict(os.environ, AHAM_BRAHMASMI_TEST_MODE="1", AHAM_BRAHMASMI_TEST_CRASH_POINT="wrap_up_after_pending")
        crashed = self.wrap(self.bundle("interrupted", durable_facts=["Alpha is enabled."]), env=env)
        self.assertNotEqual(crashed.returncode, 0)
        pending = json.loads(self.pending.read_text(encoding="utf-8"))
        self.assertEqual(pending["version"], 3)
        self.assertNotIn("inventory", pending)
        recovered = run("wrap_up.py", "--workspace", str(self.workspace), "--recover-pending")
        self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
        self.assertFalse(self.pending.exists())

    def test_inventory_is_persisted_in_a_version_4_transaction(self) -> None:
        bundle = self.bundle("with-inventory", durable_facts=["Alpha is enabled."], inventory=[
            item("enable-alpha", routes=[("durable_facts", 0)]),
            item("discussed-beta", "not_done", nothing_durable_reason="Discussion only; nothing was decided.")])
        result = self.wrap(bundle)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        receipt = self.receipt("with-inventory")
        self.assertEqual(receipt["version"], 4)
        self.assertEqual([entry["id"] for entry in receipt["inventory"]], ["enable-alpha", "discussed-beta"])
        again = self.wrap(bundle)
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertIn("EXISTING RECEIPT REUSED", again.stdout)

    def test_every_routed_entry_needs_an_item(self) -> None:
        bundle = self.bundle("unlisted", durable_facts=["Alpha is enabled.", "Beta is disabled."], inventory=[
            item("enable-alpha", routes=[("durable_facts", 0)])])
        result = self.wrap(bundle)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("durable_facts", result.stderr)
        self.assertIn("index 1", result.stderr)
        self.assertFalse(self.pending.exists())

    def test_item_needs_route_or_reason(self) -> None:
        result = self.wrap(self.bundle("no-route", inventory=[item("loose-end", "unverified")]))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("loose-end", result.stderr)
        self.assertIn("nothing_durable_reason", result.stderr)

    def test_route_must_name_an_existing_entry(self) -> None:
        result = self.wrap(self.bundle("bad-route", inventory=[item("ghost", routes=[("history", 3)])]))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ghost", result.stderr)

    def test_completed_is_derived_from_verified_items(self) -> None:
        inventory = [item("enable-alpha", routes=[("durable_facts", 0)]),
                     item("tune-beta", "unverified", routes=[("unfinished_work", 0)]),
                     item("owner-said", "owner_reported", nothing_durable_reason="Owner will handle it.",
                          evidence="Owner said so.")]
        supplied = self.bundle("supplied", durable_facts=["Alpha is enabled."],
                               unfinished_work=["Tune beta."], inventory=inventory)
        supplied["checkpoint"]["completed"] = ["Everything"]
        refused = self.wrap(supplied)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("checkpoint.completed", refused.stderr)
        derived = self.bundle("derived", durable_facts=["Alpha is enabled."],
                              unfinished_work=["Tune beta."], inventory=inventory)
        result = self.wrap(derived)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        receipt = self.receipt("derived")
        self.assertEqual(receipt["bundle"]["checkpoint"]["completed"], ["Summary of enable-alpha"])
        checkpoint = json.loads((self.workspace / receipt["checkpoint_file"]).read_text(encoding="utf-8"))
        self.assertEqual(checkpoint["completed"], ["Summary of enable-alpha"])

    def test_oversize_item_rejected_before_pending_written(self) -> None:
        result = self.wrap(self.bundle("oversize", durable_facts=["Small fact.", "f" * 700]))
        self.assertNotEqual(result.returncode, 0)
        for expected in ("durable_facts", "index 1", "700", "600"):
            self.assertIn(expected, result.stderr)
        self.assertFalse(self.pending.exists())
        accepted = self.wrap(self.bundle("history-size", history=["h" * 2500], reusable_lessons=["l" * 400]))
        self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)

    def test_duplicate_of_active_fact_rejected_with_id(self) -> None:
        first = self.wrap(self.bundle("first", durable_facts=["Alpha is enabled."],
                                      unfinished_work=["Write the release note."]))
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        state = json.loads(run("record_lifecycle.py", "list", "--workspace", str(self.workspace), "--json").stdout)
        fact_id, task_id = state["facts"][0]["fact_id"], state["tasks"][0]["task_id"]
        fact = self.wrap(self.bundle("again-fact", durable_facts=["  ALPHA   is enabled. "]))
        self.assertNotEqual(fact.returncode, 0)
        self.assertIn(fact_id, fact.stderr)
        task = self.wrap(self.bundle("again-task", unfinished_work=["write the release note."]))
        self.assertNotEqual(task.returncode, 0)
        self.assertIn(task_id, task.stderr)
        twice = self.wrap(self.bundle("twice", durable_facts=["Gamma is new.", "gamma is  new."]))
        self.assertNotEqual(twice.returncode, 0)
        self.assertIn("durable_facts", twice.stderr)
        self.assertFalse(self.pending.exists())

    def test_same_words_for_another_project_are_not_a_duplicate(self) -> None:
        def project_bundle(operation_id: str, project: str) -> dict:
            value = self.bundle(operation_id, durable_facts=["Uses the shared style guide."],
                                project_updates=[{"project": project, "content": "Started."}])
            value["checkpoint"]["project"] = project
            return value
        self.assertEqual(self.wrap(project_bundle("alpha-1", "Alpha")).returncode, 0)
        other = self.wrap(project_bundle("beta-1", "Beta"))
        self.assertEqual(other.returncode, 0, other.stdout + other.stderr)
        same = self.wrap(project_bundle("alpha-2", "Alpha"))
        self.assertNotEqual(same.returncode, 0)
        self.assertIn("repeats active fact", same.stderr)

    def test_fact_no_longer_active_may_be_recorded_again(self) -> None:
        self.assertEqual(self.wrap(self.bundle("first", durable_facts=["Alpha is enabled."])).returncode, 0)
        state = json.loads(run("record_lifecycle.py", "list", "--workspace", str(self.workspace), "--json").stdout)
        request = self.root / "retract.json"
        request.write_text(json.dumps({"operation_id": "retract", "action": "fact_retract",
                                       "fact_id": state["facts"][0]["fact_id"], "reason": "Wrong."}), encoding="utf-8")
        self.assertEqual(run("record_lifecycle.py", "apply", "--workspace", str(self.workspace),
                             "--request", str(request)).returncode, 0)
        again = self.wrap(self.bundle("second", durable_facts=["Alpha is enabled."]))
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)

    def test_caps_do_not_apply_to_replay_of_older_transactions(self) -> None:
        env = dict(os.environ, AHAM_BRAHMASMI_TEST_MODE="1", AHAM_BRAHMASMI_TEST_CRASH_POINT="wrap_up_after_pending")
        crashed = self.wrap(self.bundle("legacy", durable_facts=["Small fact."]), env=env)
        self.assertNotEqual(crashed.returncode, 0)
        # An older framework accepted this size; rewrite the pending transaction as it would have stored it.
        sys.path.insert(0, str(SCRIPTS))
        from wrap_up_core import payload_digest
        pending = json.loads(self.pending.read_text(encoding="utf-8"))
        pending["bundle"]["durable_facts"] = ["f" * 5000]
        pending["payload_digest"] = payload_digest(pending["bundle"])
        self.pending.write_text(json.dumps(pending), encoding="utf-8")
        recovered = run("wrap_up.py", "--workspace", str(self.workspace), "--recover-pending")
        self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
        rerun = self.wrap(self.bundle("legacy", durable_facts=["f" * 5000]))
        self.assertEqual(rerun.returncode, 0, rerun.stdout + rerun.stderr)
        self.assertIn("EXISTING RECEIPT REUSED", rerun.stdout)


if __name__ == "__main__":
    unittest.main()
