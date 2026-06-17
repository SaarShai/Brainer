#!/usr/bin/env python3
"""Tests for loop_run_monitor.py — plain-python (no pytest dep), runnable standalone.

Shape mirrors test_loop_lint.py: a list of test_* functions, a main() that runs
them and returns the failure count (exit 0 == all pass), registered in
scripts/run_all_tests.sh.

The three stuck triggers (S1 same-command 3×, S2 same-error 2×, S3 flat metric
across 2 iters) are the falsifiable core: a stuck trace the monitor PASSES, or a
healthy trace it flags STUCK, is a measurable bug.
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import loop_run_monitor as m  # noqa: E402


def _codes(trace, **kw):
    rep = m.monitor(json.dumps(trace), "trace.json", **kw)
    return [(f.code, f.severity) for f in rep.findings]


def _has(trace, code, sev, **kw):
    return (code, sev) in _codes(trace, **kw)


def _exit_for(trace, argv_extra=None):
    """Run main() against a temp file; return the process exit code."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        fh.write(json.dumps(trace))
        path = fh.name
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            return m.main([path] + (argv_extra or []))
    finally:
        os.unlink(path)


# A healthy trace: distinct commands, no repeated error, metric climbing,
# accepted changes with cost — the clean baseline the failure tests mutate.
HEALTHY = [
    {"i": 0, "command": "edit a.py",  "error": "", "metric": 1, "accepted": True,  "cost": 100},
    {"i": 1, "command": "pytest -q",  "error": "", "metric": 2, "accepted": False, "cost": 50},
    {"i": 2, "command": "edit b.py",  "error": "", "metric": 4, "accepted": True,  "cost": 120},
    {"i": 3, "command": "pytest -q",  "error": "", "metric": 6, "accepted": False, "cost": 50},
]


# --- healthy baseline -----------------------------------------------------

def test_healthy_trace_no_stuck():
    assert _codes(HEALTHY) == [], _codes(HEALTHY)
    assert _exit_for(HEALTHY) == 0


def test_healthy_reports_cost_per_accept():
    rep = m.monitor(json.dumps(HEALTHY), "trace.json")
    assert rep.n_accepted == 2, rep.n_accepted
    assert rep.total_cost == 320, rep.total_cost
    assert rep.cost_per_accept == 160.0, rep.cost_per_accept  # 320 / 2


# --- S1 SAME-COMMAND ------------------------------------------------------

def test_same_command_3x_stuck_s1():
    trace = [{"command": "pytest -q", "metric": i, "accepted": True} for i in range(3)]
    assert _has(trace, "S1", "STUCK"), _codes(trace)
    assert _exit_for(trace) == 2


def test_same_command_2x_not_stuck_default():
    # default window is 3 — only 2 in a row must NOT trip.
    trace = [{"command": "pytest -q", "metric": 1, "accepted": True},
             {"command": "pytest -q", "metric": 2, "accepted": True}]
    assert not _has(trace, "S1", "STUCK"), _codes(trace)


def test_same_command_window_tunable():
    trace = [{"command": "x", "metric": 1, "accepted": True},
             {"command": "x", "metric": 2, "accepted": True}]
    assert _has(trace, "S1", "STUCK", cmd_window=2), _codes(trace, cmd_window=2)


def test_empty_commands_dont_count_as_repeat_s1():
    # missing/empty command is not a "same command" repeat.
    trace = [{"command": "", "metric": i, "accepted": True} for i in range(4)]
    assert not _has(trace, "S1", "STUCK"), _codes(trace)


# --- S2 REPEATED-ERROR ----------------------------------------------------

def test_same_error_2x_stuck_s2():
    trace = [{"command": "a", "error": "AssertionError: boom", "metric": 1, "accepted": True},
             {"command": "b", "error": "AssertionError: boom", "metric": 2, "accepted": True}]
    assert _has(trace, "S2", "STUCK"), _codes(trace)
    assert _exit_for(trace) == 2


def test_distinct_errors_not_stuck_s2():
    trace = [{"command": "a", "error": "err one", "metric": 1, "accepted": True},
             {"command": "b", "error": "err two", "metric": 2, "accepted": True}]
    assert not _has(trace, "S2", "STUCK"), _codes(trace)


def test_empty_errors_dont_count_s2():
    trace = [{"command": "a", "error": "", "metric": 1, "accepted": True},
             {"command": "b", "error": "", "metric": 2, "accepted": True}]
    assert not _has(trace, "S2", "STUCK"), _codes(trace)


# --- S3 NO-PROGRESS -------------------------------------------------------

def test_flat_metric_2x_stuck_s3():
    trace = [{"command": "a", "metric": 5, "accepted": True},
             {"command": "b", "metric": 5, "accepted": True}]
    assert _has(trace, "S3", "STUCK"), _codes(trace)
    assert _exit_for(trace) == 2


def test_moving_metric_not_stuck_s3():
    trace = [{"command": "a", "metric": 5, "accepted": True},
             {"command": "b", "metric": 6, "accepted": True}]
    assert not _has(trace, "S3", "STUCK"), _codes(trace)


def test_missing_metric_is_unknown_not_stall_s3():
    # a None / absent metric in the window is "unknown" — never a stall.
    trace = [{"command": "a", "metric": None, "accepted": True},
             {"command": "b", "metric": None, "accepted": True}]
    assert not _has(trace, "S3", "STUCK"), _codes(trace)
    trace2 = [{"command": "a", "accepted": True}, {"command": "b", "accepted": True}]
    assert not _has(trace2, "S3", "STUCK"), _codes(trace2)


def test_nonnumeric_metric_not_stall_s3():
    # a string metric label is not numeric → treated as unknown, no S3.
    trace = [{"command": "a", "metric": "running", "accepted": True},
             {"command": "b", "metric": "running", "accepted": True}]
    assert not _has(trace, "S3", "STUCK"), _codes(trace)


# --- cost-per-accepted-change ---------------------------------------------

def test_cost_per_accept_value():
    trace = [{"command": "a", "metric": 1, "accepted": True,  "cost": 300},
             {"command": "b", "metric": 2, "accepted": False, "cost": 100}]
    rep = m.monitor(json.dumps(trace), "t.json")
    assert rep.cost_per_accept == 400.0, rep.cost_per_accept  # 400 total / 1 accept


def test_cost_per_accept_falls_back_to_iterations():
    # no cost in the trace → cost-per-accept falls back to iterations-per-accept.
    trace = [{"command": "a", "metric": 1, "accepted": True},
             {"command": "b", "metric": 2, "accepted": False},
             {"command": "c", "metric": 3, "accepted": False}]
    rep = m.monitor(json.dumps(trace), "t.json")
    assert rep.cost_per_accept == 3.0, rep.cost_per_accept  # 3 iters / 1 accept


def test_zero_accepts_warns_and_cost_per_accept_none():
    trace = [{"command": "a", "metric": 1, "cost": 100},
             {"command": "b", "metric": 2, "cost": 100}]
    rep = m.monitor(json.dumps(trace), "t.json")
    assert rep.cost_per_accept is None, rep.cost_per_accept
    assert _has(trace, "ACCEPT", "WARN"), _codes(trace)
    assert _exit_for(trace) == 1  # WARN, no STUCK


def test_cost_per_accept_threshold_warns():
    trace = [{"command": "a", "metric": 1, "accepted": True, "cost": 1000}]
    assert _has(trace, "COST", "WARN", max_cost_per_accept=500), _codes(trace, max_cost_per_accept=500)
    assert not _has(trace, "COST", "WARN", max_cost_per_accept=2000), _codes(trace, max_cost_per_accept=2000)
    assert _exit_for(trace, ["--max-cost-per-accept", "500"]) == 1


# --- input forms / robustness ---------------------------------------------

def test_object_with_iterations_key():
    trace = {"budget": "max_iterations=20", "iterations": HEALTHY}
    rep = m.monitor(json.dumps(trace), "t.json")
    assert rep.n_iters == 4, rep.n_iters
    assert rep.summary["STUCK"] == 0, [(f.code, f.title) for f in rep.findings]


def test_empty_trace_warns():
    rep = m.monitor(json.dumps([]), "t.json")
    assert any(f.code == "EMPTY" for f in rep.findings), [(f.code,) for f in rep.findings]
    assert _exit_for([]) == 1


def test_unparseable_trace_exit_3():
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        fh.write("{not valid json")
        path = fh.name
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = m.main([path])
        assert rc == 3, rc
    finally:
        os.unlink(path)


def test_bad_shape_exit_3():
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        fh.write(json.dumps({"no": "iterations here"}))
        path = fh.name
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = m.main([path])
        assert rc == 3, rc
    finally:
        os.unlink(path)


def test_missing_path_exit_3():
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = m.main(["/nonexistent/trace.json"])
    assert rc == 3, rc


def test_json_output_shape():
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        # a stuck trace so findings + summary are populated.
        fh.write(json.dumps([{"command": "x", "metric": 1, "accepted": True}] * 3))
        path = fh.name
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            m.main([path, "--json"])
        out = json.loads(buf.getvalue())
        assert "summary" in out and "findings" in out, out
        assert out["summary"]["STUCK"] >= 1, out
        assert "cost_per_accept" in out and "total_cost" in out, out
        assert all({"code", "severity", "title"} <= set(f) for f in out["findings"])
    finally:
        os.unlink(path)


# --- runner ---------------------------------------------------------------

def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return failed


if __name__ == "__main__":
    sys.exit(main())
