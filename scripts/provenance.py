#!/usr/bin/env python3
"""Create and verify a public authorship commitment without exposing its secret."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FORMAT = "aham-brahmasmi-provenance-commitment"
VERSION = 1
DOMAIN = b"aham-brahmasmi-provenance-v1\0"
MIN_SECRET_BYTES = 32


class ProvenanceError(RuntimeError):
    """Raised when a provenance commitment cannot be created or verified safely."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or verify an Aham Brahmasmi provenance commitment.")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="Bind an offline secret to the current Git tree")
    create.add_argument("--secret-file", required=True, help="Secret file kept outside this repository")
    create.add_argument("--repo", default=str(ROOT), help="Git repository whose current tree should be committed")
    create.add_argument("--output", help="Write public commitment JSON here; otherwise print to stdout")

    verify = sub.add_parser("verify", help="Verify a revealed secret against a public commitment")
    verify.add_argument("--secret-file", required=True)
    verify.add_argument("--commitment-file", required=True)
    verify.add_argument("--repo", help="Optional Git repository in which the recorded tree must exist")

    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def is_inside_framework(path: Path) -> bool:
    resolved = path.expanduser().resolve()
    return resolved == ROOT or ROOT in resolved.parents


def read_secret(value: str) -> bytes:
    path = Path(value).expanduser().resolve()
    if is_inside_framework(path):
        raise ProvenanceError("secret file must be stored outside the public framework repository")
    if not path.is_file():
        raise ProvenanceError("secret file does not exist or is not a regular file")
    data = path.read_bytes()
    if len(data) < MIN_SECRET_BYTES:
        raise ProvenanceError(f"secret file must contain at least {MIN_SECRET_BYTES} bytes")
    return data


def run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "Git command failed"
        raise ProvenanceError(message)
    return result.stdout.strip()


def current_tree(repo_value: str) -> tuple[Path, str]:
    repo = Path(repo_value).expanduser().resolve()
    if not repo.is_dir():
        raise ProvenanceError("repository directory does not exist")
    top = Path(run_git(repo, "rev-parse", "--show-toplevel")).resolve()
    tree = run_git(top, "rev-parse", "HEAD^{tree}")
    if len(tree) != 40 or any(ch not in "0123456789abcdef" for ch in tree.lower()):
        raise ProvenanceError("Git returned an unexpected tree identifier")
    return top, tree.lower()


def digest(secret: bytes, tree_sha: str) -> str:
    payload = DOMAIN + tree_sha.encode("ascii") + b"\0" + secret
    return hashlib.sha256(payload).hexdigest()


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    temp_path = Path(handle.name)
    try:
        with handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def create_commitment(secret_file: str, repo_value: str, output: str | None) -> int:
    secret = read_secret(secret_file)
    repo, tree = current_tree(repo_value)
    value = {
        "format": FORMAT,
        "version": VERSION,
        "project": "Aham Brahmasmi",
        "tree_sha": tree,
        "hash_algorithm": "SHA-256",
        "commitment": digest(secret, tree),
        "created_at": utc_now(),
        "note": "The secret is intentionally not included. Keep it offline until proof is needed.",
    }
    if output:
        path = Path(output).expanduser().resolve()
        if path.exists():
            raise ProvenanceError("output already exists; refusing to overwrite an existing public commitment")
        atomic_write_json(path, value)
        print("PROVENANCE COMMITMENT CREATED")
        print(f"Repository: {repo}")
        print(f"Tree: {tree}")
        print(f"Public commitment: {path}")
        print("Secret: not printed and not copied")
    else:
        print(json.dumps(value, indent=2, sort_keys=True))
    return 0


def read_commitment(path_value: str) -> dict[str, Any]:
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise ProvenanceError("commitment file does not exist")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProvenanceError(f"commitment file is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ProvenanceError("commitment file must contain a JSON object")
    if value.get("format") != FORMAT or value.get("version") != VERSION:
        raise ProvenanceError("commitment format or version is not recognized")
    tree = value.get("tree_sha")
    commitment = value.get("commitment")
    if not isinstance(tree, str) or len(tree) != 40:
        raise ProvenanceError("commitment has no valid Git tree identifier")
    if not isinstance(commitment, str) or len(commitment) != 64:
        raise ProvenanceError("commitment has no valid SHA-256 value")
    return value


def verify_commitment(secret_file: str, commitment_file: str, repo_value: str | None) -> int:
    secret = read_secret(secret_file)
    value = read_commitment(commitment_file)
    tree = str(value["tree_sha"]).lower()
    expected = str(value["commitment"]).lower()
    actual = digest(secret, tree)
    if not hmac.compare_digest(actual, expected):
        raise ProvenanceError("secret does not match the public provenance commitment")
    if repo_value:
        repo = Path(repo_value).expanduser().resolve()
        if not repo.is_dir():
            raise ProvenanceError("verification repository does not exist")
        run_git(repo, "cat-file", "-e", f"{tree}^{{tree}}")
    print("PROVENANCE VERIFIED")
    print(f"Tree: {tree}")
    print("Secret matches the public commitment.")
    return 0


def main() -> int:
    args = parse_args()
    try:
        if args.command == "create":
            return create_commitment(args.secret_file, args.repo, args.output)
        if args.command == "verify":
            return verify_commitment(args.secret_file, args.commitment_file, args.repo)
        raise ProvenanceError("unsupported provenance command")
    except (ProvenanceError, OSError, ValueError) as exc:
        print(f"PROVENANCE FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
