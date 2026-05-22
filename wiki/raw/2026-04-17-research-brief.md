---
type: raw
date: 2026-04-17
source: sonnet-4.6 research subagent
tags: [survey, token-economy]
---

# LLM Token Efficiency Survey (Apr 2026)

## Top 10 techniques

1. **Output style constraints (caveman)** — JuliusBrussee. 22-87% output savings, avg 65%. Skill.md, 10 lines. arxiv 2604.00025: terse constraints *improved* accuracy 26pp.
2. **Session-file compression (caveman-compress)** — rewrite CLAUDE.md. 36-60%, avg 46%. Compounds per session.
3. **LLMLingua / LLMLingua-2** — Microsoft. Small perplexity model drops low-salience tokens. 2-6x. arxiv 2310.05736, 2403.12968.
4. **Prefix caching** — Anthropic 90% cut. DeepSeek disk-offloaded KV $0.07/$1 per 1M. Structure: static prefix first.
5. **Karpathy wiki** — persistent markdown KB, index.md replaces vector RAG at ~100 sources.
6. **Structured outputs** — JSON schema, grammar-constrained. 3-8x output cut. Tool-call > ReAct scratchpad.
7. **Speculative decoding** — EAGLE-3 (NeurIPS'25), Medusa. 2-3x throughput, <1% quality loss.
8. **KV eviction** — StreamingLLM attention sinks, SnapKV 3.6x mem / 3.2x throughput at 380K ctx.
9. **Unsloth distill** — 2-eng team. 2x fine-tune speed, 80% less VRAM. Distill API call → local 4B specialist.
10. **Superpowers skills** — obra. Front-load behavior contracts. Subagent dispatch avoids context bloat.

## 5 buildable picks

- **A. Domain-aware compress grammar** — math/code-tuned prose compressor.
- **B. Prefix cache architect skill** — audits templates, rewrites for max cacheable prefix.
- **C. Wiki-query short-circuit** — PreToolUse hook, grep vault before full context.
- **D. ReAct→JSON skill** — ~50% per-step reasoning cut.
- **E. Tiny-model router** — 0.5B classifier, local 7B vs remote 70B.

## Gaps (novel contribution opportunities)

1. **Compound compression pipeline** — no tool chains caveman+LLMLingua+prefix-cache+structured-out. Stacking additive → 80-90%.
2. **Semantic diff for edits** — agents re-read full files; diff+10-line context could cut 5-20x on large codebases.
3. **Cross-session KV persistence for local** — llama.cpp/Ollama lack disk-offload daemon. Pieces exist, unpackaged.
4. **Brevity-calibrated evals** — arxiv 2604.00025 underexplored. Publishable benchmark opportunity.
5. **Skill-level prompt caching** — pre-warm cache for top-5 skills at startup.

## Primary sources
- github.com/JuliusBrussee/caveman
- github.com/obra/superpowers
- gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
- github.com/microsoft/LLMLingua — arxiv 2310.05736, 2403.12968
- github.com/SafeAILab/EAGLE — arxiv 2401.15077, 2406.16858
- github.com/FasterDecoding/Medusa
- github.com/mit-han-lab/streaming-llm — arxiv 2309.17453
- SnapKV arxiv 2404.14469
- github.com/unslothai/unsloth
- DeepSeek-V3 arxiv 2412.19437
- Brevity paper arxiv 2604.00025
