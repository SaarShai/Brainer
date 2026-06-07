---
name: session-recall
description: Search and synthesize across ALL prior local agent sessions (Claude Code, Codex, Cursor) to answer "have we done X", "how did we investigate Y", "what was tried before", "what failed last time", or any question about past attempts/decisions — when no handoff doc exists. Pulls cross-session, not just one; raw transcripts never enter orchestrator context.
effort: medium
tools: [Bash, Read, Agent]
auto-install: false
pulse_reminder: never read a raw session JSONL into context — they run 1-70MB. Filter with the extract scripts to a scratch dir, then dispatch a synthesis subagent that returns prose. Orchestrator state stays at file paths + small metadata.
---

# session-recall

Cross-session institutional memory. Answers *what was tried / how was X investigated / did we hit this before* by reading the local session history of **every** agent host on this machine — not just the current conversation, not just one prior session.

Where it sits in the handoff family:

| Skill | Direction | Scope |
|---|---|---|
| [`handoff`](../handoff/SKILL.md) | push forward | writes a doc for the *next* session |
| [`context-keeper`](../context-keeper/SKILL.md) | freeze present | extracts *this* session's live transcript pre-compaction |
| [`handoff-from`](../handoff-from/SKILL.md) | pull one | pulls *one* named prior session via a sidecar |
| **`session-recall`** | **pull many** | **synthesizes across ALL local sessions when no handoff doc exists** |

Use this when there's nothing to hand off *from* — the knowledge is scattered across dozens of old sessions and you need the journey, not a single file.

## When to fire

Model-invokable on questions about past agent work: "have we tried X", "how did we investigate Y", "what was the fix for Z last week", "did a previous session touch the auth middleware", "what didn't work when we…". Also when the user references prior sessions / earlier attempts without saying "session".

Do NOT fire for: continuing the current conversation (you already have it), or pulling one specific known session (use `/handoff-from`).

## Guardrails — non-negotiable

- **Never read a raw session file into context.** They run 1–70MB on this machine (measured: a 66MB Codex rollout). Always filter through the extract scripts first, route bulk to scratch with `--output`, and reason only over the filtered result.
- **Synthesis happens in a subagent, not here.** The orchestrator's working state stays at file paths + small inventory JSON. Bulk skeleton/error content lives only inside the synthesis subagent's context.
- **Never reproduce tool inputs/outputs verbatim.** Summarize what was attempted and what happened.
- **Never surface thinking/reasoning blocks.** The skeleton extractor strips them; don't resurrect any that survive.
- **Never analyze the current session** — it's already in the caller's context.
- **Surface technical, not personal, content.** Sessions hold credentials, frustration, half-thoughts. Use judgment.
- **Fail fast on access errors.** Permission/IO failure → report and stop. Do not retry with different tools.

## Year

It is 2026. Interpret session timestamps accordingly.

## Pipeline

Pre-resolve repo + branch once:

```bash
REPO=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)
TOOLS=skills/session-recall/tools
```

### 1 — Scan window

Infer from the question; start narrow, widen only on a miss.

| Signal | window |
|---|---|
| "today", "this morning" | 1 |
| "recently", "this week", or no time signal | 7 |
| "this month" | 30 |
| broad feature history | 90 |

Claude Code retains ~30d by default; wider windows may find nothing there.

### 2 — Discover + metadata

```bash
bash $TOOLS/discover-sessions.sh "$REPO" <days> \
  | tr '\n' '\0' | xargs -0 python3 $TOOLS/extract-metadata.py --cwd-filter "$REPO"
```

Each line is a session JSON (platform, file, size, ts, session, +platform fields). Final `_meta` line carries `files_processed` / `parse_errors`. `files_processed: 0` → return `no relevant prior sessions` and stop. Narrow platforms with `--platform claude|codex|cursor` on the discover call (default all three).

Host paths (verified on this machine): Claude Code `~/.claude/projects/*<repo>*/` (flat `.jsonl`, incl. worktree dirs); Codex `~/.codex/sessions/YYYY/MM/DD/` (recursive, repo-narrowed by `--cwd-filter`); Cursor `~/.cursor/projects/*<repo>*/agent-transcripts/` (absent host degrades silently).

### 3 — Filter + rank

1. **Branch filter (Claude only):** keep `branch == $BRANCH` or branch names containing a topic keyword.
2. **If branch filter is empty, or for Codex/Cursor:** derive 2–4 keywords from the question, re-run metadata with `--keyword K1,K2,...`. `files_matched: 0` → `no relevant prior sessions`, stop. Else rank by `match_count`.
3. Drop sessions outside the window (`last_ts` else `ts`).
4. Exclude the current session.
5. **Cap: ≤5 sessions** total. Narrow by branch-match → `match_count` → size>30KB → recency.
6. Proceed only if ≥1 remains.

`gitBranch` is captured at the first user message only — a session that `git checkout`-ed mid-run records the old branch. So an empty branch-match is not conclusive; the keyword fallback in step 2 exists for exactly this.

### 4 — Scratch dir

```bash
SCRATCH=$(mktemp -d -t session-recall-XXXXXX)
```

### 5 — Extract per session (file-mediated — the whole point)

For each selected session, route bulk to scratch; stdout returns only a one-line `_meta` status. **Extraction bytes never round-trip through orchestrator tool results.**

```bash
python3 $TOOLS/extract-skeleton.py --output "$SCRATCH/<sid>.skeleton.txt" < <session-file>
```

Conditional `errors`-mode when dead-ends are likely valuable (skip for Cursor — it doesn't log tool results):

```bash
python3 $TOOLS/extract-errors.py --output "$SCRATCH/<sid>.errors.txt" < <session-file>
```

### 6 — Dispatch synthesis subagent

Dispatch a **synthesis-only** subagent (host primitive: `Agent` here) on a **mid-tier model (sonnet)** — frontier reasoning isn't needed. The subagent reads only the scratch paths and returns ~1–2k tokens of prose. Pass this contract verbatim as its prompt:

> You synthesize institutional knowledge from prior coding-agent sessions. Read ONLY the scratch file paths given below via the native file-read tool — never open source session files under `~/.claude`, `~/.codex`, `~/.cursor` (they are MB-scale and blow the window). Never invoke the Skill tool. Never reproduce tool inputs/outputs or thinking blocks verbatim. Never write files. Surface technical, not personal, content. Caveat findings from sessions more than a few days old — the code may have moved on.
>
> **Problem topic:** \<one sentence; lift from the user's question\>
> **Sessions** (≤5): for each — skeleton path, optional errors path, platform, branch/cwd, ts/last_ts, match_count.
> **Output schema** (omit empty sections): *What was tried before · What didn't work · Key decisions · Related context.* When sessions span multiple hosts, flag cross-tool blind spots (duplicated effort, complementary work, gaps) only when genuinely informative.

The bulk content lives only in the subagent's context. The orchestrator holds paths + metadata.

### 7 — Return

Lead with provenance, then the subagent's prose verbatim:

```
**Sessions searched**: N (X Claude Code, Y Codex, Z Cursor) | <date range>
```

Zero sessions at step 2 or 3 → return the literal `no relevant prior sessions`. Stop as soon as the answer is complete; a fast confident "no relevant prior sessions" is a complete answer. `rm -rf "$SCRATCH"` when done (OS cleans temp regardless).

## Tail — persisting a finding worth keeping

A recalled finding is ephemeral by default. If synthesis surfaces something durable — a decision + rationale, a recurring error class, an architecture fact — **gate it, don't auto-write**:

1. Score it through [`write-gate`](../write-gate/SKILL.md) (decisions need a why-clause; recaps are rejected).
2. If it passes, persist via [`wiki-memory`](../wiki-memory/SKILL.md): `python3 skills/wiki-memory/tools/wiki.py …`. Cite the source session (platform + ts) as provenance.

Never pipe raw session content into the wiki — only the gated, synthesized fact. This is the cross-session analog of `/handoff --full`: recall pulls, write-gate filters, wiki-memory keeps.

## Self-test

```bash
bash skills/session-recall/tools/selftest.sh [repo] [days]   # default: token-economy 30
```

Checks the no-raw-into-context guardrail (stdout stays a sub-2KB `_meta` line on the largest real session) and an end-to-end discover→metadata→skeleton smoke. See [`EVAL.md`](EVAL.md).

## Files

```
tools/
├── discover-sessions.sh    # find session files per host (repo + window)
├── extract-metadata.py     # per-file metadata + --cwd-filter / --keyword scan
├── extract-skeleton.py     # conversation skeleton, --output → scratch
├── extract-errors.py       # failed tool calls / commands, --output → scratch
└── selftest.sh             # guardrail + end-to-end smoke
```

## Lineage

Adapted from [EveryInc/compound-engineering-plugin](https://github.com/EveryInc/compound-engineering-plugin) `plugins/compound-engineering/skills/ce-sessions` (the four `scripts/` are vendored near-verbatim under MIT; the `ce-session-historian` agent's guardrails are folded into the step-6 subagent contract). Grafted onto our handoff family: positioned as the *pull-many* complement to [`handoff`](../handoff/SKILL.md) / [`handoff-from`](../handoff-from/SKILL.md) / [`context-keeper`](../context-keeper/SKILL.md), with the durable-finding tail routed through [`write-gate`](../write-gate/SKILL.md) → [`wiki-memory`](../wiki-memory/SKILL.md). **Opt-in (`auto-install: false`)** until measured.
