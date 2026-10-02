#!/usr/bin/env python3
"""Verify foundation rules that should hold before deeper implementation begins."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = (
    "README.md",
    "LICENSE",
    "NOTICE",
    "THIRD_PARTY_NOTICES.md",
    "AGENTS.md",
    "PROJECT_CHECKLIST.md",
    "docs/PUBLIC_BOUNDARY.md",
    "docs/THIRD_PARTY_POLICY.md",
    "docs/TEST_PLAN.md",
    "docs/PROVENANCE.md",
    "scripts/provenance.py",
    "third_party/registry.json",
)

TEXT_SUFFIXES = {".md", ".json", ".yaml", ".yml", ".py", ".sh", ".toml", ".txt"}
SCAN_EXCLUSIONS = {
    Path("tests/verify_foundation.py"),
}

SENSITIVE_PATTERNS = {
    "Unix home path": re.compile(r"/(?:home|Users)/[^/\s]+/"),
    "Windows user path": re.compile(r"[A-Za-z]:\\\\Users\\\\[^\\\s]+\\\\"),
    "private key": re.compile(r"BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY"),
    "GitHub classic token": re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    "GitHub fine-grained token": re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    "AWS access key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "generic OpenAI-style secret": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
}

REQUIRED_SOURCE_FIELDS = {
    "id",
    "name",
    "upstream_url",
    "source_ref",
    "license",
    "integration",
    "local_changes",
    "checked_at",
    "review_status",
}

ALLOWED_INTEGRATIONS = {"link", "installer", "adapter"}
ALLOWED_REVIEW_STATUSES = {"approved", "review-required", "disabled"}


def fail(message: str, errors: list[str]) -> None:
    errors.append(message)


def check_required_files(errors: list[str]) -> None:
    for relative in REQUIRED_FILES:
        if not (ROOT / relative).is_file():
            fail(f"Missing required file: {relative}", errors)


def check_license(errors: list[str]) -> None:
    license_path = ROOT / "LICENSE"
    if not license_path.is_file():
        return
    text = license_path.read_text(encoding="utf-8", errors="replace")
    if "Apache License" not in text or "Version 2.0" not in text:
        fail("LICENSE is not recognizable as Apache License 2.0", errors)


def check_notice(errors: list[str]) -> None:
    path = ROOT / "NOTICE"
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    for required in ("Aham Brahmasmi", "Copyright 2026 loud-whisper", "Apache License, Version 2.0"):
        if required not in text:
            fail(f"NOTICE is missing required attribution text: {required}", errors)


def load_registry(errors: list[str]) -> dict | None:
    registry_path = ROOT / "third_party/registry.json"
    if not registry_path.is_file():
        return None
    try:
        data = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"third_party/registry.json is invalid JSON: {exc}", errors)
        return None
    if not isinstance(data, dict):
        fail("third_party registry must contain a JSON object", errors)
        return None
    return data


def check_registry(errors: list[str]) -> None:
    data = load_registry(errors)
    if data is None:
        return

    if data.get("version") != 1:
        fail("third_party registry version must currently be 1", errors)
    if data.get("policy") != "link-upstream":
        fail("third_party registry policy must be 'link-upstream'", errors)

    sources = data.get("sources")
    if not isinstance(sources, list):
        fail("third_party registry 'sources' must be a list", errors)
        return

    seen_ids: set[str] = set()
    for index, source in enumerate(sources):
        label = f"third_party source #{index + 1}"
        if not isinstance(source, dict):
            fail(f"{label} must be an object", errors)
            continue

        missing = REQUIRED_SOURCE_FIELDS - set(source)
        if missing:
            fail(f"{label} missing fields: {', '.join(sorted(missing))}", errors)
            continue

        source_id = source["id"]
        if not isinstance(source_id, str) or not source_id.strip():
            fail(f"{label} has an invalid id", errors)
        elif source_id in seen_ids:
            fail(f"Duplicate third_party source id: {source_id}", errors)
        else:
            seen_ids.add(source_id)

        parsed = urlparse(str(source["upstream_url"]))
        if parsed.scheme != "https" or not parsed.netloc:
            fail(f"{label} upstream_url must be a public HTTPS URL", errors)

        if source["integration"] not in ALLOWED_INTEGRATIONS:
            fail(
                f"{label} integration must be one of: {', '.join(sorted(ALLOWED_INTEGRATIONS))}",
                errors,
            )

        if source["review_status"] not in ALLOWED_REVIEW_STATUSES:
            fail(
                f"{label} review_status must be one of: {', '.join(sorted(ALLOWED_REVIEW_STATUSES))}",
                errors,
            )

        for field in ("name", "source_ref", "license", "checked_at"):
            if not isinstance(source[field], str) or not source[field].strip():
                fail(f"{label} field '{field}' must be a non-empty string", errors)

        if not isinstance(source["local_changes"], bool):
            fail(f"{label} local_changes must be true or false", errors)


def check_third_party_notices(errors: list[str]) -> None:
    registry = load_registry(errors)
    notices_path = ROOT / "THIRD_PARTY_NOTICES.md"
    if registry is None or not notices_path.is_file():
        return
    notices = notices_path.read_text(encoding="utf-8", errors="replace")
    sources = registry.get("sources")
    if not isinstance(sources, list):
        return
    for source in sources:
        if not isinstance(source, dict):
            continue
        source_id = str(source.get("id", "unknown"))
        for field in ("name", "upstream_url", "source_ref", "license"):
            value = source.get(field)
            if isinstance(value, str) and value and value not in notices:
                fail(f"THIRD_PARTY_NOTICES.md does not mention {source_id} {field}: {value}", errors)


def check_repository_boundary(errors: list[str]) -> None:
    for path in ROOT.rglob("*"):
        if ".git" in path.parts:
            continue

        relative = path.relative_to(ROOT)

        if path.is_symlink():
            try:
                target = path.resolve(strict=True)
            except FileNotFoundError:
                fail(f"Broken symlink: {relative}", errors)
                continue
            if ROOT not in target.parents and target != ROOT:
                fail(f"Symlink escapes repository boundary: {relative} -> {target}", errors)
            continue

        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if relative in SCAN_EXCLUSIONS:
            continue

        text = path.read_text(encoding="utf-8", errors="replace")
        for label, pattern in SENSITIVE_PATTERNS.items():
            if pattern.search(text):
                fail(f"Possible {label} found in {relative}", errors)


def main() -> int:
    errors: list[str] = []

    check_required_files(errors)
    check_license(errors)
    check_notice(errors)
    check_registry(errors)
    check_third_party_notices(errors)
    check_repository_boundary(errors)

    if errors:
        print("FOUNDATION CHECKS FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("FOUNDATION CHECKS PASSED")
    print("- required project and release-attribution files present")
    print("- Apache 2.0 license and NOTICE detected")
    print("- third-party registry and notices are structurally aligned")
    print("- no obvious boundary violations detected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
