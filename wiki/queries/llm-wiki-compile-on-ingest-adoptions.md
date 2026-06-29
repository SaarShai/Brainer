---
trust: asserted
schema_version: 2
title: "Adopting Karpathy LLM-Wiki compile-on-ingest"
type: decision
domain: "patterns"
tier: episodic
confidence: 0.7
created: "2026-06-29"
updated: "2026-06-29"
verified: "2026-06-29"
sources: ["Karpathy LLM-Wiki (compile-not-retrieve)", "GLM-5.2 cross-vendor review (2026-06-29 session)"]
supersedes: []
superseded-by:
tags: [decision, wiki-memory, ingest, provenance, quorum, paper]
---

# Adopting Karpathy LLM-Wiki compile-on-ingest

## Question

What should Brainer adopt from Karpathy's LLM-Wiki ([[karpathy-wiki]], "compile-not-retrieve"), and what is genuinely missing in wiki-memory?

## Decision

Adopt compile-on-ingest, but **gate it for autonomy** so the wiki compounds *without* abandoning poison-defense. Built 2026-06-29:

1. **Belief-update propagation** — `wiki.py stale-citers`: surfaces pages whose body cites a `superseded-by`/`contradicts:` page (a supersession does not ripple to its citers). Report-only; wired into [[wiki-governance]]'s reconcile (wiki-refresh). **In order to** stop a superseded claim from living on through stale citations.
2. **Quorum gate** — `provenance.quorum_decision` + `wiki.py quorum`: a compile candidate auto-files only at `corroborated+` (≥2 independent sources / verified / user-confirmed); a single unverified source is **quarantined as an `asserted` draft and surfaced to the user**. Exists **because** the write-gate scores form not truth ([[write-gate-not-truth-filter]]) — the human / a second source / a verify step is the only thing that earns durable trust.
3. **Query-compounding reflex** — file a substantive multi-page synthesis back into `queries/` (this page is the first instance), **so that** exploration compounds instead of being re-derived. Complements [[progressive-retrieval]].

## Rationale

Brainer's wiki-memory is already a Karpathy 3-layer implementation and a **superset** of the paper on retrieval (FTS5+rank), lint (8 lenses), and poison-defense (trust tiers + `resolve` + `contradict-scan`). Two gaps remained, with a deeper one beneath:

- **Visible gap:** the `ingest` verb only *deposited* a raw file; the compile half (summarize → extract → propagate → backlink → flag contradictions) was absent — the paper's namesake primitive.
- **Deep gap (the decisive one):** the paper's ingest+lint assume a **human reviews output for truth**. Brainer is autonomous and removed that human, so naive auto-compile would calcify unverified syntheses *faster*. Independently confirmed by a cross-vendor GLM-5.2 review and a `/think` self-check.

## Alternatives (rejected)

- **L1_index boot-budget guard** — premature at ~38 pages (paper's ceiling is "few hundred"); watch, don't build.
- **14-day TTL auto-purge** (GLM proposal) — conflicts with Brainer's supersede-don't-delete law and `decay` (age confidence, never delete).
- **Claim→source-chunk traceability** — real but over-built for this scale; backlog.

## Related

- [[karpathy-wiki]]
- [[write-gate-not-truth-filter]]
- [[wiki-governance]]
- [[progressive-retrieval]]
- [[index]]

**Trigger / symptom:** "what should we take from Karpathy's LLM-Wiki / why doesn't Brainer auto-compile sources" → start here before re-deriving the gap analysis.
