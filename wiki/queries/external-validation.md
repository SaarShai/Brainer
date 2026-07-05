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
sources: ["warpdotdev-demos/replatformer", "Anthropic enterprise PDF", "Loop Engineering playbook", "arXiv:2604.01687", "openforage loops article (2026-07)"]
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
