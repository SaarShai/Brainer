---
type: raw
date: 2026-04-20
source: direct-measurement
tags: [infra, baselines, m1, m1b, m2, ollama, exo]
---

# Local machine baselines — measurement pass 2026-04-20

Standard prompt used everywhere: "Explain what a hash map is in one paragraph."
`num_predict=150` (120 for deepseek), `temperature=0`, `seed=42`.
First call = includes cold-load; second call (same session) would be warm.

## M2 (localhost, 64GB, Apple M2 Max)

| model | wall | load | gen tok/s | prompt tok/s |
|---|---:|---:|---:|---:|
| `qwen3:8b` | 3.24s | 0.08s (warm) | **48.6** | 833 |
| `phi4:14b` | 5.29s | 0.05s (warm) | **29.1** | 625 |

- Free memory: ~24GB. No thermal warnings.
- Ollama procs idle (8 models loaded, all warm).
- **Bottleneck**: none. Headroom clear.
- **Recommendation**: status quo. Optionally bump `OLLAMA_KEEP_ALIVE=24h` to keep frontier models warm across sessions.

## M1 (192.168.1.218, 32GB, Apple M1 Max)

| model | wall | load (cold) | gen tok/s |
|---|---:|---:|---:|
| `qwen3:8b` | 6.91s | 2.72s | **38.0** |
| `deepseek-r1:32b` | 41.06s | **26.41s** | **8.7** |

- Free memory: ~12GB, active ~5.5GB, wired ~2.5GB.
- EXO master running (PID 78825, --force-master, bootstrap to M1B).
- Ollama serve also running.
- **Bottleneck**: **cold-load penalty**. 32GB RAM leaves only ~13GB after EXO overhead. deepseek-r1:32b (19GB) barely fits + 26s load time. Heavy model swap thrashes swap.
- **Recommendation** (minimal diff):
  - `launchctl setenv OLLAMA_KEEP_ALIVE 24h` — keeps last-used Ollama model warm 24h instead of 5min default. Eliminates repeated cold loads.
  - `launchctl setenv OLLAMA_MAX_LOADED_MODELS 1` — prevents Ollama trying to load 2 concurrent large models (default 3) which would swap-thrash.
  - Neither changes cluster-wide EXO config. Both reversible.

## M1B (192.168.1.64, 32GB, Apple M1 Max)

| check | value |
|---|---|
| EXO proc | running, worker bootstrapped to M1 |
| EXO state | 2 downloads in progress, 0 instances placed |
| Ollama | serve running, **no models pulled** |
| Free memory | ~8.5GB |

- **Bottleneck**: none while idle. Downloads in progress (likely 0.6B + 35B MLX partials per M1 docs).
- **Recommendation**:
  - Do NOTHING until 35B download completes (rule: don't restart EXO mid-download).
  - Later, if M1B should supplement local Ollama capacity: `ollama pull qwen3:8b` (5GB) for a second workstation-local model. Low priority.

## Token Economy tool fit per machine

| tool | M2 | M1 | M1B |
|---|---|---|---|
| ComCom MCP | ✓ installed (active CC user) | N/A (no CC session runs here) | N/A |
| semdiff MCP | ✓ installed | N/A | N/A |
| context-keeper hook | ✓ active | N/A | N/A |
| agents-triage | ✓ active | N/A | N/A |
| Farey Ollama queue | — | ✓ existing | — |
| EXO | — | ✓ master | ✓ worker |

Conclusion: **our tools are CC-side. M1/M1B run headless Ollama/EXO without CC.** No install target. Exception: pattern could extend to LOCAL ollama tasks we route to M1 from M2 via HTTP. Already happens via `remote_ollama_exo.sh`.

## Proposed minimal env tweaks (not applied — user confirm first)

M1 only:
```bash
# ssh new@192.168.1.218
launchctl setenv OLLAMA_KEEP_ALIVE 24h
launchctl setenv OLLAMA_MAX_LOADED_MODELS 1
# requires ollama restart to take effect
# ollama serve > /tmp/ollama.log 2>&1 &
```

Expected effect: if deepseek-r1:32b is used repeatedly, 2nd call onward saves 26s cold-load. No quality impact.

## Non-changes (followed rules)

- Did NOT touch EXO bootstrap, peer discovery, libp2p-port.
- Did NOT delete event_log/, models, caches.
- Did NOT restart EXO.
- Did NOT modify M1B (download in progress).

## Next experiments (low priority)

1. Measure warm-state tps on M1 deepseek-r1:32b for fair compare vs cold-load number.
2. If 35B download completes: place instance, measure distributed 35B throughput.
3. Consider pulling qwen3:8b on M1B as fast secondary Ollama (5GB, minimal impact on EXO RAM budget).
