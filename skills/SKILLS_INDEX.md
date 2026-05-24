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
| [handoff-from](handoff-from/SKILL.md) | Inverse of `/handoff` — pulls a previous/parallel session's state into *this* new session. Use when the source session is blocked/waiting and you can't `/handoff` from it. |
| [prompt-triage](prompt-triage/SKILL.md) | Pre-model classifier hook; routes simple tasks to cheap models. |
| [context-keeper](context-keeper/SKILL.md) | PreCompact hook: structured memory before compaction. |
| [compress-context](compress-context/SKILL.md) | LLMLingua-based compound compression with self-verify (opt-in). |
| [semantic-diff](semantic-diff/SKILL.md) | AST-node diff on file re-reads (95%+ savings; opt-in MCP). |
| [index-first](index-first/SKILL.md) | Prefer pre-built indexes / composite verbs over grep+read chains; batch N related lookups into one capped call. |
| [output-filter](output-filter/SKILL.md) | Strip ANSI/progress/dup noise from terminal output. |
| [loop-breaker](loop-breaker/SKILL.md) | PreToolUse hook: detects N consecutive identical tool calls, injects replan signal. Drift-mitigation. |
| [skill-pulse](skill-pulse/SKILL.md) | UserPromptSubmit hook: every N user turns (default 4) re-injects active skills' `pulse_reminder` rules to fight compliance decay. Paper-calibrated (arXiv 2510.07777). |
| [compliance-canary](compliance-canary/SKILL.md) | UserPromptSubmit hook: per-skill `drift_probes.json` scan recent assistant messages for filler regex / word-count creep / claim-without-evidence; injects targeted correctives. Ships an offline `measure.py` analyzer. Symptomatic complement to `skill-pulse`. |

16 skills total. Removed after measurement: `personal-assistant` / `memory-api` / `skill-creator` (v1.1.0, redundancy), `delegate` (v1.2.0, zero measured gain — auto-routing via `prompt-triage` already covers the use case), `context-refresh` (v1.3.0, merged into `handoff` — its only unique piece was the auto-launcher which never worked reliably; the rest is now `/handoff --full` and `/handoff --ask`).

External integrations: [`index-first`](index-first/SKILL.md) and [`wiki-memory`](wiki-memory/SKILL.md) recognize [graphify](https://github.com/safishamsi/graphify) (`graphify-out/graph.json`) when present — graphify owns the auto-extracted *what/how/connected* layer; wiki-memory owns the curated *why/decision* layer. See each skill's body for the exact protocol.

## Prime directive

- **Caveman-Ultra by default** for emitted prose. Reasoning budget separate.
- **Plan-first** for non-trivial tasks.
- **Lean execution**: smallest reversible action.
- **Verify before claiming done**.
- **Retrieve before reasoning** about project/wiki facts.
- **Use cheapest capable worker**; keep main context clean.

Stacking, anti-patterns, and workload guidance live in [`eval/FINDINGS.md`](../eval/FINDINGS.md) — not always-loaded; read once when installing or tuning the catalog.

## Install

```bash
./install.sh             # symlink to all four host loaders
./install.sh --host claude-code   # just one host
```

## Status

Each skill ships an `EVAL.md` with measured token/context deltas. Skills claiming >20% savings get N≥50 Kaggle-T4 verification before being promoted to default. Opt-in skills are flagged in their SKILL.md frontmatter.
