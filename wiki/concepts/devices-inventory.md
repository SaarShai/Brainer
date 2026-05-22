---
title: Devices inventory
type: concept
domain: ai-setup
tier: working
confidence: 0.95
created: 2026-04-23
updated: 2026-04-25
verified: 2026-04-25
tags: [infra, devices, inventory, compute]
---

# Devices inventory

One-stop reference for agents operating across the 3-machine compute cluster.

## Quick reference

| device | role | ip | user | ssh | active |
|---|---|---|---|---|---|
| M2 | workstation, CC host, local Ollama (11 models), TurboQuant llama-server (8080) | 192.168.1.187 | saar | local | yes |
| M1 | EXO master, Ollama runner (4 models), watchdog queue, Farey supervisor | 192.168.1.218 | new | ssh -i ~/.ssh/id_ed25519 new@... | yes |
| M1B | EXO peer node, Ollama runner (same models as M1), task-capable | 192.168.1.64 | za | ssh -i ~/.ssh/id_ed25519 za@... | yes |

See [[concepts/local-model-setup]] for the per-machine tool, skill, workflow, and harness matrix.

## Standard SSH invocation

```bash
ssh -i /Users/saar/.ssh/id_ed25519 -F /dev/null -o StrictHostKeyChecking=no -o ConnectTimeout=10 <user>@<ip> '<cmd>'
```

---

## M2 (zas-MBP-2.lan, localhost)

### System
- **Model**: MacBookPro14,6 (Mac14,6)
- **RAM**: 64 GB (68,719,476,736 bytes)
- **CPU**: Apple M2 Max
- **macOS**: 26.4.1 (BuildVersion 25E253)
- **Primary LAN IP**: 192.168.1.187
- **IPs**: 127.0.0.1, 192.168.1.187

### Ollama

- **Status**: Running (PID not fetched, but models accessible)
- **Port**: 11434
- **Models installed** (11 total, ~190 GB):
  - `qwen3.6:latest` — 22.1 GB
  - `qwen3.6-uncensored:latest` — 24.3 GB
  - `nomic-embed-text:latest` — 274 MB
  - `gemma4:31b` — 19.9 GB
  - `qwen3-vl:32b` — 20.9 GB
  - `deepseek-r1:32b` — 19.9 GB (proofs)
  - `phi4:14b` — 9.1 GB
  - `gemma4:26b` — 18.0 GB (literature)
  - `qwen3.5:27b` — 17.4 GB
  - `qwen3.5:35b` — 23.9 GB (research)
  - `qwen3:8b` — 5.2 GB

### TurboQuant llama-server

- **Status**: Installed; `~/bin/llama-tq status` reported `not running` on 2026-04-25
- **Port**: 8080 (localhost only)
- **Model served**: `/Users/saar/Library/gguf/qwen3.6-35b-q4km.gguf`
- **Config**: Q8_0 KV cache, TurboQuant V4, 99 GPU layers, 262K context
- **Binary**: `~/src/llama-cpp-turboquant/build/bin/llama-server` (13 MB, Apr 20)
- **Wrapper**: `~/bin/llama-tq` (2.5 KB, Apr 20)
- **Safe default**: `-ctk q8_0 -ctv turbo4 -fa 1 -ngl 99` for Q4_K_M GGUF
- **Smoke check**: `scripts/turboquant_smoke.py --json`

### Token Economy install

- **MCP servers**: None listed in `~/.claude/mcp-servers/`
- **Agents** (15 total, ~/.claude/agents/):
  - Core agents: `adversarial-reviewer.md`, `architect.md`, `code-reviewer.md`, `planner.md`, `security-reviewer.md`, `doc-updater.md`, `build-error-resolver.md`, `chief-of-staff.md`, `harness-optimizer.md`
  - Local compute: `local-ollama.md`, `turboquant-local.md` (Apr 20)
  - Custom/research: `kaggle-feeder.md`, `quick-fix.md`, `research-lite.md`, `wiki-note.md`

### Queues & supervisors

- **Codegen queue**: `~/Desktop/comcom_codegen_queue.txt` (empty, 0 lines)
- **Other queue files**: `fileprovider-check.txt`, `fileproviderd-sample.txt` (utility)

### Cron (system level)

Active watchdogs & schedulers (15 entries):

- `*/15 * * * * ~/bin/m1max_watchdog.sh` — M1 health every 15 min
- `*/15 * * * * ~/bin/m5max_watchdog.sh` — M5 (offsite) health every 15 min
- `*/30 * * * * ~/bin/m1_supervisor.sh` — M1 task supervisor every 30 min
- `0 */2 * * * ~/bin/overnight_monitor_papera.sh` — Research monitor every 2 hours
- `0 2 * * 0 bash ~/Documents/screenery-local/scripts/run_full_catalog.sh` — Screenery catalog Sun 02:00
- `*/30 * * * * /Users/saar/bin/farey_supervisor.sh` — Farey task router every 30 min
- `0 3 * * * /Users/saar/bin/cerebras_retry_low_traffic.sh` — Cerebras retry at 03:00
- `*/30 * * * * /Users/saar/bin/farey_haiku_monitor.sh` — Farey Haiku monitor every 30 min
- `*/5 * * * * ~/bin/farey_api_feeder.sh` — Farey API queue feeder every 5 min
- `*/30 * * * * ~/bin/farey_api_reviewer.sh` — Farey API reviewer every 30 min
- `*/15 * * * * /Users/saar/bin/farey_node_monitor.sh` — Farey node health every 15 min
- `*/10 * * * * ~/bin/farey_haiku45_watchdog.sh` — Farey Haiku 4.5 watchdog every 10 min
- `0 */2 * * * ~/bin/farey_codex_biweekly_review.sh` — Farey Codex review every 2 hours

**Retired** (commented out):
- M5B keep-busy loop (permanent off Apr 22)
- M5B watchdog (permanent off Apr 22)

---

## M1 (MacBookPro.lan, 192.168.1.218, new@)

### System
- **Model**: MacBookPro18,2
- **RAM**: 32 GB (34,359,738,368 bytes)
- **CPU**: Apple M1 Max
- **macOS**: 26.3.1 ProductVersionExtra (a) (BuildVersion 25D771280a)
- **IPs**: 127.0.0.1, 192.168.1.218

### Ollama

- **Status**: Running (`/Applications/Ollama.app/Contents/Resources/ollama serve`, PID 63687)
- **Port**: 11434
- **Keep-alive**: 24 hours (`OLLAMA_KEEP_ALIVE`)
- **Models installed** (4 total, ~72.9 GB):
  - `deepseek-r1:32b` — 19.9 GB (digested edba8017...)
  - `research-8b:latest` — 5.2 GB (qwen3 family)
  - `research-35b:latest` — 23.9 GB (qwen35moe)
  - `qwen3.5:35b` — 23.9 GB (qwen35moe, digested 3460ffe...)
  - `qwen3:8b` — 5.2 GB (digested 500a106...)

### EXO (master node)

- **Status**: Running (3 processes: main exo + 2 instance keepers)
- **Primary PID**: 26689 (`/Applications/EXO.app/Contents/Resources/exo/exo -v --libp2p-port 4001 --bootstrap-peers /ip4/192.168.1.64/tcp/4001 -m ...`)
- **Bootstrap**: M1B as peer (`/ip4/192.168.1.64/tcp/4001`)
- **Ports**: 52415 (HTTP), 4001 (libp2p)
- **MLX models cached** (~66 GB, `~/.exo/models/`):
  - `mlx-community--Qwen3-Next-80B-A3B-Thinking-4bit` (24 dirs, 768 B)
  - `mlx-community--Qwen3.6-35B-A3B-5bit` (21 dirs, 672 B)
  - `mlx-community--Qwen3-0.6B-8bit` (13 dirs, 416 B)
  - `caches/` (114 dirs, 3.6 KB, updated Apr 19)
- **Last state update**: Apr 19 19:54 (5 days old)

### TurboQuant

- **Status**: Not installed / not built as of 2026-04-25 review
- **Policy**: Do not auto-install. 32GB RAM, Ollama, and EXO master duties require explicit approval and fresh contention checks first.

### Farey queue & supervision

- **Queue**: `~/Desktop/Farey-Local/M1MAX_QUEUE.txt` — NOT FOUND (may be inactive)
- **Watchdogs** (3 cron entries):
  - `*/15 * * * * /bin/bash ~/bin/m1_local_watchdog.sh` — Health check every 15 min
  - `*/5 * * * * ~/bin/exo_watchdog.sh` — EXO uptime every 5 min
  - `*/2 * * * * ~/bin/exo_instance_keeper.sh` — Instance restart every 2 min (aggressive)

---

## M1B (zas-MacBook-Pro.local, 192.168.1.64, za@)

### System
- **Model**: MacBookPro18,2 (same as M1)
- **RAM**: 32 GB (34,359,738,368 bytes)
- **CPU**: Apple M1 Max
- **macOS**: 26.4.1 (BuildVersion 25E253)
- **IPs**: 127.0.0.1, 192.168.1.64

### EXO + Ollama (task-capable peer)

- **Status**: Running (2 processes: main exo + subprocess)
- **Primary PID**: 4838 (`/Applications/EXO.app/Contents/Resources/exo/exo -v --libp2p-port 4001 --bootstrap-peers /ip4/192.168.1.218/tcp/4001`)
- **Bootstrap**: M1 as master (`/ip4/192.168.1.218/tcp/4001`)
- **Ports**: libp2p 4001 (no HTTP listener found)
- **Ollama**: should mirror M1's task-ready model set
- **MLX models cached** (~39 GB, `~/.exo/models/`):
  - `mlx-community--DeepSeek-R1-Distill-Llama-70B-4bit` (9 dirs, 288 B)
  - `mlx-community--Qwen3-Next-80B-A3B-Thinking-4bit` (24 dirs, 768 B)
  - `mlx-community--Qwen3.6-35B-A3B-5bit` (21 dirs, 672 B)
  - `mlx-community--Qwen3-0.6B-8bit` (13 dirs, 416 B)
  - `caches/` (114 dirs, 3.6 KB, updated Apr 19)
- **Last state update**: Apr 19 23:32 (updated ~4 days ago, 4 hours after M1)

### Notes
- No cron entries detected
- Should no longer be treated as worker only
- Ready for local tasks once the M1 Ollama model set is mirrored and warmed
- TurboQuant not installed; do not install without a fresh contention check

---

## Cross-cutting observations

### EXO cluster topology

- **Master**: M1 (192.168.1.218), HTTP on 52415, libp2p/4001
- **Peer**: M1B (192.168.1.64), libp2p/4001 peer; no HTTP listener yet
- **Handshake**: M1 and M1B both bootstrap to each other's IP:4001
- **Estimated cluster size**: nodes ≥2, exact instance/runner count not sampled

### Model distribution

**Ollama** (classical):
- M2: 11 models (~190 GB) — inference workload
- M1: 4 models (~73 GB) — backup/research
- M1B: same task-ready set as M1

**EXO** (distributed MLX):
- M1: 4 MLX models (~66 GB) + 114 caches
- M1B: 4 MLX models (~39 GB) + 114 caches
- Overlap: Qwen3-Next-80B, Qwen3.6-35B, Qwen3-0.6B (mirrored for HA)
- DeepSeek-R1-Distill-Llama-70B on M1B only

### Watchdog & automation

- **M2**: 15 cron entries, mostly Farey task router + oversight
- **M1**: 3 cron entries (health + EXO instance keeper aggressive `/2`)
- **M1B**: none (no cron yet; task-capable peer status still needs supervision parity)
- **M5 Max**: remote watchdog still queried from M2 (may be offline)
- **M5B**: retired Apr 22, cron disabled

### Queue & task routing

- M2 drives Farey API → Farey nodes (Cerebras + internal API)
- M2 drives Ollama/TurboQuant for local inference
- M1 is Ollama backup + EXO master (queue file missing/unused)
- M1B is a task-capable peer node; route bounded local work there when useful

---

## Known issues / flags

1. **M1 queue file missing**: `~/Desktop/Farey-Local/M1MAX_QUEUE.txt` does not exist on M1. May indicate queue inactive or path changed.
2. **EXO last state stale**: M1 cache metadata from Apr 19 19:54 (5 days old). M1B slightly fresher (Apr 19 23:32). Consider force-refresh.
3. **M1B role change needs operational parity**: mirror M1's Ollama model set and warm settings before treating it as fully task-ready.
4. **EXO instance keeper aggressive**: M1 runs `exo_instance_keeper.sh` every 2 minutes — may indicate recurring crash/restart loop.
5. **M5B permanently retired**: Apr 22 cron disabled; confirm offline or remove from DNS.
6. **Codegen queue empty**: M2's `comcom_codegen_queue.txt` at 0 lines; Farey API feeder may be starved.

---

## Key paths (agent reference)

### Computation

- **M2 Ollama**: http://localhost:11434 (11 models)
- **M2 TurboQuant**: http://localhost:8080 (qwen3.6-35b-q4km)
- **M1 Ollama**: http://192.168.1.218:11434 (4 models)
- **EXO cluster**: HTTP on 192.168.1.218:52415 (master); peer discovery via libp2p/4001

### Supervision

- **M2 watchdog logs**: ~/Library/FareyState/*, /tmp/*_CRON.log
- **M1 watchdog logs**: /tmp/exo*.log, /tmp/m1_local_watchdog.log
- **M2 code**: ~/bin/{m1max,m5max,m1_supervisor,farey_*}.sh
- **M1 code**: ~/bin/{m1_local_watchdog,exo_watchdog,exo_instance_keeper}.sh

### Config

- **Rules**: /Users/saar/.claude/rules/common.md (M2 only)
- **Agents**: /Users/saar/.claude/agents/ (M2 only)
- **Compute control**: ~/bin/compute_control.sh (M2, referenced in common.md but status unknown)

---

## Integration checklist for agents

- [ ] Verify EXO cluster online: `curl http://192.168.1.218:52415/health` (if exposed)
- [ ] Check M1 Ollama: `curl http://192.168.1.218:11434/api/tags`
- [ ] Confirm M1 queue intent: search `Farey-Local/M1MAX_QUEUE` or grep cron for queue-handler
- [ ] Verify TurboQuant serving: `scripts/turboquant_smoke.py --require-server --json`
- [ ] Confirm M5 Max status: attempt ping + SSH, or remove from supervision if retired
- [ ] Review exo_instance_keeper restart rate (every 2 min is abnormal)
