#!/usr/bin/env python3
"""Validate drift_probes.json files consumed by compliance-canary."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"

KNOWN_KINDS = {
    "forbidden_regex",
    "word_count_per_message",
    "claim_without_evidence",
    "repeated_tool_error",
    "trajectory_drift",
    "user_correction",
    "prompt_intent",
    "early_stop",
    "completion_without_closure",
    "ledger_not_materialized",
    "workflow_nomination",
}

REQUIRED_BY_KIND = {
    "forbidden_regex": ["pattern"],
    "word_count_per_message": ["threshold"],
    "claim_without_evidence": ["claim_pattern"],
    "repeated_tool_error": ["pattern"],
    "trajectory_drift": ["min_tool_calls", "max_error_rate"],
    "user_correction": ["pattern"],
    "prompt_intent": ["pattern"],
    "early_stop": [],
    "completion_without_closure": [],
    "ledger_not_materialized": ["min_open"],
    "workflow_nomination": ["min_tool_calls"],
}

REGEX_FIELDS = [
    "pattern",
    "claim_pattern",
    "warrant_pattern",
    "unless_pattern",
    "maintenance_path_pattern",
    "trivial_pattern",
]


def validate_probe(probe: object, source: str, seen_ids: set[str]) -> list[str]:
    errors: list[str] = []
    if not isinstance(probe, dict):
        return [f"{source}: probe must be an object"]
    probe_id = probe.get("id")
    if not isinstance(probe_id, str) or not probe_id.strip():
        errors.append(f"{source}: probe missing string id")
    elif probe_id in seen_ids:
        errors.append(f"{source}: duplicate probe id {probe_id!r}")
    else:
        seen_ids.add(probe_id)
    kind = probe.get("kind")
    if kind not in KNOWN_KINDS:
        errors.append(f"{source}:{probe_id or '?'}: unknown kind {kind!r}")
        return errors
    for field in REQUIRED_BY_KIND[kind]:
        if field not in probe:
            errors.append(f"{source}:{probe_id}: {kind} probe missing {field}")
    for field in REGEX_FIELDS:
        if field not in probe:
            continue
        try:
            re.compile(str(probe[field]))
        except re.error as exc:
            errors.append(f"{source}:{probe_id}: invalid regex in {field}: {exc}")
    if "severity" in probe and probe["severity"] not in {"info", "warn", "fail"}:
        errors.append(f"{source}:{probe_id}: severity must be info, warn, or fail")
    if not isinstance(probe.get("message"), str) or not probe.get("message", "").strip():
        errors.append(f"{source}:{probe_id}: missing message")
    return errors


def validate_file(path: Path) -> list[str]:
    rel = path.relative_to(ROOT).as_posix()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{rel}: invalid JSON: {exc}"]
    if not isinstance(data, list) or not data:
        return [f"{rel}: must contain a non-empty JSON list"]
    errors: list[str] = []
    seen_ids: set[str] = set()
    for probe in data:
        errors.extend(validate_probe(probe, rel, seen_ids))
    return errors


def main() -> int:
    files = sorted(SKILLS.glob("*/drift_probes.json"))
    errors: list[str] = []
    for path in files:
        errors.extend(validate_file(path))
    if errors:
        print("Drift probe check failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Drift probe check passed: {len(files)} files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
