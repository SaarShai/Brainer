#!/usr/bin/env python3
"""Offline tests for score --panel."""
from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHARED = HERE.parents[1] / "_shared"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SHARED))

import eval_gate  # type: ignore
import model_roster  # type: ignore


def _backends():
    return [
        model_roster.Backend("GPT test", model_roster.LANE_GPT, "cli", "true", True, "test"),
        model_roster.Backend("Gemini test", model_roster.LANE_GEMINI, "cli", "true", True, "test"),
        model_roster.Backend("Claude test", model_roster.LANE_CLAUDE, "cli", "true", True, "test"),
    ]


@contextlib.contextmanager
def patched_roster(script):
    original_detect = model_roster.detect_roster
    original_run_dispatch = model_roster.run_dispatch
    eval_gate._MODEL_ROSTER = model_roster
    calls = []

    def fake_detect_roster(*args, **kwargs):
        return _backends()

    def fake_run_dispatch(member, role, task, brief, **kwargs):
        calls.append({"member": member.vendor, "role": role, "task": task, "brief": brief})
        verdict = script.pop(0)
        if verdict == "drop":
            return {"vendor": member.vendor, "lane": member.lane, "ok": False, "error": "scripted drop"}
        if verdict == "raw_true":
            return {"vendor": member.vendor, "lane": member.lane, "ok": True,
                    "raw": "holds: true\nevidence: scripted\nFINDINGS: ok"}
        if verdict == "raw_false":
            return {"vendor": member.vendor, "lane": member.lane, "ok": True,
                    "raw": "holds: false\nevidence: scripted\nFINDINGS: refuted"}
        return {"vendor": member.vendor, "lane": member.lane, "ok": True,
                "holds": bool(verdict), "findings": f"scripted holds={bool(verdict)}"}

    model_roster.detect_roster = fake_detect_roster
    model_roster.run_dispatch = fake_run_dispatch
    try:
        yield calls
    finally:
        model_roster.detect_roster = original_detect
        model_roster.run_dispatch = original_run_dispatch
        eval_gate._MODEL_ROSTER = None


def run_cli(argv):
    old_argv = sys.argv
    out = io.StringIO()
    err = io.StringIO()
    sys.argv = ["eval_gate.py", *argv]
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                rc = eval_gate.main()
            except SystemExit as e:
                rc = int(e.code)
    finally:
        sys.argv = old_argv
    return rc, out.getvalue(), err.getvalue()


def score_args(*extra):
    return ["score", "--text", "candidate output", "--rubric-text", "rubric", *extra]


def assert_json_score(out, verdict):
    data = json.loads(out)
    assert data["verdict"] == verdict, data
    return data


def test_majority_holds_passes():
    with patched_roster([True, "raw_true", False]) as calls:
        rc, out, err = run_cli(score_args("--stub-score", "5", "--panel", "3"))
    assert rc == 0, (rc, out, err)
    assert_json_score(out, "pass")
    assert err == "", err
    assert len(calls) == 3, calls
    assert all(c["role"] == "verifier" for c in calls), calls
    assert calls[0]["task"].startswith("This output meets the rubric at >= 0.7:"), calls[0]
    assert "RUBRIC:\nrubric" in calls[0]["brief"], calls[0]
    assert "SCORED OUTPUT:\ncandidate output" in calls[0]["brief"], calls[0]


def test_majority_refutes_fails():
    with patched_roster([False, "raw_false", True]):
        rc, out, err = run_cli(score_args("--stub-score", "5", "--panel", "3"))
    assert rc == 1, (rc, out, err)
    assert_json_score(out, "pass")
    assert "eval-gate panel verdicts:" in err, err
    assert "holds=false" in err, err


def test_degraded_fallback_warns_and_uses_single_exit():
    with patched_roster([True, "drop", "drop"]):
        rc, out, err = run_cli(score_args("--stub-score", "5", "--panel", "3"))
    assert rc == 0, (rc, out, err)
    assert_json_score(out, "pass")
    assert "panel degraded to single-judge (only 1 members reachable, need 3)" in err, err


def test_two_responders_is_not_a_quorum():
    # 2/2 "majority" is a fabricated quorum — must degrade to single-judge,
    # never return a panel verdict (cross-vendor review 2026-07-05).
    with patched_roster([True, True, "drop"]):
        rc, out, err = run_cli(score_args("--stub-score", "5", "--panel", "3"))
    assert rc == 0, (rc, out, err)
    assert "panel degraded to single-judge (only 2 members reachable, need 3)" in err, err
    assert "panel verdicts" not in err, err


def test_panel_argparse_rejects_bad_counts():
    for bad in ("2", "1", "-3"):
        rc, out, err = run_cli(score_args("--stub-score", "5", "--panel", bad))
        assert rc == 2, (bad, rc, out, err)
        assert out == "", (bad, out)
        assert "--panel must be an odd integer >= 3" in err, (bad, err)


def main():
    tests = [
        test_majority_holds_passes,
        test_majority_refutes_fails,
        test_degraded_fallback_warns_and_uses_single_exit,
        test_panel_argparse_rejects_bad_counts,
    ]
    for test in tests:
        test()
        print(f"ok: {test.__name__}")
    print("ALL PASS")


if __name__ == "__main__":
    main()
