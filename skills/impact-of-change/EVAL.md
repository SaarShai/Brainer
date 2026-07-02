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
