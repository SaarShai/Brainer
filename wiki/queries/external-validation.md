---
trust: corroborated
schema_version: 2
title: "External-review corroboration of Brainer loop/memory doctrine (one row per source)"
type: decision
domain: "framework"
tier: episodic
confidence: 0.6
created: "2026-06-25"
updated: "2026-06-25"
verified: "2026-06-25"
sources: ["warpdotdev-demos/replatformer", "Anthropic enterprise PDF", "Loop Engineering playbook", "arXiv:2604.01687"]
supersedes: []
superseded-by:
tags: [decision, validation, loop-engineering, external-review]
---

# External-review corroboration (one row per source)

Consolidated record of external sources reviewed against Brainer doctrine. One
ROW per source — a page per source is exactly the accretion this page exists to
avoid. Most sources only CORROBORATE what Brainer already does (no change
earned). Only CoEvoSkills earned changes.

| source | claim it validates | what Brainer already EXCEEDS / what we adopted |
|---|---|---|
| warpdotdev-demos/replatformer | generator→verifier loop with a machine gate, budget cap, fan-out per file | Brainer EXCEEDS: `loop_lint.py` refuses no-gate/self-grading/unbounded statically (R1/R2/R3); replatformer asserts the pattern in prose, we enforce it. No change. |
| Anthropic enterprise PDF | harness pre-flight (context/tools/permissions/hooks/memory) before scaling an autonomous loop; human gate before irreversible actions | Brainer EXCEEDS: pre-flight is already a SKILL.md section and R7/R10 flag irreversible/unbounded side effects statically. No change. |
| Loop Engineering playbook | "chain of self-persuasion" — a verifier that reads the generator's own justification inherits its bias | Adopted (reinforces R3): the verifier must be BLIND to the generator's reasoning/code/skill content, not merely a different actor. Drove the R3 blind-verifier wording tightening. |
| CoEvoSkills (arXiv:2604.01687) | info-isolation between proposer and evaluator; two-tier verify (objective check + independent judge) co-evolving skills | EARNED CHANGES (the only source that did): (1) two-tier verify folded into the outer-loop build; (2) the R3 tightening so the verifier sees only task + outputs, not the generator's self-justification. |

## Decision

Sources that merely restate Brainer's existing gates earn NO edit (bloat-guard:
"validation" / "we were right" is not a feature). CoEvoSkills is the sole source
that named an uncaught failure mode — a verifier reading the generator's
reasoning inherits its bias even when it is a different actor — so it earned the
R3 blind-verifier tightening (in `skills/loop-engineering/tools/schema.md` and
`skills/loop-engineering/SKILL.md`) plus the two-tier verify in the outer-loop
build.

## Related

- [[memory-as-a-tool-validation]]
- [[index]]
- [[schema]]
