---
schema_version: 2
title: Wiki Query Shortcircuit
type: pattern
domain: framework
tier: procedural
confidence: 0.7
created: 2026-04-25
updated: 2026-04-25
verified: 2026-04-25
sources: [projects/wiki-search/README.md, raw/2026-04-17-research-brief.md]
supersedes: []
superseded-by:
tags: [wiki, retrieval, context]
---

# Wiki Query Shortcircuit

Search the repo-local wiki before reloading broad files or re-synthesizing known facts. Use `./te wiki search`, then `timeline`, then `fetch` only for relevant hits.

Related: [[projects/wiki-search/README]]
