---
trust: corroborated
schema_version: 2
title: "External-review corroboration of Brainer loop/memory doctrine (one row per source)"
type: decision
domain: "framework"
tier: episodic
confidence: 0.6
created: "2026-06-25"
updated: "2026-07-05"
verified: "2026-07-05"
sources: ["warpdotdev-demos/replatformer", "Anthropic enterprise PDF", "Loop Engineering playbook", "arXiv:2604.01687", "openforage loops article (2026-07)", "EXM7777 Fable Loop Library (2026-07)", "DannyMac180/fable-advisor (2026-07)", "0xCodez 14-step Fable system (2026-07)"]
supersedes: []
superseded-by:
tags: [decision, validation, loop-engineering, external-review]
---

# External-review corroboration (one row per source)

Consolidated record of external sources reviewed against Brainer doctrine. One
ROW per source — a page per source is exactly the accretion this page exists to
avoid. Most sources only CORROBORATE what Brainer already does (no change
earned). Only CoEvoSkills and the openforage loops article earned changes.

| source | claim it validates | what Brainer already EXCEEDS / what we adopted |
|---|---|---|
| warpdotdev-demos/replatformer | generator→verifier loop with a machine gate, budget cap, fan-out per file | Brainer EXCEEDS: `loop_lint.py` refuses no-gate/self-grading/unbounded statically (R1/R2/R3); replatformer asserts the pattern in prose, we enforce it. No change. |
| Anthropic enterprise PDF | harness pre-flight (context/tools/permissions/hooks/memory) before scaling an autonomous loop; human gate before irreversible actions | Brainer EXCEEDS: pre-flight is already a SKILL.md section and R7/R10 flag irreversible/unbounded side effects statically. No change. |
| Loop Engineering playbook | "chain of self-persuasion" — a verifier that reads the generator's own justification inherits its bias | Adopted (reinforces R3): the verifier must be BLIND to the generator's reasoning/code/skill content, not merely a different actor. Drove the R3 blind-verifier wording tightening. |
| CoEvoSkills (arXiv:2604.01687) | info-isolation between proposer and evaluator; two-tier verify (objective check + independent judge) co-evolving skills | EARNED CHANGES (first source to): (1) two-tier verify folded into the outer-loop build; (2) the R3 tightening so the verifier sees only task + outputs, not the generator's self-justification. |
| 0xCodez "Build self-improving agent system with Fable 5 in 14 steps" (X article 2065089060104720776; text + 11 images transcribed) | verifier-sub-agent > self-critique, worktree isolation, state write/read discipline, skills-that-compound, 4-tier cost routing, 5-stage memory ladder (fail→investigate→verify→distill→consult) | 11/14 steps already core doctrine (R3, R9, R8 + context-keeper, learn-skill/task-retrospective, ORCHESTRATION §1+§6); 5-stage ladder decomposes onto write-gate (stage-3 verify gate) + task-retrospective (distill) + index-first/wiki (consult); "Dreaming" consolidation ≈ consolidate-memory + wiki-refresh. EARNED 2 deltas: (1) vision-verify rule in verify-before-completion (visual artifact → render + vision check vs goal/prior state; text-only checks can't see layout/overlap failures); (2) policy/classifier-block added as a failure class to R14's on_error taxonomy — provider safety layer declines + may silently substitute a weaker model (benchmark footnote corroborates: Fable→Opus fallback on cyber/bio), so re-route lane, never retry same lane; ties into ORCHESTRATION §6 verify-the-pin. |
| DannyMac180/fable-advisor (GitHub plugin, 331 lines; skill_audit PASS) | architect pattern: frontier session owns spec/routing/verdicts, cheap lanes emit code; 4-lane routing table; 5-part spec contract; advisor at commitment boundaries; codex lane w/ no-silent-fallback | Brainer EXCEEDS on routing table, delegation gates (two-strike), fail-closed reachability, cross-vendor panels, race-and-judge. EARNED ORCHESTRATION.md §6 "Architect cost discipline" (tier-generalized per user note — any frontier model, not Fable): (1) token-volume inversion stated as principle + "code block > interface signature = un-delegated spec" + corrected-spec-not-hand-fix; (2) pre-decision commitment-boundary skeptic consult (Brainer previously triggered on stuck/ship-time only); (3) verify-the-pin — host silently substitutes session model on unavailable pin, dispatch SUCCEEDS on wrong model (reachability detection can't catch); lane re-routes reported loudly. Advisor "don't manufacture objections" prompt-craft noted but not adopted (over-warning measured negative). |
| EXM7777 "The Fable Loop Library: 25 Workflows" (X article 2073432521954697653, 2026-07-04; text + all 25 prompt cards transcribed) | five-part loop anatomy (schedule/one-change/same-check/state-file/stop), autonomy colors, run-by-hand-first, cheap-first routing, pasted-proof done contract | Brainer EXCEEDS on most: colors < R7/R10 mechanical gates; "pasted proof" is generator-self-reported and fabricable vs verify-before-completion's fresh recompute; prompt-level "data not instructions" clauses < harness-enforced quarantine; uplift-metered escalation ≈ cost-per-accepted-change + prompt-triage; premortem PREVENTED/CARRIED ledger skipped (prior measured negative: [[concepts/premortem-and-think-edits-measured]]). EARNED 3 deltas, all loop-engineering: (1) typed stop states done · no-op · partial-carry · blocked/escalate (no-op kills make-work rounds — "don't invent one to feel busy"; partial-carry kills silent drops at cap); (2) freeze-the-check + ONE-change-per-round for scheduled loops (cross-round comparability + attribution); (3) evidence floor on noisy-signal gates (≥N independent cited instances, else no-op). |
| openforage "How To Use Loops In Agentic Engineering" (2026-07) | fresh-context blind verifier, rubric-guided verification, threshold/plateau stops, budget caps, north-star anti-drift | Brainer EXCEEDS on verifier isolation (R3/R13 blind > article's "fresh"), rubric machinery (eval-gate per-criterion + panel), stops (stuck detector + R2). EARNED 3 deltas: (1) spec-tied `required` rubric criterion rule (eval-gate SKILL step 1 + rubric.example.md); (2) first-gate-check-early-in-budget rule (loop-engineering spec questions); (3) `compromises` extraction category in context-keeper (regex + LLM) — compaction otherwise launders settled-for choices into "intended design". |

## Decision

Sources that merely restate Brainer's existing gates earn NO edit (bloat-guard:
"validation" / "we were right" is not a feature). CoEvoSkills named an uncaught
failure mode — a verifier reading the generator's
reasoning inherits its bias even when it is a different actor — so it earned the
R3 blind-verifier tightening (in `skills/loop-engineering/tools/schema.md` and
`skills/loop-engineering/SKILL.md`) plus the two-tier verify in the outer-loop
build.

The openforage loops article (2026-07) was 6/9 corroboration; three claims
survived the covered-needs-merits-citation check as real gaps: no rule forced a
spec-fidelity dimension into gate rubrics (hill-climb-polish-while-drifting),
no rule about when in the budget the FIRST verification lands, and
context-keeper's extraction categories had no compromise markers (its
"decisions" list flattened workarounds into intended design). All three shipped
as one-sentence rules / one extraction category — deliberately prose-sized; no
new lint rules since cadence and spec-fidelity aren't statically checkable.

## Related

- [[memory-as-a-tool-validation]]
- [[index]]
- [[schema]]
