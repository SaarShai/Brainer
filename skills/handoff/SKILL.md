---
name: handoff
description: Fires on the literal token "/handoff" in the user's message. Do NOT fire on any other input. Writes a markdown handoff document summarising the current conversation so a fresh agent can continue the work. Three modes — default (write doc to OS temp dir), --full (also route durable facts into wiki/L2_facts/), --ask (query the most recent handoff for one specific fact). Pure local — no successor launch, no API calls. Replaces the older `context-refresh` skill; manual launch is the contract for now.
model: any
effort: low
tools: [Bash, Read, Write]
argument-hint: What will the next session be used for? (or use --ask, --full)
disable-model-invocation: true
---

# handoff

## Strict trigger gate

Fires **only** when the user's most recent message starts with the literal token `/handoff` (case-insensitive). If the message doesn't start with `/handoff`, **exit silently** — do not write a file, do not propose a handoff, do not mention this skill.

## Three modes

### 1. Default — write the doc

```text
/handoff                                  # untitled handoff
/handoff fixing the auth race condition   # focus-tailored
```

Writes a structured markdown doc to `${TMPDIR}/handoff-YYYYMMDD-HHMMSS.md` and prints the absolute path on the last line so you can copy/paste it into the next session. The doc contains:

- One-sentence summary tailored to the focus argument (if given).
- Current task, what's done, what's in progress, what's next.
- Files touched / exact commands / errors to recall.
- Open questions / blockers.
- **Suggested skills** for the next session to invoke first (1–3 names from this catalog).
- **References** (paths/URLs only — never paste content from other artifacts).

Doesn't duplicate content from PRDs/plans/ADRs/issues/commits/diffs. Redacts API keys, passwords, tokens, PII.

### 2. `--full` — write doc + route durable facts to wiki

```text
/handoff --full
/handoff --full database migration plan
```

Same as default, **plus** extracts durable facts (files, commands, errors, numbers, URLs) and appends them as a new page under `wiki/L2_facts/<date>-<slug>.md`. Use when the session produced findings worth keeping across sessions, not just continuing into the next one.

### 3. `--ask` — query the most recent handoff

```text
/handoff --ask "what was the auth race condition we found?"
/handoff --ask "which file had the regression?"
```

Finds the most recent handoff doc (in `$TMPDIR` or `.token-economy/checkpoints/`) and returns matching snippets as JSON. Useful in a fresh session that needs one specific fact from the previous one without re-loading the whole handoff into context.

## What this skill no longer does

- **No successor launch.** The old `context-refresh` skill tried to spawn a fresh persistent session via `context.py relay --execute`. That path is fragile across hosts; manual launch is the contract now. Paste the handoff path into a fresh session yourself.
- **No `meter` / fill-checkpoint auto-trigger.** Slash-only invocation. If you want a periodic checkpoint, set up a host-level reminder.

## Implementation

When invoked as a slash command **inside an active agent session**, the agent assembles the doc itself from the current conversation. **Do not call any tool to "summarise the conversation"** — the agent IS the summariser. Use a single `Write` tool call to put the file at the path shown above.

**Standalone CLI** (for scripting, CI, or when no agent is in the loop):

```bash
python3 skills/handoff/tools/handoff.py --goal "<focus>"
python3 skills/handoff/tools/handoff.py --goal "<focus>" --full
python3 skills/handoff/tools/handoff.py --ask "<question>"
```

The CLI calls regex-based extraction from the bundled `tools/_lib/context.py` (lifted from the absorbed `context-refresh` skill). Measured: 3/3 integration test pass on default mode (`eval/runner_handoff.py`), 4/4 required sections present, ~2.5 KB doc, 39 ms latency.

## Files

```
tools/
├── handoff.py             # CLI entrypoint (3 modes)
└── _lib/
    ├── context.py         # checkpoint() + extract_transcript_facts() + ask_old_from_transcript()
    └── tokens.py          # token estimator (shared utility)
```

## Lineage

`mattpocock/skills/productivity/handoff` (MIT) for the slash-only / `disable-model-invocation` discipline, the suggested-skills section, the reference-don't-duplicate rule, redaction guidance, and the OS-temp-dir output convention. The `--full` and `--ask` modes are absorbed from our older `context-refresh` skill (dropped in v1.3.0 — the auto-launcher was the only unique piece and it never worked reliably).
