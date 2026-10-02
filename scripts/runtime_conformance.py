#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from state_io import StateError


ConfigKey = tuple[str, str, str, int, str | None]


def load_register(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StateError(f"could not read conformance evidence register: {exc}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("entries"), list):
        raise StateError("conformance evidence register must contain an entries list")
    return value


def rich_live(entry: dict[str, Any]) -> bool:
    return (
        entry.get("evidence_type") == "live_runtime_rehearsal"
        and entry.get("result") == "pass"
        and entry.get("independently_verified") is True
        and isinstance(entry.get("harness"), str)
        and bool(entry.get("harness"))
        and isinstance(entry.get("harness_version"), str)
        and bool(entry.get("harness_version"))
        and isinstance(entry.get("model"), str)
        and bool(entry.get("model"))
        and isinstance(entry.get("context_tokens"), int)
        and entry.get("context_tokens", 0) > 0
        and isinstance(entry.get("framework_commit"), str)
        and bool(entry.get("framework_commit"))
        and isinstance(entry.get("permission_mode"), str)
        and bool(entry.get("permission_mode"))
        and isinstance(entry.get("human_intervention"), bool)
    )


def config_key(
    harness: Any,
    version: Any,
    model: Any,
    context_tokens: Any,
    quantization: Any,
) -> ConfigKey | None:
    if not isinstance(harness, str) or not harness:
        return None
    if not isinstance(version, str) or not version:
        return None
    if not isinstance(model, str) or not model:
        return None
    if not isinstance(context_tokens, int) or context_tokens <= 0:
        return None
    if quantization is not None and (not isinstance(quantization, str) or not quantization):
        return None
    return (harness, version, model, context_tokens, quantization)


def live_config_key(entry: dict[str, Any]) -> ConfigKey | None:
    return config_key(
        entry.get("harness"),
        entry.get("harness_version"),
        entry.get("model"),
        entry.get("context_tokens"),
        entry.get("quantization"),
    )


def recovery_targets(entries: list[dict[str, Any]]) -> set[ConfigKey]:
    targets: set[ConfigKey] = set()
    for entry in entries:
        if entry.get("result") != "pass" or entry.get("independently_verified") is not True:
            continue
        if entry.get("evidence_type") == "runtime_switch_recovery" and entry.get("fresh_target_session") is True:
            key = config_key(
                entry.get("to_harness"),
                entry.get("to_harness_version"),
                entry.get("to_model"),
                entry.get("to_context_tokens"),
                entry.get("to_quantization"),
            )
        elif entry.get("evidence_type") == "runtime_failure_paths" and entry.get("fresh_target_session") is True:
            key = config_key(
                entry.get("target_harness"),
                entry.get("target_harness_version"),
                entry.get("target_model"),
                entry.get("target_context_tokens"),
                entry.get("target_quantization"),
            )
        else:
            continue
        if key is not None:
            targets.add(key)
    return targets


def selected_matrix(register: dict[str, Any], context_budget_bytes: int) -> dict[str, Any]:
    if context_budget_bytes < 1:
        raise StateError("context budget must be positive")
    entries = [entry for entry in register["entries"] if isinstance(entry, dict)]
    recovery = recovery_targets(entries)

    latest: dict[ConfigKey, dict[str, Any]] = {}
    for entry in entries:
        if not rich_live(entry):
            continue
        key = live_config_key(entry)
        if key is None:
            continue
        prior = latest.get(key)
        if prior is None or str(entry.get("verified_at") or "") >= str(prior.get("verified_at") or ""):
            latest[key] = entry

    rich: list[dict[str, Any]] = []
    for key, entry in sorted(latest.items()):
        harness, version, model, context_tokens, quantization = key
        tier = "recovery_verified" if key in recovery else "lifecycle_writer"
        rich.append(
            {
                "entry_id": entry.get("entry_id"),
                "runtime_profile": entry.get("runtime_profile"),
                "model": model,
                "harness": harness,
                "harness_version": version,
                "context_tokens": context_tokens,
                "quantization": quantization,
                "framework_commit": entry.get("framework_commit"),
                "tier": tier,
                "claim_scope": entry.get("claim_scope"),
                "verified_at": entry.get("verified_at"),
            }
        )

    legacy: list[dict[str, Any]] = []
    for entry in entries:
        if rich_live(entry):
            continue
        runtime_profile = entry.get("runtime_profile")
        if not isinstance(runtime_profile, str) or not runtime_profile:
            continue
        if entry.get("result") != "pass":
            continue
        legacy.append(
            {
                "entry_id": entry.get("entry_id"),
                "runtime_profile": runtime_profile,
                "reason": "Insufficient metadata or evidence scope for capability-based conformance classification.",
            }
        )

    return {
        "format": "aham-brahmasmi-conformance-matrix",
        "version": 1,
        "context_budget_bytes": context_budget_bytes,
        "token_equivalence_claimed": False,
        "selected_rich_evidence": rich,
        "legacy_unclassified": legacy,
        "new_live_runs_required": 0,
        "selection_policy": "Reuse retained independently verified rich evidence only for the exact demonstrated harness/model/context/quantization configuration; do not spend new live-run cost when existing evidence already covers that configuration.",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Derive runtime/harness conformance from retained evidence.")
    sub = parser.add_subparsers(dest="command", required=True)
    matrix = sub.add_parser("matrix")
    matrix.add_argument("--register", required=True)
    matrix.add_argument("--context-budget-bytes", required=True, type=int)
    matrix.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = selected_matrix(load_register(Path(args.register)), args.context_budget_bytes)
    except StateError as exc:
        print(f"CONFORMANCE FAILED: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
