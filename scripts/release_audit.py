#!/usr/bin/env python3
"""Exercise the documented Aham Brahmasmi lifecycle in an isolated temporary environment."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
REGISTRY = ROOT / "third_party" / "registry.json"


class AuditError(RuntimeError):
    """Raised when a release rehearsal step does not match the documented contract."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an isolated Aham Brahmasmi release rehearsal.")
    parser.add_argument(
        "--live-upstream",
        action="store_true",
        help="Fetch and verify approved default external sources from their original upstream repositories",
    )
    parser.add_argument("--upstream-report-out", help="Retain live-upstream scanner evidence as JSON")
    return parser.parse_args()


def run(command: list[str], *, cwd: Path = ROOT, allowed: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    if result.returncode not in allowed:
        rendered = " ".join(command)
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise AuditError(f"command failed: {rendered}\n{detail}")
    return result


def run_script(name: str, *args: str, allowed: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess[str]:
    path = SCRIPTS / name
    if not path.is_file():
        raise AuditError(f"required script is missing: scripts/{name}")
    return run([sys.executable, str(path), *args], allowed=allowed)


def git(repo: Path, *args: str) -> str:
    result = run(["git", "-C", str(repo), *args])
    return result.stdout.strip()


def make_project(root: Path) -> Path:
    project = root / "project"
    project.mkdir()
    git(project, "init")
    git(project, "config", "user.email", "rehearsal@example.invalid")
    git(project, "config", "user.name", "Aham Release Rehearsal")
    (project / "work.txt").write_text("release rehearsal\n", encoding="utf-8")
    git(project, "add", "work.txt")
    git(project, "commit", "-m", "initial rehearsal state")
    return project


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuditError(f"could not read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AuditError(f"expected JSON object in {path}")
    return value


def rehearse_runtime_switch(workspace: Path, checkpoint_id: str) -> str:
    # Unknown is deliberately exercised first so its read-only fallback is tested,
    # then explicit synthetic owner trust and a writer probe re-establish authority.
    final_session_id: str | None = None
    for runtime in ("unknown", "claude", "gemini", "codex", "local"):
        if runtime == "local":
            run_script("runtime_trust.py", "trust", "local", "--workspace", str(workspace), "--confirm", "local")
        result = run_script(
            "startup.py",
            "--workspace",
            str(workspace),
            "--runtime",
            runtime,
            "--mode",
            "regular",
            "--capability",
            "read_files",
            "--capability",
            "write_files",
            "--capability",
            "run_commands",
            "--harness",
            "release-audit",
            "--json",
        )
        report = json.loads(result.stdout)
        assert_true(report.get("ready") is True, f"startup report was not ready for runtime {runtime}")
        latest = report.get("latest_checkpoint")
        assert_true(isinstance(latest, dict), f"runtime {runtime} did not see the latest checkpoint")
        assert_true(latest.get("id") == checkpoint_id, f"runtime {runtime} saw different durable checkpoint state")
        authority = report.get("session_authority")
        assert_true(isinstance(authority, dict), f"runtime {runtime} startup returned no session authority")
        session_id = authority.get("session_id")
        assert_true(isinstance(session_id, str) and bool(session_id), f"runtime {runtime} startup returned no session ID")
        if runtime == "unknown":
            assert_true(authority.get("authority") == "read_only", "unknown runtime did not receive read-only authority")
        if runtime == "local":
            assert_true(authority.get("authority") == "read_write", "verified local runtime did not receive write authority")
            final_session_id = session_id
    assert_true(final_session_id is not None, "release rehearsal did not establish final write-capable session authority")
    return final_session_id


def rehearse_runtime_bridges(workspace: Path, root: Path) -> None:
    for runtime in ("claude", "gemini", "codex", "local", "unknown"):
        project = root / f"bridge-{runtime}"
        project.mkdir()
        installed = run_script(
            "runtime_bridge.py",
            "install",
            "--runtime",
            runtime,
            "--workspace",
            str(workspace),
            "--project",
            str(project),
        )
        assert_true("RUNTIME BRIDGE INSTALLED" in installed.stdout, f"runtime bridge install failed for {runtime}")
        status = run_script("runtime_bridge.py", "status", "--project", str(project), "--json")
        payload = json.loads(status.stdout)
        assert_true(payload.get("installed") is True, f"runtime bridge status failed for {runtime}")
        bridge_text = (project / ".aham" / "runtime.md").read_text(encoding="utf-8")
        assert_true(str(workspace) not in bridge_text, f"runtime bridge leaked workspace path for {runtime}")
        ignore_text = (project / ".aham" / ".gitignore").read_text(encoding="utf-8")
        assert_true("runtime.json" in ignore_text.splitlines(), f"runtime config is not ignored for {runtime}")


def rehearse_external_source(workspace: Path, *, session_id: str | None = None) -> dict[str, Any]:
    from third_party import activate_source, fetch_exact_source, load_registry, read_installed_manifest
    from scan_external import scan_tree
    from state_io import StateError
    registry = load_registry()
    expected = {
        source["id"]: source
        for source in registry.get("sources", [])
        if isinstance(source, dict)
        and source.get("default_offer") is True
        and source.get("review_status") == "approved"
        and source.get("integration") == "installer"
    }
    evidence: dict[str, Any] = {"format": "aham-upstream-scanner-rehearsal", "version": 1, "sources": {}}
    for source_id, source in expected.items():
        quarantine, head = fetch_exact_source(workspace, source)
        assert_true(head == source["source_ref"], f"upstream ref mismatch for {source_id}")
        report = scan_tree(quarantine / "source")
        before = read_installed_manifest(workspace)
        item = {"source_ref": head, "scan_report": report}
        if report["verdict"] == "PASS":
            active = activate_source(workspace, source, quarantine, report, session_id=session_id)
            assert_true(git(active, "rev-parse", "HEAD") == head, f"active ref mismatch for {source_id}")
            item["activation"] = "activated-pass"
        else:
            try:
                activate_source(workspace, source, quarantine, report, session_id=session_id)
            except StateError:
                pass
            else:
                raise AuditError(f"unaccepted upstream findings were activated: {source_id}")
            assert_true(read_installed_manifest(workspace) == before, "blocked scan changed active manifest")
            assert_true((quarantine / "source").is_dir(), "blocked scan lost its quarantine")
            item["activation"] = "blocked-pending-review"
        evidence["sources"][source_id] = item
        print(f"UPSTREAM SCAN: {source_id} {report['verdict']} ({item['activation']})")
    return evidence


def main() -> int:
    args = parse_args()
    try:
        foundation = run([sys.executable, str(ROOT / "tests" / "verify_foundation.py")])
        assert_true("FOUNDATION CHECKS PASSED" in foundation.stdout, "foundation verification did not pass")

        with tempfile.TemporaryDirectory(prefix="aham-release-rehearsal-") as temp:
            root = Path(temp)
            workspace = root / "workspace"
            project = make_project(root)

            setup = run_script("setup_workspace.py", "--workspace", str(workspace))
            assert_true("WORKSPACE CREATED" in setup.stdout, "fresh workspace setup did not complete")
            verified = run_script("verify_workspace.py", "--workspace", str(workspace))
            assert_true("WORKSPACE VERIFIED" in verified.stdout, "fresh workspace verification did not complete")

            semantic = run_script("semantic_memory.py", "status", "--workspace", str(workspace), "--json")
            semantic_status = json.loads(semantic.stdout)
            assert_true(semantic_status.get("configured") is False, "fresh workspace unexpectedly requires semantic memory")

            checkpoint = run_script(
                "checkpoint.py",
                "--workspace",
                str(workspace),
                "--repo",
                str(project),
                "--summary",
                "Completed release rehearsal milestone",
                "--completed",
                "Created and verified a private workspace",
                "--next-step",
                "Resume from the durable milestone",
            )
            assert_true("CHECKPOINT SAVED" in checkpoint.stdout, "checkpoint rehearsal did not save")
            pointer = load_json(workspace / "state" / "latest_checkpoint.json")
            checkpoint_id = str(pointer.get("id", ""))
            assert_true(bool(checkpoint_id), "checkpoint pointer has no id")

            (project / "work.txt").write_text("release rehearsal continued\n", encoding="utf-8")
            git(project, "add", "work.txt")
            git(project, "commit", "-m", "continue after checkpoint")
            resumed = run_script("resume.py", "--workspace", str(workspace), "--repo", str(project))
            assert_true("RESUME STATE VERIFIED" in resumed.stdout, "crash-recovery rehearsal did not verify")

            session_id = rehearse_runtime_switch(workspace, checkpoint_id)
            rehearse_runtime_bridges(workspace, root)

            bundle = root / "wrap.json"
            bundle.write_text(
                json.dumps(
                    {
                        "session_id": "release-rehearsal",
                        "durable_facts": ["Release rehearsal durable fact"],
                        "unfinished_work": ["Release rehearsal future task"],
                        "reusable_lessons": ["Verify state before reporting success"],
                        "project_updates": [
                            {"project": "Release Rehearsal", "content": "Lifecycle rehearsal completed."}
                        ],
                        "history": ["Exercised the private release lifecycle in an isolated workspace."],
                        "checkpoint": {
                            "summary": "Release rehearsal wrapped successfully",
                            "completed": ["Setup, checkpoint, resume and runtime switching rehearsed"],
                            "next_steps": ["Run remaining public-release gates"],
                            "project": "Release Rehearsal",
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            wrapped = run_script(
                "wrap_up.py",
                "--workspace",
                str(workspace),
                "--bundle",
                str(bundle),
                "--repo",
                str(project),
                "--session-id",
                session_id,
            )
            assert_true("WRAP UP COMPLETE" in wrapped.stdout, "wrap-up rehearsal did not complete")
            assert_true(not (workspace / "state" / "pending_wrap_up.json").exists(), "wrap-up left a pending transaction")

            git_init = run_script(
                "git_transport.py",
                "init",
                "--workspace",
                str(workspace),
                "--author-name",
                "Aham Release Rehearsal",
                "--author-email",
                "rehearsal@example.invalid",
            )
            assert_true("GIT TRANSPORT INITIALIZED" in git_init.stdout, "Git transport did not initialize")
            snapshot = run_script(
                "git_transport.py",
                "snapshot",
                "--workspace",
                str(workspace),
                "--message",
                "Release rehearsal durable snapshot",
            )
            assert_true("GIT SNAPSHOT SAVED" in snapshot.stdout, "durable Git snapshot did not save")
            assert_true(not git(workspace, "remote"), "Git transport unexpectedly configured a remote")

            listed = run_script("external_sources.py", "list")
            assert_true("Reviewed external sources" in listed.stdout, "external source registry listing failed")
            if args.live_upstream:
                evidence = rehearse_external_source(workspace, session_id=session_id)
                if args.upstream_report_out:
                    Path(args.upstream_report_out).write_text(json.dumps(evidence, indent=2, sort_keys=True,
                                                                        ensure_ascii=True) + "\n", encoding="utf-8")

        print("RELEASE REHEARSAL PASSED")
        print("- fresh private workspace setup and verification")
        print("- semantic-memory optionality")
        print("- checkpoint, crash recovery and caller-bound runtime authority")
        print("- Claude, Gemini, Codex, local and unknown bridge installation at framework level")
        print("- replay-safe wrap-up")
        print("- host-neutral local Git snapshot without a remote")
        print("- external source registry" + (" and live upstream scan/activation boundary" if args.live_upstream else ""))
        return 0
    except (AuditError, OSError, json.JSONDecodeError) as exc:
        print(f"RELEASE REHEARSAL FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
