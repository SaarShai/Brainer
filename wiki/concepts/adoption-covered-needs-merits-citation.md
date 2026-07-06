---
schema_version: 2
title: Adoption "covered" claims need a merits citation
type: concept
domain: framework
tier: semantic
confidence: 0.8
created: 2026-06-27
updated: 2026-06-27
verified: 2026-06-27
sources: [concepts/framework-hardening-adoption.md, skills/impact-of-change/tools/impact.py]
supersedes: []
superseded-by:
tags: [adoption, review, method, verification, code-graph]
---

# Adoption "covered" claims need a merits citation

When reviewing an external project for adoption, the verdict **"we already cover
this / reject — covered"** is a *quality claim*, not a scope decision. It must be
backed by a **head-to-head merits citation**: name the specific Brainer consumer
path (`file:line`) that actually *exercises* the capability — not merely an
adjacent tool that exists in the same area.

## The failure mode

"Covered" asserted from a **catalog-line name-match** ("we have graphify, which
builds a code graph") instead of from **what the consumer actually reads**.

Concrete recurrence — the **same miss surfaced in two independent reviews**:

- **codebase-memory-mcp review** (prior) and **cognee review** (later) both
  marked code-structure impact as "covered by graphify."
- graphify's graph.json emits relations `{contains, method, inherits, calls}`
  (tool-verified). But [`impact-of-change`](../../skills/impact-of-change/tools/impact.py)
  built its dependent index from `CALL_RELATIONS = {"calls"}` only
  (`impact.py:37`, `:217`) — it **discarded the `inherits` edges already in the
  graph**. A base-class change therefore never propagated to subclasses *when
  evaluated by impact-of-change* — graphify emitted the edge; the consumer
  dropped it.
- Both reference projects *do* ship inheritance edges (cbm emits `"INHERITS"`/
  `"EXTENDS"` constants in `internal/cbm/extract_defs.c`; cognee carries
  `extended_from_class`). The capability was real on both sides; Brainer's
  *consumer* silently dropped it. "Covered" was true of the *emitter*, false of
  the *consumer*.

## The rule

1. A "covered" verdict cites the consumer `file:line` that reads the exact
   relation / field / behavior in question. If you cannot cite it, the claim is
   **unverified** — run the head-to-head before writing "covered."
2. For code-graph capabilities specifically: check **emitted-vs-consumed**. A
   relation present in the index but ignored by every consumer is *not* covered.
3. Distinguish **categorical-axiom rejects** (the capability needs infra Brainer
   deliberately avoids — vector/graph DB, LSP engine, RDF) from
   **similarity-asserted rejects** ("a Brainer skill covers it"). Only the
   second class is a quality claim; only it needs the merits citation. The first
   stands on scope and is safe without a deep read.

## Why it matters

A shallow "covered" silently drops a real, cheap, in-philosophy improvement. The
inheritance miss was a **consumer-side one-relation widening** of code already in
the graph — found only when the reject was re-audited head-to-head. See
[[concepts/framework-hardening-adoption]] (re-audit correction + cognee verdict).

## Related

- [[concepts/framework-hardening-adoption]] — the adoption matrix this rule guards
- [[concepts/write-gate-not-truth-filter]] — sibling: verdicts gate on evidence, not phrasing
- [[queries/covered-verdicts]] — the index this rule feeds: one row per already-settled verdict, so a future session never re-derives one from a catalog line
- `skills/impact-of-change/tools/impact.py` — the consumer the miss lived in
