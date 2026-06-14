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

## Backlog (deferred — lean/deterministic/report-only, ranked)

1. **Subject+predicate key prefilter** (Zep same-entity-pair constraint) — compare
   only claims with the same subject key; cuts cross-subject antonym FPs and
   sharpens the resolution verb. Partly served by `same_subject` today.
2. **Evidence-accrual promotion** (A-MEM) — promote a hypothesis when N *subject-key-
   linked observations* accrue, sharper than `maturity`'s raw inbound count.
3. **Access-frequency decay signal** (mem0/Memary "three forgetting signals") — we
   already count fetches in `.brainer/usage.json`; feed it to `decay` so old AND
   never-fetched pages become demotion candidates.
4. **Falsification-condition on rules** (LangMem gradient) — no promotion to `rule`
   without a recorded `falsifies:` clause; deterministic presence check in write-gate.
5. **Quality-delta gate** (mem0 enrich-vs-rephrase) — write-gate from "is this signal?"
   to "does it add info over what we hold?" via token-delta on the same subject key.
6. **Louvain community synthesis** (txtai) — cluster the existing `[[wikilink]]` graph
   for `synth-candidates`, *iff* it beats tag-only clustering on the live wiki
   (falsify first; pure-python `networkx`, no ML).

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
