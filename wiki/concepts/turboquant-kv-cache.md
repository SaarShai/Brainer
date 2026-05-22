---
type: concept
axis: input_compression  # KV cache is inference-time context memory
tags: [turboquant, kv-cache, llama-cpp, apple-silicon, gguf-stack]
confidence: med
evidence_count: 5
related: [[concepts/optimization-axes]], [[raw/2026-04-20-turboquant-research]], [[raw/2026-04-25-turboquant-adoption-review]]
---

# TurboQuant — KV-cache compression (ICLR 2026)

## What it is

KV-cache quantization for transformer inference. NOT weight quantization. Runs during inference; compresses the key-value tensors that accumulate as the context grows.

**Mechanism**: Walsh-Hadamard random rotation (O(d log d)) spreads outliers → near-Beta distribution → Lloyd-Max scalar quantization per coordinate. Within ~2.7× of Shannon entropy lower bound.

## Measured compression (Apple Silicon, M5 Max)

| cache type | bits/val | compression | PPL vs q8_0 |
|---|---:|---:|---:|
| turbo4 | 4.25 | **3.8×** | **+0.23%** (safe default) |
| turbo3 (blk=128) | 3.125 | **5.1×** | +1.06% |
| turbo2 | 2.5 | **6.4×** | +6.48% (extreme) |

## Stacks on top of GGUF

User's claim verified. TurboQuant compresses the *runtime* KV cache. Weight quantization (Q4_K_M etc.) is independent. Safe stack for Q4_K_M GGUFs: **`-ctk q8_0 -ctv turbo4`** (asymmetric — K at q8_0, V compressed).

**Symmetric on low-bit weights = catastrophic** on some models (Qwen2.5-7B Q4_K_M + turbo3/turbo3 → PPL 3556, gibberish). Bigger models handle symmetric fine (104B: +3.6%, 70B: +11.4%).

## Validated findings (community cross-tested)

1. **V compression is free.** Even 2-bit V at q8_0 K = zero measurable quality loss.
2. **All quality degradation comes from K compression.** → asymmetric K/V rescues low-bit models.
3. **Boundary layers (first 2 + last 2) sensitive.** Protect them at higher precision → 37-91% of quality gap recovered.
4. **QJL stage hurts attention.** The paper's 2nd stage (1-bit residual) amplifies softmax variance. All community implementations confirm: disable it. TheTom's fork uses MSE-only.

## Repos (reviewed)

| repo | best for | install |
|---|---|---|
| **TheTom/llama-cpp-turboquant** | **Apple Silicon (Metal)** — primary | git clone + cmake + Metal |
| TheTom/turboquant_plus | research/diagnostic Python package | pip from pyproject |
| ekryski/mlx-swift-lm | fastest Apple-native (Swift MLX) | Xcode |
| OnlyTerp/turboquant | pip library + vLLM/SGLang PRs | pip install turboquant |
| tonbistudio/turboquant-pytorch | PyTorch research (CUDA/Win only) | pip + CUDA |

## 2026-04-25 adoption review

Adoption mode: **pattern-reimplementation**. Do not vendor TurboQuant repos into Token Economy. Use TheTom/turboquant_plus and TheTom/llama-cpp-turboquant as the operational reference, then encode safe defaults and checks in our docs/scripts.

Additional watchlist:
- `quantumaikr/quant.cpp`: GGUF-first pure C engine with OpenAI-compatible server; separate engine, Qwen3.6 35B marked experimental.
- `arozanov/turboquant-mlx`: promising MLX/Metal candidate; no clean EXO path and license needs verification.
- `varjoranta/turboquant-vllm`, `mitkox/vllm-turboquant`: vLLM/CUDA watchlist, not Apple Silicon path.
- `back2matching/turboquant`: HF baseline; verify license before reuse.
- Reject direct adoption of GPL or QJL-heavy implementations such as `0xSero/turboquant`.

## Relevance to our stack (Token Economy)

| our tool | interaction with TurboQuant |
|---|---|
| ComCom | orthogonal (input-side compression; TQ is inference-side) — composes cleanly |
| semdiff | no interaction |
| context-keeper | no interaction |
| Ollama (M1/M2) | **incompatible** — Ollama doesn't expose `-ctk/-ctv` flags. Bypass via direct llama-server. |
| EXO (M1/M1B MLX) | different runtime; Swift MLX fork exists but not wired into EXO. Don't patch EXO. |

## Per-machine install status

| machine | decision | reason |
|---|---|---|
| **M2 Max (local)** | PRIMARY | `~/bin/llama-tq` exists; use direct llama-server when running. |
| **M1 Max** | NO AUTO-INSTALL | 32GB + EXO/Ollama contention; install only after explicit approval and fresh machine check. |
| **M1B Max** | NO AUTO-INSTALL | task-capable EXO peer. Same contention profile as M1; don't auto-install without fresh approval. |

## Measured on M2 (2026-04-20)

| model | ctx | KV (K=q8_0 + V=turbo4) | weights | RSS |
|---|---:|---:|---:|---:|
| qwen3:8b Q4_K_M (dense, 36 layers) | 40K | 2.3GB | 5.0GB | — |
| qwen3:8b Q4_K_M | 128K | 7.3GB (K=4.9 + V=2.45) | 5.0GB | 12.1GB |
| **qwen3.6:35b Q4_K_M (MoE-A3B, 10 attn layers)** | **256K** | **2.0GB** (K=1.36 + V=0.68) | 21.1GB | **21.3GB** |
| qwen3.6:35b Q4_K_M | 512K | 4.0GB (K=2.72 + V=1.36) | 21.1GB | 24.9GB |

**MoE insight:** Qwen3.6-35B-A3B has only ~10 attention layers (rest are MoE routing). KV cache scales with attention layers, not total layers → tiny KV footprint. A 35B MoE at 512K uses less KV than an 8B dense at 128K. Sweet spot for long-context on constrained RAM.

## EXO cluster (M1+M1B combined) — TurboQuant NOT available

EXO pipeline uses MLX, not llama.cpp. TurboQuant via TheTom's llama.cpp fork doesn't plug into EXO. Swift MLX fork (`ekryski/mlx-swift-lm`) has turbo4v2 support but isn't wired into EXO.

**Without TurboQuant on EXO**: 256K of 35B on 2×32GB exceeds feasibility (f16 KV too heavy). Practical EXO ctx for 35B stays ≤32K.

**To enable TurboQuant on EXO**: patch EXO's inference path to Swift MLX fork. Non-trivial, not within "minimal diffs" constraint. Skip unless user prioritizes.

## Usage (after M2 build completes)

```bash
# Use GGUF already in Ollama cache (symlinked)
~/bin/llama-tq start ~/Library/gguf/qwen3.6-35b-q4km.gguf          # 65K default
CTX=262144 ~/bin/llama-tq start ~/Library/gguf/qwen3.6-35b-q4km.gguf   # 256K
CTX=524288 ~/bin/llama-tq start ~/Library/gguf/qwen3.6-35b-q4km.gguf   # 512K
~/bin/llama-tq status
~/bin/llama-tq test
```

Then HTTP requests to `http://localhost:8080/v1/chat/completions` — OpenAI-compatible. Qwen3.6 is a thinking model — responses go to `reasoning_content` until thinking ends. Use `max_tokens ≥ 500`.

## Smoke harness

```bash
scripts/turboquant_smoke.py --json
scripts/turboquant_smoke.py --require-server --json
```

Checks:
- local wrapper and `llama-server` binary paths
- `llama-server --help` exposes `cache-type-k`, `cache-type-v`, and `turbo4`
- `~/bin/llama-tq status`
- `http://localhost:8080/health` when a live server is expected

### Ollama GGUF reuse
```bash
# Find blob via manifest
python3 -c "
import json, os
m = json.load(open(os.path.expanduser('~/.ollama/models/manifests/registry.ollama.ai/library/<model>/<tag>')))
for l in m['layers']:
    if 'model' in l.get('mediaType',''):
        print(os.path.expanduser('~/.ollama/models/blobs/sha256-' + l['digest'].replace('sha256:', '')))
"
# Symlink to a nice name
ln -sfn <blob-path> ~/Library/gguf/<nice-name>.gguf
```

## Caveats

1. `--cache-type-k turbo3 -ctv turbo3` on Q4_K_M = can catastrophically fail. Validate PPL first.
2. macOS Metal memory cap: for 70B+ at long context, raise `iogpu.wired_limit_mb` manually.
3. Ollama is NOT compatible. Must run llama-server directly.
4. Still experimental (April 2026). Expect API churn.
5. "×6" headline = turbo2 only. Practical number is 3.8-5.1× at near-neutral quality.

## Sources

- Paper: arxiv 2504.19874
- Google Research blog
- TheTom/llama-cpp-turboquant README + docs/turboquant-recommendations.md
- Community testing across 30+ testers / multiple GPUs
- See [[raw/2026-04-20-turboquant-research]] for full subagent survey
- See [[raw/2026-04-25-turboquant-adoption-review]] for refreshed repo evidence and watchlist
