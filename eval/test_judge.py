#!/usr/bin/env python3
"""Regression tests for score parsing in eval/judge.py."""

from __future__ import annotations

from judge import _extract_score, _rubric_for_case


def test_plain_score() -> None:
    assert _extract_score("5 correct and complete") == 5


def test_labeled_score() -> None:
    assert _extract_score("Reply: 5, correct and complete") == 5
    assert _extract_score("Score: 4 — minor omission") == 4


def test_complete_think_block_is_ignored() -> None:
    raw = "<think>\n1. analyze\n2. compare\n</think>\n4 correct, minor omission"
    assert _extract_score(raw) == 4


def test_orphaned_closing_think_tag_is_ignored() -> None:
    bad_case = "Here's a thinking process:\n1. analyze\n2. compare\n</think>\n5 complete"
    assert _extract_score(bad_case) == 5


def test_out_of_range_leading_number_is_not_a_score() -> None:
    assert _extract_score("9 candidates considered\n3 mostly correct") == 3
    assert _extract_score("Reply: 9, invalid score") is None


def test_shared_rubric_is_scoped_to_current_case() -> None:
    scoped = _rubric_for_case("Prompt 1: A. Prompt 2: B.", 1)
    assert scoped.startswith("CURRENT CASE: prompt 2.")
    assert "criteria for other numbered prompts are irrelevant" in scoped


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
