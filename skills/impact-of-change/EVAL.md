# impact-of-change — EVAL

**Posture: opt-in (`auto-install: false`), unmeasured.** Ships symlinked + listed;
wires no hook. Promotion to default needs N≥50 like every other Brainer skill.

## What it is
Pre-commit blast-radius map: `git diff` → changed symbols → inbound dependents
(graphify `calls`/`inherits` reverse-traversal, depth≤3; labelled lexical grep
fallback) → LOW/MEDIUM/HIGH. Tells `verify-before-completion` WHAT to verify.

## Deterministic self-tests (green)
`tools/test_impact.py` — diff parsing, symbol extraction, graph traversal,
fallback labelling; runs in `scripts/run_all_tests.sh` (no network).

## What to measure (when N is available)
- **Dependent recall/precision** — seed known edits (rename a function with K
  real callers), check the reported dependent set against ground truth from the
  code graph; separately for graphify-present vs lexical-fallback mode.
- **Risk-score calibration** — do HIGH edits correlate with edits that actually
  broke a test/dependent in repo history? (git archaeology of past regressions.)
- **Did-it-help** — A/B on naive subjects: with the skill's report injected, do
  agents verify the right zones and miss fewer downstream breaks than without?

## Failure modes

Premortem ([`LEARNING_CONTRACT`](../_shared/LEARNING_CONTRACT.md) §8):

- **Silent-failure path** — `auto-install: false` means the blast-radius map only
  runs when explicitly invoked; an agent that commits without running `impact.py`
  gets no map, no risk score, and nothing anywhere records that the pre-commit gate
  was skipped rather than passed clean.
- **Rot-when-unwatched** — when `graphify` is absent the tool falls back to
  "labelled lexical grep" instead of true call-graph traversal; that fallback's
  recall against a growing, refactored codebase is unmeasured (the "What to
  measure" list above is still N-pending), so a HIGH-risk edit can quietly render
  as LOW under degraded mode with nothing flagging the degradation as the reason.
- **No-hooks host** — this is opt-in and unwired to any hook on any host; the
  `pulse_reminder` text is the only mechanism nudging an agent to run it before a
  done-claim, so a host or session that never re-anchors that reminder gets zero
  enforcement of the pre-commit gate this skill is meant to provide.
