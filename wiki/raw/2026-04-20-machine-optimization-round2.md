---
type: raw
date: 2026-04-20
source: direct-measurement
tags: [infra, ollama, env-tweaks, turboquant, context-window]
---

# Machine optimization — round 2 (post-TurboQuant)

## M2 (local, 64GB Apple M2 Max)

### Ollama env (applied via launchctl)
```
OLLAMA_KEEP_ALIVE=24h          # keep last model warm
OLLAMA_MAX_LOADED_MODELS=2     # 64GB can host 2 medium
OLLAMA_CONTEXT_LENGTH=32768    # from 2K default → 32K (16× more)
OLLAMA_FLASH_ATTENTION=1       # faster attention
```
Takes effect on next Ollama restart.

### TurboQuant
- Installed: `~/src/llama-cpp-turboquant/build/bin/llama-server` (Metal, 4-mag LUT).
- Wrapper: `~/bin/llama-tq`.
- Measured context limits:
  - qwen3:8b Q4_K_M @ 128K: KV 7.3GB, RSS 12GB. 40× more than Ollama default.
  - **qwen3.6:35b Q4_K_M (MoE) @ 256K: KV 2GB, RSS 21GB.** Fits easily.
  - qwen3.6:35b @ 512K: KV 4GB, RSS 25GB. Still fits.
- GGUF sourced from Ollama blobs via symlink trick (no re-download).

## M1 (32GB Apple M1 Max, 192.168.1.218)

### Ollama env (applied via SSH launchctl)
```
OLLAMA_KEEP_ALIVE=24h
OLLAMA_MAX_LOADED_MODELS=1     # tighter for 32GB + EXO concurrency
OLLAMA_CONTEXT_LENGTH=8192     # conservative — EXO competes for RAM
OLLAMA_FLASH_ATTENTION=1
```

### TurboQuant status: NOT INSTALLED
- cmake not on PATH on M1 (non-interactive shells) — would need `brew install cmake` which adds toolchain scope.
- User rule: minimal diffs. Left out pending explicit ok.
- Active Qwen3.6-35B HF download still in progress (~9.4GB → ~12GB). Finish first.

### Download status note
- hfcli subagent previously launched downloads; they stalled (same file sizes as 09:33 local).
- Re-kick requires explicit HF tool path (not on default PATH).
- Pending: get hfcli path right, re-resume downloads.

## M1B (32GB Apple M1 Max, 192.168.1.64)

### Status: DEFERRED
- EXO worker. No Ollama models pulled → no env tweaks needed.
- Download also stalled at 6.7GB.
- No TurboQuant install (would disrupt EXO cluster).

## EXO cluster 256K Qwen3.6-35B feasibility — BLOCKED

User asked: can EXO combined (2×32GB = 64GB) run Qwen3.6-35B at 256K?

- **EXO uses MLX pipeline**, not llama.cpp. TurboQuant's KV compression is llama.cpp-side only.
- Without TurboQuant, Qwen3.6-35B KV at 256K with f16 ≈ too heavy for 2×32GB even layer-split.
- EXO + TurboQuant integration path: patch EXO to call Swift MLX fork (`ekryski/mlx-swift-lm`) which has turbo4v2 support. **Non-trivial, not minimal diff.**
- Practical EXO ctx ceiling for 35B stays ≤32K until this is patched.

**Recommendation**: if 256K of Qwen3.6-35B is the goal, **run on M2 alone** (64GB single-node with TurboQuant — already validated: 21.3GB RSS at 256K). EXO cluster's value is splitting models that DON'T fit single-node.

## Ollama + TurboQuant coexistence

- Ollama: port 11434, no cache-type flags, but now runs 32K ctx default on M2.
- llama-tq (TurboQuant): port 8080, ~22-25GB RSS for 35B at 256-512K.
- Both can run concurrently on M2 — models compete for Metal GPU but RAM has headroom.
- Route short/quick tasks → Ollama (48 tok/s).
- Route long-context (>16K) → llama-tq.
- `classify.py` rule added: `long-context|35b|70b|128k|turboquant` → turboquant-local agent.

## Remaining action items

1. Qwen3.6 thinking-mode prompt: requires `max_tokens ≥ 500` to get past `reasoning_content`.
2. hfcli path fix on M1/M1B — downloads stalled.
3. If user wants M1 TurboQuant: `brew install cmake` + rebuild. ~15 min.
4. EXO TurboQuant patch = separate research project.
