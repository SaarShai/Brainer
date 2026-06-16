#!/usr/bin/env python3
"""Tests for loop_lint.py — plain-python (no pytest dep), runnable standalone.

Shape mirrors skills/cache-lint/tools/test_cache_lint.py: a list of test_*
functions, a main() that runs them and returns the failure count (exit 0 ==
all pass), registered in scripts/run_all_tests.sh.

The FAIL-rule tests (R1/R2/R3) are the falsifiable core: a self-grading or
gateless spec the linter PASSES, or a clean spec it FAILs, is a measurable bug.
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import loop_lint  # noqa: E402

CLEAN = """\
name: refactor-loop
topology: closed · inner · single
generator: opus coder agent
verifier: sonnet read-only reviewer
gate: pytest tests/ -q
stop: all target tests green
budget: max_iterations=20
"""


def _rules(text, source="spec.yaml", rule=None):
    rep = loop_lint.lint(text, source, rule_filter=rule)
    return [(f.rule, f.severity) for f in rep.findings]


def _has(text, rule, sev, **kw):
    return (rule, sev) in _rules(text, **kw)


def _exit_for(text, suffix=".yaml"):
    """Run main() against a temp file; return the process exit code."""
    with tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False) as fh:
        fh.write(text)
        path = fh.name
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            return loop_lint.main([path])
    finally:
        os.unlink(path)


# --- R1 NO-GATE -----------------------------------------------------------

def test_clean_spec_passes():
    assert _rules(CLEAN) == [], _rules(CLEAN)
    assert _exit_for(CLEAN) == 0


def test_gateless_spec_r1_fail():
    spec = CLEAN.replace("gate: pytest tests/ -q\n", "")
    assert _has(spec, 1, "FAIL"), _rules(spec)
    assert _exit_for(spec) == 2


def test_prose_gate_looks_correct_r1_fail():
    spec = CLEAN.replace("gate: pytest tests/ -q", "gate: looks correct")
    assert _has(spec, 1, "FAIL"), _rules(spec)


def test_prose_gate_reviewer_agrees_r1_fail():
    # The allowlist (not a denylist) must catch a gate with no machine token,
    # even one that dodges obvious prose words.
    spec = CLEAN.replace("gate: pytest tests/ -q", "gate: the reviewer agrees it is good")
    assert _has(spec, 1, "FAIL"), _rules(spec)


def test_command_gate_passes():
    for g in ["pytest -q", "./check.sh", "make test", "node run.mjs",
              "exit code 0", "diff golden.txt out.txt", "cargo test"]:
        spec = CLEAN.replace("gate: pytest tests/ -q", f"gate: {g}")
        assert not _has(spec, 1, "FAIL"), (g, _rules(spec))


def test_human_approval_gate_passes_r1():
    # A human-in-the-loop approval IS a concrete gate (article: "handoff to a
    # human with the run data attached"); both source harnesses use it. Must NOT
    # be treated as gateless. (Regression: PROMPTER live-test false positive.)
    for g in ["Saar approves the brief in the dashboard", "owner sign-off required",
              "escalate to FOR-REVIEW.md and a human approves", "human review + approval"]:
        spec = CLEAN.replace("gate: pytest tests/ -q", f"gate: {g}")
        spec = spec.replace("verifier: sonnet read-only reviewer", "verifier: Saar (human)")
        assert not _has(spec, 1, "FAIL"), (g, _rules(spec))


def test_human_word_without_approval_still_fails_r1():
    # "the reviewer agrees" / "looks correct" have no approval verb → still FAIL.
    for g in ["the reviewer agrees it is good", "looks correct to the team"]:
        spec = CLEAN.replace("gate: pytest tests/ -q", f"gate: {g}")
        assert _has(spec, 1, "FAIL"), (g, _rules(spec))


# --- R2 NO-STOP-OR-BUDGET -------------------------------------------------

def test_no_budget_r2_fail():
    spec = CLEAN.replace("budget: max_iterations=20\n", "")
    assert _has(spec, 2, "FAIL"), _rules(spec)
    assert _exit_for(spec) == 2


def test_no_stop_r2_fail():
    spec = CLEAN.replace("stop: all target tests green\n", "")
    assert _has(spec, 2, "FAIL"), _rules(spec)


def test_unbounded_budget_r2_fail():
    spec = CLEAN.replace("budget: max_iterations=20", "budget: unbounded")
    assert _has(spec, 2, "FAIL"), _rules(spec)


def test_budget_without_number_r2_fail():
    spec = CLEAN.replace("budget: max_iterations=20", "budget: max_iterations")
    assert _has(spec, 2, "FAIL"), _rules(spec)


# --- R3 SELF-GRADING ------------------------------------------------------

def test_self_grading_r3_fail():
    # Same actor, differing case/whitespace/punctuation → still self-grading.
    spec = CLEAN.replace("verifier: sonnet read-only reviewer", "verifier:  Opus Coder Agent.")
    spec = spec.replace("generator: opus coder agent", "generator: opus coder agent")
    assert _has(spec, 3, "FAIL"), _rules(spec)
    assert _exit_for(spec) == 2


def test_empty_verifier_closed_r3_fail():
    spec = CLEAN.replace("verifier: sonnet read-only reviewer", "verifier:")
    assert _has(spec, 3, "FAIL"), _rules(spec)


def test_distinct_actors_no_r3():
    assert not _has(CLEAN, 3, "FAIL"), _rules(CLEAN)


def test_same_actor_different_verb_r3_fail():
    # Same specific actor, different role verb → still self-grading. (Regression:
    # PROMPTER live-test false negative — "Alfred drafts" / "Alfred reviews".)
    spec = (CLEAN.replace("generator: opus coder agent", "generator: Alfred drafts the briefing")
            .replace("verifier: sonnet read-only reviewer", "verifier: Alfred reviews the briefing"))
    assert _has(spec, 3, "FAIL"), _rules(spec)


def test_generic_human_both_sides_no_false_r3():
    # "a human" on both sides is not a *specific* shared actor → must NOT fire
    # (avoids over-failing legitimately-staffed-by-two-people loops).
    spec = (CLEAN.replace("generator: opus coder agent", "generator: a human writes it")
            .replace("verifier: sonnet read-only reviewer", "verifier: a human checks it"))
    assert not _has(spec, 3, "FAIL"), _rules(spec)


# --- PROMPTER live-test regressions (round 2) -----------------------------

def test_agent_judge_gate_r1_fail():
    # B1: an AUTONOMOUS agent "approving" by feel is the LLM-judge hole — must
    # FAIL R1. The human-gate path must require a human, not just an approve verb.
    for g in ["the reviewer agent approves the draft", "the billing agent escalates when it feels right",
              "the model signs off when it looks correct"]:
        spec = CLEAN.replace("gate: pytest tests/ -q", f"gate: {g}")
        assert _has(spec, 1, "FAIL"), (g, _rules(spec))


def test_human_decision_verbs_pass_r1():
    # B5: human decision verbs beyond "approve" (select/pick/decide) are a valid
    # human gate — must NOT FAIL R1.
    for g in ["Saar selects the 3 best angles", "the owner picks one option",
              "the user decides which draft ships"]:
        spec = CLEAN.replace("gate: pytest tests/ -q", f"gate: {g}")
        spec = spec.replace("verifier: sonnet read-only reviewer", "verifier: Saar (human)")
        assert not _has(spec, 1, "FAIL"), (g, _rules(spec))


def test_subjective_eq_gate_r1_fail():
    # B4: a bare '==' between two prose words must NOT pass R1.
    spec = CLEAN.replace("gate: pytest tests/ -q", "gate: the tone == the CEO's voice and it reads well")
    assert _has(spec, 1, "FAIL"), _rules(spec)


def test_codelike_eq_gate_passes_r1():
    # control: a real assertion against a code-like operand still passes.
    for g in ["ok_to_continue == true", "exit_code == 0", "preflight.status == pass"]:
        spec = CLEAN.replace("gate: pytest tests/ -q", f"gate: {g}")
        assert not _has(spec, 1, "FAIL"), (g, _rules(spec))


def test_dotpy_midprose_gate_r1_fail():
    # B4: a '.py' name-dropped mid-sentence (no runner, no ./) must NOT pass R1.
    spec = CLEAN.replace("gate: pytest tests/ -q",
                         "gate: the report covers everything in project.py terms and feels complete")
    assert _has(spec, 1, "FAIL"), _rules(spec)


def test_same_actor_asymmetric_tail_r3_fail():
    # B2: same actor with an asymmetric descriptive tail still self-grades.
    spec = (CLEAN.replace("generator: opus coder agent", "generator: Alfred drafts the weekly board briefing")
            .replace("verifier: sonnet read-only reviewer",
                     "verifier: Alfred reviews the weekly board briefing for accuracy"))
    assert _has(spec, 3, "FAIL"), _rules(spec)


def test_shared_common_noun_no_false_r3():
    # B2 guard: distinct models sharing a common noun ("brief") are NOT self-grading.
    spec = (CLEAN.replace("generator: opus coder agent", "generator: opus brief writer")
            .replace("verifier: sonnet read-only reviewer", "verifier: sonnet brief reader"))
    assert not _has(spec, 3, "FAIL"), _rules(spec)


def test_same_model_both_sides_r3_fail():
    # reusing the SAME model for generator and verifier with nothing else
    # distinguishing them is self-grading (use a separate/cheaper verifier).
    spec = (CLEAN.replace("generator: opus coder agent", "generator: opus drafts the plan")
            .replace("verifier: sonnet read-only reviewer", "verifier: opus reviews the plan"))
    assert _has(spec, 3, "FAIL"), _rules(spec)


def test_prose_budget_with_stray_digit_r2_fail():
    # B3: a prose budget that merely contains a digit ("0 unread") is unbounded.
    for b in ["run until inbox has 0 unread", "stop when done after a while", "until it feels complete"]:
        spec = CLEAN.replace("budget: max_iterations=20", f"budget: {b}")
        assert _has(spec, 2, "FAIL"), (b, _rules(spec))


def test_real_budget_units_pass_r2():
    # control: real caps bound to a unit pass R2.
    for b in ["max_iterations=20", "max_tokens: 100000", "20 turns", "30m wallclock", "5 rounds"]:
        spec = CLEAN.replace("budget: max_iterations=20", f"budget: {b}")
        assert not _has(spec, 2, "FAIL"), (b, _rules(spec))


# --- R4 OPEN-NO-ACK -------------------------------------------------------

def test_open_loop_without_ack_warns():
    spec = CLEAN.replace("topology: closed · inner · single", "topology: open · outer · single")
    assert _has(spec, 4, "WARN"), _rules(spec)
    assert _exit_for(spec) == 1  # WARN, no FAIL


def test_open_loop_with_ack_ok():
    spec = (CLEAN.replace("topology: closed · inner · single", "topology: open · outer · single")
            + "accepted_open_loop: true\n")
    assert not _has(spec, 4, "WARN"), _rules(spec)


# --- R5 FLEET-NO-QUORUM ---------------------------------------------------

def test_fleet_without_quorum_warns():
    # "reviewer" in the verifier role IS a valid aggregation token (Fig-6 fleet
    # pattern), so strip it: a fleet with a plain checker and no quorum warns.
    spec = (CLEAN.replace("topology: closed · inner · single", "topology: closed · outer · fleet")
            .replace("verifier: sonnet read-only reviewer", "verifier: sonnet static checker"))
    assert _has(spec, 5, "WARN"), _rules(spec)


def test_fleet_with_quorum_ok():
    spec = (CLEAN.replace("topology: closed · inner · single", "topology: closed · outer · fleet")
            .replace("gate: pytest tests/ -q", "gate: pytest -q then reviewer quorum >=2/3"))
    assert not _has(spec, 5, "WARN"), _rules(spec)


# --- R6 NO-TOPOLOGY -------------------------------------------------------

def test_missing_topology_warns():
    spec = CLEAN.replace("topology: closed · inner · single\n", "")
    assert _has(spec, 6, "WARN"), _rules(spec)


# --- input forms ----------------------------------------------------------

def test_fenced_loop_block_in_markdown():
    md = "# Plan\n\nsome prose\n\n```loop\n" + CLEAN + "```\n\nmore prose\n"
    rep = loop_lint.lint(md, "PLAN.md")
    assert rep.n_specs == 1, rep.n_specs
    assert rep.summary["FAIL"] == 0, [(f.rule, f.title) for f in rep.findings]


def test_gateless_fenced_block_points_into_markdown():
    bad = CLEAN.replace("gate: pytest tests/ -q\n", "")
    md = "# Plan\n\n\n\n```loop\n" + bad + "```\n"
    rep = loop_lint.lint(md, "PLAN.md")
    r1 = [f for f in rep.findings if f.rule == 1]
    assert r1, [(f.rule, f.title) for f in rep.findings]
    assert r1[0].line >= 5, r1[0].line  # line points inside the fenced block


def test_multiple_specs_one_file():
    bad = CLEAN.replace("gate: pytest tests/ -q\n", "").replace("name: refactor-loop", "name: bad-one")
    md = "```loop\n" + CLEAN + "```\n\n```loop\n" + bad + "```\n"
    rep = loop_lint.lint(md, "PLAN.md")
    assert rep.n_specs == 2, rep.n_specs
    r1 = [f for f in rep.findings if f.rule == 1 and f.severity == "FAIL"]
    assert len(r1) == 1, [(f.rule, f.title) for f in rep.findings]


def test_json_spec():
    spec = {"name": "j", "topology": "closed inner single", "generator": "a",
            "verifier": "b", "gate": "pytest -q", "stop": "green", "budget": "max_iterations=10"}
    rep = loop_lint.lint(json.dumps(spec), "spec.json")
    assert rep.summary["FAIL"] == 0, [(f.rule, f.title) for f in rep.findings]


def test_unparseable_json_exit_3():
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        fh.write("{not valid json")
        path = fh.name
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = loop_lint.main([path])
        assert rc == 3, rc
    finally:
        os.unlink(path)


def test_no_spec_found_warns():
    rep = loop_lint.lint("# just a doc\n\nno loop here\n", "README.md")
    assert rep.summary["FAIL"] == 0
    assert any(f.rule == 0 for f in rep.findings), [(f.rule, f.title) for f in rep.findings]


def test_json_output_shape():
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        fh.write(CLEAN.replace("gate: pytest tests/ -q\n", ""))
        path = fh.name
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            loop_lint.main([path, "--json"])
        out = json.loads(buf.getvalue())
        assert "summary" in out and "findings" in out, out
        assert out["summary"]["FAIL"] >= 1, out
        assert all({"rule", "severity", "title"} <= set(f) for f in out["findings"])
    finally:
        os.unlink(path)


def test_missing_path_exit_3():
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = loop_lint.main(["/nonexistent/path/spec.yaml"])
    assert rc == 3, rc


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
