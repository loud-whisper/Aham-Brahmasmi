"""Deterministic, bounded heuristics. Findings are data, not a safety proof."""
from __future__ import annotations

import copy
import hashlib
import json
from itertools import islice
import os
from pathlib import Path
import re
import stat
import unicodedata
from typing import Any

from external_identity import tree_entries
from state_io import StateError

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "core/scanner_rules.json"
TEXT_LIMIT = 2 * 1024 * 1024
MAX_FINDINGS = 2000
RANK = {"PASS": 0, "REVIEW": 1, "FAIL": 2}
BIDI = set("\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")
ZERO_WIDTH = set("\u200b\u200c\u200d\u2060\ufeff")


def rule_pack_version() -> str:
    data = RULES.read_bytes() + Path(__file__).read_bytes() + (ROOT / "scripts/scan_external.py").read_bytes()
    return "1:" + hashlib.sha256(data).hexdigest()


def escaped_excerpt(text: str, limit: int = 240) -> str:
    rendered = json.dumps(text[:240], ensure_ascii=True)[1:-1]
    rendered = rendered.replace("\x7f", "\\u007f")
    return rendered[:limit]


def verdict(findings: list[dict[str, Any]]) -> str:
    severities = {finding["severity"].upper() for finding in findings}
    return "FAIL" if "FAIL" in severities else "REVIEW" if "REVIEW" in severities else "PASS"


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def finding(rule_id: str, severity: str, path: str, line: int, excerpt: str,
            explanation: str, remediation: str, digest: str) -> dict[str, Any]:
    identity = json.dumps([rule_id, path, line, digest, escaped_excerpt(excerpt)], separators=(",", ":"))
    return {"rule_id": rule_id, "finding_id": hashlib.sha256(identity.encode()).hexdigest()[:24],
            "severity": severity, "path": path, "line": line,
            "excerpt": escaped_excerpt(excerpt), "explanation": explanation, "remediation": remediation,
            "file_digest": digest, "message": explanation}


def frontmatter(text: str) -> tuple[dict[str, str], str | None]:
    """Safe scalar YAML subset; unsupported syntax requires human review."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, "Required YAML frontmatter is missing."
    try:
        end = lines.index("---", 1)
    except ValueError:
        return {}, "YAML frontmatter has no closing delimiter."
    values: dict[str, str] = {}
    current = None
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith((" ", "\t")):
            if current is None:
                return values, "Nested YAML requires review; it is not automatically accepted."
            values[current] += " " + line.strip()
            continue
        match = re.fullmatch(r"([a-z][a-z0-9-]*):\s*(.*)", line)
        if not match or match[1] in values:
            return values, "Unsupported or duplicate YAML fields require review."
        key, value = match.groups()
        current = key if value in {">", "|", ">-", "|-"} else None
        if current:
            value = ""
        elif value.startswith('"'):
            try:
                value = json.loads(value)
            except (ValueError, TypeError):
                return values, "Quoted YAML uses unsupported escapes."
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1].replace("''", "'")
        elif value.startswith(("[", "{", "&", "*", "!")):
            return values, "Complex YAML values require review."
        values[key] = value
    return values, None


def scan_rule_findings(root: Path) -> list[dict[str, Any]]:
    definitions = json.loads(RULES.read_text(encoding="utf-8"))["patterns"]
    patterns = [(rule, re.compile(rule["pattern"], re.IGNORECASE | re.MULTILINE)) for rule in definitions]
    findings: list[dict[str, Any]] = []
    for path in tree_entries(root):
        if not stat.S_ISREG(path.lstat().st_mode):
            continue
        relative = path.relative_to(root).as_posix()
        digest = file_digest(path)
        with path.open("rb") as handle:
            raw = handle.read(TEXT_LIMIT)
        local: list[dict[str, Any]] = []
        overflow = False
        def add(rule_id, severity, explanation, remediation, line=1, excerpt=""):
            nonlocal overflow
            item = finding(rule_id, severity, relative, line, excerpt, explanation, remediation, digest)
            if len(local) < MAX_FINDINGS:
                local.append(item)
            else:
                overflow = True
                if severity == "FAIL" and not any(f["severity"] == "FAIL" for f in local):
                    local[-1] = item
            return item
        if path.stat().st_size > TEXT_LIMIT:
            add("structural.text_limit", "REVIEW", "This file exceeds the bounded text-review limit.", "Review the full file separately.")
        try:
            text = raw.decode("utf-8")
            if "\x00" in text:
                raise UnicodeError("binary content")
        except UnicodeError:
            add("execution.binary", "REVIEW", "This tree contains binary or compiled content that may run code.", "Inspect its provenance and behavior before use.")
            findings.extend(local)
            if len(findings) >= MAX_FINDINGS:
                findings = sorted(findings, key=lambda f: f["severity"] != "FAIL")[:MAX_FINDINGS]
                findings.append(finding("structural.finding_limit", "REVIEW", ".", 1, "", "Finding count exceeded bounded review output.", "Review the source in smaller units.", ""))
                break
            continue
        lines = text.splitlines()
        instruction = path.suffix.lower() == ".md" or path.name in {"AGENTS", "CLAUDE", "GEMINI"}
        for number, line in enumerate(lines, 1):
            if any(character in BIDI for character in line):
                add("text.bidi", "FAIL" if instruction else "REVIEW", "Hidden direction controls can make instructions appear different from their bytes.", "Remove direction controls and review the visible text.", number, line)
            if any(0xE0000 <= ord(character) <= 0xE007F for character in line):
                add("text.tag", "FAIL" if instruction else "REVIEW", "Hidden Unicode tag characters appear in this text.", "Remove tag characters and review the instruction.", number, line)
            visible_line = line.lstrip("\ufeff") if number == 1 else line
            if any(character in ZERO_WIDTH for character in visible_line):
                add("text.zero_width", "REVIEW", "Invisible characters can hide or split meaningful text.", "Review and remove invisible characters unless their purpose is approved.", number, line)
            if len(line) > 2000:
                add("text.long_line", "REVIEW", "A very long line can conceal instructions from a quick review.", "Split it into readable lines and inspect the full content.", number, line)
        normalized = unicodedata.normalize("NFKC", "".join(c for c in text if c not in ZERO_WIDTH))
        # Replacing newlines preserves length for line-number mapping while matching phrases across lines.
        searchable = normalized.replace("\n", " ").replace("\r", " ")
        normalized_lines = normalized.split("\n")
        comment_targets: dict[str, bool] = {}
        for rule, pattern in patterns:
            matches = islice(pattern.finditer(searchable), 25)
            for match in matches:
                prefix = searchable[max(0, match.start() - 40):match.start()]
                if rule["id"].startswith("aham.") and re.search(r"(?:never|do not|don't|must not|cannot)\s*$", prefix, re.IGNORECASE):
                    continue
                if rule["id"] == "aham.direct_write" and re.search(r"\bdid not\s*$", prefix, re.IGNORECASE):
                    continue
                number = normalized[:match.start()].count("\n") + 1
                excerpt = "[redacted possible secret]" if rule["id"].startswith("secret.") else match.group()
                item = add(rule["id"], rule["severity"], rule["explanation"], rule["remediation"], number, excerpt)
                if rule["id"] == "target.sensitive":
                    # Only whole-line shell comments qualify. Inline comments and
                    # matches crossing executable lines retain the read escalation.
                    end_line = normalized[:match.end() - 1].count("\n") + 1
                    comment_only = path.suffix.lower() == ".sh" and all(
                        line.lstrip().startswith("#")
                        for line in normalized_lines[number - 1:end_line]
                    )
                    identity = item["finding_id"]
                    comment_targets[identity] = comment_targets.get(identity, True) and comment_only
        if re.search(r"<!--[\s\S]{256,}?-->", text):
            add("text.hidden_comment", "REVIEW", "A long HTML comment hides text from normal Markdown rendering.", "Read the complete comment and remove unnecessary hidden instructions.")
        if re.search(r"(?:[A-Za-z0-9+/]{200,}={0,2}|[0-9a-fA-F]{256,})", text) or len(re.findall(r"[A-Za-z0-9+/]{20,}={1,2}", text)) > 10:
            add("text.encoded_blob", "REVIEW", "This file contains a large encoded-looking text blob.", "Decode and inspect it with a safe viewer before acceptance.")
        if raw.startswith(b"#!") or (os.name == "posix" and path.stat().st_mode & 0o111):
            add("execution.script", "REVIEW", "This file is executable or declares an interpreter.", "Read it before any separately approved execution.")
        if path.name == "package.json":
            try:
                value = json.loads(text)
                scripts = value.get("scripts", {})
                if any(key in scripts for key in {"preinstall", "install", "postinstall", "prepare", "prepublish", "prepack", "postpack", "dependencies"}):
                    add("execution.package_lifecycle", "REVIEW", "This package declares lifecycle commands that can run during installation or packing.", "Review all lifecycle commands before installing the package.")
            except (ValueError, AttributeError, TypeError):
                add("execution.package_lifecycle", "REVIEW", "Package configuration could not be interpreted safely.", "Review the package configuration manually.")
        if relative.endswith(".vscode/tasks.json") and "folderOpen" in text:
            add("execution.editor_task", "REVIEW", "This editor task can run when a folder opens.", "Review it before trusting or opening the workspace.")
        if relative.endswith((".claude/settings.json", ".claude/settings.local.json", "hooks/hooks.json")) and '"hooks"' in text:
            add("execution.agent_hooks", "REVIEW", "This agent configuration declares lifecycle hooks.", "Review every hook before enabling the integration.")
        if path.name == ".mcp.json":
            add("execution.mcp", "REVIEW", "This configuration can start or connect to MCP servers.", "Review each server command, destination and permission.")
        if path.name == "SKILL.md":
            fields, error = frontmatter(text)
            if error:
                add("skill.frontmatter", "REVIEW", error, "Use supported scalar YAML fields or request manual review.")
            name = fields.get("name", "")
            if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?", name) or "--" in name or name != path.parent.name:
                add("skill.name", "REVIEW", "Skill name must be 1-64 lowercase letters/digits/hyphens and match its folder.", "Correct the name and folder binding.")
            if not 1 <= len(fields.get("description", "")) <= 1024:
                add("skill.description", "REVIEW", "Skill description is missing or exceeds 1024 characters.", "Provide a concise description of the task and when to use it.")
            if "compatibility" in fields and not 1 <= len(fields["compatibility"]) <= 500:
                add("skill.compatibility", "REVIEW", "Compatibility must be 1-500 characters when supplied.", "Shorten or remove the compatibility field.")
            if re.search(r"(?:Bash|shell|all|\*)", fields.get("allowed-tools", ""), re.IGNORECASE):
                add("skill.allowed_tools", "REVIEW", "This skill asks to pre-approve shell or broad tool access.", "Review the requested tools; skill text cannot grant permissions.")
            if len(lines) > 500:
                add("skill.length", "INFO", "This skill exceeds the recommended 500-line main file.", "Move details into references loaded only when needed.")
            if re.search(r"read-only|reading list|format|summari", fields.get("description", ""), re.IGNORECASE) and any(f["rule_id"].startswith(("target.", "network.")) for f in local):
                add("skill.description_mismatch", "INFO", "The description sounds narrow but this file also references sensitive or network behavior.", "Check whether the description explains the full behavior.")
        if any(f["rule_id"] == "instruction.override" for f in local) and any(f["rule_id"].startswith(("target.", "network.")) for f in local):
            for item in local:
                if item["rule_id"] == "instruction.override":
                    item["severity"] = "FAIL"
                    item["explanation"] += " It appears with a sensitive or network target in the same file."
        if path.suffix.lower() in {".py", ".sh", ".js", ".mjs", ".cjs", ".ps1", ".bat"} and re.search(r"open\s*\(|read_text\s*\(|read_bytes\s*\(|\bcat\s|Get-Content", searchable, re.IGNORECASE):
            for item in local:
                if item["rule_id"] == "target.sensitive" and not comment_targets.get(item["finding_id"], False):
                    item["severity"] = "FAIL"
                    item["explanation"] += " This bundled script also contains a read operation."
        findings.extend(local)
        if overflow or len(findings) >= MAX_FINDINGS:
            findings = sorted(findings, key=lambda f: f["severity"] != "FAIL")[:MAX_FINDINGS]
            findings.append(finding("structural.finding_limit", "REVIEW", ".", 1, "", "Finding count exceeded bounded review output.", "Review the source in smaller units.", ""))
            break
    return findings


def annotate_diff(report: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    result = copy.deepcopy(report)
    def signature(item):
        return (item.get("rule_id"), item.get("path"), item.get("line"), item.get("excerpt"))
    old = {signature(item) for item in (previous or {}).get("findings", [])}
    result["new_findings"] = [item for item in result["findings"] if signature(item) not in old]
    return result
