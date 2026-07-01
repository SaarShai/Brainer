---
trust: user_confirmed
schema_version: 2
title: "Premortem skill + /think edits — measured, mostly rejected"
type: concept
domain: "skill-authoring"
tier: semantic
confidence: 0.8
created: "2026-06-30"
updated: "2026-06-30"
verified: "2026-06-30"
sources:
  - "session A/B evals 2026-06-30 (scratchpad premortem-eval / premortem-tweak-eval / think-edits-eval): opus subjects, blind sonnet graders, seeded-flaw + sound-plan corpora"
  - "article: standalone `premortem` skill (Klein/Kahneman framing, 'Claude defaults to agreeable')"
tags: [skills, premortem, think, eval, ab-test, over-warning, sycophancy, negative-result, calibration]
supersedes: []
superseded-by:
---

# Premortem skill + /think edits — measured, mostly rejected

## Summary

**Trigger / symptom:** tempted to add a standalone `premortem` skill, or to enrich
`/think`'s premortem / anti-flattery lines, because an article pitches them.

**Finding:** tested each. Net result = **one** small measured win shipped to `/think`
(a per-failure early-warning-sign clause); everything else rejected. `/think` already
carried the premortem; a new skill wasn't justified.

## Why (decisions)

1. **No standalone premortem skill.** The article's premise ("Claude defaults to
   agreeable; ask 'is this good?' and it says yes") is **false for opus**: bare opus
   caught 10/12 seeded plan flaws, all 4 hidden assumptions, and endorsed **0 of 4**
   flawed plans. Detection was near-ceiling across bare / `/think`-line / full-method
   arms (10 / 11 / 12), so the method adds ~nothing over the existing `/think` bullet.
2. **Shipped: early-warning-sign clause.** Adding "…turn each into a preventive action
   plus one observable early-warning sign to watch for it" to `/think`'s premortem line
   was the one clean win **because** it lifted observable leading-indicators 1→21 across
   4 plans at zero detection cost — a behaviour the old "preventive action" wording did
   not elicit.
3. **Rejected: calibration / anti-over-warning clause.** Plain premortem framing
   **manufactures doom on sound plans** (7 manufactured failure-modes across 2 sound
   plans; it attacked a plan's *own* kill-switch + refund as "flaws"; false-alarmed 1/2).
   A calibration clause ("if the plan is sound, say so rather than manufacturing
   failures") fixes the over-warning (false-alarm 1→0) **but** consistently prunes a
   real *external/market* flaw (commoditization) on a genuinely flawed plan — flawed
   detection 2/2 → 1/2 in **both** the bundled and the isolated-scoped variant. Rejected
   **because** you cannot cut over-warning this way without also cutting the soft,
   contextual flaws — it biases toward plan-internal mechanics.
4. **Rejected: sharpening `/think`'s false-premise line (29).** Bare opus corrected
   **4/4** seeded false premises (GIL parallelism, binary-search-on-unsorted, "commit
   publishes to remote", "indexes always faster") unprompted — line 29 is not
   load-bearing for a strong model; verbatim and sharpened arms matched bare.
5. **Rejected earlier:** the "6-months-from-now" horizon (not a measurable lever; both
   no-horizon and 6-month arms near-ceiling) and the synthesis-schema enrichment
   (unmeasured; already reachable via `/think`).

## Durable insights

- **Premortem framing has a symmetric failure mode:** told to "find why it failed," a
  model manufactures plausible doom for a *sound* plan and attacks its own de-risking.
- **Calibration trades recall for calm** on the external/contextual class of flaws.
- **Strong models self-correct false premises and self-warn on bad plans** without the
  directive — anti-sycophancy directives aren't load-bearing for opus on these axes
  (mirror of [[concepts/systematic-debugging-skill-measured-null]]: the model already
  does it).

## Reusable method (the keeper)

To test a "how should the agent reason" directive: seed both **flawed** plans (planted
flaws → measure detection) **and genuinely sound** plans (→ measure **over-warning**:
false-alarm + manufactured-failure count, the novel instrument), plus false-premise
prompts (→ measure premise-correction). Blind grader, deterministic tally. The
sound-plan arm is what catches a directive that over-fires.

## Related

- [[concepts/systematic-debugging-skill-measured-null]] — sibling: article-pitched
  skill, A/B'd, not built.
- [[concepts/lean-execution]] — measure before adding; enrich existing over create new.

## Open Questions

- Is there a calibration wording that cuts sound-plan over-warning **without** pruning
  external/market flaws? Both tested variants failed; unclear if any single clause can.
