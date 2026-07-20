---
type: project
tags: [compaction, context-management, memory, hooks]
confidence: med
evidence_count: 1
updated: 2026-06-14
verified: 2026-06-14
---

# context-keeper — structured state preservation before compaction

## Problem
Default `/compact` runs an LLM summarizer → generic prose → loses file paths, line numbers, exact error strings, commands run, decisions + rationale, failed-attempt history (→ repeat mistakes).

## Design
Before compaction (PreCompact hook):
1. Parse current transcript JSONL.
2. Regex-extract: `user_goals`, `files_created`, `files_touched`, `commands_run`, `errors_seen`, `numbers`, `urls`, `failed_attempts`.
3. Write markdown memory page: `.brainer/sessions/YYYY-MM-DD-HHMM-<sid8>.md`.
4. stdout = terse pointer. PreCompact hook injects it into compaction context → summarizer includes pointer. Agent can read file post-compact.

## Files
```
skills/context-keeper/tools/extract.py   # the work
skills/context-keeper/SKILL.md
skills/context-keeper/tools/hook.sh
skills/context-keeper/tools/install.sh
```

## Activation

Project-local install helper:

```bash
bash skills/context-keeper/tools/install.sh
```

If you need to chain it manually, project-local `.claude/settings.json` can add a PreCompact hook when the host supports project settings:

**Option A — replace** (lose timestamp log):
```json
"PreCompact": [{
  "matcher": "*",
  "hooks": [{"type":"command","command":"bash skills/context-keeper/tools/hook.sh"}]
}]
```

**Option B — chain** (keep both):
```json
"PreCompact": [{
  "matcher": "*",
  "hooks": [
    {"type":"command","command":"bash skills/context-keeper/tools/hook.sh"}
  ]
}]
```

## First-run measurement

Ran on current session transcript (9277ec1e, ~150 assistant turns):
- **22 files_created**, 68 files touched.
- **21 commands_run** extracted verbatim.
- **21 errors_seen** logged.
- **User goals**: "implement llm wiki", "explain semantic diff", "check where you were and resume".
- Memory page: 10,434 chars — grep-able, wiki-compatible.

## Novelty vs existing

- `strategic-compact` skill: counts tool calls, nudges user. **No content extraction.**
- `pre-compact.js` stub: logs timestamp. **No content.**
- Anthropic `/compact`: LLM prose summary. **Loses structured facts.**

Unique: schema-stable extraction (structured `tool_use` walks for commands/files since 2026-06-12; regex for paths/URLs/errors/failures) + markdown output that survives compaction, coupled with a pointer injected into compaction context.

## Caveats
- Transcript format changes could break parsing (Anthropic-internal). Extract uses `ev.message.content` fallback to `ev.content`; parseable-non-dict lines and `message`-as-non-dict are normalized at `iter_events` (2026-06-12 — previously crashed extraction silently, losing the snapshot).
- Regex path filter requires file extension; may miss some paths.
- `failed_attempts` is keyword-first windowing (2026-06-12 rewrite — the old leading-`{10,150}` regex went quadratic on long unbroken lines: 23s → 0.5s per 10k events); heuristic either way — capture rationale in the handoff or wiki page when you need it.
- Tests: `skills/context-keeper/tools/tests/test_extract.py` (crash, fidelity, linear-time bound) — in `run_all_tests.sh`.

## Known gap (2026-07-20)
- SessionEnd never fires on the Claude desktop app (no exit action → sessions
  idle forever), so the raw-transcript archive is silently dead there; final
  post-compaction stretch also uncovered. Evidence + manual-fire workaround:
  [[handoffs-rot-at-mutable-values]] (`patterns/handoffs-rot-at-mutable-values.md`).

## Next
- Fix the SessionEnd gap above (archive_now.sh entry point, or archive from
  the PreCompact path too), then propagate.
- Add `decisions` extraction from `<thinking>` blocks (currently skipped — encrypted signature).
- Emit a `todos_pending` section by scanning for TodoWrite tool blocks.
- Post-compact auto-read: skill that detects `[context-keeper]` pointer and auto-Reads the memory file.
- Eval: synthetic compaction → measure fact retention with/without context-keeper.
- Cross-session memory rollup: daily merge of session memories → `YYYY-MM-DD-day.md`.
