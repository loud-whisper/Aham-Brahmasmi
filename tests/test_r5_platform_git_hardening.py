from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import git_transport  # noqa: E402
import state_io  # noqa: E402
import third_party  # noqa: E402
from third_party import activate_source, read_installed_manifest  # noqa: E402
from scan_external import scan_tree


SETUP = ROOT / "scripts" / "setup_workspace.py"
GIT_TRANSPORT = ROOT / "scripts" / "git_transport.py"
PORTABLE = ROOT / "scripts" / "portable_backup.py"
PLATFORM_DOC = ROOT / "docs" / "PLATFORM_SUPPORT.md"
FOUNDATION_WORKFLOW = ROOT / ".github" / "workflows" / "foundation-checks.yml"


class R5PlatformGitHardeningTests(unittest.TestCase):
    def run_command(
        self,
        *args: str,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args,
            cwd=cwd or ROOT,
            text=True,
            capture_output=True,
            check=False,
            env=env,
            timeout=30,
        )

    def run_tool(self, script: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return self.run_command(sys.executable, str(script), *args, env=env)

    def make_workspace(self, root: Path, name: str = "workspace") -> Path:
        workspace = root / name
        result = self.run_tool(SETUP, "--workspace", str(workspace))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return workspace

    def git(self, workspace: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return self.run_command("git", "-C", str(workspace), *args)

    def init_transport(self, workspace: Path) -> None:
        result = self.run_tool(
            GIT_TRANSPORT,
            "init",
            "--workspace",
            str(workspace),
            "--author-name",
            "Aham Test",
            "--author-email",
            "test@example.invalid",
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def source_entry(self, source_ref: str) -> dict:
        return {
            "id": "fixture-r5-source",
            "name": "Fixture R5 Source",
            "kind": "skill-collection",
            "upstream_url": "https://example.invalid/r5-source",
            "source_type": "git_commit",
            "source_ref": source_ref,
            "license": "MIT",
            "license_url": "https://example.invalid/r5-source/LICENSE",
            "integration": "installer",
            "local_changes": False,
            "checked_at": "2026-09-19",
            "review_status": "approved",
            "role": "R5 crash fixture",
            "default_offer": False,
            "activation": "workspace_external",
            "attribution": "Synthetic R5 fixture.",
            "notes": "Synthetic R5 activation fixture.",
        }

    def quarantine(self, workspace: Path, name: str, content: str) -> Path:
        quarantine = workspace / "state" / "quarantine" / name
        source = quarantine / "source"
        source.mkdir(parents=True)
        (source / "README.md").write_text(content, encoding="utf-8")
        return quarantine

    def set_crash_point(self, name: str) -> tuple[str | None, str | None]:
        original_mode = os.environ.get("AHAM_BRAHMASMI_TEST_MODE")
        original_point = os.environ.get("AHAM_BRAHMASMI_TEST_CRASH_POINT")
        os.environ["AHAM_BRAHMASMI_TEST_MODE"] = "1"
        os.environ["AHAM_BRAHMASMI_TEST_CRASH_POINT"] = name
        return original_mode, original_point

    def restore_crash_environment(self, original_mode: str | None, original_point: str | None) -> None:
        if original_mode is None:
            os.environ.pop("AHAM_BRAHMASMI_TEST_MODE", None)
        else:
            os.environ["AHAM_BRAHMASMI_TEST_MODE"] = original_mode
        if original_point is None:
            os.environ.pop("AHAM_BRAHMASMI_TEST_CRASH_POINT", None)
        else:
            os.environ["AHAM_BRAHMASMI_TEST_CRASH_POINT"] = original_point

    def test_platform_policy_and_ci_define_evidenced_support_scope(self) -> None:
        self.assertTrue(PLATFORM_DOC.is_file(), "R5 requires an explicit platform/Python support policy")
        text = PLATFORM_DOC.read_text(encoding="utf-8").lower()
        self.assertIn("python 3.10", text)
        self.assertIn("python 3.14", text)
        self.assertIn("linux", text)
        self.assertIn("macos", text)
        self.assertIn("windows", text)
        self.assertIn("not supported", text)

        workflow = FOUNDATION_WORKFLOW.read_text(encoding="utf-8").lower()
        self.assertIn("macos-latest", workflow)
        self.assertIn("3.10", workflow)
        self.assertIn("3.14", workflow)

    def test_paths_with_spaces_and_unicode_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root, "Brain space Ω")
            artifact = workspace / "projects" / "Résumé Ω.txt"
            artifact.write_text("unicode durable artifact\n", encoding="utf-8")
            bundle = root / "portable export Ω"
            restored = root / "restored Brain Ω"

            exported = self.run_tool(PORTABLE, "export", "--workspace", str(workspace), "--output", str(bundle))
            self.assertEqual(exported.returncode, 0, exported.stderr + exported.stdout)
            result = self.run_tool(PORTABLE, "restore", "--input", str(bundle), "--workspace", str(restored))
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(
                (restored / "projects" / "Résumé Ω.txt").read_text(encoding="utf-8"),
                "unicode durable artifact\n",
            )

    def test_portable_export_refuses_case_insensitive_path_collision(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            first = workspace / "projects" / "CaseCollision.txt"
            second = workspace / "projects" / "casecollision.txt"
            first.write_text("first\n", encoding="utf-8")
            second.write_text("second\n", encoding="utf-8")
            matching = [p for p in (workspace / "projects").iterdir() if p.name.casefold() == "casecollision.txt"]
            if len(matching) < 2:
                self.skipTest("test filesystem is case-insensitive and cannot construct the collision fixture")

            result = self.run_tool(PORTABLE, "manifest", "--workspace", str(workspace), "--json")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("case-insensitive", (result.stdout + result.stderr).lower())

    def test_portable_export_refuses_unicode_normalization_collision(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            composed = workspace / "projects" / "Café.txt"
            decomposed = workspace / "projects" / "Cafe\u0301.txt"
            composed.write_text("composed\n", encoding="utf-8")
            decomposed.write_text("decomposed\n", encoding="utf-8")
            matching = [p for p in (workspace / "projects").iterdir() if p.name.startswith("Caf")]
            if len(matching) < 2:
                self.skipTest("test filesystem normalizes Unicode names and cannot construct the collision fixture")

            result = self.run_tool(PORTABLE, "manifest", "--workspace", str(workspace), "--json")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unicode-normalized", (result.stdout + result.stderr).lower())

    def test_git_snapshot_refuses_detached_head_after_repository_has_commits(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.make_workspace(Path(temp))
            self.init_transport(workspace)
            first = self.run_tool(GIT_TRANSPORT, "snapshot", "--workspace", str(workspace), "--message", "initial")
            self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
            detached = self.git(workspace, "checkout", "--quiet", "--detach", "HEAD")
            self.assertEqual(detached.returncode, 0, detached.stderr + detached.stdout)
            with (workspace / "TODO.md").open("a", encoding="utf-8") as handle:
                handle.write("\n- detached change\n")

            result = self.run_tool(GIT_TRANSPORT, "snapshot", "--workspace", str(workspace), "--message", "must refuse")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("detached", (result.stdout + result.stderr).lower())

    def test_git_snapshot_refuses_clean_filter_before_it_can_execute(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            self.init_transport(workspace)
            initial = self.run_tool(GIT_TRANSPORT, "snapshot", "--workspace", str(workspace), "--message", "initial")
            self.assertEqual(initial.returncode, 0, initial.stderr + initial.stdout)

            marker = root / "filter-ran.txt"
            filter_command = (
                f'"{sys.executable}" -c "import pathlib,sys; '
                f'pathlib.Path(r\'{marker}\').write_text(\'ran\'); sys.stdout.write(sys.stdin.read())"'
            )
            configured = self.git(workspace, "config", "--local", "filter.r5evil.clean", filter_command)
            self.assertEqual(configured.returncode, 0, configured.stderr + configured.stdout)
            (workspace / ".gitattributes").write_text("MEMORY.md filter=r5evil\n", encoding="utf-8")
            with (workspace / "MEMORY.md").open("a", encoding="utf-8") as handle:
                handle.write("\nfilter fixture\n")

            result = self.run_tool(GIT_TRANSPORT, "snapshot", "--workspace", str(workspace), "--message", "must refuse filter")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("filter", (result.stdout + result.stderr).lower())
            self.assertFalse(marker.exists(), "Git clean filter executed before the transport refused it")

    def test_git_snapshot_neutralizes_inherited_autocrlf(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.make_workspace(Path(temp))
            self.init_transport(workspace)
            configured = self.git(workspace, "config", "--local", "core.autocrlf", "true")
            self.assertEqual(configured.returncode, 0, configured.stderr + configured.stdout)
            expected = b"# Memory\r\n\r\nCRLF fixture.\r\n"
            (workspace / "MEMORY.md").write_bytes(expected)

            result = self.run_tool(GIT_TRANSPORT, "snapshot", "--workspace", str(workspace), "--message", "CRLF fixture")
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            shown = subprocess.run(
                ["git", "-C", str(workspace), "show", "HEAD:MEMORY.md"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=30,
            )
            self.assertEqual(shown.returncode, 0, shown.stderr.decode(errors="replace"))
            self.assertEqual(shown.stdout, expected)

    def test_git_subprocess_helpers_set_finite_timeouts(self) -> None:
        completed = subprocess.CompletedProcess(args=["git"], returncode=0, stdout="", stderr="")
        cases = (
            (git_transport, lambda: git_transport.run_git(Path("."), "status", check=False)),
            (state_io, lambda: state_io.run_git(Path("."), "status", check=False)),
            (third_party, lambda: third_party.run_git("--version")),
        )
        for module, call in cases:
            with self.subTest(module=module.__name__):
                with mock.patch.object(module.subprocess, "run", return_value=completed) as runner:
                    call()
                    timeout = runner.call_args.kwargs.get("timeout")
                    self.assertIsNotNone(timeout, f"{module.__name__}.run_git has no subprocess timeout")
                    self.assertGreater(timeout, 0)
                    self.assertLessEqual(timeout, 120)

    def test_case_and_accented_project_names_keep_distinct_checkpoint_heads(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = self.make_workspace(Path(temporary))
            names = ("Résumé", "résumé", "Café", "Cafe\u0301")
            for index, name in enumerate(names):
                result = self.run_tool(
                    ROOT / "scripts/checkpoint.py", "--workspace", str(workspace),
                    "--project", name, "--summary", f"Synthetic checkpoint {index}",
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            registry = json.loads((workspace / "state/projects.json").read_text())
            projects = registry["projects"]
            self.assertEqual({entry["display_name"] for entry in projects.values()}, set(names))
            self.assertEqual(len(projects), 4)
            files = [entry["file"] for entry in projects.values()]
            self.assertEqual(len({path.casefold() for path in files}), 4)
            heads = list((workspace / "state/project_heads").glob("*.json"))
            self.assertEqual(len(heads), 4)
            checkpoints = {json.loads(path.read_text())["checkpoint_file"] for path in heads}
            self.assertEqual(len(checkpoints), 4)
            self.assertEqual({json.loads((workspace / path).read_text())["project"]
                              for path in checkpoints}, set(names))

    def test_missing_hard_links_do_not_publish_an_immutable_record(self) -> None:
        import errno
        import state_store

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "operation.json"
            with mock.patch.object(state_store.os, "link",
                                   side_effect=OSError(errno.EOPNOTSUPP, "fixture: no hard links")):
                with self.assertRaises(OSError):
                    state_store.create_immutable_json(path, {"synthetic": "unaccepted"})
            self.assertFalse(path.exists())
            self.assertEqual(list(path.parent.iterdir()), [])

    def test_external_activation_recovers_crash_after_destination_move(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)

            old_source = self.source_entry("1" * 40)
            old_quarantine = self.quarantine(workspace, "old", "old active\n")
            active = activate_source(workspace, old_source, old_quarantine, scan_tree(old_quarantine / "source"))
            self.assertEqual((active / "README.md").read_text(encoding="utf-8"), "old active\n")

            new_source = self.source_entry("2" * 40)
            new_quarantine = self.quarantine(workspace, "new", "new candidate\n")
            original_mode, original_point = self.set_crash_point("external_activation_after_destination_move")
            try:
                with self.assertRaises(SystemExit) as crashed:
                    activate_source(workspace, new_source, new_quarantine, scan_tree(new_quarantine / "source"), replace=True)
                self.assertEqual(crashed.exception.code, 86)
            finally:
                self.restore_crash_environment(original_mode, original_point)

            pending = workspace / "state" / "pending_external_activation.json"
            self.assertTrue(pending.is_file(), "activation crash must leave a durable recovery record")
            blocked_export = self.run_tool(
                PORTABLE,
                "export",
                "--workspace",
                str(workspace),
                "--output",
                str(root / "blocked-export"),
            )
            self.assertNotEqual(blocked_export.returncode, 0)
            self.assertIn("pending", (blocked_export.stdout + blocked_export.stderr).lower())

            recover = getattr(third_party, "recover_external_activation", None)
            self.assertTrue(callable(recover), "R5 requires an external activation recovery entry point")
            self.assertEqual(recover(workspace), "rolled_back")

            self.assertFalse(pending.exists())
            self.assertEqual((active / "README.md").read_text(encoding="utf-8"), "old active\n")
            self.assertEqual((new_quarantine / "source" / "README.md").read_text(encoding="utf-8"), "new candidate\n")
            manifest = read_installed_manifest(workspace)
            self.assertEqual(manifest["sources"][old_source["id"]]["source_ref"], old_source["source_ref"])

    def test_external_activation_recovery_conserves_committed_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            source = self.source_entry("3" * 40)
            quarantine = self.quarantine(workspace, "commit-crash", "committed candidate\n")

            original_mode, original_point = self.set_crash_point("external_activation_after_manifest_write")
            try:
                with self.assertRaises(SystemExit) as crashed:
                    activate_source(workspace, source, quarantine, scan_tree(quarantine / "source"))
                self.assertEqual(crashed.exception.code, 86)
            finally:
                self.restore_crash_environment(original_mode, original_point)

            pending = workspace / "state" / "pending_external_activation.json"
            self.assertTrue(pending.is_file())
            self.assertEqual(third_party.recover_external_activation(workspace), "committed")
            self.assertFalse(pending.exists())
            active = workspace / "external" / source["id"]
            self.assertEqual((active / "README.md").read_text(encoding="utf-8"), "committed candidate\n")
            manifest = read_installed_manifest(workspace)
            self.assertEqual(manifest["sources"][source["id"]]["source_ref"], source["source_ref"])

    def test_external_activation_rolls_back_manifest_permission_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root)
            old_source = self.source_entry("4" * 40)
            old_quarantine = self.quarantine(workspace, "permission-old", "old active\n")
            active = activate_source(workspace, old_source, old_quarantine, scan_tree(old_quarantine / "source"))

            new_source = self.source_entry("5" * 40)
            new_quarantine = self.quarantine(workspace, "permission-new", "new candidate\n")
            real_atomic = third_party.atomic_write_json

            def permission_failure(path: Path, value: dict) -> None:
                if path.name == "installed_sources.json":
                    raise PermissionError("simulated manifest permission failure")
                real_atomic(path, value)

            with mock.patch.object(third_party, "atomic_write_json", side_effect=permission_failure):
                with self.assertRaises(PermissionError):
                    activate_source(workspace, new_source, new_quarantine, scan_tree(new_quarantine / "source"), replace=True)

            self.assertFalse((workspace / "state" / "pending_external_activation.json").exists())
            self.assertEqual((active / "README.md").read_text(encoding="utf-8"), "old active\n")
            self.assertEqual((new_quarantine / "source" / "README.md").read_text(encoding="utf-8"), "new candidate\n")
            manifest = read_installed_manifest(workspace)
            self.assertEqual(manifest["sources"][old_source["id"]]["source_ref"], old_source["source_ref"])


if __name__ == "__main__":
    unittest.main()
