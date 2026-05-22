---
type: raw
date: 2026-04-25
source: gpt-5.5 external-adoption subagent + gpt-5.4-mini repo survey
tags: [turboquant, adoption-review, kv-cache, apple-silicon, gguf-stack]
---

# TurboQuant adoption review - 2026-04-25

## Workflow compliance

The review used `skills/token-economy-external-adoption/SKILL.md`.

- Source inspection: external repos were inspected under ignored `.token-economy/external-src/`.
- Deep understanding: docs, runtime code paths, tests/examples, cache flags, KV mechanics, and local Token Economy files were inspected.
- Adoption mode: `pattern-reimplementation`. Do not vendor TurboQuant repos into Token Economy.
- Contradiction check: existing Token Economy TurboQuant docs and triage agent were compared against upstream findings.
- Framework integration: update docs, agent instructions, model policy, and smoke harnesses.
- Verification plan: binary/help checks, wrapper status, server health, generation smoke, and PPL/speed validation.

## Repo evidence

| repo | commit/tag | license | adoption decision | note |
|---|---|---|---|---|
| TheTom/turboquant_plus | `0398470` | Apache-2.0 | source-summary / policy reference | Strongest guidance for GGUF + TurboQuant stacking, asymmetric K/V, quality gates. |
| TheTom/llama-cpp-turboquant | `11a241d`, tag `feature-turboquant-kv-cache-b9066-11a241d` | MIT | operational reference | Best Apple Silicon runtime target; implements `turbo2/3/4`, `-ctk/-ctv`, Metal kernels. |
| tonbistudio/turboquant-pytorch | `9997138` | MIT | research reference | Confirms asymmetric K/V and MSE-only findings; CUDA/PyTorch, not Apple runtime. |
| OnlyTerp/turboquant | `d941271` | MIT | watch/research | HF/vLLM/SGLang integration claims; lower-authority for our Apple path. |
| ekryski/mlx-swift-lm | `7e2b710` | MIT | MLX watchlist | Default branch has quantized KV hooks, but not enough to wire EXO. |
| quantumaikr/quant.cpp | `1a3807f` | Apache-2.0 claimed | watchlist | GGUF-first pure C engine with OpenAI-compatible server; separate engine, Qwen3.6 35B marked experimental. |
| 0xSero/turboquant | `7ac9b8d` | GPL-3.0 | reject direct adoption | GPL, tiny history, QJL-heavy direction conflicts with stronger sources. |
| mitkox/vllm-turboquant | `c6b2ee9` | Apache-2.0 | vLLM watchlist | CUDA/vLLM only; huge fork burden, not Apple Silicon path. |
| arozanov/turboquant-mlx | `7c6e3dc` | Apache-2.0 claimed, no LICENSE found | MLX watchlist | Promising fused Metal kernels and `mlx-lm` hooks; license incomplete, EXO path unproven. |
| alicankiraz1/Qwen3.5-TurboQuant-MLX-LM | `f7bbcc0` | Apache-2.0 | MLX watchlist | Qwen-focused preview; narrow scope and tiny history. |
| varjoranta/turboquant-vllm | `9311d91`, tag `v0.13.1` | MIT | vLLM watchlist | Useful comparison for upstream vLLM KV work; CUDA only. |
| back2matching/turboquant | `4de496d` | ambiguous in API survey | research watchlist | HF baseline, deprecates QJL/IP, supports asymmetric K/V; verify license before reuse. |
| Lucien2468/Ollama-TurboQuant-Integration | `b63759e` | MIT | reject for stock Ollama proof | Weight-quantization fork, not evidence that stock Ollama can pass `-ctk/-ctv`. |

## Adopted facts

- TurboQuant stacks with GGUF weight quantization because it compresses runtime KV cache, not weights.
- Q4_K_M GGUF + `K=q8_0`, `V=turbo4` is the safe default, expressed as `-ctk q8_0 -ctv turbo4`.
- Symmetric `turbo3/turbo3` can collapse quality on low-bit GGUFs; require model-specific PPL/smoke validation first.
- Stock Ollama should not be treated as TurboQuant-capable because it does not expose `-ctk/-ctv`; use direct `llama-server`.
- M2 is the primary TurboQuant host; current wrapper exists but reported `not running` during this review.
- M1 and M1B should not be auto-installed. Re-check EXO/Ollama contention and build tooling before any M1 install; keep M1B as EXO worker unless its role changes.

## Token Economy changes to make

- Update `concepts/turboquant-kv-cache.md` with current default policy, watchlist, and Ollama caveat.
- Update `concepts/devices-inventory.md` to reflect M2 installed-but-not-running and M1/M1B no-auto-install policy.
- Update `projects/agents-triage/agents/turboquant-local.md` with smoke validation and server-down behavior.
- Add a smoke harness for binary flags, wrapper status, health endpoint, and optional generation request.

## Verification commands

- `scripts/turboquant_smoke.py --json`
- `scripts/turboquant_smoke.py --require-server --json` when a live server is expected.
- `python3 -m unittest tests/test_universal_framework.py`
- `./te doctor`
