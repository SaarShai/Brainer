---
schema_version: 2
title: Prefix Caching
type: concept
domain: framework
tier: semantic
confidence: 0.65
created: 2026-04-25
updated: 2026-04-25
verified: 2026-04-25
sources: [raw/2026-04-17-research-brief.md, raw/m5-outputs-2026-04-18/P5_anthropic_cache_best_practices.md]
supersedes: []
superseded-by:
tags: [prompt-caching, cost]
---

# Prefix Caching

Prompt caching rewards stable prefixes. Put stable instructions, schemas, examples, and reference material before volatile user/task content. Avoid rewriting always-loaded files unless the cache win is worth invalidation.

## Repo rule

- Keep `start.md`, `L0_rules.md`, `L1_index.md`, and matched `SKILL.md` files small and stable.
- Do not put task facts, session notes, raw command output, or temporary decisions into always-loaded files.
- Put durable but situational knowledge in wiki pages, then retrieve it with `./te wiki context` only when relevant.
- For code tasks, use `./te code map` and `rg` before loading files. A smaller changing suffix lets the stable prefix stay cacheable.
- For background workers, prefer batched/non-interactive prompts where the host supports them.

Prompt caching is not a substitute for retrieval discipline. The best cache hit is still worse than not sending irrelevant context.

Related: [[raw/2026-04-17-research-brief]], [[projects/delegate-router/README]]
