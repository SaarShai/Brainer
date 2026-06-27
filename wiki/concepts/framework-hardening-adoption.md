---
schema_version: 2
title: Framework hardening and adoption learnings
type: concept
domain: framework
tier: semantic
confidence: med
created: 2026-04-25
updated: 2026-06-27
verified: 2026-06-27
sources: [raw/2026-04-25-agent-memory-framework-research-rerun.md, raw/2026-04-25-turboquant-adoption-review.md, raw/2026-04-17-research-brief.md, raw/m5-outputs-2026-04-17/prose_prefix_caching_providers.md, raw/2026-04-20-machine-baselines.md, raw/2026-04-20-machine-optimization-round2.md, projects/wiki-search.md, projects/context-refresh.md, projects/context-keeper.md, projects/context-keeper-v2.md, L4_archive/2026-05-22-skill-crystallizer/README.md, skills/write-gate/SKILL.md, concepts/optimization-axes.md]
evidence_count: 8
supersedes: []
superseded-by:
tags: [framework, adoption, retrieval, memory, routing, skills]
---

# Framework hardening and adoption learnings

This pass hardened the repo-local wiki and surrounding workflow, while separating shipped mechanics from still-open memory ideas.

## Research inputs

- Gemini ecosystem research covered ByteRover, Graphiti/Zep, Cognee, Aider repo-map, LLM Wiki, Codebase-Memory MCP, GAAI-style markdown governance, and Claude Code memory/rules/skills.
- Local M1 Gemma/Ollama research converged on Aider-style repo maps, MCP retrieval bridges, and graph memory as the main implementation categories.
- Both research passes support the same default: keep Markdown wiki as canonical memory, then add derived indexes for code structure and optional graph semantics.
- Gemini cache research says explicit cache lifecycle matters, and the 4096-token minimum makes Gemini better for large repo-scale prefixes than for tiny iterative prompts.
- Local M1/M1B measurement showed Ollama is usable for bounded local work, but cold-load cost is the main tax on M1-class machines.
- M1 warm policy that helped most: `OLLAMA_KEEP_ALIVE=24h` and `OLLAMA_MAX_LOADED_MODELS=1`.
- Baseline numbers from the local machine pass: M2 `qwen3:8b` 48.6 tok/s, M2 `phi4:14b` 29.1 tok/s; M1 `qwen3:8b` 38.0 tok/s; M1 `deepseek-r1:32b` 8.7 tok/s with a 26.41s cold load.
- M1B had Ollama serve running but no models pulled in the baseline, so it stayed a deferred local-inference peer rather than an immediate install target.

## Ranked adoption matrix

Rank order is impact first, then fit, then implementation cost.

| rank | item | decision | status | note |
|---|---|---|---|---|
| 1 | wiki context retrieval hardening | adopt | implemented | `wiki-search` now does index -> timeline -> fetch plus audited `wiki_context`. |
| 2 | documentation lifecycle routing | adopt | implemented | durable wiki memory is routed to a lightweight documenter; verified evidence only. |
| 3 | skill-crystallizer v1 | adopt | implemented | solved tasks can crystallize into conservative L3 SOPs after verification. |
| 4 | code-map / repo-map style layer | adopt | implemented | `code_map` gives compact structural pointers before broad file reads. |
| 5 | local M1/M1B Ollama warm policy | adopt | documented | warm models, limit loaded models, keep M1B mirrored when used. |
| 6 | Gemini cache lifecycle guidance | cite-only | not implemented | useful provider guidance, but external and provider-specific. |
| 7 | optional graph / temporal memory | defer | not implemented | no measured win yet; risk of rebuild complexity is high. |
| 8 | Basic Memory-style aliases | defer | not implemented | alias layer would add schema work before benefit is proven. |
| 9 | lifecycle statuses | defer | not implemented | useful for state routing, but not yet grounded in live flows. |
| 10 | deeper Codebase-Memory inspection + pattern adoption | adopt | implemented | Deep-reviewed [DeusData/codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) (a pure-C code-graph MCP — graphify's cousin). Adopted **patterns, not the engine**: grep-augment PreToolUse hook (index-first), degraded-write + loud unsupported-query + ADR (wiki-memory), hook-safety validator+CI-gate + SIGALRM deadline (compliance-canary), artifact `merge=ours`+integrity (wiki-refresh), new `impact-of-change` skill, eval ground-truth gate `validate_case.py` (eval-gate). Merged `6dc765c`. |
| 11 | host `SessionEnd` hook wiring | defer | not implemented | blocked on host-specific wiring and a reliable event source. |
| 12 | cognee (topoteretes) review + re-audit of row 10 | adopt (narrow) | partial | Deep-reviewed [topoteretes/cognee](https://github.com/topoteretes/cognee) (heavyweight AI-memory platform) adversarially + GLM-5.2 cross-check. Verdict: **mostly already covered**, 1 in-philosophy adopt. **ADOPT: inheritance/subclass blast-radius** in `impact-of-change` (graphify already emits `inherits`; `impact.py:37` consumed only `calls` — a head-to-head re-audit of row 10's "covered by graphify" call). **CONCEDE (categorical, infra Brainer rejects):** bi-temporal valid-time intervals + Hybrid-LSP cross-module type resolution — genuinely better in cognee/cbm but need a graph DB / LSP engine. **Covered/reject:** session→lesson distillation (Brainer's `task-retrospective`→`write-gate`→`wiki` gates on deterministic novelty (`overlap`) + trust-tiered conflict resolution (`resolve`); cognee's only distinct edge is *unattended* harvest — a deliberate Brainer anti-bloat trade-off, not a coverage gap), dedup (`overlap` at the right layer for a no-embedding store), retriever-router/hybrid/code-graph-extractor/temporal-as-graph (reinvent existing or need infra). Method lesson: [[concepts/adoption-covered-needs-merits-citation]]. |

## Implemented learnings

- `skills/wiki-memory/tools/wiki.py` is the current retrieval hardening surface: `search`, `timeline`, `fetch`, `context`, and `code_map` are the progressive-disclosure stack.
- The [[projects/context-refresh]] workflow makes the split explicit: the framework writes the handoff and durable wiki memory, but the host controls whether context is actually cleared.
- The skill-crystallizer detector (archived at [[L4_archive/2026-05-22-skill-crystallizer/README]]) captured the v1 rule: only verified completed work becomes an L3 SOP candidate.
- `skills/write-gate/SKILL.md` is the policy backstop: no execution, no memory.
- `skills/wiki-memory/tools/code_map.py` provides the repo-map style layer: compact structural summaries before full file reads.
- **Cross-model adversarial verification of adopted code is worth the cost.** When the codebase-memory-mcp patterns were ported, two rounds of GLM-5.2 adversaries (generator ≠ verifier; each adversary told to *break* the code, default-to-fail) caught **14 real bugs the builder agents' own passing tests missed** — e.g. `ratio=0` silently disabling a degraded-write check (90% data loss reported "ok"), non-ASCII queries falsely rejected as "unsupported", a hook emitting garbage/non-UTF8 backend output as context. Method that converged: adversary finds break → orchestrator reproduces it independently (don't trust the adversary either) → fix → lock with a regression case → re-attack → **stop when a round surfaces only fundamental limits** (static-linter indirection, trust-the-backend, by-design corruption-gate), not bugs. A builder grading its own tests is structurally blind to these; a separate skeptic on a different model is not.
- `raw/2026-04-25-agent-memory-framework-research-rerun.md` records the two research outputs that drove the adoption matrix.

## Not yet implemented

- Optional graph or temporal memory layer.
- Basic Memory-style aliases over the wiki corpus.
- Lifecycle status fields for richer state routing.
- Deeper Codebase-Memory inspection beyond the current structure map.
- Host-specific `SessionEnd` hook wiring for skill-crystallizer.

## Practical takeaways

- Prefer repo-local markdown memory over a larger memory system until the new layer proves a measurable win.
- Keep retrieval shallow by default: index, then timeline, then fetch.
- Treat speculative memory layers as deferred until they beat the current wiki plus code-map stack on a real metric.
- Keep local-model docs honest about cold-load cost; M1-class Ollama is useful, but warm-state policy matters more than model count.

## Eval-methodology learnings

Cross-cutting lessons from the eval harnesses (`eval/exp*`, `eval/kaggle_ollama`) that harden how the framework is measured:

- [[concepts/measure-triggers-by-decision-marker]] — measure skill firing by an explicit decision marker, not keyword presence.
- [[concepts/write-gate-not-truth-filter]] — the write-gate scores signal, not truth; the poisoning defense is provenance/trust.
- [[concepts/demote-vs-description-tax]] — trimming `description:` text, not demotion, cuts the always-on description tax.
- [[concepts/cross-model-ollama-eval-gotchas]] — reasoning models break local Ollama scoring; use non-reasoning models or strip `<think>`.

## Related

- [[projects/wiki-search]]
- [[projects/context-refresh]]
- [[L4_archive/2026-05-22-skill-crystallizer/README]]
- `skills/write-gate/SKILL.md` — write-gate policy (no execution, no memory)
- [[concepts/local-model-setup]]
- [[concepts/optimization-axes]]
- [[raw/2026-04-25-agent-memory-framework-research-rerun]]
- [[queries/memory-as-a-tool-validation]] — external peer-reviewed paper reaffirms the file-based / no-vector-DB bet
- [[queries/understand-anything-adoption-kept-2-3-4-dropped-1-5]] — which Understand-Anything ideas were adopted vs dropped, and why
