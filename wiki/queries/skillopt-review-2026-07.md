---
trust: verified
schema_version: 2
title: "SkillOpt review 2026-07"
type: decision
domain: "framework"
tier: episodic
confidence: 0.7
created: "2026-07-20"
updated: "2026-07-20"
verified: "2026-07-20"
sources: ["github.com/microsoft/SkillOpt", "arxiv 2605.23904", "sol gpt-5.6 no-web consult 2026-07-21", "deep-read agent 2026-07-21"]
supersedes: []
superseded-by:
tags: [decision, skillopt, skill-optimization, adoption, learning-loop, eval, covered]
---

# SkillOpt review 2026-07 — one conditional adoption, rest covered or rejected

**Trigger / symptom:** evaluating microsoft/SkillOpt (or any automated skill-optimizer: TextGrad, GEPA, EvoSkill) for Brainer; proposal to auto-train/optimize SKILL.md prose; "no skill edit without validation score" gate proposals.

## What was reviewed

microsoft/SkillOpt (verified real: microsoft org, ~13.5k stars, MIT, arXiv 2605.23904, v0.2.0 Jul 2026): trains one markdown skill doc for a frozen agent — scored rollouts → optimizer model proposes bounded edits under a token budget → accepted only on strict held-out validation improvement; rejected-edit buffer; "SkillOpt-Sleep" nightly self-evolution. Claims best-or-tied on 52/52 cells across 6 benchmarks × 7 models × 3 harnesses (incl. Claude Code); +19–25 pts over no-skill. **All evals vendor-run, zero independent replication, open issues report test-split/score inconsistencies** — banked as low-trust external evidence, not corroboration, because vendor-run results cannot upgrade our own doctrine's trust tier.

Method: deep-read agent → mechanism-level mapping vs LEARNING_CONTRACT §3/§5/§6 + learn-skill + E2 history → Sol (gpt-5.6) cold consult (first run hung 28 min in web-search and was cancelled; no-web retry answered in ~2 min — see lesson in body).

## Rulings (Sol-reconciled, citations repo-verified)

1. **Skill-size (300–2,000 tok) and cross-harness transfer findings: LOW-TRUST EVIDENCE, cite-only.** Benchmark-conditioned vendor numbers; consistent with trim doctrine but no doctrine change.
2. **Acceptance gate: ADOPTED (ratified 2026-07-21, owner-delegated; landed in docs/TESTING_SKILLS.md).** A universal "no prose edit without non-regression score" would certify evaluator noise — our own E2 history holds nulls, prompt-echo scoring, and grader bugs that moved apparent lift 0.667→0.0 ([[concepts/e2-prose-rules-measured-2026-07]]). learn-skill's `refine`/`patch` already implements the lean version (held-in/held-out gates, rollback). Proposed doctrine paragraph (for TESTING_SKILLS.md, on ratification): *when a skill already has a frozen, trustworthy behavioral corpus + scorer + baseline, a behavior-affecting body edit must rerun that exact gate; reject attributable regression or threshold failure; neutral results ship only for a named mechanical/declaration benefit; absent a trustworthy evaluator this rule creates no obligation to invent one.*
3. **Running SkillOpt on Brainer skills: REJECT.** Hundreds of rollouts against unreliable per-skill scorers optimizes grader artifacts. Reopen after independent replication AND one Brainer skill acquires a trusted automatic scorer.
4. **SkillOpt-Sleep: REJECT (boundary already drawn).** Brainer permits unattended *observation* (append-only telemetry) but never unattended *mutation* (learn-skill boundary); Sleep crosses it.
5. **Rejected-edit buffer: REJECT.** Unobserved problem; [[queries/covered-verdicts]] + task-retrospective reports already record rejections. Reopen after two independently initiated, semantically equivalent skill edits are re-proposed despite an accessible prior rejection.
6. Bounded edits / frozen checks / proposer-verifier separation / rollback / slow promotion: already present (surgical diffs, learn patch, §5, promotion telemetry). "Textual learning rate" = citation, not mechanism.

## Operational lesson (consult transport)

A repo-grounded codex consult investigates fine locally but can hang indefinitely in its web-search phase (28 min wedged, log timestamps frozen — because the search turn dies without erroring). Prevention: give consults an explicit **no-web constraint** when the brief already contains the external facts, and inject any interim findings from a cancelled run into the retry so the investigation isn't repeated. The no-web retry answered both pending briefs in ~2 min.
