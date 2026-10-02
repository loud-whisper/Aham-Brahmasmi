#!/usr/bin/env python3
"""Cross-process writer coordination and authoritative operation revisions."""

from __future__ import annotations

import hashlib
import errno
import json
import os
import re
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from state_io import (
    StateError,
    atomic_write_json,
    read_json,
    require_managed_path,
    require_workspace,
    safe_slug,
    utc_now,
    workspace_fingerprint,
)

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

try:
    import msvcrt
except ImportError:
    msvcrt = None

WINDOWS_LOCK_TIMEOUT = 30.0


def acquire_writer_lock(descriptor: int) -> None:
    if fcntl is not None:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        return
    deadline = time.monotonic() + WINDOWS_LOCK_TIMEOUT
    while True:
        os.lseek(descriptor, 0, os.SEEK_SET)
        try:
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            return
        except OSError as exc:
            if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                raise StateError(f"workspace writer lock failed: {exc}") from exc
            if time.monotonic() >= deadline:
                raise StateError("workspace writer lock timed out; another writer may still be active") from exc
            time.sleep(0.05)


def release_writer_lock(descriptor: int) -> None:
    if fcntl is not None:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
    else:
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)

STORE_FORMAT = "aham-brahmasmi-state-store"
STORE_VERSION = 1
OPERATION_FORMAT = "aham-brahmasmi-operation"
OPERATION_VERSION = 1
OPERATION_KINDS = {"wrap_up", "checkpoint", "record_lifecycle", "external_activation", "external_deactivation", "skill_review", "skills_control", "memory_control", "runtime_control"}
DIGEST = re.compile(r"^[0-9a-f]{64}$")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sync_directory(directory: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(directory, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def durable_write_json(path: Path, value: dict[str, Any]) -> None:
    atomic_write_json(path, value)
    sync_directory(path.parent)


def create_immutable_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise StateError(f"immutable operation record already exists: {path.name}")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise StateError(f"immutable operation record already exists: {path.name}") from exc
        sync_directory(path.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def operations_dir(workspace: Path) -> Path:
    path = require_managed_path(workspace, "state/operations", label="operation ledger directory")
    path.mkdir(parents=True, exist_ok=True)
    sync_directory(path.parent)
    return path


def store_path(workspace: Path) -> Path:
    return require_managed_path(workspace, "state/store.json", label="state store")


def validate_store(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise StateError("state store must be a JSON object")
    required = {"format", "version", "revision", "last_operation_id", "last_record"}
    unknown = set(value) - required
    missing = required - set(value)
    if unknown:
        raise StateError("state store contains unknown fields: " + ", ".join(sorted(unknown)))
    if missing:
        raise StateError("state store is missing fields: " + ", ".join(sorted(missing)))
    if value.get("format") != STORE_FORMAT or value.get("version") != STORE_VERSION:
        raise StateError("state store format/version is not recognized")
    revision = value.get("revision")
    if not isinstance(revision, int) or revision < 0:
        raise StateError("state store revision must be a non-negative integer")
    if revision == 0:
        if value.get("last_operation_id") is not None or value.get("last_record") is not None:
            raise StateError("revision-zero state store cannot reference an operation")
    else:
        if not isinstance(value.get("last_operation_id"), str) or not value["last_operation_id"]:
            raise StateError("state store has no valid last_operation_id")
        if not isinstance(value.get("last_record"), str) or not value["last_record"]:
            raise StateError("state store has no valid last_record")
    return value


def initial_store() -> dict[str, Any]:
    return {"format": STORE_FORMAT, "version": STORE_VERSION, "revision": 0, "last_operation_id": None, "last_record": None}


def validate_operation_record(value: Any, workspace: Path | None = None) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise StateError("operation record must be a JSON object")
    required = {"format", "version", "revision", "operation_id", "kind", "committed_at", "workspace_fingerprint", "payload_digest", "details"}
    unknown = set(value) - required
    missing = required - set(value)
    if unknown:
        raise StateError("operation record contains unknown fields: " + ", ".join(sorted(unknown)))
    if missing:
        raise StateError("operation record is missing fields: " + ", ".join(sorted(missing)))
    if value.get("format") != OPERATION_FORMAT or value.get("version") != OPERATION_VERSION:
        raise StateError("operation record format/version is not recognized")
    revision = value.get("revision")
    if not isinstance(revision, int) or revision < 1:
        raise StateError("operation revision must be a positive integer")
    if not isinstance(value.get("operation_id"), str) or not value["operation_id"]:
        raise StateError("operation record has no operation_id")
    if value.get("kind") not in OPERATION_KINDS:
        raise StateError("operation record kind is not recognized")
    if not isinstance(value.get("committed_at"), str) or not value["committed_at"]:
        raise StateError("operation record has no commit timestamp")
    fingerprint = value.get("workspace_fingerprint")
    if not isinstance(fingerprint, str) or not DIGEST.fullmatch(fingerprint):
        raise StateError("operation record workspace fingerprint is invalid")
    payload = value.get("payload_digest")
    if not isinstance(payload, str) or not DIGEST.fullmatch(payload):
        raise StateError("operation record payload digest is invalid")
    if not isinstance(value.get("details"), dict):
        raise StateError("operation record details must be an object")
    if workspace is not None:
        if fingerprint != workspace_fingerprint(require_workspace(workspace)):
            raise StateError("operation record belongs to a different workspace identity")
    return value


def operation_filename(revision: int, operation_id: str) -> str:
    return f"{revision:020d}-{safe_slug(operation_id)}.json"


def list_operation_records(workspace: Path) -> list[tuple[Path, dict[str, Any]]]:
    records: list[tuple[Path, dict[str, Any]]] = []
    seen_ids: set[str] = set()
    directory = require_managed_path(workspace, "state/operations", label="operation ledger directory")
    if directory.exists() and not directory.is_dir():
        raise StateError("operation ledger path is not a directory")
    for path in sorted(directory.glob("*.json")):
        require_managed_path(workspace, path, label="operation ledger record")
        value = validate_operation_record(read_json(path), workspace)
        if path.name != operation_filename(value["revision"], value["operation_id"]):
            raise StateError(f"operation record filename does not match its identity: {path.name}")
        if value["operation_id"] in seen_ids:
            raise StateError(f"duplicate committed operation identity: {value['operation_id']}")
        seen_ids.add(value["operation_id"])
        records.append((path, value))
    records.sort(key=lambda item: item[1]["revision"])
    for expected_revision, (_, value) in enumerate(records, start=1):
        if value["revision"] != expected_revision:
            raise StateError(f"operation revision sequence is not contiguous; expected {expected_revision}, found {value['revision']}")
    return records


def reconcile_store(workspace: Path) -> dict[str, Any]:
    require_workspace(workspace)
    records = list_operation_records(workspace)
    if records:
        last_path, last = records[-1]
        authoritative = {"format": STORE_FORMAT, "version": STORE_VERSION, "revision": last["revision"], "last_operation_id": last["operation_id"], "last_record": f"state/operations/{last_path.name}"}
    else:
        authoritative = initial_store()
    path = store_path(workspace)
    if path.exists():
        cached = validate_store(read_json(path))
        if cached["revision"] > authoritative["revision"]:
            raise StateError("state store revision is ahead of the immutable operation ledger")
    if not path.exists() or read_json(path) != authoritative:
        durable_write_json(path, authoritative)
    return authoritative


@contextmanager
def writer_lock(workspace: Path, *, allow_external_pending: bool = False) -> Iterator[dict[str, Any]]:
    require_workspace(workspace)
    if fcntl is None and msvcrt is None:
        raise StateError("cross-process workspace writer coordination is unavailable on this platform")
    lock_path = require_managed_path(workspace, "state/.writer.lock", label="workspace writer lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise StateError(f"could not open workspace writer lock safely: {exc}") from exc
    try:
        with os.fdopen(descriptor, "r+b") as handle:
            acquire_writer_lock(handle.fileno())
            try:
                if not allow_external_pending and require_managed_path(
                    workspace, "state/pending_external_activation.json", label="external activation journal"
                ).exists():
                    raise StateError("external activation is pending; recover it before unrelated writes")
                yield reconcile_store(workspace)
            finally:
                release_writer_lock(handle.fileno())
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise


def assert_expected_revision(current_revision: int, expected_revision: int | None) -> None:
    if expected_revision is None:
        return
    if expected_revision < 0:
        raise StateError("expected_revision must be a non-negative integer")
    if current_revision != expected_revision:
        raise StateError(f"revision conflict; expected {expected_revision}, current committed revision is {current_revision}")


def find_operation(workspace: Path, operation_id: str) -> tuple[Path, dict[str, Any]] | None:
    for path, record in list_operation_records(workspace):
        if record["operation_id"] == operation_id:
            return path, record
    return None


def commit_operation(workspace: Path, *, operation_id: str, kind: str, payload_digest: str, details: dict[str, Any], target_revision: int) -> tuple[Path, dict[str, Any]]:
    if kind not in OPERATION_KINDS:
        raise StateError("operation kind is not recognized")
    if not DIGEST.fullmatch(payload_digest):
        raise StateError("operation payload digest is invalid")
    head = reconcile_store(workspace)
    if target_revision != head["revision"] + 1:
        raise StateError(f"operation revision conflict; target {target_revision}, next committed revision is {head['revision'] + 1}")
    existing = find_operation(workspace, operation_id)
    if existing:
        _, record = existing
        if record["payload_digest"] != payload_digest or record["kind"] != kind:
            raise StateError("operation_id is already committed with different content")
        return existing
    record = {"format": OPERATION_FORMAT, "version": OPERATION_VERSION, "revision": target_revision, "operation_id": operation_id, "kind": kind, "committed_at": utc_now(), "workspace_fingerprint": workspace_fingerprint(require_workspace(workspace)), "payload_digest": payload_digest, "details": details}
    validate_operation_record(record, workspace)
    path = require_managed_path(
        workspace,
        operations_dir(workspace) / operation_filename(target_revision, operation_id),
        label="new operation ledger record",
    )
    create_immutable_json(path, record)
    if validate_operation_record(read_json(path), workspace) != record:
        raise StateError("immutable operation record does not match the committed payload")
    return path, record


def advance_store_head(workspace: Path, record_path: Path, record: dict[str, Any]) -> dict[str, Any]:
    validate_operation_record(record, workspace)
    require_managed_path(workspace, record_path, label="committed operation record")
    expected = {"format": STORE_FORMAT, "version": STORE_VERSION, "revision": record["revision"], "last_operation_id": record["operation_id"], "last_record": f"state/operations/{record_path.name}"}
    path = store_path(workspace)
    durable_write_json(path, expected)
    return validate_store(read_json(path))


def test_crash_point(name: str) -> None:
    if os.environ.get("AHAM_BRAHMASMI_TEST_MODE") == "1" and os.environ.get("AHAM_BRAHMASMI_TEST_CRASH_POINT") == name:
        raise SystemExit(86)
