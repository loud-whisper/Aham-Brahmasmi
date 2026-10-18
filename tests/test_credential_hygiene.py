"""Credential tests use generated inert values and never consult a real login."""
from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def synthetic_token(letter="A"):
    return "gh" + "p_" + letter * 36


class CredentialProviderTests(unittest.TestCase):
    def setUp(self):
        self.credentials = importlib.import_module("integration_credentials")

    def result(self, value=None, code=0):
        return subprocess.CompletedProcess(["gh"], code, (value or synthetic_token()) + "\n", "")

    def test_fresh_login_lookup_for_every_call_with_no_environment_override(self):
        with patch.dict(os.environ, {name: "stale-inline-value" for name in self.credentials.TOKEN_VARIABLES}), \
             patch("integration_credentials.shutil.which", return_value="gh"), \
             patch("integration_credentials.subprocess.run", side_effect=[self.result(), self.result(synthetic_token("B"))]) as run:
            self.assertEqual(self.credentials.repository_token("github"), synthetic_token())
            self.assertEqual(self.credentials.repository_token("github"), synthetic_token("B"))
        self.assertEqual(run.call_count, 2)
        for call in run.call_args_list:
            self.assertEqual(call.args[0], ["gh", "auth", "token", "--hostname", "github.com"])
            self.assertTrue(all(name not in call.kwargs["env"] for name in self.credentials.TOKEN_VARIABLES))
            self.assertEqual(call.kwargs["stdin"], subprocess.DEVNULL)
            self.assertGreater(call.kwargs["timeout"], 0)

    def test_missing_cli_and_unknown_platform_fail_without_fallback(self):
        with patch("integration_credentials.shutil.which", return_value=None), \
             patch("integration_credentials.subprocess.run") as run:
            with self.assertRaisesRegex(self.credentials.CredentialError, "gh"):
                self.credentials.repository_token("github")
            with self.assertRaises(self.credentials.CredentialError):
                self.credentials.repository_token("unreviewed")
            run.assert_not_called()

    def test_failed_empty_malformed_and_timed_out_login_never_echo_material(self):
        bad = synthetic_token()
        outcomes = [self.result(bad, code=1), self.result(" "), self.result(bad + "\nextra"),
                    self.result("x" * 5000), self.result("abc\x00def"),
                    subprocess.TimeoutExpired(["gh"], 1, output=bad, stderr=bad), OSError(bad)]
        for outcome in outcomes:
            with self.subTest(outcome=type(outcome).__name__), \
                 patch("integration_credentials.shutil.which", return_value="gh"), \
                 patch("integration_credentials.subprocess.run", **({"side_effect": outcome} if isinstance(outcome, Exception) else {"return_value": outcome})):
                with self.assertRaises(self.credentials.CredentialError) as caught:
                    self.credentials.repository_token("github")
                self.assertNotIn(bad, str(caught.exception))

    def test_launcher_passes_secret_only_in_child_environment_and_preserves_exit_code(self):
        before = dict(os.environ)
        with patch("integration_credentials.repository_token", return_value=synthetic_token()) as token, \
             patch("integration_credentials.subprocess.run", return_value=subprocess.CompletedProcess([], 7)) as run:
            code = self.credentials.run_integration("github", ["client", "literal;$argument"], token_env="SERVICE_TOKEN")
        self.assertEqual(code, 7)
        token.assert_called_once_with("github", hostname="github.com")
        self.assertEqual(run.call_args.args[0], ["client", "literal;$argument"])
        self.assertEqual(run.call_args.kwargs["env"]["SERVICE_TOKEN"], synthetic_token())
        self.assertNotIn(synthetic_token(), repr(run.call_args.args))
        self.assertFalse(run.call_args.kwargs.get("shell", False))
        self.assertEqual(dict(os.environ), before)

    def test_launcher_discards_old_github_variables(self):
        with patch.dict(os.environ, {name: "old-key" for name in self.credentials.TOKEN_VARIABLES}), \
             patch("integration_credentials.repository_token", return_value=synthetic_token()), \
             patch("integration_credentials.subprocess.run", return_value=subprocess.CompletedProcess([], 0)) as run:
            self.credentials.run_integration("github", ["client"])
        env = run.call_args.kwargs["env"]
        self.assertEqual(env["GH_TOKEN"], synthetic_token())
        self.assertTrue(all(name not in env for name in self.credentials.TOKEN_VARIABLES if name != "GH_TOKEN"))

    def test_failed_resolution_does_not_launch_consumer(self):
        with patch("integration_credentials.repository_token", side_effect=self.credentials.CredentialError("login required")), \
             patch("integration_credentials.subprocess.run") as run:
            with self.assertRaises(self.credentials.CredentialError):
                self.credentials.run_integration("github", ["client"])
            run.assert_not_called()

    def test_invalid_launch_options_are_rejected_before_login(self):
        for command, env_name, hostname in [([], None, "github.com"), (["client"], "BAD=NAME", "github.com"),
                                             (["client"], "PATH", "github.com"), (["client"], None, "https://github.com"),
                                             (["client"], None, "bad\nname")]:
            with self.subTest(command=command, env_name=env_name, hostname=hostname), \
                 patch("integration_credentials.repository_token") as token:
                with self.assertRaises(self.credentials.CredentialError):
                    self.credentials.run_integration("github", command, token_env=env_name, hostname=hostname)
                token.assert_not_called()

    def test_enterprise_host_uses_host_specific_login_and_environment(self):
        with patch("integration_credentials.repository_token", return_value=synthetic_token()) as token, \
             patch("integration_credentials.subprocess.run", return_value=subprocess.CompletedProcess([], 0)) as run:
            self.credentials.run_integration("github", ["client"], hostname="github.example.test")
        token.assert_called_once_with("github", hostname="github.example.test")
        self.assertEqual(run.call_args.kwargs["env"]["GH_ENTERPRISE_TOKEN"], synthetic_token())


class ConfigurationHygieneTests(unittest.TestCase):
    def setUp(self):
        self.hygiene = importlib.import_module("credential_hygiene")

    def test_known_and_generic_secret_shapes_warn_without_values_or_snippets(self):
        samples = [synthetic_token(), "github" + "_pat_" + "B" * 80, "sk" + "-" + "C" * 40,
                   "AK" + "IA" + "D" * 16, "BEGIN " + "PRIVATE KEY", '"api_key": "' + "E" * 32 + '"']
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / ".aham/runtime.json"
            config.parent.mkdir()
            for value in samples:
                with self.subTest(shape=value[:4]):
                    config.write_text("\n" + value, encoding="utf-8")
                    findings = self.hygiene.scan_managed_configuration(root, [".aham/runtime.json"])
                    self.assertTrue(findings)
                    self.assertEqual(findings[0]["line"], 2)
                    self.assertNotIn(value, json.dumps(findings))

    def test_scanning_is_read_only_and_does_not_search_unrelated_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / ".aham/runtime.json"
            config.parent.mkdir()
            config.write_text('{"runtime": "codex", "token_env": "GH_TOKEN"}', encoding="utf-8")
            (root / "unrelated.txt").write_text(synthetic_token(), encoding="utf-8")
            before = config.read_bytes()
            findings = self.hygiene.scan_managed_configuration(root, [".aham/runtime.json", ".codex/hooks.json"])
            self.assertEqual(findings, [])
            self.assertEqual(config.read_bytes(), before)

    @unittest.skipIf(os.name == "nt", "unprivileged Windows symlink creation is not assumed")
    def test_symlinked_configuration_is_not_read(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            outside = root / "outside"
            outside.write_text(synthetic_token(), encoding="utf-8")
            project = root / "project"
            (project / ".aham").mkdir(parents=True)
            (project / ".aham/runtime.json").symlink_to(outside)
            findings = self.hygiene.scan_managed_configuration(project, [".aham/runtime.json"])
            self.assertEqual(findings[0]["kind"], "not_checked")
            self.assertNotIn(synthetic_token(), json.dumps(findings))

    def test_oversized_or_nonregular_config_is_explicitly_not_checked(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "config.json"
            path.write_bytes(b" " * (self.hygiene.CONFIG_LIMIT + 1))
            self.assertEqual(self.hygiene.scan_managed_configuration(root, ["config.json"])[0]["kind"], "not_checked")
            directory = root / "directory.json"
            directory.mkdir()
            self.assertEqual(self.hygiene.scan_managed_configuration(root, ["directory.json"])[0]["kind"], "not_checked")

    def test_doctor_warns_even_when_secret_makes_bridge_config_invalid(self):
        import doctor
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / ".aham").mkdir()
            path = project / ".aham/runtime.json"
            path.write_text(json.dumps({"token": synthetic_token()}), encoding="utf-8")
            before = path.read_bytes()
            report, code = doctor.build_report(argparse.Namespace(workspace=None, project=str(project)))
            rendered = json.dumps(report)
            warnings = [item for item in report["findings"] if item["name"] == "Credential hygiene"]
            self.assertTrue(warnings)
            self.assertIn(".aham/runtime.json", rendered)
            self.assertNotIn(synthetic_token(), rendered)
            self.assertIn("docs/CREDENTIAL_HYGIENE.md", warnings[0]["action"])
            self.assertEqual(path.read_bytes(), before)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                doctor.print_human(report)
            self.assertNotIn(synthetic_token(), output.getvalue())

    def test_doctor_checks_native_integration_settings_and_workspace_config(self):
        import doctor
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            created = subprocess.run([sys.executable, str(ROOT / "scripts/setup_workspace.py"), "--workspace", str(workspace)], capture_output=True, text=True)
            self.assertEqual(created.returncode, 0, created.stdout + created.stderr)
            brain = workspace / "BRAIN.json"
            value = json.loads(brain.read_text())
            value["optional_integrations"]["fixture"] = {"api_key": synthetic_token()}
            brain.write_text(json.dumps(value), encoding="utf-8")
            project = root / "project"
            (project / ".codex").mkdir(parents=True)
            (project / ".codex/hooks.json").write_text(json.dumps({"token": synthetic_token()}), encoding="utf-8")
            report, _ = doctor.build_report(argparse.Namespace(workspace=str(workspace), project=str(project)))
            warnings = [item for item in report["findings"] if item["name"] == "Credential hygiene"]
            self.assertTrue(any("BRAIN.json" in item["detail"] for item in warnings))
            self.assertTrue(any(".codex/hooks.json" in item["detail"] for item in warnings))
            self.assertNotIn(synthetic_token(), json.dumps(report))


if __name__ == "__main__":
    unittest.main()
