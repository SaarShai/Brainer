---
trust: user_confirmed
schema_version: 2
title: "When to extract a SKILL.md section into tools/"
type: concept
domain: "skill-authoring"
tier: semantic
confidence: 0.6
created: "2026-06-30"
updated: "2026-06-30"
verified: "2026-06-30"
sources:
  - "wiki/log.md#2026-06-30 — skill-suite lean-pass (extract → cross-vendor review → revert 3)"
supersedes: []
superseded-by:
tags: [skills, authoring, refactor, extraction, bloat, lazy-load]
---

# When to extract a SKILL.md section into tools/

## Summary

**Trigger / symptom:** about to move a catalog or section out of a SKILL.md body into a `tools/*.md` "to reduce bloat" / shrink the line count.

**Rule:** extract only when ALL four hold — the block is (1) large, (2) pure author-reference (not the step protocol the agent executes), (3) stable (not a freshly-added, still-changing feature), and (4) the skill is rarely loaded. Otherwise keep it inline.

## Why

Trimming body lines buys ~0 boot-token savings **because** SKILL.md bodies lazy-load on trigger, not at boot — so the line count is a misleading "bloat" signal. Meanwhile each extraction costs +1 file, an indirection hop, and a body↔file drift surface. So a body→`tools/` split is net-negative unless the block is big / pure / stable / cold; a skill that loads its whole body on invoke (e.g. a slash skill) gets no token win from extraction at all.

## Evidence

2026-06-30 lean-pass over the Brainer skill suite (`skills/`): 5 extraction candidates considered. Only `compliance-canary`'s 9 probe-kind JSON schemas (~134 lines, pure author-reference) qualified → `tools/PROBES.md` (body keeps the probe names + one-liners). The other 3 were reverted:

- `think/CODICES.md` — the ideation catalog is unique to `think` AND `/think` loads its whole body, so extraction saved no tokens and only added a hop.
- `wiki-memory/quality-scans.md` — the OKF / eval-lens verbs were freshly added and still stabilizing, so extracting a moving target invited body↔file drift.
- `loop-engineering/multi_model.md` — netted only 191→188 body lines while adding a file + indirection.

The first pass extracted all 5; a cross-vendor review (GLM-5.2 via z.ai) plus a re-think reverted 3. See `wiki/log.md` 2026-06-30.

## Corollary

Prefer **link-don't-restate** for genuine cross-skill *duplication* (collapse to one canonical home + a pointer), but keep a terse inline gist for a single load-bearing rule so the skill still works standalone if the pointer rots. Relocating a *unique* catalog is not the same as deduplicating a *restated* rule — only the latter is a clear win. Related practice: [[superpowers-skills]] (small named skills, evidence before completion).

## Related

- [[superpowers-skills]]
- [[index]]

## Open Questions

- Should a `suite-health` check flag bodies that grew a large pure-reference block, to surface extraction candidates without hand-auditing? (Deferred — adding tooling was judged scope-creep in the 2026-06-30 pass.)
