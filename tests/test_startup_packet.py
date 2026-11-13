from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SETUP = ROOT / "scripts" / "setup_workspace.py"
WRAP_UP = ROOT / "scripts" / "wrap_up.py"
STARTUP = ROOT / "scripts" / "startup.py"
LIFECYCLE = ROOT / "scripts" / "record_lifecycle.py"
AHAM = ROOT / "aham.py"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, *args], cwd=ROOT, text=True, capture_output=True, check=False)


class StartupPacketTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.workspace = self.root / "workspace"
        result = run(str(SETUP), "--workspace", str(self.workspace))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def write_json(self, name: str, value: dict) -> Path:
        path = self.root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def wrap(self, operation_id: str, *, facts=(), tasks=(), lessons=(), history=()) -> None:
        bundle = {
            "operation_id": operation_id,
            "durable_facts": list(facts),
            "unfinished_work": list(tasks),
            "reusable_lessons": list(lessons),
            "project_updates": [],
            "history": list(history),
            "checkpoint": {"summary": "State after " + operation_id, "completed": [], "next_steps": ["Continue"]},
        }
        result = run(str(WRAP_UP), "--workspace", str(self.workspace), "--bundle",
                     str(self.write_json(operation_id + ".json", bundle)))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def lifecycle(self, request: dict) -> None:
        result = run(str(LIFECYCLE), "apply", "--workspace", str(self.workspace), "--request",
                     str(self.write_json(request["operation_id"] + ".json", request)))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def build(self, mode: str = "regular", **kwargs) -> dict:
        from startup_packet import build_startup_packet
        return build_startup_packet(self.workspace, mode, **kwargs)

    def items(self, packet: dict, section: str) -> list[dict]:
        return [item for part in packet["parts"] if part["section"] == section for item in part["items"]]

    def set_budget(self, value: int) -> None:
        path = self.workspace / "INDEX.json"
        index = json.loads(path.read_text(encoding="utf-8"))
        index["startup_budget_bytes"] = value
        path.write_text(json.dumps(index), encoding="utf-8")

    def test_packet_reads_ledger_not_markdown(self) -> None:
        self.wrap("origin", tasks=["Finish the alpha migration."])
        task = self.items(self.build(), "open_tasks")[0]
        self.assertTrue(task["id"].startswith("task_"))
        self.lifecycle({"operation_id": "close-alpha", "action": "task_complete", "task_id": task["id"],
                        "reason": "Verified in testing."})
        packet = self.build()
        self.assertEqual(self.items(packet, "open_tasks"), [])
        self.assertIn("Finish the alpha migration.", (self.workspace / "TODO.md").read_text(encoding="utf-8"))
        self.assertEqual(packet["format"], "aham-brahmasmi-startup-packet")
        self.assertEqual(packet["version"], 1)
        self.assertIs(packet["token_equivalence_claimed"], False)

    def test_same_revision_gives_same_digest(self) -> None:
        self.wrap("origin", facts=["Alpha is enabled."], lessons=["Check the listener first."])
        first, second = self.build(), self.build()
        self.assertEqual(first["packet_sha256"], second["packet_sha256"])
        self.assertEqual(first["source_revision"], 1)
        self.assertEqual(first, second)

    def test_regular_begins_with_quick_parts(self) -> None:
        self.wrap("origin", facts=["Alpha is enabled.", "Beta is disabled."], tasks=["Write the release note."])
        quick, regular = self.build("quick"), self.build("regular")
        self.assertEqual({part["section"] for part in quick["parts"]}, {"standing_files", "active_facts"})
        self.assertGreater(len(regular["parts"]), len(quick["parts"]))
        self.assertEqual([part["part_sha256"] for part in quick["parts"]],
                         [part["part_sha256"] for part in regular["parts"][:len(quick["parts"])]])
        for part in regular["parts"]:
            self.assertEqual(part["of"], len(regular["parts"]))
        fact = self.items(quick, "active_facts")[0]
        self.assertTrue(fact["id"].startswith("fact_"))

    def test_low_budget_truncates_with_counts(self) -> None:
        self.wrap("origin", facts=[f"Fact number {n}: " + "x" * 480 for n in range(30)],
                  lessons=[f"Lesson number {n}: " + "y" * 300 for n in range(10)])
        full = self.build()
        self.assertFalse(full["truncated"])
        self.assertEqual(len(self.items(full, "active_facts")), 30)
        from drift_checks import load_index, startup_sources
        total = startup_sources(self.workspace, load_index(self.workspace), "unknown")["total_bytes"]
        self.set_budget(total - 9000)
        packet = self.build()
        self.assertTrue(packet["truncated"])
        self.assertGreater(sum(packet["omitted"].values()), 0)
        self.assertGreater(packet["omitted"]["lessons"], 0)
        accounting = startup_sources(self.workspace, load_index(self.workspace), "unknown")
        self.assertLessEqual(accounting["total_bytes"], accounting["budget_bytes"])

    def test_long_item_is_cut_within_part_ceiling(self) -> None:
        self.lifecycle({"operation_id": "long-fact", "action": "fact_assert", "statement": "z" * 20000,
                        "source": "legacy import"})
        packet = self.build(max_part_bytes=6000)
        for part in packet["parts"]:
            encoded = json.dumps(part, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
            self.assertLessEqual(len(encoded.encode("utf-8")), 6000)
        fact = self.items(packet, "active_facts")[0]
        self.assertIs(fact["truncated_item"], True)
        self.assertTrue(fact["id"].startswith("fact_"))
        self.assertTrue(packet["truncated"])

    def test_standing_file_over_budget_fails_naming_file(self) -> None:
        from state_io import StateError
        (self.workspace / "README.md").write_text("r" * 70000, encoding="utf-8")
        with self.assertRaises(StateError) as caught:
            self.build()
        self.assertIn("README.md", str(caught.exception))

    def test_standing_file_longer_than_a_part_is_delivered_whole(self) -> None:
        text = "".join(f"line {n} \u00e9\n" for n in range(300))
        # Bytes, so the file on disk has the same line endings on every platform.
        (self.workspace / "README.md").write_bytes(text.encode("utf-8"))
        packet = self.build("quick", max_part_bytes=1024)
        chunks = [item for item in self.items(packet, "standing_files") if item["file"] == "README.md"]
        self.assertGreater(len(chunks), 1)
        self.assertEqual("".join(item["text"] for item in chunks), text)

    def test_grown_markdown_no_longer_blocks_start(self) -> None:
        for name in ("MEMORY.md", "TODO.md", "LESSONS.md"):
            with (self.workspace / name).open("a", encoding="utf-8") as handle:
                handle.write("\n" + "old projection line\n" * 2000)
        result = run(str(STARTUP), "--workspace", str(self.workspace), "--mode", "regular", "--json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertLessEqual(report["startup_context"]["total_bytes"], report["startup_context"]["budget_bytes"])

    def test_context_startup_command_prints_manifest_and_part(self) -> None:
        self.wrap("origin", facts=["Alpha is enabled."])
        packet = self.build("quick")
        manifest = run(str(AHAM), "context", "--startup", "--workspace", str(self.workspace), "--mode", "quick")
        self.assertEqual(manifest.returncode, 0, manifest.stdout + manifest.stderr)
        listing = json.loads(manifest.stdout)
        self.assertEqual(listing["packet_sha256"], packet["packet_sha256"])
        self.assertEqual(len(listing["parts"]), len(packet["parts"]))
        self.assertNotIn("items", listing["parts"][0])
        self.assertIn("bytes", listing["parts"][0])
        one = run(str(AHAM), "context", "--startup", "--workspace", str(self.workspace), "--mode", "quick",
                  "--part", "1")
        self.assertEqual(one.returncode, 0, one.stdout + one.stderr)
        self.assertEqual(json.loads(one.stdout), packet["parts"][0])


if __name__ == "__main__":
    unittest.main()
