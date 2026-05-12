---
name: relay-sessions
description: Use when the user asks to relay, hand off, summarize, continue in a fresh Codex session, or let a new session ask an old/older session targeted follow-up questions.
---

# Relay Sessions

Goal: when context is getting full, the old session makes the leanest informative handoff, launches a fresh successor, and stays available as a targeted retrieval source.

The handoff should not try to preserve everything. It should preserve enough for the successor to start safely, then let the successor ask the old session for missing details only when needed.

## Do This

1. Build one compact goal string: current task, done, in progress, next step, blockers, touched files, exact commands/errors.
2. Launch:
   ```bash
   ./te context relay \
     --goal "<current goal, state, next step>" \
     --name "<short old-session name>" \
     --execute
   ```
3. Report the successor result briefly.
4. Stop. The fresh session continues the work.

The relay command writes the handoff and starts a persistent successor with `start.md` plus the handoff only. The handoff includes the old-session pointer for targeted follow-up retrieval.

## Keep It Lean

Put in the handoff:

- Task and desired outcome.
- Done / in progress / next.
- Files, commands, errors, decisions, blockers.
- Branch/dirty state if relevant.
- Repo/wiki pointers to retrieve later.

Leave out details that can be recovered from repo state or by asking the old session later. Exclude transcript noise, broad archives, raw logs, and background research not needed to begin.

## Fallback Only

If launch is unavailable, write `session_handoff.md`:

```bash
./te context checkpoint \
  --goal "<current goal, state, next step>" \
  --print-packet > session_handoff.md
```

## Ask Old

In the new session, retrieve from repo state first. If one missing fact is still blocking progress, ask the old session:

```bash
./te context ask-old \
  --handoff <handoff-file> \
  --question "<specific missing fact>" \
  --execute
```

Ask narrow questions only. Pull one missing fact at a time, then continue. If the answer points to an even older handoff, repeat `ask-old` with that handoff and the same narrow question.

Do not use `--ephemeral`.
