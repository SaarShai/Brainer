# Token Economy

A token- and context-efficient skill catalog for AI coding agents — Claude Code, Codex, Cursor, Gemini CLI, GitHub Copilot.

**Skills, not a framework.** Drop the catalog into any [agentskills.io](https://agentskills.io)-compatible host. Each skill is a single folder with a `SKILL.md`, optional bundled tools, and measured evaluation numbers.

## The catalog (15 skills)

| Skill | Trigger | Desc tokens | Notes |
|---|---|---:|---|
| [caveman-ultra](skills/caveman-ultra/SKILL.md) | session-start, "be terse" | 81 | Terse output style. ~65% output reduction reported (juliusbrussee/caveman lineage). |
| [plan-first-execute](skills/plan-first-execute/SKILL.md) | task > 3 steps | 70 | Plan-mode gate. |
| [lean-execution](skills/lean-execution/SKILL.md) | "simplify / lean / prune" | 63 | Pruning rule. |
| [verify-before-completion](skills/verify-before-completion/SKILL.md) | before any "done" claim | 49 | Evidence-first. |
| [wiki-memory](skills/wiki-memory/SKILL.md) | retrieve OR write durable | 108 | Tier-aware (L0–L4) repo-local markdown wiki. |
| [context-refresh](skills/context-refresh/SKILL.md) | 20% fill, `/refresh`, `summ` | 89 | Lean handoff + persistent fresh successor. |
| [prompt-triage](skills/prompt-triage/SKILL.md) | UserPromptSubmit hook | 89 | Pre-model regex+Ollama classifier; routes simple tasks to cheap models. |
| [personal-assistant](skills/personal-assistant/SKILL.md) | `/pa`, `/btw` | 57 | Explicit context-light routing. |
| [delegate](skills/delegate/SKILL.md) | independent subtasks, research | 97 | Subagent orchestration + cost preflight + model registry. |
| [context-keeper](skills/context-keeper/SKILL.md) | PreCompact hook | 80 | Structured memory before compaction. |
| [memory-api](skills/memory-api/SKILL.md) | optional MCP | 82 | Tier-aware memory MCP server. |
| [compress-context](skills/compress-context/SKILL.md) | opt-in long-context | 127 | LLMLingua-based compound compression. 44.9% savings, Δscore −0.12 measured on SQuAD v2 (n=8). |
| [semantic-diff](skills/semantic-diff/SKILL.md) | file re-read | 99 | AST-node diff. 95.5% measured savings on argparse.py re-reads. |
| [output-filter](skills/output-filter/SKILL.md) | terminal output hook | 99 | Strip ANSI/progress/dup noise; preserves errors. |
| [skill-creator](skills/skill-creator/SKILL.md) | "add / edit a skill" | 138 | Authoring helper + linter + overlap detector. |

**Always-resident context tax (all 15 descriptions): 1,328 tokens.** Roughly 0.66% of a 200K context window.

Full body cost (worst case, all loaded at once): 7,838 tokens. In practice, only the triggered skill's body loads.

See [eval/results/static_cost.json](eval/results/static_cost.json) for the full measurement.

## Install

```bash
git clone https://github.com/saarshai/token-economy.git
cd token-economy
./install.sh                            # wires skills into all detected hosts
./install.sh --host claude-code         # one host
./install.sh --dry-run                  # see what would happen
```

| Host | Target | Mechanism |
|---|---|---|
| Claude Code | `.claude/skills/` + `.claude-plugin/marketplace.json` | symlinks + plugin manifest |
| Codex | `.codex/skills/` | symlinks |
| Cursor | `.cursor/skills/` + `.cursor/rules/*.mdc` | symlinks + MDC rule shims |
| Gemini CLI | `.gemini/skills/` + `.gemini/settings.json` | symlinks + settings extension |
| Copilot / VS Code | root `AGENTS.md` | shared shim, auto-discovered |

Single canonical source — `skills/` at repo root. Installer fans out to per-host loaders. Pattern lifted from `amtiYo/agents`.

### Plugin install (Claude Code)

```bash
claude plugin install ./.claude-plugin/marketplace.json
```

Installs all 15 skills as one named plugin (`token-economy`) with optional `UserPromptSubmit` and `PreCompact` hooks (off by default; toggle in plugin config).

## What changed (vs the old framework)

This used to be framed as a framework with a `te` CLI, layered docs (`start.md`, `L0_rules.md`, `L1_index.md`, `token-economy.yaml`), and project-style research under `projects/`. All of that is gone.

- `te` CLI → deleted. Each skill owns its scripts in `skills/<name>/tools/`.
- `start.md`, `L0_rules.md`, `L1_index.md`, `token-economy.yaml`, `models.yaml` → deleted. Replaced by `skills/SKILLS_INDEX.md`.
- `adapters/`, `prompts/`, `hooks/` → deleted. Folded into per-skill `tools/`.
- 11 old skills → consolidated into 15 new ones via the audit (merges, renames, one new `skill-creator` skill).
- Working Python projects (ComCom, semdiff, context-keeper, agents-triage, output-filter) → bundled into their matching skills' `tools/` folders.
- Wiki content (`raw/`, `concepts/`, `patterns/`, `projects/`, `people/`, `queries/`, `L2_facts/`, `L3_sops/`, `L4_archive/`, `index.md`, `log.md`, `schema.md`, `templates/`) → moved under `wiki/`. The `wiki-memory` skill reads it.
- `bench/` → kept at root for eval datasets.
- 8 stale agent worktrees → cleaned via `git worktree remove`.

Result: ~50 framework files removed; the catalog is 800K of skill folders plus a small installer.

## Measurement

The repo ships a measurement harness at `eval/`:

```bash
python3 eval/static_cost.py                              # static description/body/tools cost
python3 eval/runner.py --task eval/tasks/<skill>.yaml    # A/B per skill (needs Ollama or Anthropic API)
python3 eval/judge.py eval/results/<skill>.json          # LLM-as-judge quality scoring
```

Per-skill `EVAL.md` files carry static numbers today; live A/B numbers fill in once a backend is wired. See [eval/README.md](eval/README.md) for the full methodology including Kaggle T4 batching and Xiaomi MiMo judging via HuggingFace Inference.

## Lineage

Built on prior work:

- [agentskills.io](https://agentskills.io) — open standard, 35+ hosts.
- [anthropics/skills](https://github.com/anthropics/skills) — canonical SKILL.md and `skill-creator` patterns.
- [amtiYo/agents](https://github.com/amtiYo/agents) — canonical-source-of-truth + symlink-fanout pattern.
- [shinpr/sub-agents-skills](https://github.com/shinpr/sub-agents-skills) — `run-agent: codex|claude|cursor-agent|gemini` cross-LLM dispatch.
- [muratcankoylan/Agent-Skills-for-Context-Engineering](https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering) — 15-skill catalog precedent.
- [coleam00/claude-memory-compiler](https://github.com/coleam00/claude-memory-compiler) — SessionEnd → wiki distillation.
- [cocoindex-io/cocoindex-code](https://github.com/cocoindex-io/cocoindex-code) — AST MCP code search.
- [microsoft/LLMLingua](https://github.com/microsoft/LLMLingua) — neural prompt compression (LLMLingua-2 powers `compress-context`).
- [lm-sys/RouteLLM](https://github.com/lm-sys/RouteLLM) — model routing reference for `prompt-triage` and `delegate`.

## Status

- 15 skills written and lint-clean.
- 4 hosts wired and verified (Claude Code, Codex, Cursor, Gemini CLI).
- Static-cost measurements published.
- Live A/B harness ready; needs a healthy Ollama / explicit `ANTHROPIC_API_KEY` / `HF_TOKEN` to run.

Author: Saar Shai. MIT.
