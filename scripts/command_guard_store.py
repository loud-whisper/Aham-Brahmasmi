"""Private, transactional approval/audit state for the optional command guard."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from command_guard_policy import Limits
from state_io import require_managed_path

STATE = ".aham/command-guard"
APPROVAL_TTL = 300


def state_path(project: Path, name: str) -> Path:
    path = require_managed_path(project, f"{STATE}/{name}", label="command guard state")
    if path.exists() and (not path.is_file() or path.stat().st_nlink != 1):
        raise ValueError("command guard state must be a private regular file without hard links")
    return path


def read_policy(project: Path) -> Limits:
    value = json.loads(state_path(project, "config.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != {"version", "max_bytes", "max_files"} or value["version"] != 1:
        raise ValueError("missing or unsupported command guard configuration")
    return Limits(value["max_bytes"], value["max_files"])


@contextmanager
def database(project: Path, *, create: bool = False):
    path = state_path(project, "audit.sqlite3")
    if not create and not path.is_file():
        raise ValueError("guard audit database is missing; run the installer")
    # IMMEDIATE serializes approval consumption across independent hook processes.
    connection = sqlite3.connect(path, timeout=5, isolation_level=None)
    try:
        os.chmod(path, 0o600)
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("BEGIN IMMEDIATE")
        if create:
            connection.execute("CREATE TABLE IF NOT EXISTS approvals (id INTEGER PRIMARY KEY, binding TEXT NOT NULL, expires REAL NOT NULL, used INTEGER NOT NULL DEFAULT 0)")
            connection.execute("CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, time REAL NOT NULL, event TEXT NOT NULL, details TEXT NOT NULL)")
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def binding(runtime, session, command, cwd, limits, decision):
    value = {"runtime": runtime, "session": session, "command": command, "cwd": str(cwd.resolve()),
             "limits": [limits.max_bytes, limits.max_files], "decision": decision.to_dict()}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def log(connection, event, details):
    connection.execute("INSERT INTO audit(time,event,details) VALUES(?,?,?)",
                       (time.time(), event, json.dumps(details, sort_keys=True)))


def audit(project, event, details):
    with database(project) as connection:
        log(connection, event, details)


def grant(project, key, details):
    with database(project) as connection:
        # Reissuing the same approval does not accumulate reusable grants.
        connection.execute("UPDATE approvals SET used=1 WHERE binding=? AND used=0", (key,))
        cursor = connection.execute("INSERT INTO approvals(binding,expires) VALUES(?,?)", (key, time.time() + APPROVAL_TTL))
        log(connection, "approved", {**details, "approval_id": cursor.lastrowid, "binding": key})
        return {"approval_id": cursor.lastrowid, "expires_in_seconds": APPROVAL_TTL}


def consume(project, key, details):
    with database(project) as connection:
        row = connection.execute("SELECT id FROM approvals WHERE binding=? AND used=0 AND expires>? ORDER BY id DESC LIMIT 1", (key, time.time())).fetchone()
        if row is None:
            log(connection, "approval_missing", details)
            return False
        connection.execute("UPDATE approvals SET used=1 WHERE id=?", (row[0],))
        log(connection, "consumed", {**details, "approval_id": row[0]})
        return True


def events(project):
    with database(project) as connection:
        return [{"event": event, "details": json.loads(details)}
                for event, details in connection.execute("SELECT event,details FROM audit ORDER BY id")]
