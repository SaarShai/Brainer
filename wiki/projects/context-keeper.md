---
type: project
tags: [compaction, context-management, memory, hooks]
confidence: med
evidence_count: 1
---

# context-keeper — structured state preservation before compaction

## Problem
Default `/compact` runs an LLM summarizer → generic prose → loses file paths, line numbers, exact error strings, commands run, decisions + rationale, failed-attempt history (→ repeat mistakes).

## Design
Before compaction (PreCompact hook):
1. Parse current transcript JSONL.
2. Regex-extract: `user_goals`, `files_created`, `files_touched`, `commands_run`, `errors_seen`, `numbers`, `urls`, `failed_attempts`.
3. Write markdown memory page: `.token-economy/sessions/YYYY-MM-DD-HHMM-<sid8>.md`.
4. stdout = terse pointer. PreCompact hook injects it into compaction context → summarizer includes pointer. Agent can read file post-compact.

## Files
```
projects/context-keeper/extract.py   # the work
projects/context-keeper/SKILL.md
projects/context-keeper/hook.sh
projects/context-keeper/install.sh
```

## Activation

Project-local install helper:

```bash
bash projects/context-keeper/install.sh --project
```

If you need to chain it manually, project-local `.claude/settings.json` can add a PreCompact hook when the host supports project settings:

**Option A — replace** (lose timestamp log):
```json
"PreCompact": [{
  "matcher": "*",
  "hooks": [{"type":"command","command":"bash ./.claude/skills/context-keeper/hook.sh"}]
}]
```

**Option B — chain** (keep both):
```json
"PreCompact": [{
  "matcher": "*",
  "hooks": [
    {"type":"command","command":"bash ./.claude/skills/context-keeper/hook.sh"}
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

Unique: schema-stable regex extraction + markdown output that survives compaction, coupled with a pointer injected into compaction context.

## Caveats
- Transcript format changes could break parsing (Anthropic-internal). Extract uses `ev.message.content` fallback to `ev.content`.
- Regex path filter requires file extension; may miss some paths.
- `failed_attempts` regex is heuristic; capture rationale in the handoff or wiki page when you need it.

## Next
- Add `decisions` extraction from `<thinking>` blocks (currently skipped — encrypted signature).
- Emit a `todos_pending` section by scanning for TodoWrite tool blocks.
- Post-compact auto-read: skill that detects `[context-keeper]` pointer and auto-Reads the memory file.
- Eval: synthetic compaction → measure fact retention with/without context-keeper.
- Cross-session memory rollup: daily merge of session memories → `YYYY-MM-DD-day.md`.
