"""Conservative, non-evaluating blast-radius classification for literal POSIX argv.

This is an optional accident guard, not a shell parser or execution sandbox.
Anything outside the recognized grammar belongs to the user.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import stat
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Limits:
    max_bytes: int = 1_000_000_000
    max_files: int = 10_000

    def __post_init__(self):
        if any(type(value) is not int or value < 1 for value in (self.max_bytes, self.max_files)):
            raise ValueError("limits must be positive integers")


@dataclass(frozen=True)
class Decision:
    tier: str
    reason: str
    effect: str = ""
    undo: str = ""
    argv: tuple[str, ...] = ()
    bytes: int = 0
    files: int = 0
    snapshot: str = ""

    def to_dict(self):
        return asdict(self)


SYSTEM_TREES = {"bin", "sbin", "etc", "usr", "var", "dev", "proc", "sys", "boot",
                "run", "opt", "lib", "lib64", "mnt", "media", "System", "Library",
                "Applications", "Windows", "Program Files", "ProgramData"}
MUTATIONS = {"rm", "rmdir", "unlink", "mv", "cp", "chmod", "chown", "truncate"}
MAX_COMMAND_BYTES = 32_768
DATABASE_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".db3", ".mdb", ".accdb", ".dbf", ".ibd", ".rdb", ".sst", ".ldb", ".wt"}


def database_file(entry, info):
    name = entry.name.lower()
    if (entry.suffix.lower() in DATABASE_SUFFIXES or name in {"pg_version", "wiredtiger", "dump.rdb"}
            or re.fullmatch(r"ibdata[0-9]+", name) or name.endswith((".db-wal", ".sqlite-wal", ".sqlite3-wal"))):
        return True
    # Recognize renamed SQLite databases too, without executing a database tool.
    # Fixed-size reads are bounded and no-follow where supported. Metadata drift
    # during this read refuses classification instead of following a new target.
    descriptor = os.open(entry, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    try:
        actual = os.fstat(descriptor)
        if (actual.st_dev, actual.st_ino, actual.st_mode, actual.st_size, actual.st_mtime_ns, actual.st_ctime_ns) != (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns):
            raise ValueError("target changed during database identification")
        return os.read(descriptor, 16) == b"SQLite format 3\x00"
    finally:
        os.close(descriptor)


def unbounded_program_reason(argv):
    name = argv[0]
    if name in {"ssh", "scp", "sftp", "rsync", "rsh", "mosh"}:
        return "remote-machine effects cannot be measured locally"
    if name in {"dd", "mount", "umount", "fdisk", "sfdisk", "parted", "wipefs", "losetup", "diskutil", "zpool", "zfs", "lvm", "lvremove", "vgremove"} or name.startswith(("mkfs", "fsck")):
        return "disk, partition or volume operations are user-only"
    if name in {"psql", "mysql", "mariadb", "sqlite3", "dropdb", "mongosh", "redis-cli"}:
        return "database operations cannot acquire an agent approval"
    if name in {"docker", "podman", "nerdctl", "kubectl"}:
        return "container/volume or cluster effects cannot be measured as local file changes"
    if name == "git":
        return "Git history or mutation effects are outside the measured file-operation grammar"
    return "effects of this program are not bounded by the literal file-operation grammar"


def literal_argv(command: str) -> tuple[str, ...]:
    # Refusing even quoted metacharacters is deliberate. Do not strip quotes and
    # then try to distinguish active shell syntax from literal user data.
    if (not isinstance(command, str) or not command.strip()
            or len(command.encode("utf-8")) > MAX_COMMAND_BYTES
            or any(ord(char) < 32 or ord(char) == 127 for char in command)
            or any(char in command for char in "$`|;&<>*?[]{}()~\\!#")):
        raise ValueError("command has expansion, indirection, control syntax or unbounded input")
    try:
        argv = tuple(shlex.split(command, posix=True))
    except ValueError as exc:
        raise ValueError("command is not literal POSIX argv") from exc
    if not argv or not argv[0] or "/" in argv[0] or "=" in argv[0]:
        raise ValueError("executable path or assignment has unverified behavior")
    return argv


def inspection(argv: tuple[str, ...]) -> bool:
    name, *args = argv
    if name in {"pwd", "true", "false"}:
        return not args
    if name in {"cat", "ls", "wc", "head", "tail"}:
        # These tools do not execute subcommands. Refuse legacy tail +N syntax
        # only when its semantics would matter to measurement (not applicable).
        return True
    if name == "git" and args:
        allowed = {
            "status": {"--short", "-s", "--branch", "-b", "--porcelain", "--porcelain=v1", "--porcelain=v2"},
            "diff": {"--stat", "--name-only", "--name-status", "--cached", "--staged", "--exit-code",
                     "--quiet", "--no-ext-diff", "--no-textconv"},
        }
        return args[0] in allowed and all(arg in allowed[args[0]] for arg in args[1:])
    return False


def operands(argv: tuple[str, ...]) -> tuple[list[str], int]:
    """Return affected literal paths and requested truncate size, if any."""
    name, *args = argv
    growth = 0
    if name in {"chmod", "chown"}:
        if args and args[0] == "-R":
            args = args[1:]
        if not args or not re.fullmatch(r"[0-7]{3,4}" if name == "chmod" else r"[A-Za-z0-9_.-]+(?::[A-Za-z0-9_.-]+)?", args[0]):
            raise ValueError("unsupported permission or ownership expression")
        args = args[1:]
    elif name == "truncate":
        if len(args) < 3 or args[0] != "-s" or not re.fullmatch(r"[0-9]{1,18}", args[1]):
            raise ValueError("only literal truncate -s BYTE_COUNT is measurable")
        growth = int(args[1])
        args = args[2:]
    else:
        flags = {"rm": "rfvdR", "rmdir": "v", "unlink": "", "mv": "fvn", "cp": "rRfvnp"}[name]
        while args and args[0].startswith("-") and args[0] != "--":
            option = args.pop(0)
            if len(option) < 2 or option.startswith("--") or any(c not in flags for c in option[1:]):
                raise ValueError("unsupported mutation option")
    if args and args[0] == "--":
        args = args[1:]
    if not args or any(not arg or arg.startswith("-") or ":" in arg for arg in args):
        raise ValueError("missing, ambiguous or remote target")
    if name in {"mv", "cp"} and len(args) != 2:
        raise ValueError("only one literal source and destination can be measured")
    if name == "unlink" and len(args) != 1:
        raise ValueError("unlink requires exactly one target")
    return args, growth


def protected(path: Path, project: Path) -> bool:
    # Root folders, selected project root and everything outside the project are
    # never delegated. This also covers a user's home root without reading it.
    if path == project or path in project.parents or project not in path.parents:
        return True
    return len(path.parts) > 1 and path.parts[1] in SYSTEM_TREES


def measure(paths: list[Path], project: Path, limits: Limits, missing_destination: Path | None):
    total = count = 0
    rows = []
    deadline = time.monotonic() + 3.0
    device = project.stat().st_dev
    for path in paths:
        # Check each component before traversal; never follow child symlinks.
        current = project
        for part in path.relative_to(project).parts:
            current /= part
            try:
                info = current.lstat()
            except FileNotFoundError:
                if current == missing_destination and current.parent.is_dir():
                    rows.append((str(current), "missing"))
                    break
                raise ValueError("a target or its parent does not exist")
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("symlink or reparse target cannot be bounded")
        stack = [path] if path.exists() else []
        while stack:
            entry = stack.pop()
            if time.monotonic() > deadline:
                raise ValueError("measurement time budget exceeded")
            info = entry.lstat()
            if info.st_dev != device or os.path.ismount(entry):
                raise ValueError("mount or volume boundary requires the user")
            if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                raise ValueError("link, device or special file cannot be bounded")
            if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
                raise ValueError("hard-linked data has effects outside the target")
            if stat.S_ISREG(info.st_mode) and database_file(entry, info):
                raise ValueError("database files and database-containing trees are user-only")
            count += 1
            total += info.st_size if stat.S_ISREG(info.st_mode) else 0
            if total >= limits.max_bytes or count >= limits.max_files:
                raise ValueError("measured size reaches or exceeds the configured limit")
            rows.append((str(entry), info.st_dev, info.st_ino, info.st_mode, info.st_uid,
                         info.st_gid, info.st_size, info.st_mtime_ns, info.st_ctime_ns))
            if stat.S_ISDIR(info.st_mode):
                # Bound discovery too, even for a huge empty directory. Avoid an
                # unbounded sorted(scandir(...)) before checking the entry limit.
                with os.scandir(entry) as children:
                    for child in children:
                        stack.append(Path(child.path))
                        if count + len(stack) >= limits.max_files:
                            raise ValueError("entry discovery reaches the configured limit")
    digest = hashlib.sha256(json.dumps(sorted(rows), ensure_ascii=True).encode()).hexdigest()
    return total, count, digest


def classify(command: str, cwd: Path, project: Path, *, limits: Limits = Limits()) -> Decision:
    argv = ()
    try:
        argv = literal_argv(command)
        project = Path(project).resolve(strict=True)
        raw_cwd = Path(cwd)
        if not raw_cwd.is_absolute():
            raise ValueError("working directory must be absolute")
        cwd = raw_cwd.resolve(strict=True)
        if cwd != project and project not in cwd.parents:
            raise ValueError("working directory is outside the selected project")
        if inspection(argv):
            return Decision("allow", "recognized inspection command", argv=argv)
        if argv[0] not in MUTATIONS:
            raise ValueError(unbounded_program_reason(argv))
        values, growth = operands(argv)
        paths = [Path(os.path.abspath(cwd / value)) for value in values]
        for path in paths:
            if protected(path, project):
                raise ValueError("project root, ancestor, system folder or target outside project")
            # The guard may not delete or rewrite its own control files or native
            # hook configuration under an ordinary small-change approval.
            relative = path.relative_to(project)
            if any(part in {".aham", ".claude", ".codex", ".gemini", ".git", ".gitignore", ".gitattributes"} for part in relative.parts):
                raise ValueError("guard, hook or repository control data requires the user")
        for index, path in enumerate(paths):
            if any(path == other or path in other.parents or other in path.parents for other in paths[:index]):
                raise ValueError("overlapping operands cannot be measured independently")
        destination = paths[-1] if argv[0] in {"mv", "cp"} else None
        if destination and destination.is_dir():
            raise ValueError("directory destination has implicit merge or overwrite effects")
        total, count, snapshot = measure(paths, project, limits, destination)
        # A copy can allocate source-size bytes in addition to the overwritten
        # destination, while truncate can increase the apparent byte footprint.
        total = max(total * (2 if argv[0] == "cp" else 1), growth * len(paths))
        if total >= limits.max_bytes:
            raise ValueError("resulting size reaches or exceeds the configured byte limit")
        actions = {"rm": "Remove", "rmdir": "Remove directories", "unlink": "Remove",
                   "mv": "Move or replace", "cp": "Copy or replace", "chmod": "Change permissions on",
                   "chown": "Change ownership of", "truncate": "Resize"}
        effect = f"{actions[argv[0]]} {', '.join(values)} ({total} bytes, {count} entries)"
        undo = "restore affected data and metadata from a verified backup; without one undo is not assured"
        if argv[0] == "mv" and destination and not destination.exists():
            undo = "move the destination back to its original source path"
        return Decision("ask", "measured local change below both limits", effect, undo, argv, total, count, snapshot)
    except (OSError, ValueError, RuntimeError) as exc:
        return Decision("user_runs", str(exc), argv=argv)
