from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
HEX64 = re.compile(r"[0-9a-f]{64}")


def run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args], cwd=ROOT, text=True,
                          capture_output=True, check=False)


def aham(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(ROOT / "aham.py"), *args], cwd=ROOT, text=True,
                          capture_output=True, check=False)


class ContextConfirmationTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.workspace = self.root / "workspace"
        result = run("setup_workspace.py", "--workspace", str(self.workspace))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        bundle = self.root / "origin.json"
        bundle.write_text(json.dumps({
            "operation_id": "origin", "durable_facts": ["Alpha is enabled."],
            "unfinished_work": ["Write the release note."], "reusable_lessons": ["Check the listener first."],
            "project_updates": [], "history": ["Set up alpha."],
            "checkpoint": {"summary": "Origin", "completed": [], "next_steps": ["Continue"]}}), encoding="utf-8")
        result = run("wrap_up.py", "--workspace", str(self.workspace), "--bundle", str(bundle))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        trust = run("runtime_trust.py", "trust", "local", "--workspace", str(self.workspace), "--confirm", "local")
        self.assertEqual(trust.returncode, 0, trust.stdout + trust.stderr)

    def start(self, mode: str = "regular", *extra: str) -> dict:
        result = run("startup.py", "--workspace", str(self.workspace), "--runtime", "local", "--mode", mode,
                     "--capability", "read_files", "--capability", "write_files", "--json", *extra)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def session_record(self) -> dict:
        return json.loads((self.workspace / "state/session_authority.json").read_text(encoding="utf-8"))

    def digests(self, mode: str) -> list[str]:
        from startup_packet import build_startup_packet
        return [part["part_sha256"] for part in build_startup_packet(self.workspace, mode, runtime="local")["parts"]]

    def confirm(self, session: str, digests: list[str]) -> subprocess.CompletedProcess[str]:
        command = ["confirm-context", "--workspace", str(self.workspace), "--session-id", session]
        for digest in digests:
            command += ["--part-digest", digest]
        return aham(*command)

    def save(self, session: str, summary: str = "milestone") -> subprocess.CompletedProcess[str]:
        return run("checkpoint.py", "--workspace", str(self.workspace), "--summary", summary,
                   "--session-id", session)

    def test_new_regular_session_is_pending(self) -> None:
        report = self.start()
        self.assertEqual(report["context_status"], "pending")
        context = self.session_record()["context"]
        self.assertEqual(context["status"], "pending")
        self.assertEqual(context["mode"], "regular")
        self.assertEqual(context["confirmed_parts"], [])
        self.assertEqual(context["source_revision"], report["session_authority"]["current_revision"])
        self.assertRegex(context["packet_sha256"], HEX64)

    def test_all_part_digests_confirm(self) -> None:
        session = self.start()["session_authority"]["session_id"]
        result = self.confirm(session, self.digests("regular"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CONTEXT CONFIRMED", result.stdout)
        self.assertEqual(self.session_record()["context"]["status"], "confirmed")

    def test_missing_part_reports_index_not_digest(self) -> None:
        session = self.start()["session_authority"]["session_id"]
        digests = self.digests("regular")
        result = self.confirm(session, digests[:1] + digests[2:])
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        output = result.stdout + result.stderr
        self.assertIn("2", output)
        self.assertIsNone(HEX64.search(output), output)
        self.assertEqual(self.session_record()["context"]["status"], "pending")

    def test_save_refused_while_pending(self) -> None:
        session = self.start()["session_authority"]["session_id"]
        result = self.save(session)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("confirm-context", result.stdout + result.stderr)

    def test_recovery_allowed_while_pending(self) -> None:
        from session_authority import require_operation_authority
        report = self.start()
        session = report["session_authority"]["session_id"]
        revision = report["session_authority"]["current_revision"]
        require_operation_authority(self.workspace, "recover_wrap_up", session_id=session,
                                    committed_revision=revision)
        require_operation_authority(self.workspace, "recover_checkpoint", session_id=session,
                                    committed_revision=revision)

    def test_upgrade_reuses_quick_parts_at_same_revision(self) -> None:
        quick = self.start("quick")["session_authority"]["session_id"]
        quick_digests = self.digests("quick")
        self.assertEqual(self.confirm(quick, quick_digests).returncode, 0)
        regular = self.start("regular", "--upgrade-from", quick)
        self.assertEqual(regular["context_status"], "pending")
        session = regular["session_authority"]["session_id"]
        self.assertEqual(self.session_record()["context"]["confirmed_parts"],
                         list(range(1, len(quick_digests) + 1)))
        added = self.digests("regular")[len(quick_digests):]
        partial = self.confirm(session, added[:-1])
        self.assertEqual(partial.returncode, 1)
        self.assertIn(str(len(quick_digests) + len(added)), partial.stdout + partial.stderr)
        self.assertEqual(self.confirm(session, added).returncode, 0)
        self.assertEqual(self.save(session).returncode, 0)

    def test_regular_start_without_upgrade_proof_reuses_nothing(self) -> None:
        quick = self.start("quick")["session_authority"]["session_id"]
        self.assertEqual(self.confirm(quick, self.digests("quick")).returncode, 0)
        self.start("regular")
        self.assertEqual(self.session_record()["context"]["confirmed_parts"], [])

    def test_quick_session_can_confirm_but_stays_read_only(self) -> None:
        quick = self.start("quick")["session_authority"]["session_id"]
        self.assertEqual(self.confirm(quick, self.digests("quick")).returncode, 0)
        result = self.save(quick)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("start --mode regular", result.stdout + result.stderr)

    def test_own_writes_keep_confirmation(self) -> None:
        session = self.start()["session_authority"]["session_id"]
        self.assertEqual(self.confirm(session, self.digests("regular")).returncode, 0)
        first = self.save(session, "first")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        second = self.save(session, "second")
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)

    def test_changed_context_cannot_be_confirmed(self) -> None:
        session = self.start()["session_authority"]["session_id"]
        digests = self.digests("regular")
        with (self.workspace / "README.md").open("a", encoding="utf-8") as handle:
            handle.write("\nA new standing instruction.\n")
        result = self.confirm(session, digests)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("start", result.stdout + result.stderr)

    def test_owner_control_session_exempt(self) -> None:
        self.start()
        result = run("owner_phrases.py", "set", "--workspace", str(self.workspace),
                     "--wrap-up", "finish for today", "--confirm", "set-phrases")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_chat_import_requires_packet_digest(self) -> None:
        from project_state import project_by_id  # noqa: F401
        bundle = self.root / "project.json"
        bundle.write_text(json.dumps({
            "operation_id": "project-origin", "durable_facts": [], "unfinished_work": [],
            "reusable_lessons": [], "project_updates": [{"project": "Alpha", "content": "Started."}],
            "history": [], "checkpoint": {"summary": "Alpha", "completed": [], "next_steps": ["Continue"],
                                          "project": "Alpha"}}), encoding="utf-8")
        result = run("wrap_up.py", "--workspace", str(self.workspace), "--bundle", str(bundle))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        from project_state import project_id_by_name
        project = project_id_by_name(self.workspace, "Alpha")
        exported = aham("context", "--workspace", str(self.workspace), "--project-id", project, "--for-chat")
        self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
        packet = json.loads(exported.stdout)
        template = packet["wrapup_template"]
        self.assertEqual(template["context_packet_sha256"], packet["context"]["packet_sha256"])
        template["bundle"]["checkpoint"]["summary"] = "Chat session summary"
        session = self.start()["session_authority"]["session_id"]

        without = {key: value for key, value in template.items() if key != "context_packet_sha256"}
        wrong = dict(template, context_packet_sha256="0" * 64)
        for name, response in (("without", without), ("wrong", wrong)):
            path = self.root / (name + ".json")
            path.write_text(json.dumps(response), encoding="utf-8")
            refused = aham("import-wrapup", str(path), "--workspace", str(self.workspace), "--session-id", session)
            self.assertNotEqual(refused.returncode, 0, name)
            self.assertEqual(self.session_record()["context"]["status"], "pending", name)

        path = self.root / "good.json"
        path.write_text(json.dumps(template), encoding="utf-8")
        accepted = aham("import-wrapup", str(path), "--workspace", str(self.workspace), "--session-id", session)
        self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)

    def test_chat_import_cannot_write_through_a_quick_session(self) -> None:
        bundle = self.root / "project.json"
        bundle.write_text(json.dumps({
            "operation_id": "project-origin", "durable_facts": [], "unfinished_work": [],
            "reusable_lessons": [], "project_updates": [{"project": "Alpha", "content": "Started."}],
            "history": [], "checkpoint": {"summary": "Alpha", "completed": [], "next_steps": ["Continue"],
                                          "project": "Alpha"}}), encoding="utf-8")
        self.assertEqual(run("wrap_up.py", "--workspace", str(self.workspace), "--bundle", str(bundle)).returncode, 0)
        from project_state import project_id_by_name
        project = project_id_by_name(self.workspace, "Alpha")
        packet = json.loads(aham("context", "--workspace", str(self.workspace), "--project-id", project,
                                 "--for-chat").stdout)
        session = self.start("quick")["session_authority"]["session_id"]
        path = self.root / "good.json"
        path.write_text(json.dumps(packet["wrapup_template"]), encoding="utf-8")
        refused = aham("import-wrapup", str(path), "--workspace", str(self.workspace), "--session-id", session)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("start --mode regular", refused.stdout + refused.stderr)


if __name__ == "__main__":
    unittest.main()
