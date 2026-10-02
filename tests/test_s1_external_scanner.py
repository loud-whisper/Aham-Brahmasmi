"""Explicit external adapters are optional and can never lower the local verdict."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import tempfile
import unittest
import test_r5_platform_git_hardening as fixtures

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from scan_external import scan_tree
from state_io import StateError


class S1ExternalScannerTests(unittest.TestCase):
    def test_adapter_changed_tree_requires_review(self):
        from scanner_external import run_external_scanner
        with tempfile.TemporaryDirectory() as temporary:
            tree, report, source, executable = self.fixture(Path(temporary))
            original = executable.read_text()
            original = original.replace("else: print(", "else:\n from pathlib import Path\n Path(" + repr(str(tree / "README.md")) + ").write_text('changed')\n print(")
            executable.write_text(original)
            result = run_external_scanner(tree, report, source, executable=str(executable))
            self.assertEqual(result["verdict"], "REVIEW")
            self.assertIn("external.incomplete", {f["rule_id"] for f in result["findings"]})

    def fixture(self, parent, verdict="PASS"):
        tree = parent / "tree"
        tree.mkdir()
        (tree / "README.md").write_text("ordinary local data\n")
        report = scan_tree(tree)
        source = fixtures.R5PlatformGitHardeningTests().source_entry("1" * 40)
        source.update({"kind": "tool", "integration": "adapter", "activation": "manual",
                       "scanner_adapter": {"protocol": "aham-json-v1", "version": "synthetic-1",
                                           "executable": "synthetic-scanner", "version_args": ["--version"]}})
        executable = parent / "scanner"
        payload = {"format": "aham-external-scan", "version": 1, "verdict": verdict,
                   "tree_digest": report["tree_digest"], "findings": []}
        executable.write_text("#!/usr/bin/env python3\nimport sys\n"
                              "if '--version' in sys.argv: print('synthetic-1')\n"
                              "else: print(" + repr(json.dumps(payload)) + ")\n")
        executable.chmod(0o755)
        return tree, report, source, executable

    def test_registered_explicit_adapter_combines_most_severe_verdict(self):
        from scanner_external import run_external_scanner
        with tempfile.TemporaryDirectory() as temporary:
            tree, report, source, executable = self.fixture(Path(temporary), "REVIEW")
            result = run_external_scanner(tree, report, source, executable=str(executable))
            self.assertEqual(result["verdict"], "REVIEW")
            self.assertIn(source["id"], result["external_scanners"])
            failed = {**report, "verdict": "FAIL"}
            self.assertEqual(run_external_scanner(tree, failed, source, executable=str(executable))["verdict"], "FAIL")

    def test_unapproved_source_is_refused_before_execution(self):
        from scanner_external import run_external_scanner
        from third_party import validate_registry
        with tempfile.TemporaryDirectory() as temporary:
            tree, report, source, executable = self.fixture(Path(temporary))
            source["review_status"] = "review-required"
            self.assertEqual(validate_registry({"version": 1, "policy": "link-upstream", "sources": [source]}), [])
            executable.write_text("#!/UNAVAILABLE\n")
            with self.assertRaises(StateError):
                run_external_scanner(tree, report, source, executable=str(executable))

    def test_bad_output_wrong_identity_missing_tool_and_timeout_cannot_pass(self):
        from scanner_external import run_external_scanner
        for behavior in ("not-json", "wrong-tree", "oversized", "timeout", "nonzero", "wrong-version", "wrong-type"):
            with self.subTest(behavior=behavior), tempfile.TemporaryDirectory() as temporary:
                tree, report, source, executable = self.fixture(Path(temporary))
                actions = {
                    "not-json": "print('not JSON')",
                    "wrong-tree": "print('{\"format\":\"aham-external-scan\",\"version\":1,\"verdict\":\"PASS\",\"tree_digest\":\"wrong\",\"findings\":[]}')",
                    "oversized": "print('x' * 200000)",
                    "timeout": "import time; time.sleep(2)",
                    "nonzero": "raise SystemExit(9)",
                    "wrong-version": "print('not the registered version')",
                    "wrong-type": "print('{\"format\":\"aham-external-scan\",\"version\":1,\"verdict\":[],\"tree_digest\":\"" + report["tree_digest"] + "\",\"findings\":[]}')",
                }
                executable.write_text("#!/usr/bin/env python3\nimport sys\n"
                                      "if '--version' in sys.argv: print('" + ("wrong" if behavior == "wrong-version" else "synthetic-1") + "')\n"
                                      "else:\n    " + actions[behavior] + "\n")
                result = run_external_scanner(tree, report, source, executable=str(executable), timeout=0.2)
                self.assertEqual(result["verdict"], "REVIEW")
                self.assertTrue(result["findings"])
        with tempfile.TemporaryDirectory() as temporary:
            tree, report, source, _ = self.fixture(Path(temporary))
            self.assertEqual(run_external_scanner(tree, report, source, executable=str(Path(temporary) / "missing"))["verdict"], "REVIEW")


if __name__ == "__main__":
    unittest.main()
