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

## Eval-design flaws (cross-vendor review 2026-07-05, recorded not hidden)

Two frontier reviewers flagged that these evals were *weaker* than the null
verdict implied — which only strengthens "no measured lift," but the design
faults are named for honesty and future re-runs:
- **Control arm smuggled the treatment (eval A).** Both arms' subject prompt
  mandated a `{id, description, weight, required}` JSON shape — so armA was
  handed the `required` field the rule under test introduces. A free-form
  rubric format is the real test; the 5/6 armA baseline is partly
  harness-induced.
- **Declaration effect is prompt-echo (eval B).** `CARRY_RE` matches
  `partial|carry|remainder|next round's queue` — verbatim armB vocabulary,
  absent from armA. Measuring whether output parrots terms the prompt just
  supplied is near-tautological; the "robust declaration effect" is *the model
  repeats the words it was given*, not an independent behavioral change. No
  length/attention-matched control arm exists.
- **Cap-violation grades as PASS (eval B-followup).** `leftover_named` counts a
  leftover ID as "acknowledged" even in a run that ignored the cap and
  processed it; `over_cap` is tracked but non-gating. The shipped cells all
  show `over_cap 0`, so the verdict stands, but the grader shape biases the
  cap-discipline question toward null.

## Deletion criterion (the accretion falsifier)

A standing critique: every rule this series added was kept — measured-lift →
keep, measured-null → keep for "declaration value." Nothing a measurement
returns ever *removes* a rule, so doctrine grows monotonically. The counterweight:
a rule is a **deletion candidate at the next `suite-health` pass** when ALL of —
(1) it measured behaviorally null, (2) it has no load-bearing mechanical
function (no lint/gate/hook depends on it), and (3) it is not cited/loaded by
another skill. The two rules here survive on (2)/(3) — eval-gate's `required`
criterion is read by the per-criterion gate; typed-stop feeds `loop_lint`
semantics — but the criterion now exists so a future null-and-inert rule can be
cut, not just accumulated. No composed-load eval exists yet (findings F6/F7/F12
live in rule *interactions*, which no single-rule eval measures) — that is the
one eval this series still owes.
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

## Follow-up: PHASE 0 + LANE REPORT behavioral A/B (2026-07-05, isolated cells)

Tested the two architect-loop adoptions ([[concepts/architect-loop-adoption-2026-07]])
now default in `brief_header.py`. Subjects: 6 naive haiku builder agents, each in
a **physically isolated** project tree (first run was void — a shared parent dir
let a cell read a sibling's already-written code, laundering the planted flaw;
re-run in `proj_<rand>/svc/` with cwd-confinement). Brief carried a planted trap:
"reuse the existing `load_yaml()`" — but the file only has JSON `load_config()`.
Arm A (n=3): brief WITHOUT PHASE 0 / LANE REPORT. Arm B (n=3): WITH. Grading is
deterministic from artifacts, not self-reports.

| signal | A (no rule) | B (PHASE 0 + LANE REPORT) |
|---|---|---|
| typed `STATUS:` line emitted | 0/3 | 3/3 |
| planted flaw escalated to reviewer (vs silently resolved) | 0/3 | 2/3 |
| phantom `load_yaml`+yaml dependency injected | 1/3 | 0/3 |

Read: the **declaration half is robust** (typed STATUS 3/3 vs 0/3 — same
declaration effect as the rules above), and unlike the earlier null results the
**behavioral half moved the right way**: every A cell noticed the `load_yaml`
discrepancy too, but all 3 silently resolved it in post-hoc "Assumptions"
("refers to load_config"), while 2/3 B cells raised it to the verifier as an
unresolved concern *before* closing — the PHASE-0 "silent compliance is a defect"
framing converted a quietly-papered ambiguity into a surfaced one. Modest n, and
consistent on the phantom-injection axis (0/3 vs 1/3).

**Caveat (eval-design debt, unpaid):** the trap was MILD — a rename a competent
subject resolves correctly on its own (5/6 did), so it under-tests the dangerous
case: a flaw that silently produces WRONG output. Behavioral lift on genuinely
costly flaws is still unmeasured — the same debt the rules above owe. Verdict:
ship-justified (declaration effect real + directional behavioral gain), not
"proven prevents bad builds."

**Also unverified live:** escalate-up's spawn-obedience. `classify.py` emits the
correct frontier-advisor directive in PROMPTER (confirmed), but the headless
`claude -p` run that would prove a cheap main loop ACTS on it hit a 401 (no auth
in that env). Directive-injection proven; spawn-obedience not. See
[[concepts/frontier-routing-topology-2026-07]].

## Related

- [[queries/external-validation]] — the adoption rows these rules came from
- [[concepts/team-lead-upstream-2026-07]] — never-sample rule, applied here to
  the eval's own cells
- [[concepts/architect-loop-adoption-2026-07]] — the rules under test here
- [[concepts/frontier-routing-topology-2026-07]] — escalate-up live-test status
