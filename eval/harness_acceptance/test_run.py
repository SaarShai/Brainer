#!/usr/bin/env python3
"""Tests for run.py RUNNER MECHANICS ONLY — plain-python (no pytest dep),
runnable standalone. Shape mirrors skills/loop-engineering/tools/test_loop_lint.py:
a list of test_* functions, a main() that runs them and returns the failure
count (exit 0 == all pass), registered in scripts/run_all_tests.sh.

These tests assert the HARNESS behaves correctly (a raising check is reported
as FAIL not a crash; --gate exit codes; --report always exits 0; table format).
They do NOT assert the H-check verdicts themselves — those are free to flip
as the repo improves (see BASELINE.md for the day-one honest report).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
RUN_PY = Path(__file__).resolve().parent / "run.py"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_marketplace_count_discovers_package_root_skills():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        marketplace = root / ".claude-plugin" / "marketplace.json"
        _write(marketplace, json.dumps({"plugins": [{"source": "./plugin"}]}))
        plugin = root / "plugin"
        _write(plugin / ".claude-plugin" / "plugin.json", json.dumps({"name": "demo"}))
        _write(plugin / "skills" / "alpha" / "SKILL.md", "alpha\n")
        _write(plugin / "skills" / "beta" / "SKILL.md", "beta\n")
        _write(plugin / "skills" / "not-a-skill" / "README.md", "no\n")
        _write(plugin / "skills" / "_shared" / "SKILL.md", "internal\n")

        assert run._marketplace_skill_count(marketplace) == 2


def test_raising_check_is_reported_as_fail_not_crash():
    def _boom():
        raise RuntimeError("kaboom")

    results = run.run_checks(checks=[_boom])
    assert len(results) == 1
    check_id, axis, ok, reason = results[0]
    assert ok is False
    assert "CRASHED" in reason
    assert "kaboom" in reason


def test_run_checks_preserves_order_and_count():
    def _a():
        return ("A1", "axis1", True, "ok")

    def _b():
        return ("B2", "axis2", False, "not ok")

    results = run.run_checks(checks=[_a, _b])
    assert [r[0] for r in results] == ["A1", "B2"]
    assert results[0][2] is True
    assert results[1][2] is False


def test_format_table_reports_pass_and_fail_counts():
    results = [
        ("H1", "token", True, "fine"),
        ("H2", "reliability", False, "broken"),
    ]
    table = run.format_table(results)
    assert "H1" in table and "PASS" in table
    assert "H2" in table and "FAIL" in table
    assert "1/2 PASS" in table
    assert "1 FAIL" in table


def test_format_table_all_pass_shows_zero_fail():
    results = [("H1", "token", True, "fine")]
    table = run.format_table(results)
    assert "1/1 PASS, 0 FAIL" in table


def test_report_mode_always_exits_zero_even_with_fails():
    proc = subprocess.run(
        [sys.executable, str(RUN_PY), "--report"],
        capture_output=True, text=True, cwd=str(REPO), timeout=30,
    )
    assert proc.returncode == 0, f"--report must always exit 0, got {proc.returncode}"


def test_default_mode_behaves_like_report():
    proc = subprocess.run(
        [sys.executable, str(RUN_PY)],
        capture_output=True, text=True, cwd=str(REPO), timeout=30,
    )
    assert proc.returncode == 0, f"default mode must exit 0 (report semantics), got {proc.returncode}"


def test_gate_mode_exits_nonzero_when_any_check_fails():
    proc = subprocess.run(
        [sys.executable, str(RUN_PY), "--gate"],
        capture_output=True, text=True, cwd=str(REPO), timeout=30,
    )
    # Whatever today's honest baseline is (see BASELINE.md), --gate must
    # reflect it. Match an actual per-row FAIL verdict ("| FAIL |", exactly
    # how format_table renders a failing row), not the bare substring "FAIL"
    # — the latter also matches inside a fully-passing summary line like
    # "16/16 PASS, 0 FAIL", which would wrongly demand a nonzero exit on a
    # clean run.
    if "| FAIL |" in proc.stdout:
        assert proc.returncode != 0, "--gate must exit nonzero when any check FAILs"
    else:
        assert proc.returncode == 0


def test_gate_mode_main_returns_zero_when_all_checks_pass():
    def _ok():
        return ("Z1", "axis", True, "fine")

    # run_checks()'s default param is the SAME list object as module-level
    # CHECKS (bound at def-time) — mutate it in place (not reassign the name)
    # so main()'s no-arg call to run_checks() picks up the fixture checks.
    original = list(run.CHECKS)
    try:
        run.CHECKS[:] = [_ok]
        rc = run.main(["--gate"])
        assert rc == 0
    finally:
        run.CHECKS[:] = original


def test_gate_mode_main_returns_nonzero_when_a_check_fails():
    def _bad():
        return ("Z2", "axis", False, "broken")

    original = list(run.CHECKS)
    try:
        run.CHECKS[:] = [_bad]
        rc = run.main(["--gate"])
        assert rc != 0
    finally:
        run.CHECKS[:] = original


def test_table_output_has_expected_columns():
    proc = subprocess.run(
        [sys.executable, str(RUN_PY), "--report"],
        capture_output=True, text=True, cwd=str(REPO), timeout=30,
    )
    header_line = next(l for l in proc.stdout.splitlines() if l.startswith("id"))
    assert "axis" in header_line and "verdict" in header_line and "reason" in header_line


def test_all_sixteen_checks_present_in_report():
    proc = subprocess.run(
        [sys.executable, str(RUN_PY), "--report"],
        capture_output=True, text=True, cwd=str(REPO), timeout=30,
    )
    for check_id in ["H1a", "H1b", "H1c", "H2a", "H2b", "H2c", "H3a", "H3b",
                      "H4a", "H4b", "H4c", "H5a", "H5b", "H6a", "H6b", "H7"]:
        assert check_id in proc.stdout, f"{check_id} missing from --report output"
    assert "H8" not in proc.stdout, \
        "H8 is explicitly excluded from this suite (model-dependent; see eval/MEASUREMENT_QUEUE.md)"


def test_run_completes_within_ten_seconds():
    import time
    start = time.monotonic()
    proc = subprocess.run(
        [sys.executable, str(RUN_PY), "--report"],
        capture_output=True, text=True, cwd=str(REPO), timeout=15,
    )
    elapsed = time.monotonic() - start
    assert proc.returncode == 0
    assert elapsed < 10, f"run.py --report took {elapsed:.1f}s, must be <10s"


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]


def main() -> int:
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    return failed


if __name__ == "__main__":
    sys.exit(main())
