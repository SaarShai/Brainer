---
name: relay-sessions
description: Use when the user asks to relay, hand off, summarize, continue in a fresh Codex session, or let a new session ask an old/older session targeted follow-up questions.
---

# Relay Sessions

Use the framework's `./te context` relay surface to create compact handoffs and launch fresh Codex successor sessions. (The standalone `relay_session` Python package under `projects/relay-session/` exists for users who want the same behavior outside Token Economy; ignore it inside a TE-installed repo.)

## Rules

- Keep handoffs under 2K estimated tokens.
- Read `start.md` plus the handoff only in the successor.
- Do not load broad archives unless retrieval proves relevance.
- Narrow repo retrieval means targeted reads/searches of known files, status, or symbols; it does not mean loading broad archives.
- Ask old sessions only for specific missing facts after narrow repo retrieval is insufficient.
- If the old session identifies an even older relay handoff as the source, repeat `ask-old` with that older handoff and the same narrow question.
- Treat UI visibility as user-confirmed; backend `listed_after_start: true` proves app-server listing, not immediate sidebar rendering.
- Use the handoff's progressive disclosure order: Layer 1 `start.md` plus handoff, Layer 2 narrow repo retrieval, Layer 3 `ask-old`, Layer 4 repeat `ask-old` on an older handoff if pointed there.
- Prefer factual packet sections over transcript snippets when judging continuity quality.

## Commands

Create a handoff only:

```bash
./te context checkpoint \
  --goal "<current task and critical facts>" \
  --plan "<next step>" \
  --print-packet > session_handoff.md
```

Launch a fresh successor:

```bash
./te context relay \
  --goal "<current task and critical facts>" \
  --name "<session name>" \
  --version 01 \
  --execute
```

Auto-launch a relay only when the context threshold is crossed:

```bash
./te context auto-relay --execute
```

Ask the old session a narrow follow-up:

```bash
./te context ask-old \
  --handoff <handoff-file> \
  --question "<specific missing fact>" \
  --execute
```

Omit `--execute` on `relay` / `auto-relay` / `ask-old` to dry-run routing and confirm what would be launched/queried. Add `--execute` to actually do it. Use `--ephemeral` on `relay` only for throwaway smoke tests.
