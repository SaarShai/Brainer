---
schema_version: 2
title: "auto-handoff — built then dropped (2026-05-31)"
type: decision
domain: framework
tier: episodic
confidence: 0.9
created: 2026-05-31
updated: 2026-05-31
verified: 2026-05-31
sources: ["session 2026-05-31", "commit b02d524 on eval-gate-skill (reverted)"]
supersedes: []
superseded-by:
contradicts: []
tags: [auto-handoff, dropped, session-launch, context-refresh]
---

# auto-handoff — built, then dropped

Built a working `auto-handoff` skill (UserPromptSubmit hook: measure transcript
fill each turn → at ≥threshold write a lean packet → hand off). Committed
`b02d524`, then **reverted at user request**. Detection/checkpoint worked
(meter 4/4, gate+packet+loop 8/8); the **auto-launch goal did not**.

## Why dropped

Goal: *type a trigger in one session → a NEW Claude Code session opens by itself,
loaded with the summary.* Found **not achievable in-app** today:

1. **No session-create API for hooks/skills.** Claude Code exposes nothing to
   programmatically create + load an in-app session. The `ccd_session_mgmt` MCP
   is list / search / archive only — no *create*. Dispatch / Remote-Control /
   desktop "new session" are **user/UI-triggered**, not hook-callable.
2. **Headless `claude -p` → 401.** The only programmatic launch needs
   `ANTHROPIC_API_KEY`; on OAuth/subscription it returns
   `401 Invalid authentication credentials` — **verified live** (hook-spawned
   pid 75757 *and* a plain `claude -p` from the shell both failed).
3. **The only working auto-open = a Terminal window** (`osascript` → interactive
   `claude`, which uses subscription auth). Rejected: wanted it in-app, not a
   terminal.

So the three launch paths are: no-API (impossible), headless (401), terminal
(rejected). The shipped fallback was `mode=notify` (detect + checkpoint, user
opens the session) — which the user did not want either.

## Lesson (don't re-attempt blindly)

Hook-driven **auto-creation of an in-app Claude Code session is not possible**
with current Claude Code + subscription auth. Revisit only if: Claude Code ships
a session-create API/tool; or an `ANTHROPIC_API_KEY` is adopted (then headless
`mode=spawn` works, metered + `--max-budget-usd`); or an out-of-app terminal
launch becomes acceptable.

Same root cause as [[context-refresh]] — whose auto-launcher was dropped in
v1.3.0 for being unreliable. This attempt reconfirms *why*: the missing piece was
never the trigger (UserPromptSubmit solved that), it's the **launch**.
