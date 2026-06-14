# Instruction-efficacy A/B (#2): are the prose instructions load-bearing or inert?

**Question:** does prepending a SKILL.md body actually change the model's
behavior in the intended direction, or is some of the instruction prose inert
(model already does it / doesn't land)? Inert prose is dead weight — the
improvement is *removing* it, lowering on-invocation body cost.

## Method

`eval/inert_probe.py` — for each output-shaping prose skill, run tasks that
create an OPPORTUNITY for the skill's intended behavior:

- **BASELINE** = task only.
- **TREATMENT** = skill body + task.
- A deterministic scorer measures the intended behavior; a consistent
  treatment-vs-baseline delta in the expected direction == load-bearing.

Local model (`gemma2:9b`, temp 0 — clean instruct output, capable enough to
follow simple directives). Model-dependent, so this is a **flag, not a gate**: a
null delta could also mean "model can't follow," so it never auto-deletes prose.

## Results (gemma2:9b, 4 tasks/skill)

| Skill | Intended effect | base → treat | Δ | Verdict |
|---|---|---:|---:|---|
| verify-before-completion | demand verification before "done" | 0.25 → 2.25 | **+2.0** | load-bearing |
| plan-first-execute | plan before acting | 1.25 → 3.0 | **+1.75** | load-bearing |
| lean-execution | prune / minimal-action framing | 0.0 → 6.25 | **+6.25** | load-bearing |

Plus H4 (`eval/behavioral.py`): caveman-ultra 95.2% output-token reduction; think.
**5 of 16 skills now have behavioral evidence; 0 inert directives found → nothing
trimmed.**

## What this cost me to get right (two scorer traps — documented, not hidden)

The first two skills were clean. lean-execution took three passes — a worked
example of why a single number is not evidence until the instrument is
validated:

1. **Floor effect.** First tasks were trivial (fix a typo, rename a var) →
   baseline ceremony ~0, no room to move. Δ=+0.25 "WEAK/INERT?" was a *task*
   flaw. Fixed: tasks that TEMPT over-engineering (add an endpoint, a helper).
2. **Negation-blind scorer.** With tempting tasks, a ceremony-keyword count went
   the *wrong* way (Δ=+1.5 "BACKFIRES?") — because the lean body makes the model
   SAY "avoid tests/docs", and counting 'tests'/'docs' scored avoidance as
   ceremony. A **manual read of the raw outputs** confirmed the opposite:
   baseline lists "Document the new endpoint" unprompted; treatment explicitly
   "Delete extensive documentation before it exists", picks the "Smallest
   Reversible Action: barebones endpoint", "Avoid unnecessary refactoring".
3. **Direction-correct scorer.** Switched to measuring pruning/minimality
   *framing* (the intended effect): Δ=+6.25, unambiguously load-bearing.

Lesson (same family as the test-vacuity / negation-blind defects elsewhere in
this repo): a behavioral A/B is only as trustworthy as its scorer, and a scorer
is only trusted after a ground-truth read + a known-direction check.

## Scope + caveats

- Output-shaping prose skills are A/B-able this way; procedural/tool skills
  (wiki-memory, cache-lint, semantic-diff, …) are validated by their unit tests
  + measured gains (`eval/gains.py`), not by this harness.
- Single local model. A frontier model may already exhibit some of these
  behaviors by default, shrinking the delta — but a positive delta on a
  capable-enough 9B is strong evidence the instruction *lands* and is not inert.
- Verdict thresholds (|Δ|≥0.5) and scorers are heuristic; rows are printed so
  results are inspectable, not just a headline number.
