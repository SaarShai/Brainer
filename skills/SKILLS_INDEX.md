# Token Economy Skills

Lean skills for AI coding agents (Claude Code · Codex · Cursor · Gemini · Copilot) across four pillars: **(1)** token-use optimization, **(2)** context-window optimization & management, **(3)** LLM wiki-memory framework, **(4)** self-improvement & learning.

This replaces the old `start.md` boot doc. Each skill is a self-contained folder under `skills/<name>/`. Skill descriptions are the only thing always resident in the agent's context; full bodies load on trigger.

For measured per-skill deltas and the live A/B table see [`eval/FINDINGS.md`](../eval/FINDINGS.md); each skill also ships its own `EVAL.md`.

## Catalog

| Skill | One-line |
|---|---|
| [caveman-ultra](caveman-ultra/SKILL.md) | Terse output style. Drops filler; preserves code/numbers/errors verbatim. |
| [plan-first-execute](plan-first-execute/SKILL.md) | Plan before executing non-trivial tasks. |
| [lean-execution](lean-execution/SKILL.md) | Prune plans/scope to the smallest safe path. |
| [verify-before-completion](verify-before-completion/SKILL.md) | Run fresh verification before claiming done. |
| [wiki-memory](wiki-memory/SKILL.md) | Repo-local markdown wiki: progressive retrieval + gated writes. |
| [handoff](handoff/SKILL.md) | Unified session handoff. `/handoff` writes a doc; `--full` also routes facts to wiki; `--ask` queries the last handoff. Mattpocock-style, slash-only. |
| [handoff-from](handoff-from/SKILL.md) | Inverse of `/handoff` — pulls a previous/parallel session's state into *this* new session. Use when the source session is blocked/waiting and you can't `/handoff` from it. |
| [prompt-triage](prompt-triage/SKILL.md) | Pre-model classifier hook; routes simple tasks to cheap models. |
| [context-keeper](context-keeper/SKILL.md) | PreCompact hook: structured memory before compaction. |
| [session-recall](session-recall/SKILL.md) | Synthesize across ALL prior local sessions (Claude Code/Codex/Cursor) for "have we done X / what was tried before" when no handoff doc exists. Filters MB-scale transcripts to scratch + dispatches a synthesis subagent; raw transcripts never enter orchestrator context. Pull-many complement to handoff/handoff-from. **Opt-in** (`auto-install: false`) — guardrail+smoke verified; A/B unmeasured. Lineage: [EveryInc/compound-engineering-plugin](https://github.com/EveryInc/compound-engineering-plugin) (`ce-sessions`). |
| [compress-context](compress-context/SKILL.md) | LLMLingua-based compound compression with self-verify. **Opt-in** (`auto-install: false`) — heavy torch+llmlingua dep; not auto-installed. |
| [semantic-diff](semantic-diff/SKILL.md) | AST-node diff on file re-reads (95%+ savings; opt-in MCP). |
| [index-first](index-first/SKILL.md) | Prefer pre-built indexes / composite verbs over grep+read chains; batch N related lookups into one capped call. |
| [output-filter](output-filter/SKILL.md) | Strip ANSI/progress/dup noise from terminal output. |
| [loop-breaker](loop-breaker/SKILL.md) | PreToolUse hook: detects N consecutive identical tool calls, injects replan signal. Drift-mitigation. |
| [skill-pulse](skill-pulse/SKILL.md) | UserPromptSubmit hook: every N user turns (default 4) re-injects active skills' `pulse_reminder` rules to fight compliance decay. Paper-calibrated (arXiv 2510.07777). **Opt-in** (`auto-install: false`) — unmeasured in-repo; hook not auto-wired. |
| [compliance-canary](compliance-canary/SKILL.md) | UserPromptSubmit hook: per-skill `drift_probes.json` scan recent assistant messages for filler regex / word-count creep / claim-without-evidence; injects targeted correctives. Ships an offline `measure.py` analyzer. Symptomatic complement to `skill-pulse`. **Opt-in** (`auto-install: false`) — unmeasured in-repo; hook not auto-wired. |
| [write-gate](write-gate/SKILL.md) | Content-quality gate before persistent writes. Signal-score (decisions / errors / architecture / code / numbers, minus filler / speculation) + why-clause enforcement for decisions. Lineage: ogham-mcp + codenamev/claude_memory. |
| [memory-decay](memory-decay/SKILL.md) | Exponential confidence decay for wiki-memory pages (5%/30d default). Errors / lessons / SOPs / high-evidence pages bypass decay (protection class). Dry-run by default. Lineage: ogham-mcp + doobidoo/mcp-memory-service. |
| [wiki-refresh](wiki-refresh/SKILL.md) | Reconcile wiki pages against the current codebase (Keep/Update/Consolidate/Replace/Delete); code-grounded via `audit-refs`, emits typed `contradicts:` edges. Companion to memory-decay (time) — this is ground-truth. Lineage: [EveryInc/compound-engineering-plugin](https://github.com/EveryInc/compound-engineering-plugin) (`plugins/compound-engineering/skills/ce-compound-refresh`). |
| [cache-lint](cache-lint/SKILL.md) | Static audit against Anthropic's 6 prompt-cache rules — dynamic content above breakpoint, prefix mutation by Stop-hooks, model switching, breakpoint sizing. Lineage: ussumant/cache-audit. |

21 skills total — **17 default-installed, 4 opt-in** (`compress-context`, `skill-pulse`, `compliance-canary`, `session-recall`, marked `auto-install: false`: a bare `./install.sh` symlinks and lists them but does **not** run their `tools/install.sh`, so no heavy dep is pulled and no hook is auto-wired). Enable one with `bash skills/<name>/tools/install.sh`. Rationale: only measured-win or cheap load-bearing skills sit on the default install path; unmeasured-in-repo or heavy-dependency skills are opt-in (see [`eval/FINDINGS.md`](../eval/FINDINGS.md)).

Removed after measurement: `personal-assistant` / `memory-api` / `skill-creator` (v1.1.0, redundancy), `delegate` (v1.2.0, zero measured gain — auto-routing via `prompt-triage` already covers the use case), `context-refresh` (v1.3.0, merged into `handoff` — its only unique piece was the auto-launcher which never worked reliably; the rest is now `/handoff --full` and `/handoff --ask`).

External integrations: [`index-first`](index-first/SKILL.md) and [`wiki-memory`](wiki-memory/SKILL.md) recognize [graphify](https://github.com/safishamsi/graphify) (`graphify-out/graph.json`) when present — graphify owns the auto-extracted *what/how/connected* layer; wiki-memory owns the curated *why/decision* layer. See each skill's body for the exact protocol.

## Most-recommended stack

The eight slots below cover the measured-win axes (output × routing × memory × retrieval × re-read × terminal × done-claims). Each skill earns its slot with a measured number; numbers compose across axes, diminish within. Per-axis sources in [`eval/FINDINGS.md`](../eval/FINDINGS.md).

| Slot | Skill | Headline measurement |
|---|---|---|
| Output style | [`caveman-ultra`](caveman-ultra/SKILL.md) + [`lean-execution`](lean-execution/SKILL.md) | **−87.7%** output (combo) |
| Routing | [`prompt-triage`](prompt-triage/SKILL.md) | −20.9% total, 100% accuracy |
| Memory across compaction | [`context-keeper`](context-keeper/SKILL.md) | 97.7% transcript compression |
| Retrieval — what/how/connected | external: [graphify](https://github.com/safishamsi/graphify) | **−93%** vs grep+read at parity evidence (`graphify explain`) |
| Retrieval — why/decision | [`wiki-memory`](wiki-memory/SKILL.md) | 100% evidence on project-history questions; combo with graphify: −87% vs grep at 100% evidence |
| Re-reads | [`semantic-diff`](semantic-diff/SKILL.md) | 95.5% reduction on unchanged re-reads |
| Terminal output | [`output-filter`](output-filter/SKILL.md) | −88.8% bytes, errors preserved |
| Claims of done | [`verify-before-completion`](verify-before-completion/SKILL.md) | −33.5% output, evidence-first |

Bootstrap once per project: `python3 skills/wiki-memory/tools/wiki.py init && graphify extract .` (graphify is auto-installed by `./install.sh`; pass `--no-graphify` to opt out).

## Prime directive

- **Caveman-Ultra by default** for emitted prose. Reasoning budget separate.
- **Plan-first** for non-trivial tasks.
- **Lean execution**: smallest reversible action.
- **Verify before claiming done**.
- **Retrieve before reasoning** about project/wiki facts — prefer `graphify explain` for code questions, `wiki-memory` for decision questions.
- **Use cheapest capable worker**; keep main context clean.

Stacking, anti-patterns, and workload guidance live in [`eval/FINDINGS.md`](../eval/FINDINGS.md) — not always-loaded; read once when installing or tuning the catalog.

## Install

```bash
./install.sh             # symlink to all four host loaders
./install.sh --host claude-code   # just one host
```

## Status

Each skill ships an `EVAL.md` with measured token/context deltas. Skills claiming >20% savings get N≥50 Kaggle-T4 verification before being promoted to default. Opt-in skills carry `auto-install: false` in their SKILL.md frontmatter; `install.sh` skips their `tools/install.sh` so they never auto-wire a hook or pull a heavy dependency. To **disable** one you previously enabled: per-skill installers append to `.claude/settings.json` and never delete, so remove the stale hook entry from `.claude/settings.json` by hand.
