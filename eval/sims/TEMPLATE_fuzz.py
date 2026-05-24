#!/usr/bin/env python3
"""TEMPLATE: fuzz sim for a parser- / file-handling skill.

Copy to eval/sims/<skill>_fuzz.py, fill in:
  - SKILL_NAME
  - call_under_test(payload) — wrap the skill's entry point
  - extra_cases() — skill-specific malformed inputs beyond common_fuzz_payloads()
  - correctness_checks() — assertions on specific cases

A 0-exit means: no crashes AND all correctness checks pass.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import (  # noqa: E402
    Report, Timer, common_fuzz_payloads,
    import_skill_module, print_report, write_report,
)


SKILL_NAME = "REPLACE_ME"


def call_under_test(payload: str | bytes) -> dict:
    """Run the skill against a payload. Should NOT raise; should return a dict
    with at least {'ok': bool, 'fails': int, 'warns': int}. Wrap any expected
    exceptions inside this function and translate to a dict."""
    raise NotImplementedError("fill me in")


def extra_cases() -> dict[str, bytes | str]:
    """Skill-specific evil payloads. Merged with common_fuzz_payloads()."""
    return {}


def correctness_checks(results: dict[str, dict]) -> dict[str, bool]:
    """Map check-name → did-it-pass. Empty dict if the skill has no shape-specific
    expectations beyond not-crashing."""
    return {}


def main() -> int:
    t = Timer()
    payloads = {**common_fuzz_payloads(), **extra_cases()}
    results = {}
    crashes = 0
    for name, payload in payloads.items():
        try:
            results[name] = call_under_test(payload)
        except Exception as e:
            crashes += 1
            results[name] = {"ok": False, "error": f"{type(e).__name__}: {e}"}

    checks = correctness_checks(results)
    failed_checks = [k for k, v in checks.items() if not v]

    report = Report(
        skill=SKILL_NAME, shape="fuzz", elapsed_s=t.elapsed(),
        summary={
            "n_cases": len(payloads),
            "crashes": crashes,
            "correctness_checks": checks,
        },
        findings=[
            {"case": n, **r}
            for n, r in results.items()
            if not r.get("ok") or "error" in r
        ],
    )
    report.passed = (crashes == 0 and not failed_checks)
    print_report(report)
    path = write_report(report)
    print(f"\nfull JSON: {path}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
