"""Explicit invocation of a registered, user-installed JSON scanner adapter."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time

from external_identity import report_digest, tree_digest
from scanner_rules import finding, RANK
from state_io import StateError

OUTPUT_LIMIT = 128 * 1024


def validate_adapter(source: dict, *, require_approved: bool = True) -> dict:
    adapter = source.get("scanner_adapter")
    if ((require_approved and source.get("review_status") != "approved") or source.get("kind") != "tool"
            or source.get("integration") != "adapter" or not isinstance(adapter, dict)
            or set(adapter) != {"protocol", "version", "executable", "version_args"}
            or adapter.get("protocol") != "aham-json-v1"
            or not isinstance(adapter.get("version"), str) or not adapter["version"].strip()
            or not isinstance(adapter.get("executable"), str) or not adapter["executable"]
            or any(c in adapter["executable"] for c in "/\\\x00")
            or not isinstance(adapter.get("version_args"), list)
            or not 1 <= len(adapter["version_args"]) <= 8
            or not all(isinstance(a, str) and len(a) <= 200 and "\x00" not in a
                       for a in adapter["version_args"])):
        raise StateError("external scanner requires an approved, registered JSON adapter")
    return adapter


def _run(argv: list[str], timeout: float) -> str:
    """Bound output on disk and time; this is not an execution sandbox."""
    environment = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "WINDIR", "LANG")
                   if key in os.environ}
    with tempfile.TemporaryDirectory(prefix="aham-scanner-") as directory:
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(argv, cwd=directory, env=environment,
                                       stdin=subprocess.DEVNULL, stdout=output, stderr=errors,
                                       start_new_session=os.name == "posix")
            deadline = time.monotonic() + timeout
            failure = None
            try:
                while True:
                    if os.fstat(output.fileno()).st_size + os.fstat(errors.fileno()).st_size > OUTPUT_LIMIT:
                        failure = "external scanner output exceeds the limit"
                        break
                    if process.poll() is not None:
                        break
                    if time.monotonic() >= deadline:
                        failure = "external scanner timed out"
                        break
                    time.sleep(0.01)
            finally:
                # Also stop descendants that retained the output handles after the parent exited.
                if os.name == "posix":
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                elif process.poll() is None:
                    process.kill()
                process.wait()
            if failure:
                raise StateError(failure)
            if process.returncode != 0:
                raise StateError("external scanner returned a nonzero status")
            output.seek(0)
            raw = output.read(OUTPUT_LIMIT + 1)
            if len(raw) > OUTPUT_LIMIT:
                raise StateError("external scanner output exceeds the limit")
            return raw.decode("utf-8")


def run_external_scanner(tree: Path, report: dict, source: dict, *,
                         executable: str | None = None, timeout: float = 10) -> dict:
    adapter = validate_adapter(source)  # Reject unapproved sources before any execution.
    if not 0 < timeout <= 60:
        raise StateError("external scanner timeout must be within 60 seconds")
    result = copy.deepcopy(report)
    metadata = {"version": adapter["version"], "protocol": adapter["protocol"]}
    try:
        expected = report.get("tree_digest")
        if not expected or tree_digest(tree) != expected:
            raise StateError("external scanner content differs from the local report")
        selected = executable or shutil.which(adapter["executable"])
        if not selected:
            raise StateError("external scanner is not installed")
        selected = str(Path(selected).resolve(strict=True))
        version = _run([selected, *adapter["version_args"]], timeout).strip()
        if version != adapter["version"]:
            raise StateError("external scanner version differs from the registered version")
        raw = _run([selected, "--tree", str(tree.resolve())], timeout)
        payload = json.loads(raw)
        if (not isinstance(payload, dict)
                or set(payload) != {"format", "version", "tree_digest", "verdict", "findings"}
                or payload["format"] != "aham-external-scan" or type(payload["version"]) is not int
                or payload["version"] != 1 or payload["tree_digest"] != expected
                or payload["verdict"] not in RANK or not isinstance(payload["findings"], list)
                or len(payload["findings"]) > 200):
            raise StateError("external scanner returned an invalid report")
        imported = []
        for index, item in enumerate(payload["findings"], 1):
            if (not isinstance(item, dict) or set(item) != {"severity", "message"}
                    or item["severity"] not in ("REVIEW", "FAIL")
                    or not isinstance(item["message"], str) or not 1 <= len(item["message"]) <= 2000):
                raise StateError("external scanner returned an invalid finding")
            imported.append(finding("external.concern", item["severity"], ".", index, item["message"],
                                    "Optional external scanner raised concern.",
                                    "Review the registered scanner output and source content.", report_digest(item)))
        if tree_digest(tree) != expected:
            raise StateError("external scanner changed the reviewed tree")
        level = max([payload["verdict"], *(f["severity"] for f in imported)], key=RANK.get)
        if level != "PASS" and not imported:
            imported.append(finding("external.concern", level, ".", 0, "",
                                    "Optional external scanner raised concern.",
                                    "Review the registered scanner output and source content.", ""))
        result["findings"].extend(imported)
        result["verdict"] = max(result["verdict"], level, key=RANK.get)
        metadata["verdict"] = level
    except (OSError, ValueError, TypeError, UnicodeError, StateError, subprocess.SubprocessError) as error:
        result["findings"].append(finding("external.incomplete", "REVIEW", ".", 0, str(error),
                                         "Optional external scanner did not complete a valid review.",
                                         "Resolve the adapter failure and rerun the scanner.", ""))
        result["verdict"] = max(result["verdict"], "REVIEW", key=RANK.get)
        metadata["verdict"] = "REVIEW"
    result.setdefault("external_scanners", {})[source["id"]] = metadata
    return result
