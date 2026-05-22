---
name: context-refresh
description: Use when context is at 20% fill, on /refresh, on "summ", or when context feels stale. Splits work-in-progress into a lean handoff packet plus durable wiki memory, then launches a fresh successor session that starts from the handoff only. Successor can ask the old session targeted follow-up questions via ask-old.
model: any
effort: medium
tools: [Bash, Read, Write]
---

# context-refresh

When context fills, the old session makes the leanest informative handoff, launches a fresh successor, and stays available as a targeted retrieval source.

## Trigger

- `meter` action returns `refresh`
- user says `summ` or `/refresh`
- 20% context-fill checkpoint
- host context feels stale/overloaded

## Protocol

1. Run `python skills/context-refresh/tools/context.py meter --transcript <file>` when transcript path exists.
2. Split info into fresh-handoff material vs durable wiki memory.
3. Route a lightweight wiki-documenter (cheap subagent) to write durable memory first.
4. Build a compact goal string: current task, done, in progress, next step, blockers, touched files, exact commands/errors, branch/dirty state if relevant.
5. Launch the successor:

```bash
python skills/context-refresh/tools/context.py relay \
  --goal "<current goal, state, next step>" \
  --name "<short old-session name>" \
  --execute
```

This writes the handoff + starts a persistent successor with `SKILLS_INDEX.md` plus the handoff only. Handoff includes the old-session pointer for targeted retrieval.

6. Report the successor result briefly. Stop. Fresh session continues.

## Keep it lean

Put in the handoff:
- Task and desired outcome
- Done / in progress / next
- Files, commands, errors, decisions, blockers
- Branch/dirty state if relevant
- Repo/wiki pointers to retrieve later

Leave out:
- Details recoverable from repo state
- Details the successor can ask the old session for later
- Transcript noise, broad archives, raw logs
- Background research not needed to begin

## Hard rules

- Handoff ≤ 2000 estimated tokens.
- Don't paste full transcript into fresh session.
- Don't load docs-only wiki memory into fresh context; link to it instead.
- Don't execute first in fresh session — enter plan-first mode.
- A handoff without a fresh context is not a completed refresh.

## Fallback (no launch available)

```bash
python skills/context-refresh/tools/context.py checkpoint \
  --goal "<current goal>" \
  --print-packet > session_handoff.md
```

Then in the fresh session, read `SKILLS_INDEX.md` + `session_handoff.md` only.

## Ask the old session

In the new session, retrieve from repo state first. If one fact is still blocking:

```bash
python skills/context-refresh/tools/context.py ask-old \
  --handoff <handoff-file> \
  --question "<specific missing fact>" \
  --execute
```

Narrow questions only. One missing fact at a time. If the answer points to an even older handoff, repeat with that handoff and the same question. Do not use `--ephemeral`.

## Host-specific notes

- **Claude Code**: `/clear` is the manual clear path; relay produces a clean successor.
- **Codex**: current-thread clear/compact is unsolved in tested environments. `relay` launches a persistent fresh successor thread; this is clean continuation, not clearing.

## Files

```
tools/
├── context.py             # meter/checkpoint/relay/ask-old/lint-handoff
├── codex_app_server.py    # Codex App-Server adapter for persistent successors
└── INSTALL.md
```
