# Token Economy

A token- and context-efficient skill catalog for AI coding agents — Claude Code, Codex, Cursor, Gemini CLI, GitHub Copilot.

**Skills, not a framework.** Drop the catalog into any [agentskills.io](https://agentskills.io)-compatible host. Each skill is a single folder with a `SKILL.md`, optional bundled tools, and measured evaluation numbers.

## The catalog (11 skills)

| Skill | Trigger | Desc tokens | Notes |
|---|---|---:|---|
| [caveman-ultra](skills/caveman-ultra/SKILL.md) | session-start, "be terse" | 81 | Terse output style. ~65% output reduction reported (juliusbrussee/caveman lineage). |
| [plan-first-execute](skills/plan-first-execute/SKILL.md) | task > 3 steps | 70 | Plan-mode gate. |
| [lean-execution](skills/lean-execution/SKILL.md) | "simplify / lean / prune" | 63 | Pruning rule. |
| [verify-before-completion](skills/verify-before-completion/SKILL.md) | before any "done" claim | 49 | Evidence-first. |
| [wiki-memory](skills/wiki-memory/SKILL.md) | retrieve OR write durable | 108 | Tier-aware (L0–L4) repo-local markdown wiki. |
| [handoff](skills/handoff/SKILL.md) | explicit `/handoff` (+ `--full`, `--ask`) | ~150 | Unified session handoff. Three modes: write doc to $TMPDIR / write doc + route facts to wiki / query last handoff. Replaces `context-refresh`; manual successor launch only. |
| [prompt-triage](skills/prompt-triage/SKILL.md) | UserPromptSubmit hook | 89 | Pre-model regex+Ollama classifier; routes simple tasks to cheap models. |
| [context-keeper](skills/context-keeper/SKILL.md) | PreCompact hook | 80 | Structured memory before compaction. |
| [compress-context](skills/compress-context/SKILL.md) | opt-in long-context | 127 | LLMLingua-based compound compression. 44.9% savings, Δscore −0.12 measured on SQuAD v2 (n=8). |
| [semantic-diff](skills/semantic-diff/SKILL.md) | file re-read | 99 | AST-node diff. 95.5% measured savings on argparse.py re-reads. |
| [output-filter](skills/output-filter/SKILL.md) | terminal output hook | 99 | Strip ANSI/progress/dup noise; preserves errors. |

**Always-resident context tax (11 descriptions): ~1,000 tokens.** Roughly 0.5% of a 200K context window.

Full body cost (worst case, all loaded at once): ~6,500 tokens. In practice, only the triggered skill's body loads.

See [eval/results/static_cost.json](eval/results/static_cost.json) for the full measurement.

**Tuning your install:** stacking guidance, anti-patterns, and workload-aware install advice live in [`eval/FINDINGS.md`](eval/FINDINGS.md) — read once when you adopt the catalog or change which skills are enabled.

### Removed after measurement

**v1.1.0** (no measurable gain or redundant):
- `personal-assistant` — redundant with `prompt-triage` (auto > manual `/pa`).
- `memory-api` — thin MCP wrapper over wiki-memory; same value via CLI.
- `skill-creator` — maintainer tool (not an end-user efficiency skill). Linter and overlap detector live at `scripts/lint_skill_md.py` and `scripts/skill_overlap.py`.

**v1.2.0** (zero measured win after dedicated attempts):
- `delegate` — orchestration contract with no per-call gain; `prompt-triage` already automates the cheap-model routing it advised manually. Subagent lifecycle prose folded into `prompts/` if needed for downstream use.

**v1.3.0** (merged, not dropped):
- `context-refresh` — its only unique piece beyond `handoff` was the auto-launcher (`context.py relay --execute`), which never worked reliably. The other useful bits (`checkpoint` doc-write, `extract_transcript_facts`, `ask_old_from_transcript`) live on inside `skills/handoff/tools/_lib/context.py` and surface as `/handoff` modes (`--full`, `--ask`). Manual successor launch is the contract now — paste the handoff path into a fresh session yourself.

## Install

**Pick your row.** Claude Code has a real plugin format; the other hosts don't (skills are bare files there). One canonical source (`skills/`), one plugin (`.claude-plugin/marketplace.json`), one installer (`install.sh`) for the rest.

| You use… | Want skills… | Run this |
|---|---|---|
| **Claude Code** | **everywhere** (recommended) | `git clone https://github.com/SaarShai/token-economy.git ~/.local/share/token-economy && claude plugin install ~/.local/share/token-economy/.claude-plugin/marketplace.json` |
| Claude Code | in one project only | clone into `<project>/.token-economy`, then `mkdir -p .claude/skills && ln -sfn ../.token-economy/skills/* .claude/skills/` |
| Codex / Cursor / Gemini CLI / Copilot | per-project (no plugin format exists for these) | clone into `<project>/.token-economy`, then `.token-economy/install.sh --host <name>` + symlink — see [Per-project install](#per-project-install-non-claude-code-hosts) |
| any host (inside the token-economy clone itself, e.g. contributing) | for that clone only | `./install.sh` (all hosts) or `./install.sh --host <name>` |

The plugin (`token-economy` v1.3.0) bundles all 11 skills plus optional `UserPromptSubmit` and `PreCompact` hooks (off by default; toggle in plugin config).

### Host install matrix

| Host | Plugin? | Where skills land | Extra wiring |
|---|---|---|---|
| Claude Code | **Yes** (`.claude-plugin/marketplace.json`) | `.claude/skills/` or the plugin registry | optional hooks declared in the plugin manifest |
| Codex | No | `.codex/skills/<name>/` | none — SKILL.md auto-discovered |
| Cursor | No | `.cursor/skills/<name>/` | `.cursor/rules/<name>.mdc` shim per skill (set by `install.sh`) |
| Gemini CLI | No | `.gemini/skills/<name>/` | `.gemini/settings.json` extension entry (set by `install.sh`) |
| Copilot / VS Code | No | root `AGENTS.md` shim | auto-discovered by VS Code Copilot |

Plugin packaging is Claude-Code-specific. Other hosts read SKILL.md files directly — there's nothing for them to "plug into," so a Codex/Cursor/Gemini plugin would be a no-op wrapper. Pattern for the fan-out installer is lifted from `amtiYo/agents`.

### `install.sh` flags

```bash
./install.sh                            # all detected hosts
./install.sh --host claude-code         # one host
./install.sh --host claude-code,codex   # comma-separated subset
./install.sh --dry-run                  # show what would happen
SKILLS_DIR=skills.new ./install.sh      # alternate canonical dir
```

`install.sh` always targets *its own repo*'s hidden dirs (`.claude/skills/`, `.codex/skills/`, etc., next to `install.sh` itself — **not** next to the project you're working in). For per-project install on non-Claude-Code hosts, see below.

### Per-project install (non-Claude-Code hosts)

```bash
cd /path/to/project-X
git clone https://github.com/SaarShai/token-economy.git .token-economy
.token-economy/install.sh --host codex          # wires .token-economy/.codex/skills/
mkdir -p .codex/skills
ln -sfn ../.token-economy/.codex/skills/* .codex/skills/
```

Repeat the last two lines per host (`.cursor/skills/`, `.gemini/skills/`, etc.). For Claude Code, use the plugin command in the table above — it's cwd-independent and skips the symlink dance entirely.

### Bootstrap wiki-memory in a fresh project

The `wiki-memory` skill needs a `wiki/` tree in your project root. After installing the catalog, run once per project:

```bash
python3 ~/.local/share/token-economy/skills/wiki-memory/tools/wiki.py init
# (or .token-economy/skills/wiki-memory/tools/wiki.py init for per-project installs)
```

Creates `wiki/{L0_rules.md, L1_index.md, schema.md, L2_facts/, L3_sops/, L4_archive/, raw/, concepts/, patterns/, projects/, people/, queries/, templates/}` seeded from the skill's bundled defaults. Idempotent — safe to re-run. Default target is `./wiki` in cwd; override with `--root <path>` or `WIKI_ROOT=<path>`. Without this step, `wiki-memory` triggers correctly but has nothing to retrieve.

## What changed (vs the old framework)

This used to be framed as a framework with a `te` CLI, layered docs (`start.md`, `L0_rules.md`, `L1_index.md`, `token-economy.yaml`), and project-style research under `projects/`. All of that is gone.

- `te` CLI → deleted. Each skill owns its scripts in `skills/<name>/tools/`.
- `start.md`, `L0_rules.md`, `L1_index.md`, `token-economy.yaml`, `models.yaml` → deleted. Replaced by `skills/SKILLS_INDEX.md`.
- `adapters/`, `prompts/`, `hooks/` → deleted. Folded into per-skill `tools/`.
- 11 old skills → audited up to 15, then trimmed to 11 after measurement (drops listed above).
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

- 11 skills written and lint-clean.
- 4 hosts wired and verified (Claude Code, Codex, Cursor, Gemini CLI).
- Static-cost measurements published.
- Live A/B harness ready; needs a healthy Ollama / explicit `ANTHROPIC_API_KEY` / `HF_TOKEN` to run.

Author: Saar Shai. MIT.
