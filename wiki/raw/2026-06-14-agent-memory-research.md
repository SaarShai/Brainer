---
schema_version: 2
title: "Agent-memory practice research (Anthropic/OpenAI/Google/OSS/PKM)"
type: source-summary
domain: framework
tier: semantic
confidence: 0.8
created: 2026-06-14
updated: 2026-06-14
verified: 2026-06-14
sources: [https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents, https://arxiv.org/html/2501.13956v1, https://raw.githubusercontent.com/mem0ai/mem0/main/mem0/configs/prompts.py, https://arxiv.org/html/2502.12110v1, https://notes.andymatuschak.org/Evergreen_notes_should_be_concept-oriented]
resource: skills/wiki-memory/tools/wiki.py
trust: corroborated
supersedes: []
superseded-by:
contradicts: []
tags: [research, agent-memory, contradiction, synthesis, claim-quality, maturity, backlog]
---

# Agent-memory practice research

5-agent research pass (2026-06-14) on how leading players handle our four epistemic
angles, scoped to NET-NEW, lean, deterministic, report-only ports. Extract the
*rules*, reject the *infra* — **because** every framework here is LLM+embedding-
backed by default and our constraint is no-ML-deps.

## Adopted (shipped)

- **Resolution-verb stage** on `contradict-scan` (`de1e65e`): Zep "invalidate-don't-
  delete / newer-info-prioritized" + mem0 polarity→invalidate / value→supersede,
  keyed on our trust tier + `updated` date. Emits `suggested_resolution`
  (invalidate / supersede / dispute), report-only. Closed our measured weakest
  area: we detected contradictions but never emitted what to do.

## Backlog — dispositions

**Shipped (2026-06-14):**
- ~~Evidence-accrual promotion~~ (A-MEM) → `maturity.corroborating_inbound` (`960db6e`):
  citations from observation pages = evidence, distinct from popularity.
- ~~Falsification-condition on rules~~ (LangMem/Popper) → `maturity` promotion
  readiness flag `has_falsifier` (`e8185e2`); applied as a promotion gate (not a
  flag on all rules, which would be noise).

**Deferred — marginal (revisit only if a real failure shows up):**
- **Subject+predicate key prefilter** (Zep same-entity-pair) — `same_subject`
  already covers most of it; measured FPs already ~0 on Brainer, 2 on PROMPTER.
- **Access-frequency decay** (mem0/Memary) — we count fetches in
  `.brainer/usage.json`, but it is tangential to the four epistemic angles and
  touches `decay.py`'s regression surface; not worth it now.
- **Quality-delta gate** (mem0 enrich-vs-rephrase) — marginal over `overlap`/
  `novelty`, and modifying `write_gate.py` carries regression risk.

**Rejected on reflection:**
- **Louvain community synthesis** (txtai) — a `networkx` dep (or ~100 lines of
  modularity code) for a marginal synthesis-clustering gain, on a lean no-deps
  report-only tool **to avoid** dependency creep. Tag-clustering already works.

## Rejected (with reason)

- **Graph DB / Neo4j / temporal KG infra** (Zep/Graphiti/cognee) — adopt the rule
  (~30 lines), reject the rewrite. Our prior pass already deferred this.
- **Embeddings everywhere** — only one justified exception (paraphrase-contradiction
  MiniLM on already-flagged same-subject pairs, behind a flag, gated by a
  falsification test); reject corpus-wide embedding **to avoid** an ML dep.
- **cognee Memify auto-mutation / Letta sleep-time rewrite** — silent self-mutation
  destroys provenance; our structured supersede+archive is auditable. Surface, never mutate.
- **mem0 MD5 hash-dedup** — proven to store both sides of a contradiction (issue #4896).
- **Two-phase grading-agent / `_meta` block** (Anthropic-agent suggestion) — heavier,
  speculative; our write-gate + report-only lenses cover the need.
- **seedling/budding/evergreen rename** (digital gardens) — a reframe of maturity, not
  clearly better than observation→hypothesis→rule; **to avoid** churn, keep ours.

See [[concepts/framework-hardening-adoption]] (prior adoption matrix) and
[[patterns/blind-validation-for-classifiers]] (validation discipline).
