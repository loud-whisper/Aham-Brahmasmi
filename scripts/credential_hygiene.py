"""Read-only, redacted secret-shape warnings for explicitly managed config paths."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat

from state_io import StateError, require_managed_path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_LIMIT = 2 * 1024 * 1024
PROJECT_CONFIG_PATHS = (
    ".aham/runtime.json", ".aham/runtime.md", ".aham/command-guard/config.json",
    ".claude/settings.json", ".claude/settings.local.json", ".codex/hooks.json",
    ".codex/config.toml", ".gemini/settings.json", ".mcp.json",
)
WORKSPACE_CONFIG_PATHS = ("BRAIN.json",)


def secret_patterns() -> list[tuple[str, re.Pattern]]:
    # Reuse the project's secret rules without changing the external-skill
    # scanner identity or the validity of existing source reviews.
    definitions = json.loads((ROOT / "core/scanner_rules.json").read_text(encoding="utf-8"))["patterns"]
    patterns = [(rule["id"], re.compile(rule["pattern"])) for rule in definitions if rule["id"].startswith("secret.")]
    patterns.extend([
        ("secret.aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
        ("secret.api_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
        ("secret.assignment", re.compile(
            r'''(?i)["']?\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|token|secret|password|[A-Z_]*(?:_TOKEN|_API_KEY))["']?\s*[:=]\s*["']?[A-Za-z0-9_./+=-]{20,}''')),
    ])
    return patterns


def scan_managed_configuration(root: Path, relatives: tuple[str, ...] | list[str]) -> list[dict]:
    """Never recurse, repair files, follow managed links, or return secret text."""
    findings = []
    patterns = secret_patterns()
    for relative in relatives:
        try:
            path = require_managed_path(root, relative, label="credential check configuration")
            if not path.exists():
                continue
            metadata = path.stat()
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_size > CONFIG_LIMIT:
                raise ValueError("configuration is not a bounded private regular file")
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
            with os.fdopen(descriptor, "rb") as handle:
                opened = os.fstat(handle.fileno())
                if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
                    raise ValueError("configuration changed during inspection")
                raw = handle.read(CONFIG_LIMIT + 1)
            if len(raw) > CONFIG_LIMIT:
                raise ValueError("configuration exceeds check limit")
            text = raw.decode("utf-8")
        except (StateError, OSError, ValueError):
            findings.append({"path": relative, "line": None, "kind": "not_checked"})
            continue
        # Decode JSON string escapes too, so a stored escaped token is not
        # invisible to the check. Raw text remains the line-number source.
        for line_number, line in enumerate(text.splitlines(), 1):
            for kind, pattern in patterns:
                if pattern.search(line):
                    findings.append({"path": relative, "line": line_number, "kind": kind})
                    break
        try:
            decoded = json.loads(text)
        except (ValueError, RecursionError):
            continue
        normalized = json.dumps(decoded, ensure_ascii=False)
        if not any(item["path"] == relative for item in findings):
            for kind, pattern in patterns:
                if pattern.search(normalized):
                    findings.append({"path": relative, "line": None, "kind": kind})
                    break
    return findings
