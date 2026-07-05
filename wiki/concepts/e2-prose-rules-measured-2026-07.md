---
trust: verified
schema_version: 2
title: "E2 A/B on two 2026-07 prose rules — mostly null; one robust declaration effect"
type: concept
domain: "framework"
tier: episodic
confidence: 0.8
created: "2026-07-05"
updated: "2026-07-05"
verified: "2026-07-05"
sources: ["eval/e2-rules-202607/ (loop-spec.md, run_e2.py, raw.json, results.json)"]
supersedes: []
superseded-by:
tags: [eval-methodology, ab-test, negative-result, eval-gate, loop-engineering, measured]
---

# E2 A/B on two 2026-07 prose rules — mostly null

**Question:** do two article-adoption prose rules change naive-subject behavior?
(1) eval-gate's spec-tied `required` criterion (0daaaf2); (2) loop-engineering's
typed stop states (87cdf41).

**Method:** paired A/B, 6 scenarios/eval, subjects = glm-5.2 fresh-context
(thinking disabled), never told it's an eval; arm text presented as "your
team's guidance". Grading: deterministic regex + blind cross-family Ollama
judge (spec-tie question only). Spec linted clean by loop_lint (gate / stop /
budget / separate verifier). Harness: `eval/e2-rules-202607/run_e2.py`.

## Results

| Metric | armA (old text) | armB (new text) | verdict |
|---|---|---|---|
| A: rubric has spec-tied `required` criterion | 5/6 | 6/6 | **ceiling** — baseline already high; +0.167 at n=6 is not evidence |
| B primary: behaves correctly on planted empty round (declares no-op, invents nothing) | 6/6 | 6/6 | **NULL** — subjects handle empty rounds fine without the rule |
| B secondary: spec declares partial/carry semantics | 0/6 | 6/6 | **robust** — the rule reliably changes what specs DECLARE |

## Decision

- Keep both rules (cost ≈ 0: lazy-loaded bodies; no harm measured), but **do
  not cite them as measured behavioral lift**. The one real effect is
  declaration-level: typed stop text makes every spec carry partial/carry
  semantics it otherwise never mentions. Whether that declaration prevents
  silent drops **at cap** (the rule's other half) was tested in the follow-up
  below: also null.

## Follow-up: drop-at-cap (2026-07-05, run_e2b.py)

6 paired scenarios, queue > per-round cap, planted explicit item IDs so
leftover-detection is deterministic. Result: **armA 6/6, armB 6/6, lift 0.0**
— glm-5.2 does not silently drop leftovers at cap even without the rule; all
12 raw cells eyeballed, grading clean on first pass this time. Arm difference
is vocabulary only: armB emits typed machine-parseable states
(`state: partial`, `remainder_queue_head: …`) where armA writes free prose
("Deferred to next round: M5–M9"). Standing caveats: leftovers were SALIENT
(crisp enumerated IDs); the untested condition is a messy/implicit queue where
the remainder isn't enumerated in the input — and weaker-than-glm subjects.
Verdict unchanged: keep the rule for its declaration-standardization value (a
monitor can parse `partial` states), claim no behavioral lift.
- Consistent with house precedent: prose additions to already-competent
  frontier/near-frontier subjects tend to measure null on behavior the model
  already does ([[concepts/premortem-and-think-edits-measured]],
  [[concepts/systematic-debugging-skill-measured-null]]).

## Grader lessons (the eval's real yield)

Three grader bugs were found ONLY by eyeballing raw outputs, each of which
would have shipped a wrong verdict:

1. `_run_glm` without `thinking:{disabled}` → 9/12 unparseable cells (the
   documented delegate-router gotcha, walked into anyway — the gotcha needs to
   live in the CALLER's path, not just the wiki).
2. Whole-output regex counted the LOOP SPEC's restatement of the job as
   "invented work" → scope grading to the result section.
3. Negation blindness: "**No** themes promoted" matched the promotion regex →
   negation guard. And inverse: correct "No SOP edit proposed" phrasings
   weren't in the no-op vocabulary → grader recall bug deflated armA.

General form: **an A/B verdict is only as good as the grader; eyeball every
FAIL and every strongest-claim cell before certifying** (never-sample applies
to eval cells too). The apparent lift moved 0.667 → 0.5 → 0.0 as grader bugs
were fixed — each intermediate number would have been a false positive.

## Related

- [[queries/external-validation]] — the adoption rows these rules came from
- [[concepts/team-lead-upstream-2026-07]] — never-sample rule, applied here to
  the eval's own cells
