---
type: project
axis: skill_crystallization
tags: [skill, L3-sop, automation]
confidence: low
evidence_count: 0
---

# skill-crystallizer — auto-convert solved tasks → reusable L3 SOPs

**Status: IMPLEMENTED v1 DETECTOR.** Detects verified completed tasks and writes conservative repo-local `L3_sops/` candidates with wiki log/index refresh.

## When a task is "solved"

Heuristic signals (need ≥2 to fire):
1. User ended with positive close: "done", "works", "ship it", "good", ✓.
2. Recent test/verify/build command succeeded.
3. Recent git commit with non-trivial diff.
4. No open TodoWrite items flagged incomplete.
5. `verify` or `test` tool returned grounded=true within last 5 turns.

## Extraction

1. Detect verified completion from recent events.
2. Extract task title, reusable command/tool steps, changed files, and compact evidence.
3. Write a v2 `L3_sops/<slug>.md` page only when verified and non-trivial.
4. Append `log.md` and rebuild the wiki index.

## Hook

`detector.crystallize_task(events, root, task)` is the v1 entrypoint. A future `SessionEnd` hook can call it with host transcript events.

## Non-goals

- Not extracting general knowledge — that's L2 facts.
- Not creating SOPs for trivial one-tool tasks.
- Not overwriting existing SOPs (manual merge if pattern repeats).

## Not implemented yet
- Host-specific `SessionEnd` hook wiring.
- Optional LLM extraction/merge for repeated SOPs.
- Lifecycle status routing for richer task state.

## Borrowed from

- GenericAgent: `update_working_checkpoint` + `start_long_term_update` pattern.
- Our context-keeper v1: transcript parsing utilities (reused).
