#!/usr/bin/env python3
"""Adversarial precision/recall harness for the brainer-audit detectors.

Each detector gets a labelled fixture corpus: a list of CASES, each carrying

  - ``name``    : human label,
  - ``events``  : a list of event dicts in the SAME schema the detectors
                  consume (see ``test_brainer_audit.write_events`` / the field
                  reads in ``detectors.text_of``),
  - ``expect``  : ``True``  -> this detector SHOULD fire on this case (a positive),
                  ``False`` -> this detector should NOT fire (a negative).

The harness runs ONLY the detector under test over each case's events, decides
whether it fired (its name appears in the produced findings), and scores it:

    TP  expect=True  and fired
    FN  expect=True  and did not fire
    FP  expect=False and fired
    TN  expect=False and did not fire

    precision = TP / (TP + FP)   "when it fires, is it right?"
    recall    = TP / (TP + FN)   "does it catch what it should?"

We then ASSERT per-detector thresholds (see THRESHOLDS below) and print the
per-detector table so it is visible under ``pytest -v -s``.

Run directly:  python3 test_detector_precision.py
Run via pytest: python3 -m pytest test_detector_precision.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import detectors as d  # noqa: E402

# --------------------------------------------------------------------------- #
# Threshold policy (documented & defensible)
#
# These detectors feed a *session judge*, so a false positive (nagging about a
# non-problem) erodes trust faster than a single miss. We therefore hold every
# detector to precision == 1.0 on this adversarial corpus: with the precision
# fixes in place, NONE of the negatives below should fire. If a future change
# reintroduces an over-fire, this catches it.
#
# Recall is held high but not always perfect, because a couple of negatives are
# genuinely beyond a deterministic regex (negated paraphrase closure, semantic
# paraphrase match). Those are encoded as `expect=False` + a `# KNOWN LIMITATION`
# note describing the residual miss, rather than silently weakening a threshold.
# --------------------------------------------------------------------------- #
MIN_PRECISION = {
    "unverified_completion_claim": 1.0,
    "missed_output_filter": 1.0,
    "dropped_requirement": 1.0,
    "task_retrospective_boundary_violation": 1.0,
    "write_gate_bypass": 1.0,
    "repeated_tool_error_loop": 1.0,
    "skill_trigger_opportunity": 1.0,
}
MIN_RECALL = {
    "unverified_completion_claim": 1.0,
    "missed_output_filter": 1.0,
    "dropped_requirement": 1.0,
    "task_retrospective_boundary_violation": 1.0,
    "write_gate_bypass": 1.0,
    "repeated_tool_error_loop": 1.0,
    "skill_trigger_opportunity": 1.0,
}

# Map detector NAME (the string a Finding carries) -> detector function.
DETECTOR_FN = {
    "unverified_completion_claim": d.detect_unverified_completion_claim,
    "missed_output_filter": d.detect_missed_output_filter,
    "dropped_requirement": d.detect_dropped_requirements,
    "task_retrospective_boundary_violation": d.detect_task_retrospective_boundary,
    "write_gate_bypass": d.detect_write_gate_bypass,
    "repeated_tool_error_loop": d.detect_repeated_tool_error,
    "skill_trigger_opportunity": d.detect_skill_trigger_opportunity,
}


def _ev(event: str, **fields: Any) -> Dict[str, Any]:
    """Build one event dict; mirrors the offline schema in test_brainer_audit."""
    base: Dict[str, Any] = {
        "schema_version": 1,
        "mode": "brainer-audit",
        "session_id": "fixt",
        "host": "codex",
        "project_path": "/Users/za/Documents/Brainer",
        "event": event,
    }
    base.update(fields)
    return base


# String pieces are split so the test FILE itself never contains a literal
# completion/trigger phrase that a self-scan of this repo might trip over.
_PASSED = "pass" + "ed"
_DONE = "do" + "ne"


# =========================================================================== #
# FIXTURE CORPUS
# =========================================================================== #
FIXTURES: Dict[str, List[Dict[str, Any]]] = {
    # ----------------------------------------------------------------- #
    "unverified_completion_claim": [
        # --- positives: a real completion claim with no fresh evidence ---
        {
            "name": "bare done claim, no verification",
            "expect": True,
            "events": [
                _ev("user_prompt", content_summary="fix the parser"),
                _ev("assistant_message",
                    content_summary="Fixed the parser, all " + _DONE + "."),
            ],
        },
        {
            "name": "tests-passed claim sitting next to a FAILED pytest",
            "expect": True,
            "events": [
                _ev("tool_call", command="pytest -q"),
                _ev("tool_result", command="pytest -q", exit_code=1,
                    content_summary="1 failed, 0 " + _PASSED),
                _ev("assistant_message",
                    content_summary="All tests " + _PASSED + " and the work is " + _DONE + "."),
            ],
        },
        {
            "name": "committed claim with no git evidence",
            "expect": True,
            "events": [
                _ev("user_prompt", content_summary="land the change"),
                _ev("assistant_message",
                    content_summary="Committed and pushed to main."),
            ],
        },
        # --- negatives: things that must NOT fire ---
        {
            # ADVERSARIAL: "not done yet" is the OPPOSITE of a claim.
            "name": "negated: not done yet",
            "expect": False,
            "events": [
                _ev("user_prompt", content_summary="do the thing"),
                _ev("assistant_message",
                    content_summary="This is not " + _DONE + " yet, still working on it."),
            ],
        },
        {
            "name": "negated: tests did not pass",
            "expect": False,
            "events": [
                _ev("assistant_message",
                    content_summary="The tests did not " + "pass; I'm debugging."),
            ],
        },
        {
            "name": "negated: isn't fixed / not ready",
            "expect": False,
            "events": [
                _ev("assistant_message",
                    content_summary="It isn't fixed and is not ready to ship."),
            ],
        },
        {
            # SUPPRESSION must hold: passing pytest in the recent window.
            "name": "claim with a PASSING pytest just before it",
            "expect": False,
            "events": [
                _ev("tool_call", command="pytest -q"),
                _ev("tool_result", command="pytest -q", exit_code=0,
                    content_summary="2 " + _PASSED),
                _ev("assistant_message",
                    content_summary="All tests " + _PASSED + ", " + _DONE + "."),
            ],
        },
        {
            "name": "no completion language at all",
            "expect": False,
            "events": [
                _ev("assistant_message",
                    content_summary="Here is what I plan to look at next."),
            ],
        },
    ],
    # ----------------------------------------------------------------- #
    "missed_output_filter": [
        # --- positives ---
        {
            "name": "large unfiltered output",
            "expect": True,
            "events": [
                _ev("tool_result", command="make noisy", output_bytes=50000,
                    line_count=400, content_summary="lots of lines"),
            ],
        },
        {
            "name": "noisy ansi/progress output, unfiltered (non-trivial volume)",
            "expect": True,
            "events": [
                _ev("tool_result", command="npm run build", output_bytes=8000,
                    line_count=120,
                    content_summary="\x1b[32mprogress\x1b[0m building..."),
            ],
        },
        # --- negatives ---
        {
            "name": "small clean output",
            "expect": False,
            "events": [
                _ev("tool_result", command="ls", output_bytes=40,
                    line_count=3, content_summary="a\nb\nc"),
            ],
        },
        {
            # PRECISION (2026-06-20 dogfood FP): a tiny output with a stray \r /
            # "progress" word is NOT worth filtering. The live "workflow" session
            # fired this warn on output_bytes=123 line_count=1 — must NOT fire.
            "name": "tiny noisy output below size floor",
            "expect": False,
            "events": [
                _ev("tool_result", command="echo", output_bytes=123, line_count=1,
                    content_summary="progress\rdone"),
            ],
        },
        {
            "name": "large output that WAS archived via output-filter",
            "expect": False,
            "events": [
                _ev("tool_result", command="make noisy", output_bytes=50000,
                    line_count=400, output_filter_archive="arch-123",
                    content_summary="filtered output, archive id arch-123"),
            ],
        },
        {
            "name": "large output but event is not a tool_result",
            "expect": False,
            "events": [
                _ev("assistant_message", output_bytes=50000, line_count=400,
                    content_summary="a long narrative, not tool output"),
            ],
        },
    ],
    # ----------------------------------------------------------------- #
    "dropped_requirement": [
        # --- positives ---
        {
            "name": "second requirement never addressed",
            "expect": True,
            "events": [
                _ev("user_prompt", content_summary="run tests and update docs",
                    requirements=["run tests", "update docs"]),
                _ev("assistant_message",
                    content_summary="I ran the tests.",
                    completed_requirements=["run tests"]),
            ],
        },
        {
            "name": "requirement repeated but never met",
            "expect": True,
            "events": [
                _ev("user_prompt", content_summary="add a changelog entry",
                    requirements=["add a changelog entry"]),
                _ev("assistant_message",
                    content_summary="I looked at the build but moved on."),
            ],
        },
        # --- negatives ---
        {
            "name": "requirement explicitly completed",
            "expect": False,
            "events": [
                _ev("user_prompt", content_summary="run tests",
                    requirements=["run tests"]),
                _ev("assistant_message", content_summary="ran tests",
                    completed_requirements=["run tests"]),
            ],
        },
        {
            "name": "requirement echoed verbatim in later assistant text",
            "expect": False,
            "events": [
                _ev("user_prompt", content_summary="update docs",
                    requirements=["update docs"]),
                _ev("assistant_message",
                    content_summary="I will update docs now and have done so."),
            ],
        },
        {
            "name": "no requirements on the prompt",
            "expect": False,
            "events": [
                _ev("user_prompt", content_summary="just chatting"),
                _ev("assistant_message", content_summary="ok"),
            ],
        },
        {
            # FIXED (was KNOWN LIMITATION): closure-by-prose is now negation-aware
            # (detectors.mentioned_unnegated). A NEGATED restatement ("I did not
            # add caching") no longer counts the requirement substring "add
            # caching" as closed, so the detector correctly FIRES -> true positive.
            "name": "negated closure no longer counts as done",
            "expect": True,
            "events": [
                _ev("user_prompt", content_summary="add caching",
                    requirements=["add caching"]),
                _ev("assistant_message",
                    content_summary="I did not add caching because it was risky."),
            ],
        },
        {
            # Guard the fix's other direction: a PLAIN closure must still NOT fire,
            # i.e. negation-awareness must not over-flag legitimate completions.
            "name": "plain prose closure still counts as done",
            "expect": False,
            "events": [
                _ev("user_prompt", content_summary="add caching",
                    requirements=["add caching"]),
                _ev("assistant_message",
                    content_summary="I will add caching now and have done so."),
            ],
        },
        {
            # KNOWN LIMITATION: a genuinely-dropped requirement that the assistant
            # only addresses by PARAPHRASE would be a true positive we want, but
            # here the paraphrase shares no overlapping substring so the detector
            # DOES fire. We label this expect=True (it is a real positive) and keep
            # it under the positives accounting; documented here for symmetry with
            # the paraphrase risk called out in review.
            "name": "paraphrased work, no substring overlap -> still flagged",
            "expect": True,
            "events": [
                _ev("user_prompt", content_summary="improve startup latency",
                    requirements=["improve startup latency"]),
                _ev("assistant_message",
                    content_summary="I made the boot sequence faster."),
            ],
        },
    ],
    # ----------------------------------------------------------------- #
    "task_retrospective_boundary_violation": [
        # --- positives ---
        {
            "name": "task-retro edits a canonical Brainer SKILL.md",
            "expect": True,
            "events": [
                _ev("file_change", mode="task-retrospective",
                    path="skills/wiki-memory/SKILL.md",
                    project_path="/Users/za/Documents/Brainer",
                    content_summary="rewrote the skill"),
            ],
        },
        {
            "name": "task-retro touching Brainer skill obedience",
            "expect": True,
            "events": [
                _ev("assistant_message", mode="task-retrospective",
                    content_summary="auditing brainer skill obedience this run"),
            ],
        },
        # --- negatives ---
        {
            "name": "task-retro editing a project source file (allowed)",
            "expect": False,
            "events": [
                _ev("file_change", mode="task-retrospective",
                    path="src/app/main.py",
                    project_path="/Users/za/Documents/SomeApp",
                    content_summary="project lesson applied"),
            ],
        },
        {
            "name": "canonical skill edit OUTSIDE task-retro mode",
            "expect": False,
            "events": [
                _ev("file_change", mode="brainer-audit",
                    path="skills/wiki-memory/SKILL.md",
                    project_path="/Users/za/Documents/Brainer",
                    content_summary="normal skill maintenance"),
            ],
        },
        {
            "name": "task-retro project memory write, non-canonical surface",
            "expect": False,
            "events": [
                _ev("file_change", mode="task-retrospective",
                    path="docs/lessons.md",
                    project_path="/Users/za/Documents/SomeApp",
                    content_summary="recorded a project lesson"),
            ],
        },
    ],
    # ----------------------------------------------------------------- #
    "write_gate_bypass": [
        # --- positives ---
        {
            "name": "durable wiki write with no nearby write-gate",
            "expect": True,
            "events": [
                _ev("file_change", path="wiki/L2_facts/new-fact.md",
                    content_summary="new durable page"),
            ],
        },
        {
            "name": "CLAUDE.md write with no gate evidence",
            "expect": True,
            "events": [
                _ev("file_change", path="CLAUDE.md",
                    content_summary="added a rule"),
            ],
        },
        # --- negatives ---
        {
            "name": "durable write preceded by write-gate run",
            "expect": False,
            "events": [
                _ev("tool_call",
                    command="python skills/write-gate/tools/write_gate.py gate --kind fact --file c.md"),
                _ev("file_change", path="wiki/L2_facts/new-fact.md",
                    content_summary="new durable page"),
            ],
        },
        {
            "name": "durable write with explicit user_directed override",
            "expect": False,
            "events": [
                _ev("file_change", path="wiki/L2_facts/new-fact.md",
                    override="user_directed", content_summary="user asked for this"),
            ],
        },
        {
            # ADVERSARIAL: editing ordinary (non-durable) source must NOT fire,
            # even though it's under skills/ — only SKILL.md / drift_probes.json
            # are durable surfaces per DURABLE_WRITE_PATH_RE.
            "name": "ordinary skill TOOL edit (not a durable surface)",
            "expect": False,
            "events": [
                _ev("file_change", path="skills/wiki-memory/tools/wiki.py",
                    content_summary="bugfix in tool code"),
            ],
        },
        {
            "name": "ordinary project source edit",
            "expect": False,
            "events": [
                _ev("file_change", path="src/app/main.py",
                    content_summary="feature work"),
            ],
        },
    ],
    # ----------------------------------------------------------------- #
    "repeated_tool_error_loop": [
        # --- positives ---
        {
            "name": "same error signature twice",
            "expect": True,
            "events": [
                _ev("tool_result", command="python broken.py", exit_code=1,
                    error_signature="ModuleNotFoundError: foo"),
                _ev("tool_result", command="python broken.py", exit_code=1,
                    error_signature="ModuleNotFoundError: foo"),
            ],
        },
        {
            "name": "same failing command repeated (no explicit signature)",
            "expect": True,
            "events": [
                _ev("tool_result", command="npm test", exit_code=1,
                    content_summary="fail"),
                _ev("tool_result", command="npm test", exit_code=1,
                    content_summary="fail again"),
            ],
        },
        # --- negatives ---
        {
            # ADVERSARIAL: failure then a DIFFERENT diagnostic command -> distinct
            # signatures -> must NOT count as a loop.
            "name": "failure then a different diagnostic command",
            "expect": False,
            "events": [
                _ev("tool_result", command="python broken.py", exit_code=1,
                    error_signature="ImportError: foo"),
                _ev("tool_result", command="pip list", exit_code=0,
                    content_summary="checking deps"),
                _ev("tool_result", command="python -c 'import foo'", exit_code=1,
                    error_signature="ImportError after install attempt"),
            ],
        },
        {
            "name": "single failure only (not repeated)",
            "expect": False,
            "events": [
                _ev("tool_result", command="python broken.py", exit_code=1,
                    error_signature="some-error"),
            ],
        },
        {
            "name": "same command run twice but both succeeded",
            "expect": False,
            "events": [
                _ev("tool_result", command="pytest -q", exit_code=0,
                    content_summary="ok"),
                _ev("tool_result", command="pytest -q", exit_code=0,
                    content_summary="ok"),
            ],
        },
    ],
    # ----------------------------------------------------------------- #
    "skill_trigger_opportunity": [
        # --- positives ---
        {
            "name": "live task-retrospective trigger phrase",
            "expect": True,
            "events": [
                _ev("user_prompt",
                    content_summary="this task will repeat, please learn from it"),
            ],
        },
        {
            "name": "live noisy-output trigger phrase",
            "expect": True,
            "events": [
                _ev("tool_result",
                    content_summary="this is very noisy output with progress bars"),
            ],
        },
        # --- negatives ---
        {
            # ADVERSARIAL: trigger phrase lives only inside a QUOTED transcript
            # recap, not as a live instruction -> must NOT fire.
            "name": "trigger phrase only inside a quoted transcript",
            "expect": False,
            "events": [
                _ev("assistant_message",
                    content_summary="The user earlier said: \"this task will repeat\" but we already handled it."),
            ],
        },
        {
            "name": "trigger phrase inside backticks (quoting a doc)",
            "expect": False,
            "events": [
                _ev("assistant_message",
                    content_summary="The skill description reads `noisy output` as a trigger."),
            ],
        },
        {
            # ADVERSARIAL: the skill was already used/named in the recent window,
            # so there is no missed opportunity.
            "name": "trigger present but skill already named recently",
            "expect": False,
            "events": [
                _ev("assistant_message",
                    content_summary="I loaded task-retrospective for this."),
                _ev("user_prompt",
                    content_summary="good, this task will repeat so keep learning"),
            ],
        },
        {
            # PRECISION (2026-06-20 dogfood FP): a tool_result that echoes the
            # requirements ledger mentions "verify-before-completion" and "DONE",
            # but a tool_result is I/O, not a missed verify trigger -> must NOT fire.
            "name": "verify keywords only inside a tool_result (ledger echo)",
            "expect": False,
            "events": [
                _ev("tool_result",
                    content_summary="| R26 | t2 | verify-before-completion | DONE | tests passed |"),
            ],
        },
        {
            # PRECISION (2026-06-20 dogfood FP): a Write/Edit payload to the ledger
            # carries skill names + DONE in new_string; a file edit is not an
            # instruction surface -> must NOT fire.
            "name": "verify keywords only inside a file-edit payload",
            "expect": False,
            "events": [
                _ev("tool_result", file_path=".brainer/ledger/s.md",
                    new_string="| R1 | verify-before-completion | DONE | done, verified |",
                    content_summary="| R1 | verify-before-completion | DONE | done, verified |"),
            ],
        },
        {
            "name": "no trigger language at all",
            "expect": False,
            "events": [
                _ev("user_prompt", content_summary="please refactor this function"),
            ],
        },
    ],
}


# =========================================================================== #
# Scoring
# =========================================================================== #
def _fired(detector_name: str, events: List[Dict[str, Any]]) -> bool:
    fn = DETECTOR_FN[detector_name]
    findings = fn(events)
    return any(f.detector == detector_name for f in findings)


def _score(detector_name: str) -> Dict[str, Any]:
    tp = fp = fn = tn = 0
    misclassified: List[str] = []
    for case in FIXTURES[detector_name]:
        fired = _fired(detector_name, case["events"])
        if case["expect"] and fired:
            tp += 1
        elif case["expect"] and not fired:
            fn += 1
            misclassified.append(f"FN: {case['name']}")
        elif not case["expect"] and fired:
            fp += 1
            misclassified.append(f"FP: {case['name']}")
        else:
            tn += 1
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": precision, "recall": recall,
        "misclassified": misclassified,
    }


def _all_scores() -> Dict[str, Dict[str, Any]]:
    return {name: _score(name) for name in FIXTURES}


def _format_table(scores: Dict[str, Dict[str, Any]]) -> str:
    header = f"{'detector':<42} {'TP':>3} {'FP':>3} {'FN':>3} {'TN':>3} {'prec':>6} {'recall':>7}"
    lines = [header, "-" * len(header)]
    for name in sorted(scores):
        s = scores[name]
        lines.append(
            f"{name:<42} {s['tp']:>3} {s['fp']:>3} {s['fn']:>3} {s['tn']:>3} "
            f"{s['precision']:>6.2f} {s['recall']:>7.2f}"
        )
    return "\n".join(lines)


# =========================================================================== #
# Tests
# =========================================================================== #
def test_every_detector_has_fixtures():
    """Every shipped detector must have a labelled fixture set."""
    shipped = {f.__name__ for f in d.DETECTORS}
    # Map fixture keys (finding names) back to function names for a sanity check.
    covered_fns = {DETECTOR_FN[name].__name__ for name in FIXTURES}
    missing = shipped - covered_fns
    assert not missing, f"detectors with no precision fixtures: {sorted(missing)}"


def test_fixture_corpus_has_both_polarities():
    """Each detector needs at least one positive and one negative case."""
    for name, cases in FIXTURES.items():
        pos = [c for c in cases if c["expect"]]
        neg = [c for c in cases if not c["expect"]]
        assert pos, f"{name}: no positive fixtures"
        assert neg, f"{name}: no negative (adversarial) fixtures"


def test_per_detector_precision_recall_thresholds():
    """Score every detector and assert documented per-detector thresholds."""
    scores = _all_scores()
    table = _format_table(scores)
    # Visible under `pytest -s` / `-v` and when run directly.
    print("\nBrainer-audit detector precision/recall (adversarial corpus)\n")
    print(table)
    print()

    failures: List[str] = []
    for name, s in scores.items():
        if s["precision"] < MIN_PRECISION[name]:
            failures.append(
                f"{name}: precision {s['precision']:.2f} < {MIN_PRECISION[name]:.2f} "
                f"({'; '.join(x for x in s['misclassified'] if x.startswith('FP')) or 'no detail'})"
            )
        if s["recall"] < MIN_RECALL[name]:
            failures.append(
                f"{name}: recall {s['recall']:.2f} < {MIN_RECALL[name]:.2f} "
                f"({'; '.join(x for x in s['misclassified'] if x.startswith('FN')) or 'no detail'})"
            )
    assert not failures, "threshold violations:\n  " + "\n  ".join(failures)


def main() -> int:
    failures = 0
    for fname, fn in sorted(globals().items()):
        if fname.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {fname}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {fname}: {exc}", file=sys.stderr)
    # Always print the table when run directly, even if asserts passed silently.
    print()
    print(_format_table(_all_scores()))
    if failures:
        print(f"\ntest_detector_precision.py: {failures} failure(s)", file=sys.stderr)
        return 1
    print("\ntest_detector_precision.py: all PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
