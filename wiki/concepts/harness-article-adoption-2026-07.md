---
schema_version: 2
title: "Harness article adoption (2026-07) — framing, 3 shipped, 3 rejected"
type: concept
domain: "skill-authoring"
tier: semantic
confidence: 0.85
created: "2026-07-03"
updated: "2026-07-03"
verified: "2026-07-03"
sources:
  - "article: 'Anatomy of an Agent Harness' (2026, 12 components + 7 design decisions)"
  - "session review 2026-07-03: framing + adoption scoring + incident learning"
tags: [skills, harness, article-adoption, tool-scoping, error-taxonomy, negative-result]
supersedes: []
superseded-by:
---

# Harness article adoption (2026-07) — framing, 3 shipped, 3 rejected

## Summary

**Trigger / symptom:** reviewed "Anatomy of an Agent Harness" article (2026 formalization of 12 harness components + 7 design decisions) for Brainer adoption.

**Finding:** Brainer is a skill layer riding host harnesses, not a harness itself. ~85% of the article confirmed existing Brainer bets. Three concrete rules adopted (shipped in commits 2a36d13 + 8551662), three rejected on evidence or scope grounds.

## Why (decisions)

1. **Framing: category error avoidance.** The article's 12 components map primarily to host harness (orchestration loop, output parsing, permissions, sandboxing, prompt assembly, state persistence, subagent execution, guardrail tripwires) — ~8 of 12. Judging Brainer against host-owned components is a category error. **Because:** Brainer lives in the model-invocation layer (skills, directives, memory gates) and is orthogonal to transport/orchestration. Confirmed: ~85% of article reasoning already present in Brainer as parallel bets: verify split (verify-before-completion + eval-gate) mirrors article's "verify" design axis; memory-as-hint (wiki-refresh) mirrors "memory persistence"; compaction (context-keeper) mirrors "state compression"; Ralph loop concept mirrors loop-engineering memory contract + baton; single-agent-first mirrors our ORCHESTRATION.md.

2. **Adopted: cache-lint rule 7 UNUSED-TOOL-SURFACE.** Report-only WARN on project-scoped MCP servers with no `mcp__X__` usage in recent transcripts. **Because:** Vercel cut 80% of v0 tools, improved results — motivates surface reduction. Motivation confirmed measurable (precedent case + first-principles cost). Tests 20→23, all green, shipped in 2a36d13. **Scope boundary (by design):** rejected extending rule 7 to user-global ~/.claude.json — measured on this machine: 0 project servers, 1 global server, 51 project transcript dirs; global servers are cross-project so per-repo transcript mining cannot prove "unused anywhere" (false-positive by construction), and the session's ~150 resident tools are host-injected connectors with no readable config file to grep.

3. **Adopted: loop_lint R14 UNCLASSIFIED-FAILURE-POLICY.** WARN on unattended loop specs lacking an `on_error` failure classification (LangGraph taxonomy: transient→retry capped / recoverable-by-generator→error-as-observation / user-fixable→interrupt / unexpected→halt). **Because:** article surfaces "failure handling" as a design axis; loops are the recurring failure-mode context in Brainer (compare incident logs). Tests 116→120, all green, shipped in 8551662.

4. **Adopted: MEASUREMENT_QUEUE scaffold-shrink rule.** On each frontier-model release re-baseline default skills, demote vanished deltas (precedent: think→slash-only). **Because:** article emphasizes "measure design decisions"; frontier-model shifts are the recurring invalidation trigger. Queued as item 12; **gains NOT yet measured** — defer confidence until measured; recorded in GOAL.md backlog.

5. **Rejected: extending rule 7 to global ~/.claude.json.** False-positive by construction (cross-project tools cannot be proven locally unused) + host-injected tools have no config surface to audit. Scope boundary documented in cache-lint SKILL.md.

6. **Rejected: observation masking skill.** Host owns transcript; no new leverage without major refactor (not scoped). **Because:** article mentions "observability" as a design goal but implementation sits in orchestration layer, not skill layer.

7. **Rejected: "harness design" checklist skill.** Unmeasurable prose (premortem precedent: [[concepts/premortem-and-think-edits-measured]] showed checklist skills overfire and require calibration clauses that trade recall for false-alarm reduction). **Because:** wrote it down, tested the shape on a prior article, rejected. No remeasure needed.

## Incident learned

**Codex-reverts-dirty-tree incident:** a codex-rescue agent implementing rule 7 reverted concurrent uncommitted work (SKILLS_INDEX/MEASUREMENT_QUEUE edits + a GLM agent's in-progress loop_lint.py rule) as "out-of-scope diffs since initial git status was clean". Only .gitignored paths survived.

**Decision:** isolate strict-scope executors (worktree/clean tree) or explicitly whitelist concurrent diffs. **Applied:** re-grep own edits after any codex run (now standard practice in this session).

**Durability:** recorded in memory for [[propagate]] runs to sibling repos (isolated worktrees mandatory before multi-agent syncs).

## Durable insights

- **Article-pitched additions mostly confirm-or-reject, rarely net-new.** The premortem-and-think-edits-measured session (2026-06-30) predicted this shape; linking it here as validation of the measurement-before-adopting discipline.
- **Scope boundary is sharp: skill layer ≠ harness layer.** Trying to adopt harness-level rules into a skill catalog surfaces category errors (not-in-our-control components) and false positives (config files we cannot audit). Better to document the boundary and skip category-error adoptions.
- **Three-rule adoption rate is consistent.** Compare: framework-hardening-adoption, understand-anything-adoption — article reviews converge on ~3 adopted of 7-12 proposed. This consistency suggests a stable filtering method; note for future article reviews.

## Related

- [[concepts/premortem-and-think-edits-measured]] — article-pitched additions usually confirm/reject, rarely net-new; measured win + measured rejections on evidence.
- [[concepts/lean-execution]] — measure before adding; enrich existing over create new. Extended here: category-error detection (skill vs harness) is a scope-boundary special case.
- [[concepts/systematic-debugging-skill-measured-null]] — sibling precedent: article-pitched skill, A/B'd, not built.
- [[concepts/framework-hardening-adoption]] — earlier article review; same 3-adoption pattern.
- [[GOAL.md]] — MEASUREMENT_QUEUE item 12 queued for gains measurement on next frontier-model release.
- [[projects/okf-adoption]] — memory-as-hint precedent (article pitch adopted via wiki-refresh reconciliation).

## Open Questions

- Is the 3-of-7 adoption rate on articles a real regularity or sampling noise? (Need 2-3 more data points to call it a pattern.)
- Can cache-lint rule 7 scale to "unused-in-recent-sessions" across a fleet (not just single-machine globals)?
