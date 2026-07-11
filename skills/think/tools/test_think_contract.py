#!/usr/bin/env python3
"""Positive and adversarial checks for think_contract and its drift probe."""

from __future__ import annotations

import json
import re
from pathlib import Path

from think_contract import load_eval_text, validate_contract


ROOT = Path(__file__).resolve().parents[3]
SKILL = (ROOT / "skills" / "think" / "SKILL.md").read_text(encoding="utf-8")
EVAL = load_eval_text(ROOT)
PROBES = json.loads((ROOT / "skills" / "think" / "drift_probes.json").read_text(encoding="utf-8"))


def test_real_contract_passes() -> None:
    assert validate_contract(SKILL, EVAL, PROBES) == []


def test_contract_degrades_without_canonical_eval_tree() -> None:
    assert validate_contract(SKILL, "", PROBES) == []


def test_known_bad_missing_route_fails() -> None:
    bad_skill = SKILL.replace("matched companion skill", "mentioned companion skill")
    errors = validate_contract(bad_skill, EVAL, PROBES)
    assert any("matched companion skill" in error for error in errors)


def test_known_bad_absolute_ingest_rule_fails() -> None:
    bad_skill = SKILL + "\nDeposit and compile one source at a time.\n"
    errors = validate_contract(bad_skill, EVAL, PROBES)
    assert any("one source at a time" in error for error in errors)


def test_known_bad_mutable_raw_fallback_fails() -> None:
    bad_skill = SKILL.replace("raw sources are immutable", "raw sources may be edited")
    errors = validate_contract(bad_skill, EVAL, PROBES)
    assert any("raw sources are immutable" in error for error in errors)


def test_known_bad_prestige_role_fails() -> None:
    bad_skill = SKILL.replace(
        "Be a rigorous, resourceful collaborator",
        "Operate at the level of the sharpest people in the world — intellectual firepower and erudition. Be a rigorous, resourceful collaborator",
    )
    errors = validate_contract(bad_skill, EVAL, PROBES)
    assert any("sharpest people in the world" in error for error in errors)


def test_known_bad_probe_regex_fails() -> None:
    bad_probes = [{**PROBES[0], "pattern": "["}]
    errors = validate_contract(SKILL, EVAL, bad_probes)
    assert any("invalid regex" in error for error in errors)


def test_sycophancy_probe_has_boundary_fixtures() -> None:
    pattern = re.compile(PROBES[0]["pattern"])
    positives = (
        "Great question — you're absolutely right.",
        "Excellent idea. I couldn't agree more.",
        "That's a brilliant approach.",
    )
    negatives = (
        "The premise is wrong; here is the evidence.",
        "Good catch: the fresh test fails at line 8.",
        "That result is correct because the reproduced trace confirms it.",
        "I agree with the conclusion because sources A and B independently support it.",
    )
    assert all(pattern.search(text) for text in positives)
    assert all(not pattern.search(text) for text in negatives)


def main() -> int:
    tests = [value for name, value in globals().items() if name.startswith("test_")]
    failures = 0
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
        except Exception as exc:  # noqa: BLE001 - standalone test harness
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
