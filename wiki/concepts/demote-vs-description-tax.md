---
schema_version: 2
title: "demote-vs-description-tax"
type: concept
domain: "eval-methodology"
tier: semantic
confidence: 0.5
created: "2026-06-06"
updated: "2026-06-06"
verified: "2026-06-06"
sources: []
supersedes: []
superseded-by:
tags: []
---

# demote-vs-description-tax

## Summary

One compact statement.

## Evidence

- Source or command path.

## Related

- [[index]]
- [[schema]]

## Open Questions

- None yet.

## Lesson

DECISION: `auto-install:false` does NOT reduce the always-on description tax, because demoted skills stay symlinked and `static_cost.py` sums every skill's description regardless. The real lever is trimming the `description:` frontmatter text — verified safe via `eval/exp8_trigger` (top-1 trigger accuracy held 18/19 across a 1642→1505-token trim). Demote only helps hook skills (skip per-turn wiring) and heavy-dep skills like compress-context (skip the torch/llmlingua install).
