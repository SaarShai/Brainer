#!/usr/bin/env python3
"""TEMPLATE: calibration sim for a classifier-style skill.

Copy to eval/sims/<skill>_corpus.py, fill in:
  - SKILL_NAME
  - CASES (labeled examples)
  - classify_one(case) — call into the skill's classifier
  - Optionally: a "real corpus" pass that scans real project files

Exits 0 if accuracy ≥ ACCURACY_TARGET, 1 otherwise.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import (  # noqa: E402
    LabeledCase, Report, Timer, calibration_metrics,
    import_skill_module, print_report, write_report,
)


SKILL_NAME = "REPLACE_ME"
ACCURACY_TARGET = 0.85


# Replace with real labeled examples
CASES: list[LabeledCase] = [
    # LabeledCase(label="pos_thing_1", inputs=("...",), expected=True),
    # LabeledCase(label="neg_thing_1", inputs=("...",), expected=False),
]


def classify_one(case: LabeledCase) -> bool:
    """Call the skill's classifier. Return the bool prediction."""
    # mod = import_skill_module(SKILL_NAME, "classify")
    # return mod.classify(*case.inputs)
    raise NotImplementedError("fill me in")


def main() -> int:
    t = Timer()
    rows = []
    for c in CASES:
        try:
            actual = classify_one(c)
            rows.append({
                "label": c.label,
                "expected": c.expected,
                "actual": actual,
                "correct": actual == c.expected,
            })
        except Exception as e:
            rows.append({
                "label": c.label,
                "expected": c.expected,
                "actual": None,
                "correct": False,
                "error": f"{type(e).__name__}: {e}",
            })

    metrics = calibration_metrics(rows)
    report = Report(skill=SKILL_NAME, shape="calibration",
                    elapsed_s=t.elapsed(), summary=metrics)
    report.findings = [r for r in rows if not r["correct"]]
    report.passed = metrics.get("accuracy", 0) >= ACCURACY_TARGET
    print_report(report)
    if report.findings:
        print("\nmisclassifications:")
        for r in report.findings:
            print(f"  [{r.get('error', '?')}] {r['label']}")
    path = write_report(report)
    print(f"\nfull JSON: {path}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
