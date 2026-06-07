---
schema_version: 2
title: "demote-vs-description-tax"
type: concept
domain: "eval-methodology"
tier: semantic
confidence: 0.5
created: "2026-06-06"
updated: "2026-06-07"
verified: "2026-06-06"
sources: [eval/exp8_trigger/run_trigger.py]
supersedes: []
superseded-by:
tags: [eval-methodology, skills, description-tax, cost]
---

# demote-vs-description-tax

## Summary

Demoting a skill (`auto-install:false`) does not cut the always-on description tax; trimming the `description:` frontmatter text does.

## Evidence

- `eval/exp8_trigger` — top-1 trigger accuracy held 18/19 across a 1642→1505-token description trim.
- `static_cost.py` sums every skill's `description:` regardless of demotion (demoted skills stay symlinked).
- Demote helps only hook skills (skip per-turn wiring) and heavy-dep skills like compress-context (skip torch/llmlingua install).

## Related

- [[concepts/optimization-axes]]
- [[concepts/framework-hardening-adoption]]
- [[index]]
- [[schema]]

## Open Questions

- None yet.

## Lesson

DECISION: `auto-install:false` does NOT reduce the always-on description tax, because demoted skills stay symlinked and `static_cost.py` sums every skill's description regardless. The real lever is trimming the `description:` frontmatter text — verified safe via `eval/exp8_trigger` (top-1 trigger accuracy held 18/19 across a 1642→1505-token trim). Demote only helps hook skills (skip per-turn wiring) and heavy-dep skills like compress-context (skip the torch/llmlingua install).
