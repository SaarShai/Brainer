---
trust: user_confirmed
schema_version: 2
title: "systematic-debugging skill — measured null, reverted"
type: concept
domain: "skill-authoring"
tier: semantic
confidence: 0.85
created: "2026-06-30"
updated: "2026-06-30"
verified: "2026-06-30"
sources:
  - "session A/B eval 2026-06-30 (scratchpad/debug-eval): 4 toy bugs x {bare,skill}, sonnet subjects, hidden truth-test verifier"
  - "session A/B eval 2026-06-30 (scratchpad/debug-eval-hard): 5 hard multi-file / stateful / silent / decoy bugs x {bare,skill}, OPUS subjects — replicated the null"
  - "article 'From Average to Top 1%: How to Truly Master Claude' (steal-these-prompts: reproduce-with-a-failing-test-first)"
supersedes: []
superseded-by:
tags: [skills, debugging, eval, ab-test, negative-result, redundancy, rule-of-three]
---

# systematic-debugging skill — measured null, reverted

## Summary

**Trigger / symptom:** tempted to build a `systematic-debugging` skill (root-cause
phases: reproduce-first → isolate → fix-at-root → verify-no-regression), because a
popular article names it as a top-tier move.

**Finding:** built it, A/B-tested it against no-skill, and it produced **zero lift**
on every quality axis — so it was **reverted** (deleted), not adopted. The null
**replicated across model tier (sonnet → opus) and difficulty (toy → hard multi-file
/ stateful / silent / decoy-trapped)**: 18 runs, identical fixes both arms. Its
reflexes are already owned by verify-before-completion + lean-execution +
impact-of-change, and frontier models already reproduce, root-cause, resist decoy
fixes, and stay surgical unaided.

## Why (decision)

Reverted **because** two independent A/B runs measured a clean null with a positive
cost: identical fixes for more work. Keeping an unproven, cost-adding recombination
of three existing skills on the auto-fire path contradicts Brainer's "only
measured-win or cheap load-bearing skills sit on the default path" policy — the same
reason `delegate` / `compress-context` were cut. An auto-firing debugging skill would
impose repro ceremony on the common easy-bug case (it even wrote a repro test for a
one-line `!!`→`!` typo) **in order to** buy insurance that never paid off, even on
bugs engineered to defeat guess-and-check.

## Evidence

Design (both runs): each subject saw a `SYMPTOM.md` + a visible regression test but
**never** the hidden `truth_test` the harness ran afterward. The hidden test asserts
the **root contract** (e.g. `parse_row("x:10")[1] == 10`), so a symptom-local decoy
passes the visible case but fails generalization → the harness discriminates
root-cause fixes from band-aids **on exit codes alone, no grader**. Arms: `bare`
(minimal prompt) vs `skill` (bare + injected 4-phase method). Isolated per-run dirs
outside the repo; subagents told no git/commit; repo verified clean after.

| regime | subjects | bugs | clean-fix bare/skill | blast bare/skill | wrote-repro bare/skill |
|---|---|---|---|---|---|
| toy (`debug-eval`) | sonnet | 4 (mutable-default, off-by-one, swallowed-except, trivial) | 4/4 · 4/4 | 10 · 10 | 0/4 · 4/4 |
| hard (`debug-eval-hard`) | **opus** | 5 (cache-invalidation, shared class attr, unsorted-merge, str-vs-int cross-file, trivial) | **5/5 · 5/5** | **10 · 10** | 0/5 · 5/5 |

In the hard run the `bare` and `skill` source diffs were **byte-identical** on every
bug, and **both arms fixed the decoy-trapped h4 at the source** (`parse.py`, not the
symptom-site sort key in `inventory.py`). The skill's sole effect was a repro test on
every bug (incl. the typo) at ~1.2–1.8× the tool calls. No placebo arm was run —
pre-registered as gated on "skill beats bare," which failed in both regimes.

## Scope limit (what is and isn't shown)

Two regimes tested: toy self-contained bugs (sonnet) and hard multi-file / stateful /
silent / decoy bugs (opus). Both null. This is strong evidence the skill is redundant
for **frontier models on synthetic bugs up to the difficulty a scratchpad can
manufacture**. It is **not** proof about **real large unfamiliar codebases**
(thousands of LOC, cross-package, poor tests) where even a strong model may genuinely
flail — the synthetic corpus could not induce that (opus root-caused even the
decoy-trap). Absent a measured win, there is nothing to ship on the default path.

## Revisit condition

Only reconsider with a corpus of **real historical bugs from large codebases** where
a `bare` frontier agent demonstrably flails — symptom-patches that fail a hidden
generalization test, or thrash across files. Synthetic single-concept bugs (any
difficulty) will not separate the arms; frontier models already root-cause them.

## Reusable method (the keeper)

The eval *design* generalizes to any "does this methodology change behavior?"
question: **naive subjects + a hidden truth-test the subject can't see** (only a
visible symptom + regression), scored deterministically on exit codes + a file-diff
blast metric — no grader. A symptom-patch passes the visible case but fails the hidden
generalization check, so the harness separates root-cause fixes from band-aids
mechanically. Pairs with Brainer's behavioral test method (naive subjects, cold
deterministic scoring).

## Related

- [[concepts/when-to-extract-a-skill-md-section-into-tools]] — sibling "don't add the
  artifact unless it earns its keep" skill-authoring lesson.
- [[concepts/lean-execution]] — YAGNI / rule-of-three; a new skill earns its place on
  the 3rd real repeat, not on an article's say-so.

## Open Questions

- Even hard synthetic multi-file bugs didn't make opus flail. Is there any source of
  *genuinely* agent-defeating debugging tasks short of real production incidents
  (e.g. mined from bug-fix commits in large OSS repos with the fix withheld)?
