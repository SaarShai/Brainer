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


def _rules(text, source="spec.yaml", rule=None, strict_memory=False):
    rep = loop_lint.lint(text, source, rule_filter=rule, strict_memory=strict_memory)
    return [(f.rule, f.severity) for f in rep.findings]


def _has(text, rule, sev, **kw):
    return (rule, sev) in _rules(text, **kw)


def _exit_for(text, suffix=".yaml", args=None):
    """Run main() against a temp file; return the process exit code."""
    with tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False) as fh:
        fh.write(text)
        path = fh.name
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            return loop_lint.main([*(args or []), path])
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
              "exit code 0", "diff golden.txt out.txt", "cargo test",
              # common test runners beyond the core set (combined-stack regression:
              # a real 'newman run postman/collection.json' must not FAIL R1)
              "newman run postman/collection.json", "playwright test e2e/", "k6 run load.js"]:
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


# --- sibling name-drops + degenerate budget (round 3) ---------------------

def test_sibling_namedrop_gates_r1_fail():
    # The vacuous-prose class is bigger than == / .py: a 'status N' / 'returns N'
    # rating, or a 'diff' used as an English noun, must NOT pass R1 either.
    for g in ["the reviewer rates a status 8 quality and it reads correct",
              "the partner returns 1 thumbs-up in the dashboard",
              "the diff between the draft and the brief is acceptable"]:
        spec = CLEAN.replace("gate: pytest tests/ -q", f"gate: {g}")
        assert _has(spec, 1, "FAIL"), (g, _rules(spec))


def test_legit_exitcode_and_diff_gates_pass_r1():
    # control: real exit-code / diff / grep gates (no subjective prose, real
    # operands) must still pass — the tightening must not over-fire.
    for g in ["exit status 0", "script returns 0", "diff golden.txt out.txt",
              "grep -c TODO src.py"]:
        spec = CLEAN.replace("gate: pytest tests/ -q", f"gate: {g}")
        assert not _has(spec, 1, "FAIL"), (g, _rules(spec))


def test_zero_budget_warns_r2():
    # A cap of 0 is parseable but degenerate (the loop body never runs): WARN, not
    # FAIL, and not a clean pass.
    for b in ["max_iterations=0", "0 iterations", "max_tokens: 0"]:
        spec = CLEAN.replace("budget: max_iterations=20", f"budget: {b}")
        assert _has(spec, 2, "WARN"), (b, _rules(spec))
        assert not _has(spec, 2, "FAIL"), (b, _rules(spec))
    spec = CLEAN.replace("budget: max_iterations=20", "budget: max_iterations=0")
    assert _exit_for(spec) == 1, _rules(spec)  # WARN, no FAIL


# --- composition R3 false-positives (cross-skill / combined-stack) --------

def test_different_models_sharing_domain_words_no_r3():
    # Combined-stack regression: a loop built on wiki-refresh vocabulary —
    # opus generator + sonnet verifier both naming Keep/Update/Replace — is NOT
    # self-grading. A model-slug mismatch overrides the shared capitalized words.
    spec = (CLEAN
            .replace("generator: opus coder agent",
                     "generator: opus refresh agent applies Keep/Update/Consolidate/Replace/Delete")
            .replace("verifier: sonnet read-only reviewer",
                     "verifier: sonnet reconcile agent recomputes Keep/Update/Replace"))
    assert not _has(spec, 3, "FAIL"), _rules(spec)


def test_shared_qualifier_distinct_actors_no_r3():
    # Two distinct actors sharing a Capitalized QUALIFIER (not an acting name) are
    # not self-grading: "Payments service team" vs "Payments platform auditor",
    # "Senior Marketing Writer" vs "Senior Editorial Reviewer".
    spec = (CLEAN.replace("generator: opus coder agent", "generator: the Payments service team implements it")
            .replace("verifier: sonnet read-only reviewer", "verifier: the Payments platform auditor validates it"))
    assert not _has(spec, 3, "FAIL"), _rules(spec)
    spec2 = (CLEAN.replace("generator: opus coder agent", "generator: Senior Marketing Writer drafts the copy")
             .replace("verifier: sonnet read-only reviewer", "verifier: Senior Editorial Reviewer checks the copy"))
    assert not _has(spec2, 3, "FAIL"), _rules(spec2)


# --- round-4 adversarial regressions --------------------------------------

def _gen_ver(g, v):
    return (CLEAN.replace("generator: opus coder agent", f"generator: {g}")
            .replace("verifier: sonnet read-only reviewer", f"verifier: {v}"))


def test_same_name_nonadjacent_verb_r3_fail():
    # B1: the same person self-grades even when an appositive comma, a conjunction,
    # a parenthetical, or a possession/authority verb sits between name and action.
    cases = [
        ("Alfred, our lead, drafts the section", "Alfred, our lead, reviews the section"),
        ("Alfred owns the draft", "Alfred owns the review"),
        ("Alfred and a peer write the draft", "Alfred and a peer check the draft"),
        ("Alfred maintains the document", "Alfred signs the document"),
        ("Alfred (opus) drafts the migration", "Alfred (sonnet) reviews the migration"),
    ]
    for g, v in cases:
        assert _has(_gen_ver(g, v), 3, "FAIL"), (g, v, _rules(_gen_ver(g, v)))


def test_distinct_named_actors_no_r3():
    # control: two different people are not self-grading.
    assert not _has(_gen_ver("Alfred drafts the section", "Beatrice reviews the section"), 3, "FAIL")


def test_distributive_subbudget_r2_fail():
    # B2: a cap on a SUB-unit over an unbounded outer set is unbounded total work.
    for b in ["50 iterations per page", "500 tokens at a time", "5 retries per file"]:
        spec = CLEAN.replace("budget: max_iterations=20", f"budget: {b}")
        assert _has(spec, 2, "FAIL"), (b, _rules(spec))


def test_distributive_with_total_ok_r2():
    # control: a distributive phrasing WITH a total cap is bounded.
    spec = CLEAN.replace("budget: max_iterations=20", "budget: 200 iterations total across all files")
    assert not _has(spec, 2, "FAIL"), _rules(spec)


def test_subjective_runner_and_adverb_r1_fail():
    # B3/B4: a runner word used as a prose noun, and a taste adverb laundered by a
    # weak token, are not machine gates.
    for g in ["the cypress vines look healthy", "the prose reads elegantly and returns 0 vibes",
              "the k6 results feel good and the vibe is right"]:
        spec = CLEAN.replace("gate: pytest tests/ -q", f"gate: {g}")
        assert _has(spec, 1, "FAIL"), (g, _rules(spec))


# --- R7 IRREVERSIBLE-NO-HUMAN ---------------------------------------------

def test_irreversible_autonomous_warns_r7():
    # an autonomous loop that takes an irreversible action with no human warns.
    # Broad verb set hardened by 1 adversarial round (wire/revoke/truncate/
    # force-merge/delete-branch/email-blast/overwrite-prod/tag-release).
    for stop in ["deploys to prod when tests pass", "merges to main automatically",
                 "runs the db migration", "charges the customer card",
                 "wires the money and initiates a transfer to the vendor",
                 "revokes the api key automatically", "truncates the table once archived",
                 "force merges the pull request", "deletes the branch from the remote",
                 "sends the email blast to the subscriber list",
                 "overwrites prod data with the new snapshot",
                 "tags a release and pushes the git tag", "lints and deploys to prod"]:
        spec = CLEAN.replace("stop: all target tests green", f"stop: {stop}")
        assert _has(spec, 7, "WARN"), (stop, _rules(spec))


def test_reversible_context_no_r7():
    # a test / dry-run / preview / config-edit OF an irreversible verb is reversible.
    for stop in ["writes and runs migration unit tests", "performs a --dry-run of the migration",
                 "deploys to a preview staging env"]:
        spec = CLEAN.replace("stop: all target tests green", f"stop: {stop}")
        assert not _has(spec, 7, "WARN"), (stop, _rules(spec))
    # action word inside a config file / path is not an action
    spec = (CLEAN.replace("generator: opus coder agent", "generator: opus agent edits and lints deploy.yaml")
            .replace("stop: all target tests green", "stop: the yaml lints clean"))
    assert not _has(spec, 7, "WARN"), _rules(spec)


def test_irreversible_with_human_gate_no_r7():
    # a human approval gate (or a human verifier) silences R7.
    spec = (CLEAN.replace("stop: all target tests green", "stop: deploys to prod after sign-off")
            .replace("gate: pytest tests/ -q", "gate: Saar approves the release in the dashboard")
            .replace("verifier: sonnet read-only reviewer", "verifier: Saar (human)"))
    assert not _has(spec, 7, "WARN"), _rules(spec)


def test_reversible_loop_no_r7():
    # a normal closed loop with no irreversible action does not warn.
    assert not _has(CLEAN, 7, "WARN"), _rules(CLEAN)


def test_deploy_word_in_path_no_false_r7():
    # "test_deploy.py" / "deploy-config" name-drop 'deploy' but take no action.
    spec = (CLEAN.replace("gate: pytest tests/ -q", "gate: pytest tests/test_deploy.py")
            .replace("name: refactor-loop", "name: deploy-config-linter"))
    assert not _has(spec, 7, "WARN"), _rules(spec)


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


# --- R8/R9 LOOP MEMORY CONTRACT ------------------------------------------

MEMORY_FIELDS = """\
anchor_files: VISION.md, PROMPT.md, skills/loop-engineering/SKILL.md
state_store: work/LOOP-STATE.json
recall: wiki.py search plus state_store read before every pass
writeback: append verifier verdict and attempts after every pass
"""


def test_outer_loop_without_memory_contract_warns_r8():
    spec = CLEAN.replace("topology: closed · inner · single", "topology: closed · outer · single")
    assert _has(spec, 8, "WARN"), _rules(spec)


def test_scheduled_loop_without_memory_contract_warns_r8():
    spec = CLEAN.replace("stop: all target tests green", "stop: nightly cron run completes green")
    assert _has(spec, 8, "WARN"), _rules(spec)


def test_loop_run_monitor_gate_not_scheduled_r8():
    spec = CLEAN.replace("gate: pytest tests/ -q", "gate: python3 skills/loop-engineering/tools/loop_run_monitor.py trace.json")
    assert not _has(spec, 8, "WARN"), _rules(spec)


def test_inner_single_loop_does_not_need_memory_contract_r8():
    assert not _has(CLEAN, 8, "WARN"), _rules(CLEAN)


def test_outer_loop_with_memory_contract_ok_r8():
    spec = CLEAN.replace("topology: closed · inner · single", "topology: closed · outer · single")
    spec += MEMORY_FIELDS
    assert not _has(spec, 8, "WARN"), _rules(spec)


def test_fleet_state_store_without_concurrency_warns_r9():
    spec = (CLEAN.replace("topology: closed · inner · single", "topology: closed · outer · fleet")
            .replace("gate: pytest tests/ -q", "gate: pytest -q then reviewer quorum >=2/3")
            + MEMORY_FIELDS)
    assert _has(spec, 9, "WARN"), _rules(spec)


def test_fleet_state_concurrency_ok_r9():
    spec = (CLEAN.replace("topology: closed · inner · single", "topology: closed · outer · fleet")
            .replace("gate: pytest tests/ -q", "gate: pytest -q then reviewer quorum >=2/3")
            + MEMORY_FIELDS
            + "state_concurrency: optimistic_revision\n")
    assert not _has(spec, 8, "WARN"), _rules(spec)
    assert not _has(spec, 9, "WARN"), _rules(spec)


def test_fleet_state_concurrency_invalid_warns_r9():
    spec = (CLEAN.replace("topology: closed · inner · single", "topology: closed · outer · fleet")
            .replace("gate: pytest tests/ -q", "gate: pytest -q then reviewer quorum >=2/3")
            + MEMORY_FIELDS
            + "state_concurrency: vibes\n")
    assert _has(spec, 9, "WARN"), _rules(spec)


def test_memory_findings_are_advisory_by_default():
    spec = CLEAN.replace("topology: closed · inner · single", "topology: closed · outer · single")
    assert _has(spec, 8, "WARN"), _rules(spec)
    assert not _has(spec, 8, "FAIL"), _rules(spec)
    assert _exit_for(spec) == 1


def test_strict_memory_missing_contract_fails_r8():
    for spec in [
        CLEAN.replace("topology: closed · inner · single", "topology: closed · outer · single"),
        CLEAN.replace("stop: all target tests green", "stop: nightly cron run completes green"),
        CLEAN.replace("stop: all target tests green", "stop: background worker runs continuously"),
    ]:
        assert _has(spec, 8, "FAIL", strict_memory=True), _rules(spec, strict_memory=True)
        assert not _has(spec, 8, "WARN", strict_memory=True), _rules(spec, strict_memory=True)
        assert _exit_for(spec, args=["--strict-memory"]) == 2


def test_strict_memory_missing_fleet_state_concurrency_fails_r9():
    spec = (CLEAN.replace("topology: closed · inner · single", "topology: closed · outer · fleet")
            .replace("gate: pytest tests/ -q", "gate: pytest -q then reviewer quorum >=2/3")
            + MEMORY_FIELDS)
    assert _has(spec, 9, "FAIL", strict_memory=True), _rules(spec, strict_memory=True)
    assert not _has(spec, 9, "WARN", strict_memory=True), _rules(spec, strict_memory=True)
    assert _exit_for(spec, args=["--strict-memory"]) == 2


def test_strict_memory_valid_contract_and_concurrency_pass():
    spec = (CLEAN.replace("topology: closed · inner · single", "topology: closed · outer · fleet")
            .replace("gate: pytest tests/ -q", "gate: pytest -q then reviewer quorum >=2/3")
            + MEMORY_FIELDS
            + "state_concurrency: worktree_isolated\n")
    assert _rules(spec, strict_memory=True) == [], _rules(spec, strict_memory=True)
    assert _exit_for(spec, args=["--strict-memory"]) == 0


# --- R10 OUTPUT-SURFACE-UNBOUNDED ----------------------------------------

# An unattended (outer) loop with its memory contract satisfied, so R10 is the
# ONLY finding under test. The side-effecting world action lives in `stop`.
UNATTENDED = (
    "name: mod-bot\n"
    "topology: closed · outer · single\n"
    "generator: claude agent triages each new issue\n"
    "verifier: sonnet reviewer (fresh context)\n"
    "gate: regex: spam patterns match\n"
    "stop: nightly cron completes; the bot closes the issue and posts a comment\n"
    "budget: max_iterations=50\n"
) + MEMORY_FIELDS


def test_unattended_side_effecting_no_allowlist_warns_r10():
    # the falsifiable core: an unattended loop that mutates the world with no
    # declared output surface MUST warn, and it must be the sole finding (exit 1).
    assert _has(UNATTENDED, 10, "WARN"), _rules(UNATTENDED)
    assert _rules(UNATTENDED) == [(10, "WARN")], _rules(UNATTENDED)
    assert _exit_for(UNATTENDED) == 1


def test_unattended_bounded_allowlist_silences_r10():
    spec = UNATTENDED + "output_actions: add-label[wontfix] max 5, close-issue max 5\n"
    assert not any(r == 10 for r, _ in _rules(spec)), _rules(spec)
    assert _exit_for(spec) == 0


def test_unattended_unbounded_allowlist_warns_r10():
    # an allowlist of '*' permits everything — not a control, still warns.
    spec = UNATTENDED + "output_actions: *\n"
    assert _has(spec, 10, "WARN"), _rules(spec)


def test_inner_watched_loop_side_effecting_no_r10():
    # a human watches an inner loop and IS its output gate — no allowlist required.
    spec = CLEAN.replace("generator: opus coder agent",
                         "generator: opus agent commits the fix and pushes to the branch")
    assert not any(r == 10 for r, _ in _rules(spec)), _rules(spec)


def test_scheduled_pure_compute_no_r10():
    # a nightly loop that mutates nothing outside itself needs no output allowlist.
    spec = UNATTENDED.replace(
        "stop: nightly cron completes; the bot closes the issue and posts a comment",
        "stop: nightly cron completes green")
    assert not any(r == 10 for r, _ in _rules(spec)), _rules(spec)


def test_r10_rule_filter_resolves():
    # --rule 10 isolates R10; filtering to another rule drops it.
    assert (10, "WARN") in _rules(UNATTENDED, rule=10), _rules(UNATTENDED, rule=10)
    assert not any(r == 10 for r, _ in _rules(UNATTENDED, rule=1)), _rules(UNATTENDED, rule=1)


# neutralise UNATTENDED's stop action so the swapped-in generator is the sole trigger.
_NEUTRAL = UNATTENDED.replace(
    "stop: nightly cron completes; the bot closes the issue and posts a comment",
    "stop: nightly cron completes green")


def _with_gen(gen):
    return _NEUTRAL.replace("generator: claude agent triages each new issue", "generator: " + gen)


def test_r10_no_false_positive_on_readonly_state():
    # active-verb gating: read-only noun/adjective phrases ('commit hash', 'open
    # issues', 'merged PRs', 'deleted files') describe STATE, not an action — an
    # output-surface warning on a loop that only reads them would be a false nag.
    for gen in ["agent reviews the latest commit hash and merged PRs",
                "agent triages when 0 open issues remain",
                "agent counts closed pull-requests and deleted files",
                "agent summarizes the open issue backlog",
                "agent inspects the deployment config"]:
        spec = _with_gen(gen)
        assert not any(r == 10 for r, _ in _rules(spec)), (gen, _rules(spec))


def test_r10_fires_through_adjectives():
    # an adjective between the active verb and its object ('closes the duplicate
    # issue', 'adds a wontfix label') must still register as a side effect.
    for gen in ["bot closes the duplicate issue",
                "bot adds a wontfix label",
                "bot merges the approved PR",
                "bot posts a templated comment",
                "bot deletes the stale branch"]:
        spec = _with_gen(gen)
        assert _has(spec, 10, "WARN"), (gen, _rules(spec))


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


# --- Diagram (Mermaid) ----------------------------------------------------

BROKEN_DIAG = """\
name: vibe-loop
topology: open · inner · single
generator: claude
verifier: claude
gate: looks correct
stop: when it feels done
"""


def _diagram(text, source="spec.yaml"):
    return "\n\n".join(loop_lint.diagrams(text, source))


def _diagram_main(text, suffix=".yaml"):
    with tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False) as fh:
        fh.write(text)
        path = fh.name
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = loop_lint.main(["--diagram", path])
        return rc, buf.getvalue()
    finally:
        os.unlink(path)


def test_diagram_clean_has_ok_node_no_fail():
    d = _diagram(CLEAN)
    assert "flowchart LR" in d
    assert ":::ok" in d and "OK —" in d
    assert ":::fail" not in d, d
    for nid in ('G["gen:', 'K{"gate:', 'V["verify:', 'S(["stop:', 'B[/"budget:', 'TOPO["topology:'):
        assert nid in d, nid


def _class_nodes(d, sev):
    """Union of node ids in every `class <ids> <sev>` line of a diagram."""
    nodes = set()
    for l in d.splitlines():
        s = l.strip()
        if s.startswith("class ") and s.endswith(f" {sev}"):
            nodes |= set(s.split()[1].split(","))
    return nodes


def test_diagram_broken_overlays_findings():
    d = _diagram(BROKEN_DIAG)
    assert "subgraph lint" in d
    assert ":::fail" in d
    # the indicted nodes are coloured FAIL-red, not only the findings list:
    # R1 → gate (K), R3 → generator+verifier (G,V), R2 (no budget) → stop+budget (S,B)
    assert {"K", "G", "V"} <= _class_nodes(d, "fail"), _class_nodes(d, "fail")
    assert "R1 FAIL" in d and "R3 FAIL" in d


def test_diagram_node_colour_matches_severity_r2_zero_cap():
    # R2 cap==0 is a WARN, not a FAIL: the stop+budget nodes must be warn-
    # coloured, never FAIL-red (the diagram must not contradict the verdict).
    spec = ("name: z\ntopology: closed · inner · single\ngenerator: a\n"
            "verifier: b\ngate: pytest -q\nstop: all green\nbudget: max_iterations=0\n")
    assert _has(spec, 2, "WARN") and not _has(spec, 2, "FAIL"), _rules(spec)
    d = _diagram(spec)
    assert {"S", "B"} <= _class_nodes(d, "warn"), _class_nodes(d, "warn")
    assert not ({"S", "B"} & _class_nodes(d, "fail")), _class_nodes(d, "fail")
    assert "R2 WARN" in d and "R2 FAIL" not in d


def test_diagram_exit_code_is_lint_verdict():
    assert _diagram_main(CLEAN)[0] == 0
    assert _diagram_main(BROKEN_DIAG)[0] == 2


def test_diagram_multi_spec_one_block_each():
    two = json.dumps([
        {"name": "a", "generator": "g", "verifier": "v", "gate": "pytest -q",
         "stop": "green", "budget": "max_iterations=3", "topology": "closed"},
        {"name": "b", "generator": "c", "verifier": "c", "gate": "looks ok",
         "stop": "feels done", "topology": "open"},
    ])
    blocks = loop_lint.diagrams(two, "multi.json")
    assert len(blocks) == 2, len(blocks)
    assert "flowchart LR" in blocks[0] and "flowchart LR" in blocks[1]


def test_diagram_label_sanitization_strips_mermaid_breakers():
    spec = ('name: x\ngenerator: a|b[c]"d{e}(f)\ngate: pytest -q\n'
            'stop: green\nbudget: max_iterations=3\nverifier: rev\ntopology: closed\n')
    d = _diagram(spec)
    gen_line = next(l for l in d.splitlines() if l.strip().startswith('G["gen:'))
    # node is  G["gen: <content>"]  — test the CONTENT, not the delimiters
    content = gen_line.split("gen: ", 1)[1]
    assert content.endswith('"]'), gen_line
    content = content[:-2]
    for bad in ('|', '[', ']', '"', '{', '}', '(', ')'):
        assert bad not in content, (bad, repr(content))


def test_diagram_no_spec_is_graceful():
    rc, out = _diagram_main("")
    assert "no loop spec found" in out
    assert rc == 1, rc


# --- non-iterating pipeline = budget=1 loop -------------------------------

def test_noniterating_pipeline_budget1_passes():
    """A fixed once-through pipeline modeled as a budget=1 closed loop must lint
    CLEAN — the load-bearing claim that a pipeline needs no new schema/tool. If
    loop_lint ever FAILs this, the 'a pipeline is a budget=1 loop' doctrine is
    broken (see SKILL.md 'Do you even need a loop?' + schema.md)."""
    spec = (
        "name: import-pipeline\n"
        "topology: closed · inner · single\n"
        "generator: import + transform stages\n"
        "verifier: validate stage + final schema check (separate actor)\n"
        "gate: python3 ./validate.py && python3 ./check_schema.py out.json\n"
        "stop: out.json written and passes the schema check\n"
        "budget: max_iterations=1\n"
    )
    assert _rules(spec) == [], _rules(spec)
    assert _exit_for(spec) == 0


def test_naive_pipeline_without_budget1_still_fails():
    """A pipeline written WITHOUT the budget=1 framing (no budget, self-grading,
    prose gate) is correctly refused — the failure that sends the author to the
    budget=1 spec, not to a new tool."""
    spec = (
        "name: import-naive\n"
        "topology: closed · inner · single\n"
        "generator: claude does all the stages\n"
        "verifier: claude\n"
        "gate: each stage hands its output to the next\n"
        "stop: when out.json is written\n"
    )
    rules = _rules(spec)
    assert (1, "FAIL") in rules and (2, "FAIL") in rules and (3, "FAIL") in rules, rules
    assert _exit_for(spec) == 2


# --- R11 STUCK-NO-ADVISOR -------------------------------------------------

_R11_BASE = (
    "name: fix-loop\n"
    "topology: closed · inner · single\n"
    "generator: opus coder agent\n"
    "verifier: sonnet read-only reviewer\n"
    "gate: pytest tests/ -q\n"
    "stop: target tests green\n"
    "budget: max_iterations=3\n"
)


def test_r11_stuck_policy_without_advisor_warns():
    """A loop that declares a stuck policy but names no advisor leaves the stuck
    agent re-deriving alone — the warning the whole multi-model design hangs on."""
    spec = _R11_BASE + "stuck: same error 2x\n"
    assert (11, "WARN") in _rules(spec), _rules(spec)


def test_r11_stuck_with_advisor_is_clean():
    spec = _R11_BASE + "stuck: same error 2x\nadvisor: cross-vendor panel (codex + gemini), read-only\n"
    assert (11, "WARN") not in _rules(spec), _rules(spec)


def test_r11_silent_when_no_stuck_declared():
    """Opt-in: a plain inner fix loop with neither field gets no R11 — the rule
    must not perturb the existing specs that declare no stuck policy."""
    assert (11, "WARN") not in _rules(CLEAN), _rules(CLEAN)


def test_r11_advisor_equals_verifier_warns():
    """Advisor (divergent, proposes) collapsing into verifier (convergent, judges)
    is self-grading by another door — propose-then-judge-your-own-proposal."""
    spec = (
        "name: collapsed-roles\n"
        "topology: closed · inner · single\n"
        "generator: opus coder\n"
        "verifier: codex reviewer\n"
        "advisor: codex reviewer\n"
        "gate: pytest -q\n"
        "stop: green\n"
        "budget: max_iterations=3\n"
        "stuck: same command 3x\n"
    )
    assert (11, "WARN") in _rules(spec), _rules(spec)


def test_r11_is_warn_not_fail():
    """R11 is advisory: a stuck-no-advisor spec that is otherwise complete exits 1,
    never 2 — it must not block an otherwise-valid loop."""
    spec = _R11_BASE + "stuck: 2 iters no movement\n"
    assert _exit_for(spec) == 1, _exit_for(spec)


def test_r11_rule_filter_isolates():
    spec = _R11_BASE + "stuck: same error 2x\n"
    assert _rules(spec, rule=11) == [(11, "WARN")], _rules(spec, rule=11)


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
