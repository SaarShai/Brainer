---
name: prompt-triage
description: Use on every UserPromptSubmit (pre-model hook) to classify the prompt and emit a directive telling the main model which subagent/model should handle it. Regex fast-path then local-Ollama fallback. Goal: avoid spending opus tokens on tasks solvable by haiku/sonnet/local. Override per prompt by typing NO TRIAGE.
effort: low
tools: [Bash]
---

# prompt-triage — bypass opus for simple tasks

## Problem

Heavy default model (opus, high-effort) burns tokens deciding what model a task needs. Many tasks — wiki notes, one-line fixes, factual lookups — don't need opus.

## Approach (3-layer)

### Layer 1: pre-model hook (`UserPromptSubmit`)

`tools/hook.sh` runs BEFORE main model sees prompt. Calls `tools/classify.py`:
- **Length gate** (0ms) — prompts >1500 chars never get a cheap-route directive (`AGENTS_TRIAGE_LENGTH_GATE` to tune). Long briefs are the main model's job.
- **Regex fast-path** (<5ms) matches known patterns.
- **Ollama fallback** (<1.5s) — local small model classifies if regex uncertain. Model auto-resolves from installed tags (preference order in `PREFERRED_MODELS`; pin with `AGENTS_TRIAGE_OLLAMA_MODEL`). First call of a session may miss while the model cold-loads (`keep_alive=2h` keeps it warm after).
- **Fail-closed** — a prompt carrying complex-work hints with no LLM available defers to the main model; no directive is emitted below 0.7 confidence.
- **Context guard** (0ms) — prompts referencing the current session/conversation ("what we built", "this suite") get NO directive: a fresh subagent cannot see chat history, so any verdict just forces the main model to evaluate-and-override.
- **Platform models only** — routing targets are in-platform small models (haiku/sonnet in Claude Code). Never out-of-platform local models; those are for explicit manual dispatch.

Outputs JSON + directive block appended to context:

```json
{"tier": "simple|medium|hard",
 "agent": "wiki-note|quick-fix|research-lite|general-purpose|none",
 "model": "haiku|sonnet|opus",
 "confidence": 0-1,
 "reason": "...",
 "lean_context": [...]}
```

### Layer 2: main model sees directive, dispatches

Main model reads `⚡ [prompt-triage] ...` block → emits `Task(subagent_type, model, prompt)` immediately. Minimal thinking because the directive already specifies what to do.

Full opus bypass isn't possible (the host always routes through main), but the directive keeps thinking budget near zero on simple tasks.

### Layer 3: specialized subagents

Five bundled agents, each minimal-context:
- **wiki-note** (haiku) — repo-local wiki edits only.
- **quick-fix** (haiku) — small scoped edits, one Bash verify max.
- **local-ollama** (haiku coordinator) — shells out to local Ollama models. Manual dispatch only — triage never routes here (2026-06-12 policy).
- **research-lite** (haiku) — ≤5 web calls, ≤800-word output.
- **kaggle-feeder** (haiku) — archived Kaggle eval pipeline maintainer.

## Install

Claude Code:
```bash
bash skills/prompt-triage/tools/install.sh
```

Wires:
- skill → `.claude/skills/prompt-triage/`
- agent defs → `.claude/agents/`
- `UserPromptSubmit` hook → `.claude/settings.json`

## Override

Type `NO TRIAGE` anywhere in the prompt → hook exits silently → main model handles normally.

## Environment vars

- `AGENTS_TRIAGE_NO_OLLAMA=1` — skip Ollama fallback, regex-only.
- `AGENTS_TRIAGE_OLLAMA_MODEL=<tag>` — pin the fallback model (default: auto-resolve from `ollama /api/tags`).
- `AGENTS_TRIAGE_LENGTH_GATE=<chars>` — long-prompt hard gate (default 1500).

## Known failure modes

1. False-positive classification → wrong subagent → returns "escalate" → main re-handles. Small wasted round-trip.
2. Ollama down → regex-only, and complex-hinted prompts fail CLOSED (defer to main model) rather than emitting a cheap route.
3. Adversarial prompt ("this is simple: [complex thing]") → mis-routes. Mitigation: main can override directive.
4. Subagent can't escalate mid-task → returns "escalate" and stops.
5. *(fixed 2026-06-12)* Hardcoded fallback tag rotted (model uninstalled) → every LLM fallback silently failed for weeks; complex prompts fell through to a still-emitted cheap route. Fixes: tag auto-resolution, fail-closed, <0.7-confidence silence, 1500-char length gate, `test_classify.py` regression lock.

## Files

```
tools/
├── classify.py        # regex + Ollama classifier (length gate, fail-closed)
├── test_classify.py   # deterministic regression tests (no network)
├── triage_xmodel.py   # cross-model corpus check for the LLM-fallback path
├── hook.sh            # UserPromptSubmit entry
├── install.sh         # wires into project-local .claude/; verifies fallback model
└── agents/
    ├── wiki-note.md
    ├── quick-fix.md
    ├── local-ollama.md
    ├── research-lite.md
    └── kaggle-feeder.md
```
