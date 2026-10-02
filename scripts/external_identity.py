"""Content identity for reviewed external trees, independent of Git metadata."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any

from state_io import StateError, is_link_or_reparse

MAX_TREE_ENTRIES = 20000
MAX_TREE_BYTES = 128 * 1024 * 1024
MAX_FILE_BYTES = 25 * 1024 * 1024


class IdentityLimit(StateError):
    """Content exceeds bounded identity review; it cannot receive PASS."""


def report_digest(report: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(report, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()


def tree_entries(root: Path) -> list[Path]:
    """Do not follow directory links, and omit .git at every depth."""
    paths: list[Path] = []
    def failed(error: OSError) -> None:
        raise error
    for directory, directories, files in os.walk(root, followlinks=False, onerror=failed):
        directories[:] = [name for name in directories if name != ".git"]
        for name in directories + files:
            if name != ".git":
                candidate = Path(directory) / name
                if is_link_or_reparse(candidate) and not candidate.is_symlink():
                    raise StateError("reviewed source contains a reparse directory or file")
                paths.append(candidate)
                if len(paths) > MAX_TREE_ENTRIES:
                    raise IdentityLimit("reviewed source exceeds the tree entry limit")
    return sorted(paths, key=lambda path: path.relative_to(root).as_posix())


def tree_digest(root: Path) -> str:
    if is_link_or_reparse(root) or not root.is_dir():
        raise StateError("reviewed source tree is missing or is a symlink")
    root = root.resolve()
    entries = []
    total_bytes = 0
    for path in tree_entries(root):
        relative = path.relative_to(root).as_posix()
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            target = path.resolve(strict=True)
            if root not in target.parents or ".git" in target.relative_to(root).parts:
                raise StateError("symlink escapes reviewed source content")
            entry = [relative, "link", os.readlink(path)]
        elif stat.S_ISDIR(mode):
            entry = [relative, "directory"]
        elif stat.S_ISREG(mode):
            info = path.stat()
            if info.st_nlink != 1:
                raise StateError("reviewed source file has hard-link aliases")
            if info.st_size > MAX_FILE_BYTES or total_bytes + info.st_size > MAX_TREE_BYTES:
                raise IdentityLimit("reviewed source exceeds the content identity byte limit")
            digest = hashlib.sha256()
            file_bytes = 0
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    total_bytes += len(chunk)
                    file_bytes += len(chunk)
                    if file_bytes > MAX_FILE_BYTES or total_bytes > MAX_TREE_BYTES:
                        raise IdentityLimit("reviewed source exceeds the content identity byte limit")
                    digest.update(chunk)
            # Write bits change when a tree is frozen. Executability affects behavior.
            entry = [relative, "file", mode & 0o111, digest.hexdigest()]
        else:
            raise StateError("reviewed source contains an unsupported special file")
        entries.append(entry)
    return hashlib.sha256(json.dumps(entries, separators=(",", ":"), ensure_ascii=True)
                          .encode("ascii")).hexdigest()


def freeze_tree(root: Path) -> None:
    """Accidental-edit protection; an owner can deliberately undo these permissions."""
    if os.name != "posix":
        return
    for path in reversed(tree_entries(root)):
        if not path.is_symlink():
            path.chmod(path.stat().st_mode & ~0o222)
    root.chmod(root.stat().st_mode & ~0o222)
