# Token Economy

A repo-local framework for reducing LLM token/compute consumption while preserving capability.

## Universal agent start

Give any AI agent [`start.md`](start.md). It provides the lean operating contract: Caveman Ultra, repo-local markdown wiki memory, progressive retrieval, 20% context refresh, and model-aware delegation.

Important: downstream agents use Token Economy for their own target project. They are not working on this framework unless the user explicitly asks them to maintain Token Economy itself. Bundled framework docs, roadmap items, handoffs, and `projects/` pages are not downstream project goals.

Core commands:

```bash
./te doctor
./te wiki search "topic"
./te context status
./te context codex-fresh-thread --handoff <handoff-file>
./te delegate classify "task"
./te pa --directive "/pa quick context-light request"
./te output-filter stats
./te output-filter rewind
```

Config lives in [`token-economy.yaml`](token-economy.yaml). Agent-specific adapters live in [`adapters/`](adapters/).

Supplemental productization:

```bash
./te wiki new --template page --title "New Memory"
./te wiki lint --strict
./te context meter --transcript session.jsonl
./te hooks doctor
./te profile show
./te bench run --suite framework-smoke
```

Skills, prompts, hooks, configs, templates, and extension recipes live in their matching top-level folders.

For manual context refresh, use [`prompts/summ dot md`](prompts/summ.md). Copy-paste prompts are available for the old session ([`prompts/manual-summ-document-and-handoff dot md`](prompts/manual-summ-document-and-handoff.md)) and fresh session ([`prompts/manual-fresh-session-from-handoff dot md`](prompts/manual-fresh-session-from-handoff.md)). For complete project migration, use [`prompts/complete-migrate-export dot md`](prompts/complete-migrate-export.md) in the old project and [`prompts/complete-migrate-import dot md`](prompts/complete-migrate-import.md) in the fresh Token Economy-enabled target project folder. In Codex, current-thread clear/compact is unsolved in the tested Desktop/App Server environment; use `./te context codex-fresh-thread --handoff <handoff-file> --execute` for a persistent fresh successor thread with only `start.md` plus the handoff. This is clean continuation, not clearing the old visible thread.

**Framework development projects, not downstream goals:**

| project | what | status |
|---|---|---|
| [ComCom](projects/compound-compression-pipeline/) | Compound compression pipeline (caveman + LLMLingua + self-verify escalation) | **v3 eval passed**: 44.9% savings, Δquality −0.12 (CI touches 0) on SQuAD |
| [semdiff](projects/semdiff/) | AST-node-level diff for LLM file re-reads. MCP server + CC plugin. | **Working**: 95.5% savings on argparse.py re-read; Py/JS/TS/Rust tested |
| [context-keeper](projects/context-keeper/) | PreCompact hook that extracts structured state (files/commands/errors/decisions) to preserve facts across compaction | **Working**: project-local hook recipe |
| [output-filter](hooks/output-filter/) | Terminal-output filtering with raw-output recovery, savings stats, custom rules, and session-aware suppression | **Working**: native hook + CLI |
| [bench/](bench/) | Benchmark registry + Kaggle/HF fetchers + uniform eval schema | **Working**: 7 datasets registered, 2 downloaded |

See [ROADMAP.md](ROADMAP.md) for all directions, progress, next steps.

---

## TL;DR — key measured results

- **ComCom**: 44.9% input-token cut, quality preserved (Δ score −0.12 with 95% CI touching 0). Works via 3-stage escalation: compressed → verify → retry or fall back.
- **semdiff**: 19,280 → 859 tokens on argparse.py after 2 method edits (95.5%). 99.5% on stable re-read.
- **context-keeper**: extracts 68 files, 21 commands, 21 errors from a 100-turn transcript into a grep-able markdown page before `/compact`.
- **output-filter**: strips ANSI/progress noise, deduplicates adjacent lines, preserves errors, stores raw output under `.token-economy/output-filter/`, and exposes `stats`/`rewind`.

## Quick start (per tool)

### ComCom (compound compression)

```python
from pipeline_v2 import compress
from verify import escalate_gen

# Adaptive mode — recommended for personal use
def my_gen(ctx):
    # your model-call wrapper; returns answer string
    return call_model(prompt=build_prompt(ctx, question))

answer, meta = escalate_gen(question, context, my_gen,
                             rates=(0.5, 0.7, None))
# meta: {rate_used, attempts, total_verify_tokens, grounded}
```

### semdiff (AST-diff file reads)

MCP server, works with Claude Code, Cursor, Cline, Zed, any MCP client. See [projects/semdiff/INSTALL.md](projects/semdiff/INSTALL.md).

```bash
# Example MCP client
claude mcp add semdiff -- python /path/to/semdiff/semdiff_mcp/server.py
```

### context-keeper (PreCompact memory)

Context-keeper writes session memory under repo-local `.token-economy/` paths by default. Do not configure global agent settings unless a human explicitly requests machine-wide behavior outside this framework.

### output-filter (terminal noise)

The hook at `hooks/output-filter/filter.sh` keeps filtered terminal output short while preserving raw output locally for debugging:

```bash
some noisy command | TOKEN_ECONOMY_ROOT="$PWD" hooks/output-filter/filter.sh
./te output-filter stats
./te output-filter rewind
./te output-filter rules --init
```

Custom rules live at `.token-economy/output-filter-rules.txt` by default. Use `keep:<regex>`, `drop:<regex>`, and `collapse:<regex>`. Session-aware suppression is available with `--session-aware` or `output_filter_session_aware: true`, but stays disabled by default because repeated lines can be meaningful during debugging.

## Wiki

The `Token Economy` folder doubles as a repo-local markdown LLM wiki. See [index.md](index.md), [schema.md](schema.md).

Folders:
- `concepts/` — atomic technique pages
- `patterns/` — reusable workflows
- `projects/` — target-project pages and framework component docs
- `raw/` — immutable source material (research notes, surveys)
- `people/` — referenced humans
- `queries/` — durable Q&A
- `sessions/` — auto-generated by context-keeper

## Status

This is active research. Interfaces may change. Evals are small-N; see each project's RESULTS for limitations.

Author: Saar Shai.
