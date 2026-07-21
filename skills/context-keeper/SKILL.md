---
name: context-keeper
description: PreCompact hook that extracts structured state (files, commands, errors, numbers, decisions, failures) from the transcript before compaction, so the summarizer can't silently drop facts; a SessionEnd hook also archives the raw transcript to .brainer/sessions/raw/ (git-ignored), and a SessionStart/PreCompact staleness sweep catches sessions on hosts (e.g. Claude desktop) where SessionEnd never fires. Use when the host supports project-local PreCompact/SessionEnd/SessionStart hooks.
model: haiku
effort: low
tools: [Bash, Read, Write]
---

# context-keeper — structured memory before compaction

## What it does

Parses the transcript JSONL, regex-extracts structured state (goals, files touched, commands, errors, numbers, URLs, failure signals). Optional LLM pass (local `qwen3:8b` by default, off by default in the hook) pulls out decisions and next-steps. Writes a terse markdown packet to `.brainer/sessions/<YYYY-MM-DD-HHMM>-<sid8>.md` and emits a multi-line pointer on the hook's stdout — Claude Code prepends that pointer to the compaction prompt so the summarizer references the checkpoint path.

Two provenance rules (adopted 2026-07-01 from [blader/baton](https://github.com/blader/baton)):

- **Iron Rule** — the snapshot opens with a *Repo state (verified at snapshot)* section captured by running `git branch --show-current` / `git status --porcelain` at PreCompact time. Runtime truth, not chat narrative; the section states that it wins over any contradicting narrative below. Fails soft outside a repo.
- **Verified vs assumed** — tool-call-derived sections (files created, commands run, URLs) are tagged *verified*; regex-over-narrative sections (goals, numbers, errors, failure signals) are tagged *assumed — narrative-derived, unverified* so a post-compaction reader never mistakes an extracted claim for a checked fact.

Measured on an 893-line transcript: 100 files, 40 commands, 30 errors logged in ~290 lines. See [`EVAL.md`](EVAL.md).

## Session archive (SessionEnd)

Separate from the compaction checkpoint above. On `SessionEnd`, `archive.py` copies the just-ended transcript verbatim into `<cwd>/.brainer/sessions/raw/<session-id>.jsonl` — a lossless full-session record kept *in the project*, in addition to the host's default global store (`~/.claude/projects/...`). No enrichment, no secret-scrub: it's a byte-for-byte copy, so it carries all generated info as-is.

The copy dir gets a self-contained `.gitignore` (`*`) so the raw transcripts stay out of version control in any host repo — they're for local reference, not commits. cwd resolves from the hook payload, then `$CLAUDE_PROJECT_DIR`, then `os.getcwd()`. Overwrites by session-id, so re-fires don't duplicate.

Retention and deletion for this archive: see [`POLICY.md`](POLICY.md) (`tools/retention.py status|expire`). Redaction is not provided yet — treat archived transcripts as containing secrets.

Scope:

- **Claude Code** — `SessionEnd` → `archive.py` (transcript path from the hook payload).
- **Codex** — `Stop` → `codex_archive.py`. Codex doesn't pass a transcript path, so it resolves the current dir, finds the newest `~/.codex/sessions` rollout whose recorded `session_meta.cwd` matches, and copies that. Wired via `.codex/hooks.json` (mirrors the `.claude` wiring).
- **Gemini** — `gemini hooks migrate --from-claude` maps `PreCompact`→`PreCompress` and `SessionEnd`→`SessionEnd` into `.gemini/settings.json`. The migrator reads `.claude/settings.local.json` FIRST and silently stops if it exists — temporarily move it aside before migrating. Hooks are fail-open (smoke-tested: exit 0 on synthetic payloads).
- **Antigravity** — not supported. Conversations are stored as binary SQLite (`.db`) + protobuf (`.pb`) under `~/.gemini/antigravity/conversations/`, UUID-keyed with no plaintext `cwd` and no per-project routing key, and the GUI app exposes no session-end hook. A clean lossless-text, project-routed copy isn't possible without decoding its proprietary store; revisit if Antigravity adds a session-end hook or a text export.

## Staleness sweep (never-exited desktop sessions)

The gap: on the Claude desktop app, sessions are never "exited" in a way that
fires `SessionEnd` — closing the window is a UI-close, not a session-end event
(see `docs/HOST_CAPABILITY_MATRIX.md`). That silently killed `archive.py`'s
raw-transcript archive on that host with no error, no log line, nothing —
found only by manual inspection of a live-test day (2026-07-20).

`sweep.py` fixes this by piggybacking on hooks that DO fire reliably —
`SessionStart` (`session_start.py`/`.sh`, dedicated) and `PreCompact`
(`hook.py`, as a second call after the extract pass) — instead of adding a new
daemon or watcher. At hook time it scans `~/.claude/projects/<encoded-cwd>/`
(the host's own global transcript store) for `.jsonl` files that are:

1. not the current session (by session-id, when known);
2. mtime-stale beyond a threshold (24h default);
3. not already archived under `.brainer/sessions/raw/` (skipped when a copy
   with a matching file size already exists — idempotent, no re-copy).

Matching files get archived the same way `archive.py` does: verbatim
`shutil.copy2`, plus the same self-contained `.gitignore`. Both call sites
launch `sweep.py` as a detached background process (`subprocess.Popen(...,
start_new_session=True)`) so a slow or hung sweep can never add latency to
session start or compaction — same reliability contract as the other workers:
every error is logged to stderr and swallowed, never raised.

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

Wires `tools/hook.sh` into `.claude/settings.json` under `PreCompact`, `tools/archive.sh` under `SessionEnd`, `tools/session_start.sh` under `SessionStart`, and `tools/codex_archive.sh` into `.codex/hooks.json` under `Stop`. Idempotent; preserves existing hooks/permissions.

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
├── sweep.py           # staleness sweep: archives stale unarchived transcripts SessionEnd missed
├── session_start.py   # Claude SessionStart worker: launches sweep.py detached
├── session_start.sh   # Claude SessionStart shell shim (settings.json points here)
├── codex_archive.py  # Codex Stop worker: cwd-matches newest rollout, copies into .brainer/sessions/raw/
├── codex_archive.sh  # Codex Stop shell shim (.codex/hooks.json points here)
└── install.sh        # wires Claude PreCompact+SessionEnd+SessionStart (.claude/) and Codex Stop (.codex/)
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

`session_start.py` and `sweep.py` hold the same contract too — always exit 0,
every error logged and swallowed, never raised. `sweep.py`'s per-file loop is
additionally fail-soft *per file*: one unreadable/unwritable transcript logs
and is skipped without aborting the rest of the sweep.

## Premortem / failure modes (LEARNING_CONTRACT §8)

- **SessionEnd silently dead on never-exited hosts.** Root cause of this
  section: the desktop app never fires `SessionEnd`, so `archive.py` never
  ran, and nothing surfaced the gap — no error, no log, no missing-file
  alert. Found only by manual inspection of a live-test day. Mitigation:
  don't rely on any single hook event firing; piggyback the same outcome on a
  hook proven to fire (`SessionStart`), and add a second independent trigger
  (`PreCompact`) so a gap in one still gets caught by the other.
- **Sweep encoding drift.** `encode_project_dir()` hard-codes Claude Code's
  current `~/.claude/projects/<encoded-cwd>` naming (every `/` becomes `-`).
  If a future Claude
  Code version changes that encoding, the sweep silently finds nothing (the
  glob just returns empty) rather than erroring — same class of silent gap
  this sweep exists to close. No automated cross-check exists yet; a stale
  sweep is not distinguishable from "nothing to archive" without also
  checking that `transcript_dir_for()` actually resolves to a real,
  non-empty directory when a session is known to be live.
- **Sweep never runs if the host lacks both SessionStart and PreCompact
  delivery.** Some hosts/configurations may suppress SessionStart (e.g. a
  plugin-precedence router skipping a duplicate hook — see
  `docs/HOST_CAPABILITY_MATRIX.md`). The sweep degrades to "only runs on
  PreCompact" in that case, not zero coverage, but a host that fires neither
  reliably still has the original gap. Live-verify per host before trusting
  the sweep as the sole coverage mechanism.
- **Background Popen leaks an orphaned process if a host kills the parent
  hard.** `start_new_session=True` detaches the sweep from the hook's process
  group deliberately (so a hook timeout doesn't kill the sweep mid-copy), but
  that means a sweep that hangs (e.g. on a stalled network filesystem) keeps
  running after the hook returns. `sweep.py` does no long-blocking I/O by
  design (local file stats/copies only) to keep this a theoretical risk, not
  an observed one.

## Lineage

Pattern aligned with coleam00/claude-memory-compiler (SessionEnd → distillation). This skill targets PreCompact specifically — intra-session memory survival, not cross-session synthesis. Compaction is the bulk-ingestion point for loop pass state; durable fact promotion stays outside the hook so a failing or noisy memory write can never block compaction.
