---
schema_version: 2
title: Local model setup matrix
type: concept
domain: ai-setup
tier: working
confidence: 0.9
created: 2026-04-25
updated: 2026-04-25
verified: 2026-04-25
sources: [concepts/devices-inventory.md, token_economy/delegate.py, projects/agents-triage/SKILL.md, projects/context-keeper/README.md, projects/semdiff/README.md, skills/context-refresh/SKILL.md, skills/verification-before-completion/SKILL.md, start.md]
supersedes: []
superseded-by:
tags: [infra, devices, models, routing, harnesses]
---

# Local model setup matrix

M2 is the control plane. See [[concepts/devices-inventory]] for the current cluster map and [[projects/delegate-router/README]] for the routing policy. M1 and M1B are local inference peers. M1B should not be treated as worker-only; it should mirror M1's task-ready model set and be able to take bounded tasks directly.

## Shared on all three

- `start.md`
- `./te doctor`
- `./te delegate classify "<task>"`
- `./te delegate plan "<task>"`
- `./te wiki search|timeline|fetch`
- `./te context status|meter|checkpoint|lint-handoff`
- `./te output-filter stats|rewind`
- `./te bench run --suite framework-smoke`
- `./te hooks doctor`

## Skills to keep reachable

- [[skills/caveman-ultra/SKILL]]
- [[skills/plan-first-execute/SKILL]]
- [[skills/wiki-retrieve/SKILL]]
- [[skills/wiki-write/SKILL]]
- [[skills/context-refresh/SKILL]]
- [[skills/verification-before-completion/SKILL]]
- [[skills/subagent-orchestrator/SKILL]]
- [[skills/personal-assistant/SKILL]]
- [[skills/token-economy-external-adoption/SKILL]] on maintainer repos only

## M2: orchestration and measurement

Set up:

- [[projects/compound-compression-pipeline/RESULTS|ComCom]]
- [[projects/semdiff/README|semdiff]] MCP/plugin
- [[projects/context-keeper/README|context-keeper]] PreCompact hook
- [[projects/agents-triage/SKILL|agents-triage]] hook and bundled subagents
- output-filter
- benchmark suite
- `./te profile show`
- `scripts/turboquant_smoke.py --json`
- `./te context meter --transcript <file>`
- `./te context checkpoint --handoff-template`
- `./te context codex-fresh-thread --handoff <handoff-file> --execute`

Use for:

- model routing
- wiki retrieval
- compaction and handoff generation
- save-points
- smoke tests and measurement

How to install:

```bash
./INSTALL.sh --dry-run
./INSTALL.sh --scope project
bash projects/agents-triage/install.sh --project
bash projects/context-keeper/install.sh --project
bash projects/semdiff/install.sh --project
```

## M1 and M1B: task-capable local inference

Set up:

- the same Ollama model set on both nodes
- warm settings such as `OLLAMA_KEEP_ALIVE=24h` and `OLLAMA_MAX_LOADED_MODELS=1`
- the `local-ollama` worker path for bounded summaries, extraction, short drafts, and rewrites
- optional EXO peer bootstrap if the cluster still uses it, but not as a worker-only lock-in

Use for:

- cheap bounded work
- local classification
- short-form drafting
- reruns and overflow from M2
- direct local inference when the task does not justify frontier routing

Measured guidance:

- M1 warm-state throughput is good enough for bounded work, but cold loads dominate large-model cost.
- `qwen3:8b` was the best low-friction M1 baseline in the local pass; `deepseek-r1:32b` worked but was expensive to load.
- Keep M1B mirrored with M1's task-ready Ollama set before assigning bounded local tasks.

How to install:

```bash
launchctl setenv OLLAMA_KEEP_ALIVE 24h
launchctl setenv OLLAMA_MAX_LOADED_MODELS 1
ollama list
ollama pull qwen3:8b
ollama pull qwen3.5:35b
ollama pull deepseek-r1:32b
```

On M1B, mirror M1's live `ollama list` / `curl http://<host>:11434/api/tags` output before routing tasks, then keep the same warm settings.

## Recommended harnesses

- `./te doctor`
- `./te hooks doctor`
- `./te bench run --suite framework-smoke`
- `./te wiki lint --strict`
- `./te output-filter stats`
- `./te context lint-handoff <handoff-file>`
- `scripts/turboquant_smoke.py --json` on M2 only when TurboQuant is in scope

## Do not set up

- global agent settings outside the repo
- TurboQuant on M1/M1B without a new install decision
- full transcript loading on the local model nodes
- vendor code copies or external wiki writes

## Related

- [[concepts/turboquant-kv-cache]]
- [[concepts/framework-hardening-adoption]]
- [[projects/context-refresh/host-context-controls]]
- [[skills/verification-before-completion/SKILL]]
