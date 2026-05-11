---
name: relay-sessions
description: Use when the user asks to relay, hand off, summarize, continue in a fresh Codex session, or let a new session ask an old/older session targeted follow-up questions.
---

# Relay Sessions

Use the framework's `te context` relay surface to create compact handoffs and launch fresh Codex successor sessions. In a root install the command is `./te`; in an embedded install use the command named in the handoff, usually `./framework/te`. (The standalone `relay_session` Python package under `projects/relay-session/` exists for users who want the same behavior outside Token Economy; ignore it inside a TE-installed repo.)

## Rules

- Keep handoffs under 2K estimated tokens.
- Read the startup doc named in the handoff plus the handoff only in the successor. This may be `start.md` or `framework/start.md`.
- Do not load broad archives unless retrieval proves relevance.
- Narrow repo retrieval means targeted reads/searches of known files, status, or symbols; it does not mean loading broad archives.
- Ask old sessions only for specific missing facts after narrow repo retrieval is insufficient.
- If the old session identifies an even older relay handoff as the source, repeat `ask-old` with that older handoff and the same narrow question.
- Launch normal relay successors as persistent, named, continue-work sessions. The successor must verify the handoff, then continue executing the next tasks instead of stopping at a status report.
- Name the successor from the old session name. If the old name has no version suffix, append `v2`; if it already ends with `vN`, replace that with `v<N+1>`.
- Do not put the session name or old prompt title at the top of the successor prompt. Keep UI naming separate from the first message: the app-server launcher must apply the visible title with `thread/name/set` after thread creation and again after `turn/start`. If Codex reports a prompt-shaped title instead of a clean session name, use the explicit fallback name or a short goal-derived label.
- Treat UI visibility as user-confirmed; backend `listed_after_start: true` proves app-server listing, not immediate sidebar rendering.
- Use the handoff's progressive disclosure order: Layer 1 startup doc plus handoff, Layer 2 narrow repo retrieval, Layer 3 `ask-old`, Layer 4 repeat `ask-old` on an older handoff if pointed there.
- If `ask-old --execute` returns an app-server/pipe error with a transcript fallback, use the fallback snippets as bounded old-context retrieval and continue.
- Prefer factual packet sections over transcript snippets when judging continuity quality.

## Commands

Create a handoff only:

```bash
<te-command> context checkpoint \
  --goal "<current task and critical facts>" \
  --plan "<next step>" \
  --print-packet > session_handoff.md
```

Launch a fresh successor:

```bash
<te-command> context relay \
  --goal "<current task and critical facts>" \
  --name "<fallback old-session name if title lookup fails>" \
  --execute
```

The relay command derives the visible successor name and passes `--continue-work` to the new Codex thread. Do not use `--ephemeral` for real relays; it is only for backend smoke tests and will not reliably surface in the UI.

Auto-launch a relay only when the context threshold is crossed:

```bash
<te-command> context auto-relay --execute
```

Ask the old session a narrow follow-up:

```bash
<te-command> context ask-old \
  --handoff <handoff-file> \
  --question "<specific missing fact>" \
  --execute
```

Omit `--execute` on `relay` / `auto-relay` / `ask-old` to dry-run routing and confirm what would be launched/queried. Add `--execute` to actually do it. Use `--ephemeral` on `relay` only for throwaway smoke tests.
