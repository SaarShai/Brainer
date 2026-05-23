# Token Economy Skills

Lean, token/context-efficient skills for AI coding agents (Claude Code · Codex · Cursor · Gemini · Copilot).

This replaces the old `start.md` boot doc. Each skill is a self-contained folder under `skills/<name>/`. Skill descriptions are the only thing always resident in the agent's context; full bodies load on trigger.

For ratings and measured deltas see [`SKILLS_INDEX_RATED.md`](SKILLS_INDEX_RATED.md).

## Catalog

| Skill | One-line |
|---|---|
| [caveman-ultra](caveman-ultra/SKILL.md) | Terse output style. Drops filler; preserves code/numbers/errors verbatim. |
| [plan-first-execute](plan-first-execute/SKILL.md) | Plan before executing non-trivial tasks. |
| [lean-execution](lean-execution/SKILL.md) | Prune plans/scope to the smallest safe path. |
| [verify-before-completion](verify-before-completion/SKILL.md) | Run fresh verification before claiming done. |
| [wiki-memory](wiki-memory/SKILL.md) | Repo-local markdown wiki: progressive retrieval + gated writes. |
| [handoff](handoff/SKILL.md) | Unified session handoff. `/handoff` writes a doc; `--full` also routes facts to wiki; `--ask` queries the last handoff. Mattpocock-style, slash-only. |
| [prompt-triage](prompt-triage/SKILL.md) | Pre-model classifier hook; routes simple tasks to cheap models. |
| [context-keeper](context-keeper/SKILL.md) | PreCompact hook: structured memory before compaction. |
| [compress-context](compress-context/SKILL.md) | LLMLingua-based compound compression with self-verify (opt-in). |
| [semantic-diff](semantic-diff/SKILL.md) | AST-node diff on file re-reads (95%+ savings; opt-in MCP). |
| [output-filter](output-filter/SKILL.md) | Strip ANSI/progress/dup noise from terminal output. |

11 skills total. Removed after measurement: `personal-assistant` / `memory-api` / `skill-creator` (v1.1.0, redundancy), `delegate` (v1.2.0, zero measured gain — auto-routing via `prompt-triage` already covers the use case), `context-refresh` (v1.3.0, merged into `handoff` — its only unique piece was the auto-launcher which never worked reliably; the rest is now `/handoff --full` and `/handoff --ask`).

## Prime directive

- **Caveman-Ultra by default** for emitted prose. Reasoning budget separate.
- **Plan-first** for non-trivial tasks.
- **Lean execution**: smallest reversible action.
- **Verify before claiming done**.
- **Retrieve before reasoning** about project/wiki facts.
- **Use cheapest capable worker**; keep main context clean.

## Install

```bash
./install.sh             # symlink to all four host loaders
./install.sh --host claude-code   # just one host
```

## Status

Each skill ships an `EVAL.md` with measured token/context deltas. Skills claiming >20% savings get N≥50 Kaggle-T4 verification before being promoted to default. Opt-in skills are flagged in their SKILL.md frontmatter.
