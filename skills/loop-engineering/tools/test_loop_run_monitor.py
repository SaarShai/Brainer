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
import loop_lint  # noqa: E402

_DEFAULT_RESOLVED = object()


def _resolved_for(trace):
    if isinstance(trace, dict) and trace.get("self_modifying") is True:
        return SELF_MOD_RESOLVED
    return None


def _codes(trace, resolved_spec=_DEFAULT_RESOLVED, **kw):
    if resolved_spec is _DEFAULT_RESOLVED:
        resolved_spec = _resolved_for(trace)
    rep = m.monitor(json.dumps(trace), "trace.json", resolved_spec=resolved_spec, **kw)
    return [(f.code, f.severity) for f in rep.findings]


def _has(trace, code, sev, **kw):
    return (code, sev) in _codes(trace, **kw)


def _exit_for(trace, argv_extra=None, resolved_spec=_DEFAULT_RESOLVED):
    """Run main() against a temp file; return the process exit code."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        fh.write(json.dumps(trace))
        path = fh.name
    resolved_path = None
    if resolved_spec is _DEFAULT_RESOLVED:
        resolved_spec = _resolved_for(trace)
    if resolved_spec is not None:
        with tempfile.NamedTemporaryFile("w", suffix=".resolved.json", delete=False) as fh:
            fh.write(json.dumps(resolved_spec))
            resolved_path = fh.name
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            args = [path] + (argv_extra or [])
            if resolved_path:
                args.extend(["--resolved-spec", resolved_path])
            return m.main(args)
    finally:
        os.unlink(path)
        if resolved_path:
            os.unlink(resolved_path)


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


def test_iteration_index_nonfinite_defaults_without_traceback():
    trace = json.loads(json.dumps(HEALTHY))
    trace[0]["i"] = float("nan")
    trace[1]["i"] = float("inf")
    trace[2]["i"] = float("-inf")
    trace[3]["i"] = 10 ** 400
    parsed = m.parse_trace(json.dumps(trace), "trace.json")
    assert [it.i for it in parsed[:3]] == [0, 1, 2], [it.i for it in parsed]
    assert parsed[3].i == 10 ** 400 and isinstance(parsed[3].i, int)
    assert _codes(trace) == [], _codes(trace)
    assert _exit_for(trace) == 0

    finite = json.loads(json.dumps(HEALTHY))
    finite[0]["i"] = 7.9
    assert m.parse_trace(json.dumps(finite), "trace.json")[0].i == 7


def test_metric_nonfinite_and_huge_integer_are_unknown_without_traceback():
    for value in (float("nan"), float("inf"), float("-inf"), 10 ** 400, -(10 ** 400)):
        trace = json.loads(json.dumps(HEALTHY))
        trace[0]["metric"] = value
        parsed = m.parse_trace(json.dumps(trace), "trace.json")
        assert parsed[0].metric is None, (value, parsed[0].metric)
        assert _codes(trace) == [], (value, _codes(trace))
        assert _exit_for(trace) == 0
    ordinary = json.loads(json.dumps(HEALTHY))
    ordinary[0]["metric"] = 7
    assert m.parse_trace(json.dumps(ordinary), "trace.json")[0].metric == 7.0


def test_cost_nonfinite_and_huge_integer_default_to_zero_without_traceback():
    for value in (float("nan"), float("inf"), float("-inf"), 10 ** 400, -(10 ** 400)):
        trace = json.loads(json.dumps(HEALTHY))
        trace[0]["cost"] = value
        parsed = m.parse_trace(json.dumps(trace), "trace.json")
        assert parsed[0].cost == 0.0, (value, parsed[0].cost)
        rep = m.monitor(json.dumps(trace), "trace.json")
        assert rep.total_cost == 220.0, (value, rep.total_cost)
        assert _exit_for(trace) == 0
    ordinary = json.loads(json.dumps(HEALTHY))
    ordinary[0]["cost"] = 7
    assert m.parse_trace(json.dumps(ordinary), "trace.json")[0].cost == 7.0


# --- S1 SAME-COMMAND ------------------------------------------------------

def test_same_command_3x_stuck_s1():
    trace = [{"command": "pytest -q", "accepted": False} for _ in range(3)]
    assert _has(trace, "S1", "STUCK"), _codes(trace)
    assert _exit_for(trace) == 2


def test_same_command_2x_not_stuck_default():
    # default window is 3 — only 2 in a row must NOT trip.
    trace = [{"command": "pytest -q", "metric": 1, "accepted": True},
             {"command": "pytest -q", "metric": 2, "accepted": True}]
    assert not _has(trace, "S1", "STUCK"), _codes(trace)


def test_same_command_window_tunable():
    trace = [{"command": "x", "accepted": False},
             {"command": "x", "accepted": False}]
    assert _has(trace, "S1", "STUCK", cmd_window=2), _codes(trace, cmd_window=2)


def test_same_command_progress_not_stuck_s1():
    accepted = [{"command": "pytest -q", "accepted": False},
                {"command": "pytest -q", "accepted": False},
                {"command": "pytest -q", "accepted": True}]
    rising = [{"command": "pytest -q", "metric": i, "accepted": False}
              for i in range(3)]
    assert not _has(accepted, "S1", "STUCK"), _codes(accepted)
    assert not _has(rising, "S1", "STUCK"), _codes(rising)


def test_same_command_uses_latest_stuck_window():
    trace = [{"command": "pytest -q", "accepted": True}] + [
        {"command": "pytest -q", "accepted": False} for _ in range(3)
    ]
    assert _has(trace, "S1", "STUCK"), _codes(trace)


def test_empty_commands_dont_count_as_repeat_s1():
    # missing/empty command is not a "same command" repeat.
    trace = [{"command": "", "metric": i, "accepted": True} for i in range(4)]
    assert not _has(trace, "S1", "STUCK"), _codes(trace)


# --- S2 REPEATED-ERROR ----------------------------------------------------

def test_same_error_2x_stuck_s2():
    trace = [{"command": "a", "error": "AssertionError: boom", "accepted": False},
             {"command": "b", "error": "AssertionError: boom", "accepted": False}]
    assert _has(trace, "S2", "STUCK"), _codes(trace)
    assert _exit_for(trace) == 2


def test_same_error_progress_not_stuck_s2():
    accepted = [{"command": "a", "error": "AssertionError: boom", "accepted": False},
                {"command": "b", "error": "AssertionError: boom", "accepted": True}]
    rising = [{"command": "a", "error": "AssertionError: boom", "metric": 1},
              {"command": "b", "error": "AssertionError: boom", "metric": 2}]
    assert not _has(accepted, "S2", "STUCK"), _codes(accepted)
    assert not _has(rising, "S2", "STUCK"), _codes(rising)


def test_same_error_uses_latest_stuck_window():
    trace = [{"command": "a", "error": "boom", "accepted": True},
             {"command": "b", "error": "boom", "accepted": False},
             {"command": "c", "error": "boom", "accepted": False}]
    assert _has(trace, "S2", "STUCK"), _codes(trace)


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
    trace = [{"command": "a", "metric": 5, "accepted": False},
             {"command": "b", "metric": 5, "accepted": False}]
    assert _has(trace, "S3", "STUCK"), _codes(trace)
    assert _exit_for(trace) == 2


def test_flat_metric_with_accepted_change_not_stuck_s3():
    trace = [{"command": "a", "metric": 5, "accepted": False},
             {"command": "b", "metric": 5, "accepted": True}]
    assert not _has(trace, "S3", "STUCK"), _codes(trace)


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


def test_string_booleans_parse_without_truthiness_bug():
    trace = [{"command": "a", "metric": 1, "accepted": "false"},
             {"command": "b", "metric": 2, "accepted": "TRUE"}]
    rep = m.monitor(json.dumps(trace), "t.json")
    assert rep.n_accepted == 1, rep.n_accepted


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


# --- S4 RE-FETCH-LOOP (WARN, pagination-variant) --------------------------

# Same logical command, only the limit grows — distinct raw strings so S1's
# exact-match misses it; each call succeeds so S2/S3 miss it too.
REFETCH = [
    {"command": "grep foo src | head -50"},
    {"command": "grep foo src | head -100"},
    {"command": "grep foo src | head -200"},
]


def test_refetch_variant_loop_warns_s4():
    assert _has(REFETCH, "S4", "WARN"), _codes(REFETCH)
    assert _exit_for(REFETCH) == 1            # WARN, not STUCK
    assert not _has(REFETCH, "S1", "STUCK"), _codes(REFETCH)  # S1 blind (raw differ)


def test_identical_command_is_s1_not_s4():
    # All-identical commands are S1's job; S4 must not double-report.
    trace = [{"command": "pytest -q"} for _ in range(3)]
    assert _has(trace, "S1", "STUCK"), _codes(trace)
    assert not _has(trace, "S4", "WARN"), _codes(trace)


def test_refetch_progress_guard_accepted():
    trace = [dict(REFETCH[0]), dict(REFETCH[1]), {**REFETCH[2], "accepted": True}]
    assert not _has(trace, "S4", "WARN"), _codes(trace)


def test_refetch_uses_latest_stuck_window():
    trace = [
        {"command": "rg foo | head -10", "accepted": True},
        {"command": "rg foo | head -20", "accepted": False},
        {"command": "rg foo | head -30", "accepted": False},
        {"command": "rg foo | head -40", "accepted": False},
    ]
    assert _has(trace, "S4", "WARN"), _codes(trace)


def test_refetch_progress_guard_metric_rising():
    trace = [{**REFETCH[0], "metric": 1}, {**REFETCH[1], "metric": 2}, {**REFETCH[2], "metric": 5}]
    assert not _has(trace, "S4", "WARN"), _codes(trace)


def test_distinct_commands_no_s4():
    assert not _has(HEALTHY, "S4", "WARN"), _codes(HEALTHY)


def test_refetch_under_window_no_s4():
    trace = [{"command": "grep foo | head -50"}, {"command": "grep foo | head -100"}]
    assert not _has(trace, "S4", "WARN"), _codes(trace)


def test_refetch_window_disabled():
    assert not _has(REFETCH, "S4", "WARN", refetch_window=0), _codes(REFETCH, refetch_window=0)


def test_canonical_command_collapses_pagination_only():
    assert m._canonical_command("grep foo | head -50") == m._canonical_command("grep foo | head -100")
    assert m._canonical_command("git log -n 20") == m._canonical_command("git log -n 100")
    # differing in more than pagination must stay distinct (no false collapse)
    assert m._canonical_command("tail -n 50 a.log") != m._canonical_command("tail -n 50 b.log")


def test_canonical_does_not_collapse_distinct_numeric_args():
    # Regression guard: we deliberately did NOT port Headroom's bare-integer
    # collapse, which manufactured phantom loops from distinct commands. These
    # pairs differ in a meaningful number (not pagination) and MUST stay distinct.
    for a, b in [
        ("kill 1234", "kill 5678"),
        ("sleep 1", "sleep 60"),
        ("git checkout HEAD~1", "git checkout HEAD~2"),
        ("docker run -p 8080:80 img", "docker run -p 9090:90 img"),
    ]:
        assert m._canonical_command(a) != m._canonical_command(b), (a, b)


def test_canonical_n_flag_does_not_bite_substring():
    # `-n N` stripping must be boundary-anchored: it must NOT eat the tail of a
    # longer flag like `--foo-n 5` (regression guard for the substring bite).
    assert m._canonical_command("cmd --foo-n 5 x") == "cmd --foo-n 5 x"
    # but a real standalone `-n N` IS pagination and collapses
    assert m._canonical_command("git log -n 5") == m._canonical_command("git log -n 9")


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
        fh.write(json.dumps([{"command": "x", "metric": 1, "accepted": False}] * 3))
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


# --- self-modifying candidate lineage ------------------------------------

SELF_MOD_SPEC = """\
name: monitored-self-modification
topology: closed · outer · single
generator: coding agent
verifier: independent reviewer
gate: python3 run_gate.py
stop: both gates pass
budget: max_iterations=2
self_modifying: true
editable_surfaces: candidate/
locked_surfaces: evaluator/
held_in_gate: gate-id held-in
held_out_gate: gate-id held-out
artifact_binding: sha256 candidate tree
human_approval: owner approves promotion
anchor_files: SKILL.md, evals/
state_store: .brainer/self-improvement/state.sqlite3
recall: read anchor_files and state_store before each pass
writeback: append verified results after each pass
on_error: transient=retry with backoff max 2; recoverable-by-generator=return error as observation; user-fixable=interrupt; unexpected=halt and surface
"""
SELF_MOD_RESOLVED = loop_lint.resolve_snapshot(
    loop_lint.parse_specs(SELF_MOD_SPEC, "self-mod.loop")[0])

SELF_MOD_HEALTHY = {
    "self_modifying": True,
    "spec_hash": SELF_MOD_RESOLVED["spec_hash"],
    "iterations": [
        {
            "i": 0, "command": "edit candidate", "metric": 1, "accepted": False,
            "candidate_id": "candidate-001", "artifact_hash": "sha256:aaa",
            "evaluator_revision": "eval-v3", "diff_size": 12,
            "trace_refs": ["traces/candidate-001.json"],
        },
        {
            "i": 1, "command": "run held gates", "metric": 2, "accepted": True,
            "candidate_id": "candidate-002", "artifact_hash": "sha256:bbb",
            "evaluator_revision": "eval-v3", "diff_size": 4,
            "trace_refs": ["traces/candidate-002.json", "traces/held-out.json"],
        },
    ],
}


def test_self_modifying_complete_lineage_is_healthy():
    assert _codes(SELF_MOD_HEALTHY) == [], _codes(SELF_MOD_HEALTHY)
    assert _exit_for(SELF_MOD_HEALTHY) == 0


def test_self_modifying_requires_resolved_snapshot_and_trace_hash():
    assert _has(SELF_MOD_HEALTHY, "PROVENANCE", "STUCK", resolved_spec=None)
    assert _exit_for(SELF_MOD_HEALTHY, resolved_spec=None) == 2

    trace = json.loads(json.dumps(SELF_MOD_HEALTHY))
    del trace["spec_hash"]
    assert _has(trace, "PROVENANCE", "STUCK")
    assert _exit_for(trace) == 2


def test_resolved_self_modifying_spec_rejects_trace_downgrade():
    base_iteration = {
        "command": "edit candidate", "metric": 1, "accepted": True,
    }
    downgraded = (
        [base_iteration],
        {"spec_hash": SELF_MOD_RESOLVED["spec_hash"], "iterations": [base_iteration]},
        {
            "self_modifying": False,
            "spec_hash": SELF_MOD_RESOLVED["spec_hash"],
            "iterations": [base_iteration],
        },
        {"self_modifying": False, "spec_hash": 7, "iterations": [base_iteration]},
    )
    for trace in downgraded:
        codes = _codes(trace, resolved_spec=SELF_MOD_RESOLVED)
        assert ("PROVENANCE", "STUCK") in codes, (trace, codes)
        assert _exit_for(trace, resolved_spec=SELF_MOD_RESOLVED) == 2, trace


def test_ordinary_resolved_spec_preserves_ordinary_trace_behavior():
    ordinary = loop_lint.resolve_snapshot(
        loop_lint.parse_specs(SELF_MOD_SPEC.replace("self_modifying: true",
                                                   "self_modifying: false"),
                              "ordinary.loop")[0])
    assert _codes(HEALTHY, resolved_spec=ordinary) == []
    assert _exit_for(HEALTHY, resolved_spec=ordinary) == 0


def test_supplied_resolved_spec_is_validated_before_trace_activation():
    assert _has(HEALTHY, "PROVENANCE", "STUCK", resolved_spec={})
    assert _exit_for(HEALTHY, resolved_spec={}) == 3


def test_self_modifying_rejects_mismatched_spec_hash():
    trace = json.loads(json.dumps(SELF_MOD_HEALTHY))
    trace["spec_hash"] = "sha256:" + "0" * 64
    assert _has(trace, "PROVENANCE", "STUCK")
    assert _exit_for(trace) == 2


def test_self_modifying_rejects_malformed_trace_hash():
    for invalid in ("", "SHA256:" + "0" * 64, "sha256:xyz", True, 7, {}, []):
        trace = json.loads(json.dumps(SELF_MOD_HEALTHY))
        trace["spec_hash"] = invalid
        assert _has(trace, "PROVENANCE", "STUCK"), invalid
        assert _exit_for(trace) == 2


def test_self_modifying_rejects_tampered_or_malformed_resolved_snapshot():
    tampered = json.loads(json.dumps(SELF_MOD_RESOLVED))
    tampered["fields"]["budget"] = "max_iterations=999"
    assert _has(SELF_MOD_HEALTHY, "PROVENANCE", "STUCK", resolved_spec=tampered)
    assert _exit_for(SELF_MOD_HEALTHY, resolved_spec=tampered) == 3

    for malformed in ([], [SELF_MOD_RESOLVED], {},
                      {**SELF_MOD_RESOLVED, "schema_version": 2}):
        assert _has(SELF_MOD_HEALTHY, "PROVENANCE", "STUCK", resolved_spec=malformed)
        assert _exit_for(SELF_MOD_HEALTHY, resolved_spec=malformed) == 3


def test_resolved_spec_rejects_nonclean_lint_verdicts():
    for severity, verdict in (("WARN", "warn"), ("FAIL", "fail")):
        snapshot = json.loads(json.dumps(SELF_MOD_RESOLVED))
        snapshot["lint"] = {
            "verdict": verdict,
            "summary": {
                "WARN": int(severity == "WARN"),
                "FAIL": int(severity == "FAIL"),
            },
            "findings": [{"severity": severity}],
        }
        snapshot["spec_hash"] = m.resolved_spec_hash(snapshot)
        assert _has(SELF_MOD_HEALTHY, "PROVENANCE", "STUCK",
                    resolved_spec=snapshot), verdict
        assert _exit_for(SELF_MOD_HEALTHY, resolved_spec=snapshot) == 3, verdict


def test_resolved_spec_rejects_verdict_summary_inconsistency():
    snapshot = json.loads(json.dumps(SELF_MOD_RESOLVED))
    snapshot["lint"]["summary"]["FAIL"] = 1
    snapshot["lint"]["findings"] = [{"severity": "FAIL"}]
    snapshot["spec_hash"] = m.resolved_spec_hash(snapshot)
    assert _exit_for(SELF_MOD_HEALTHY, resolved_spec=snapshot) == 3


def test_resolved_spec_rejects_findings_summary_inconsistency():
    snapshot = json.loads(json.dumps(SELF_MOD_RESOLVED))
    snapshot["lint"]["findings"] = [{"severity": "WARN"}]
    snapshot["spec_hash"] = m.resolved_spec_hash(snapshot)
    assert _exit_for(SELF_MOD_HEALTHY, resolved_spec=snapshot) == 3


def test_self_modifying_cannot_bind_to_ordinary_resolved_spec():
    ordinary = loop_lint.resolve_snapshot(
        loop_lint.parse_specs(SELF_MOD_SPEC.replace("self_modifying: true",
                                                    "self_modifying: false"),
                              "ordinary.loop")[0])
    trace = json.loads(json.dumps(SELF_MOD_HEALTHY))
    trace["spec_hash"] = ordinary["spec_hash"]
    assert _has(trace, "PROVENANCE", "STUCK", resolved_spec=ordinary)
    assert _exit_for(trace, resolved_spec=ordinary) == 2


def test_self_modifying_missing_lineage_stuck_per_field():
    """Known-bad proof: a candidate score floating free of artifact lineage must
    stop the self-modifying loop, with deterministic field-level findings."""
    trace = {"self_modifying": True, "iterations": [
        {"command": "edit candidate", "metric": 1, "accepted": True}
    ]}
    codes = _codes(trace)
    assert codes.count(("LINEAGE", "STUCK")) == 5, codes
    assert _exit_for(trace) == 2


def test_self_modifying_accepted_empty_diff_is_stuck():
    trace = json.loads(json.dumps(SELF_MOD_HEALTHY))
    trace["iterations"][1]["diff_size"] = 0
    assert _has(trace, "NOOP", "STUCK"), _codes(trace)
    assert _exit_for(trace) == 2


def test_self_modifying_empty_trace_refs_is_missing_lineage():
    trace = json.loads(json.dumps(SELF_MOD_HEALTHY))
    trace["iterations"][0]["trace_refs"] = []
    assert _has(trace, "LINEAGE", "STUCK"), _codes(trace)


def test_self_modifying_nonfinite_diff_size_is_missing_lineage():
    for value in (float("nan"), float("inf"), float("-inf")):
        trace = json.loads(json.dumps(SELF_MOD_HEALTHY))
        trace["iterations"][0]["diff_size"] = value
        assert _has(trace, "LINEAGE", "STUCK"), (value, _codes(trace))


def test_self_modifying_numeric_string_diff_size_remains_missing_lineage():
    """Existing parser behavior: numeric strings are not JSON numbers."""
    trace = json.loads(json.dumps(SELF_MOD_HEALTHY))
    trace["iterations"][0]["diff_size"] = "12"
    assert _has(trace, "LINEAGE", "STUCK"), _codes(trace)


def test_self_modifying_huge_integer_diff_size_is_exact_and_controlled():
    huge = 10 ** 400
    positive = json.loads(json.dumps(SELF_MOD_HEALTHY))
    positive["iterations"][1]["diff_size"] = huge
    assert _codes(positive) == [], _codes(positive)
    assert _exit_for(positive) == 0
    parsed = m.parse_trace(json.dumps(positive), "trace.json")
    assert parsed[1].diff_size == huge and isinstance(parsed[1].diff_size, int)

    negative = json.loads(json.dumps(SELF_MOD_HEALTHY))
    negative["iterations"][1]["diff_size"] = -huge
    assert _has(negative, "NOOP", "STUCK"), _codes(negative)
    assert not _has(negative, "LINEAGE", "STUCK"), _codes(negative)
    assert _exit_for(negative) == 2


def test_self_modifying_identity_fields_reject_nonstring_coercions():
    for field in ("candidate_id", "artifact_hash", "evaluator_revision"):
        for invalid in (True, False, 7, {}, [], "   "):
            trace = json.loads(json.dumps(SELF_MOD_HEALTHY))
            trace["iterations"][0][field] = invalid
            assert _has(trace, "LINEAGE", "STUCK"), (field, invalid, _codes(trace))


def test_self_modifying_trace_refs_are_strict_strings():
    for invalid in (True, 7, {}, [], [""], ["ok", ""], ["ok", {}], [7]):
        trace = json.loads(json.dumps(SELF_MOD_HEALTHY))
        trace["iterations"][0]["trace_refs"] = invalid
        assert _has(trace, "LINEAGE", "STUCK"), (invalid, _codes(trace))
    for valid in ("trace.json", ["trace.json"], ["a.json", " b.json "]):
        trace = json.loads(json.dumps(SELF_MOD_HEALTHY))
        trace["iterations"][0]["trace_refs"] = valid
        assert not _has(trace, "LINEAGE", "STUCK"), (valid, _codes(trace))


def test_self_modifying_activation_requires_json_boolean():
    for invalid in ("true", "false", 1, 0, None, {}, []):
        trace = {"self_modifying": invalid, "iterations": HEALTHY}
        assert _has(trace, "ACTIVATION", "STUCK"), (invalid, _codes(trace))
        assert _exit_for(trace) == 2
        assert len(m.parse_trace(json.dumps(trace), "trace.json")) == len(HEALTHY)
    assert _codes({"self_modifying": False, "iterations": HEALTHY}) == []
    assert _codes(SELF_MOD_HEALTHY) == []


def test_malformed_activation_empty_trace_is_stuck_not_only_empty_warn():
    trace = {"self_modifying": "true", "iterations": []}
    assert _has(trace, "ACTIVATION", "STUCK"), _codes(trace)
    assert _exit_for(trace) == 2


def test_ordinary_trace_does_not_require_candidate_lineage():
    assert _codes(HEALTHY) == [], _codes(HEALTHY)
    wrapped = {"self_modifying": False, "iterations": HEALTHY}
    assert _codes(wrapped) == [], _codes(wrapped)
    # Even a stray malformed hash remains ignored unless self-modification is on.
    wrapped["spec_hash"] = 7
    assert _codes(wrapped) == [], _codes(wrapped)
    assert _exit_for(wrapped, resolved_spec=None) == 0


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
