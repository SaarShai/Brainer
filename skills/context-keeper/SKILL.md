---
name: context-keeper
description: PreCompact hook that extracts structured state (files, commands, errors, numbers, decisions, failures) from the transcript before compaction. Preserves grep-able recovery memory so the summarizer can't silently drop facts. Also ships a SessionEnd hook that saves a raw, lossless copy of the whole transcript into the project (.brainer/sessions/raw/, git-ignored) in addition to the host's default global store. Use when the host supports project-local PreCompact/SessionEnd hooks.
model: haiku
effort: low
tools: [Bash, Read, Write]
---

# context-keeper — structured memory before compaction

## What it does

Parses the transcript JSONL, regex-extracts structured state (goals, files touched, commands, errors, numbers, URLs, failure signals). Optional LLM pass (local `gemma4:31b` by default, off by default in the hook) pulls out decisions and next-steps. Writes a terse markdown packet to `.brainer/sessions/<YYYY-MM-DD-HHMM>-<sid8>.md` and emits a multi-line pointer on the hook's stdout — Claude Code prepends that pointer to the compaction prompt so the summarizer references the checkpoint path.

Measured on an 893-line transcript: 100 files, 40 commands, 30 errors logged in ~290 lines. See [`EVAL.md`](EVAL.md).

## Session archive (SessionEnd)

Separate from the compaction checkpoint above. On `SessionEnd`, `archive.py` copies the just-ended transcript verbatim into `<cwd>/.brainer/sessions/raw/<session-id>.jsonl` — a lossless full-session record kept *in the project*, in addition to the host's default global store (`~/.claude/projects/...`). No enrichment, no secret-scrub: it's a byte-for-byte copy, so it carries all generated info as-is.

The copy dir gets a self-contained `.gitignore` (`*`) so the raw transcripts stay out of version control in any host repo — they're for local reference, not commits. cwd resolves from the hook payload, then `$CLAUDE_PROJECT_DIR`, then `os.getcwd()`. Overwrites by session-id, so re-fires don't duplicate.

Scope:

- **Claude Code** — `SessionEnd` → `archive.py` (transcript path from the hook payload).
- **Codex** — `Stop` → `codex_archive.py`. Codex doesn't pass a transcript path, so it resolves the current dir, finds the newest `~/.codex/sessions` rollout whose recorded `session_meta.cwd` matches, and copies that. Wired via `.codex/hooks.json` (mirrors the `.claude` wiring).
- **Antigravity** — not supported. Conversations are stored as binary SQLite (`.db`) + protobuf (`.pb`) under `~/.gemini/antigravity/conversations/`, UUID-keyed with no plaintext `cwd` and no per-project routing key, and the GUI app exposes no session-end hook. A clean lossless-text, project-routed copy isn't possible without decoding its proprietary store; revisit if Antigravity adds a session-end hook or a text export.

## Loop-pass checkpoints

When a session contains a long-running loop, the checkpoint must preserve the compact pass state that would otherwise rot out of context. The regex pass extracts:

- pass / iteration / round identifiers;
- anchor files the loop says it re-reads before each pass;
- state store paths such as `LOOP-STATE.json` or `STATE.md`;
- verifier verdict lines;
- attempts tried / failed attempts summaries;
- next-pass / next-action lines.

This is a compaction checkpoint, not a durable learning write. The hook may surface the loop state so the next context recalls it, but durable project lessons are written only when explicitly requested or selected by an armed [`task-retrospective`](../task-retrospective/SKILL.md), then routed through [`write-gate`](../write-gate/SKILL.md) and [`wiki-memory`](../wiki-memory/SKILL.md) after verification.

## Install

Claude Code (project-local):

```bash
bash skills/context-keeper/tools/install.sh --project
```

Wires `tools/hook.sh` into `.claude/settings.json` under `PreCompact`, `tools/archive.sh` under `SessionEnd`, and `tools/codex_archive.sh` into `.codex/hooks.json` under `Stop`. Idempotent; preserves existing hooks/permissions.

## Rules

- Don't load the full transcript in the hook — read JSONL incrementally.
- Output stays terse.
- Preserve exact paths, commands, numbers, error strings verbatim.

## Files

```
tools/
├── extract.py     # regex extractor + optional LLM pass
├── hook.py        # PreCompact worker: parses stdin payload, invokes extract.py
├── hook.sh        # PreCompact shell shim (settings.json points here)
├── archive.py        # Claude SessionEnd worker: copies the transcript into .brainer/sessions/raw/
├── archive.sh        # Claude SessionEnd shell shim (settings.json points here)
├── codex_archive.py  # Codex Stop worker: cwd-matches newest rollout, copies into .brainer/sessions/raw/
├── codex_archive.sh  # Codex Stop shell shim (.codex/hooks.json points here)
└── install.sh        # wires Claude PreCompact+SessionEnd (.claude/) and Codex Stop (.codex/)
```

## Reliability contract

The hook MUST exit 0 on every input. A failing PreCompact hook would block compaction and corrupt the session. Edge cases all verified to exit 0:

- empty stdin payload
- malformed JSON
- missing `transcript_path` field
- transcript file does not exist
- empty transcript file
- malformed JSONL lines mid-file
- extract.py timeout (30s cap)

Errors are logged to stderr with an ISO timestamp prefix; Claude Code captures them in the session transcript without aborting compaction.

The SessionEnd worker (`archive.py`) holds the same contract — always exit 0. Verified exit-0 on: empty stdin, malformed JSON, missing/absent `transcript_path`, unresolvable cwd, and copy errors (e.g. permission denied). A failed copy logs and is skipped; the host session ends normally.

## Lineage

Pattern aligned with coleam00/claude-memory-compiler (SessionEnd → distillation). This skill targets PreCompact specifically — intra-session memory survival, not cross-session synthesis. Compaction is the bulk-ingestion point for loop pass state; durable fact promotion stays outside the hook so a failing or noisy memory write can never block compaction.
