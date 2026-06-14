---
schema_version: 2
title: "Progressive retrieval over a markdown wiki"
type: concept
domain: patterns
tier: semantic
confidence: 0.8
created: 2026-06-14
updated: 2026-06-14
verified: 2026-06-14
sources: [concepts/karpathy-wiki.md, projects/wiki-search.md, patterns/wiki-query-shortcircuit.md]
resource: skills/wiki-memory/tools/wiki.py
trust: corroborated
supersedes: []
superseded-by:
contradicts: []
tags: [retrieval, progressive-disclosure, wiki, memory, synthesis]
---

# Progressive retrieval over a markdown wiki

Higher-order synthesis of three same-subject pages the `synth-candidates` lens
clustered under `retrieval`. They are one principle realized at three levels;
kept separate **because** each answers a different query, and unified here
**so that** the through-line is findable in one place.

## The principle (concept)

Persistent markdown memory can replace loading a whole transcript or vector
store **when** it has a compact index, a stable schema, raw/source separation,
and progressive retrieval — see [[concepts/karpathy-wiki]]. The win is that an
agent fetches the *minimum necessary* instead of rehydrating everything.

## The implementation (project)

[[projects/wiki-search]] realizes it as a 3-layer API (adopting claude-mem's
pattern): `search` → tier-1 IDs + ~50–100-token previews; `timeline` → tier-2
neighbours + backlinks; `fetch` → tier-3 full page; plus an audited `context`
packet for task-scoped loading. Measured motivation: the wiki is 70+ files /
~400KB, **so** loading whole pages into context is wasteful and grep alone
returns structure-less fragments.

## The discipline (pattern)

[[patterns/wiki-query-shortcircuit]] is the habit that makes the machinery pay
off: search the wiki *before* reloading broad files or re-synthesizing known
facts — `search` → `timeline` → `fetch` only for relevant hits.

## Scope note

[[concepts/framework-hardening-adoption]] also carries the `retrieval` tag but is
a broader hardening/adoption record in which retrieval is one thread among many
(repo maps, graph memory, cache lifecycle) — related, not a fourth level.
