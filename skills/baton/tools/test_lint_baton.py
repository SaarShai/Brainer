#!/usr/bin/env python3
"""Regression tests for lint_baton.py — no pytest, no network.

Negative test (contract §3): a fixture baton containing an untagged stale
sha fails the drop lint; the same fixture with `VERIFY-AT-GRAB` tags passes.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lint_baton import lint_baton  # noqa: E402

STALE_UNTAGGED = """\
# Baton: fix rounding bug

## State of Play (verified against git)
- Branch: main — HEAD is dc1dcb655fbaf73998b7f92173ac87f981e5ee4c
- Committed: canon regenerated, touching 4 files
- Verified working: `pytest tests/` green
"""

STALE_TAGGED = """\
# Baton: fix rounding bug

## State of Play (verified against git)
- Branch: main — HEAD is dc1dcb655fbaf73998b7f92173ac87f981e5ee4c VERIFY-AT-GRAB
- Committed: canon regenerated, touching 4 files VERIFY-AT-GRAB
- Verified working: `pytest tests/` green
"""

CLEAN_LIVE_COMMAND = """\
# Baton: fix rounding bug

## State of Play (verified against git)
- Branch: `git branch --show-current`
- Canon pin: `cat canon/canon.sha256`
- Verified working: `pytest tests/` green
"""

FENCED_SHA_EXEMPT = """\
# Baton: fix rounding bug

## Pointers
```
git show dc1dcb655fbaf73998b7f92173ac87f981e5ee4c
```
"""

PASS = 0
FAIL = 0


def check(name: str, cond: bool) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"FAIL: {name}")


def test_untagged_sha_and_file_count_fail() -> None:
    violations = lint_baton(STALE_UNTAGGED)
    check("untagged sha detected", any("sha" in v for v in violations))
    check("untagged file count detected", any("file count" in v for v in violations))


def test_tagged_values_pass() -> None:
    violations = lint_baton(STALE_TAGGED)
    check("tagged fixture has no violations", violations == [])


def test_live_command_only_passes() -> None:
    violations = lint_baton(CLEAN_LIVE_COMMAND)
    check("live re-derivation baton has no violations", violations == [])


def test_fenced_sha_is_exempt() -> None:
    violations = lint_baton(FENCED_SHA_EXEMPT)
    check("fenced sha is exempt from lint", violations == [])


if __name__ == "__main__":
    test_untagged_sha_and_file_count_fail()
    test_tagged_values_pass()
    test_live_command_only_passes()
    test_fenced_sha_is_exempt()
    print(f"{PASS} passed, {FAIL} failed")
    raise SystemExit(1 if FAIL else 0)
