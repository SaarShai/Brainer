---
type: raw
date: 2026-04-20
source: sonnet subagent
tags: [turboquant, research, kv-cache]
---

# TurboQuant research — subagent survey 2026-04-20

## Three repos + paper reviewed

### TheTom/turboquant_plus
- Research/diagnostic Python package. Benchmarks + quality validation suite.
- Validated on M5 Max up to 104B at 128K context (PPL 4.024, 74GB peak).
- Points at companion `llama-cpp-turboquant` (llama.cpp fork with Metal) + `ekryski/mlx-swift-lm` (Swift MLX).
- "×6" = turbo2 (2.5 bits/val, +6.48% PPL). Practical: turbo4 (3.8×, +0.23%) or turbo3 (4.6-5.1×, +1.06%).
- turbo3 at block_size=128 achieves 5.12× compression with same PPL (M2 Pro +3-7% decode).

### TheTom/llama-cpp-turboquant (primary install target for Apple Silicon)
- Fork of llama.cpp with Metal kernels for turbo2/3/4.
- `--cache-type-k turbo3 --cache-type-v turbo3` flags.
- Turbo2 Metal now supported.
- 4-mag LUT auto-detected on M1/M2/M3/M4 → +38-45% decode at long context.
- q8_0 prefill speed parity (2747 vs 2694 tok/s).
- 511+ Python tests in turboquant_plus companion.

### tonbistudio/turboquant-pytorch
- Pure PyTorch CUDA/Windows research. No Apple Silicon.
- K6/V4 ~2× real. K4/V2 ~5× but generation broken at 3-bit keys.
- Findings: QJL removed in V3. MSE-only.

### OnlyTerp/turboquant
- pip-installable (PyPI: `turboquant`).
- HF transformers + vLLM (PR #39890 merged) + SGLang (PR #21419) integration.
- Rotation: Hadamard (O(d log d)) or dense QR (O(d²)).
- No Apple Silicon benchmarks published.
- RTX 5090: 1.24× faster at 32K, 2-bit faster than FP16 at decode.

### Google paper (ICLR 2026)
- arxiv 2504.19874, Zandieh/Daliri/Hadian, submitted Apr 28 2025.
- Randomized Walsh-Hadamard rotation + Lloyd-Max per-coord scalar quantization.
- Within ~2.7× of Shannon entropy lower bound.
- Core result: 3.5-bit Llama-3.1-8B identical LongBench (50.06) + NIAH (0.997) to FP16.

## Three validated follow-on findings (community)

1. **V compression is free** — 2-bit V at q8_0 K = zero quality loss. Cross-tested Metal, CUDA 3090/4090.
2. **All quality loss from K compression** → asymmetric K/V rescues low-bit models.
3. **Boundary layers sensitive** — first 2 + last 2 at higher precision recovers 37-91% of quality gap.

## Stacking with GGUF — user's claim verified

- TurboQuant operates on runtime KV cache; GGUF weight format is orthogonal.
- TheTom README: "TurboQuant quality depends on your base weight quantization. Models with Q8_0+ weights work well with symmetric turbo. Some low-bit models with Q4_K_M weights may benefit from asymmetric K/V: `-ctk q8_0 -ctv turbo4`."
- Symmetric turbo3/turbo3 on Qwen2.5-7B Q4_K_M → PPL 3556 (catastrophic).
- Safe Q4_K_M start: asymmetric `q8_0-K + turbo4-V` → validate PPL.
- Stacking with AWQ, GGUF, NVFP4 confirmed across repos (Towards AI article cited).

## Integration with our stack

### Orthogonal / compatible
- ComCom: compresses input tokens. TQ compresses runtime KV cache. Compose cleanly.
- semdiff, context-keeper: no interaction.

### Incompatible / bypass required
- Ollama: no `-ctk/-ctv` pass-through. Must run direct llama-server.
- EXO (MLX pipeline): needs patching at MLX attention layer. Non-trivial. Do not modify.

### CC sessions "universal" install
- TQ is model-runtime-side. CC sessions talk to Anthropic API — no benefit from TQ directly.
- Can wrap via a subagent definition (analog of local-ollama) that routes tasks to TQ-enabled llama-server. Saves tokens for local inference tasks.

## Per-machine decision tree

### M2 Max (local, 64GB Apple Silicon) — INSTALL
- Clean, no conflict, 64GB headroom.
- Build: `cmake -B build -DLLAMA_METAL=ON && cmake --build build --config Release -j`.
- Run: `./build/bin/llama-server -m <Q4_K_M.gguf> -ctk q8_0 -ctv turbo4 -fa 1 -ngl 99 --port 8080`.
- Safe defaults. Validate PPL on target model before production use.

### M1 Max (32GB, EXO master + Ollama) — WAIT
- Active Qwen3.6-35B download (resumed by haiku subagent).
- 32GB RAM is tight. Only after download complete.
- When unblocked: same llama.cpp fork path. Run on different port from EXO.

### M1B Max (32GB, EXO worker) — NO
- EXO worker. Disrupting = breaking cluster.
- Skip entirely unless user explicitly repurposes M1B.

## Risks

1. **Symmetric turbo on Q4_K_M weights** → catastrophic on Qwen2.5-7B. Asymmetric only for low-bit weights.
2. **macOS Metal memory cap** — must raise `iogpu.wired_limit_mb` for 70B+ at long ctx.
3. **QJL trap** — only use MSE-only implementations (TheTom's fork does this; check OnlyTerp uses V3).
4. **EXO conflict** — llama-server + EXO on same GPU splits VRAM. Schedule carefully.
5. **API churn** — April 2026 code, still experimental.
6. **Ollama replacement** — for models you want TQ'd, stop using Ollama and use llama-server directly.

## Citations

- arxiv 2504.19874
- research.google/blog/turboquant-redefining-ai-efficiency-with-extreme-compression/
- github.com/TheTom/turboquant_plus
- github.com/TheTom/llama-cpp-turboquant
- github.com/ekryski/mlx-swift-lm
- github.com/tonbistudio/turboquant-pytorch
- github.com/OnlyTerp/turboquant
- vllm PR #39890, sglang PR #21419
