---
name: handoff-from
description: Fires on the literal token "/handoff-from" in the user's message. Do NOT fire on any other input. Pulls another session's transcript (via a context-keeper sidecar) and writes a handoff doc here, so this session can pick up work blocked or waiting in a parallel/previous session. Inverse of /handoff — that one writes outbound for the next session; this one pulls inbound from a previous/parallel one.
effort: low
tools: [Bash, Read, Write]
argument-hint: <session-id-or-prefix> | latest | stuck
disable-model-invocation: true
---

# handoff-from

## When to use

- The previous/parallel session is blocked (waiting on a long agent, paused, queued) and you can't type `/handoff` there.
- You want to start fresh work in *this* session in parallel, picking up that session's state.
- A previous session ended without a handoff and you need to resume.

Do NOT use this for:
- Continuing your own conversation — just keep talking.
- Cross-session synthesis of many sessions (out of scope).

## Strict trigger gate

Fires **only** when the user's most recent message starts with the literal token `/handoff-from` (case-insensitive). Otherwise **exit silently** — do not write a file, do not mention this skill.

## Usage

```text
/handoff-from 2f5a8fd9                                    # by session-id prefix
/handoff-from 2f5a8fd9-2aff-4f58-bd3d-e4de9dd82690        # by full sid
/handoff-from latest                                       # most recently active project session
/handoff-from stuck                                        # least-recently-active session modified in last 24h
```

Writes a structured markdown doc to `${TMPDIR}/handoff-from-<sid8>-<ts>.md` and prints the absolute path on the last line, ready to paste into a next prompt.

## What the agent does

1. Run `python3 skills/handoff-from/tools/resolve.py <arg>` in the project cwd.
2. Read the JSON output. It contains:
   - `transcript_path` — original JSONL of the source session
   - `sidecar_path` — small grep-able sidecar produced by context-keeper's extract.py
   - `session_id` — full sid of the resolved session
   - `events`, `last_event_age_seconds`, `sidecar_bytes` — diagnostics
3. `Read` the sidecar (it's small — typically <15 KB).
4. Synthesize a handoff doc in this conversation. Same sections as `/handoff`:
   - One-sentence summary of what the source session was working on.
   - Current task, what's done, what's in progress, what's next.
   - Files touched / commands run / errors to recall (lifted from the sidecar).
   - Open questions / blockers — especially: **why was that session waiting?**
   - **Suggested skills** for this session to invoke first (1–3 names from the catalog).
   - **References** — `transcript_path` and `sidecar_path`. Do not paste their contents.
5. Single `Write` call to `${TMPDIR}/handoff-from-<sid8>-<ts>.md`. Print the absolute path.

Redact API keys, passwords, tokens, PII. Reference paths only — never paste content from the source transcript.

## Files

```
tools/
└── resolve.py    # session-id → sidecar resolver (composes with context-keeper/extract.py)
```

## Lineage

Inverse of [`handoff`](../handoff/SKILL.md). Same family, mirrored direction. Uses [`context-keeper`](../context-keeper/SKILL.md)'s `extract.py` for the regex extraction layer; the synthesis step is agent-authored.
