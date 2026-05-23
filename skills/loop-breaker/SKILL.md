---
name: loop-breaker
description: PreToolUse hook that detects mid-task loops — N consecutive identical tool calls (same tool, same args). Injects a structured replan signal naming the loop and (optionally) hard-blocks on further repetition. Catches the most expensive drift symptom in long agent runs (rework loops burning opus tokens). Use when the host supports project-local PreToolUse hooks.
model: haiku
effort: low
tools: [Bash, Read, Write]
---

# loop-breaker — mid-task loop detector

## What it does

Watches every tool call. Computes a signature `(tool_name, sha256(canonical_json(tool_input)))`. Counts consecutive identical signatures. When the count hits a threshold (default 5), emits a structured `additionalContext` message naming the loop and quoting the repeated call — the agent sees it on the next turn and replans.

Optional escalation (`LOOP_BREAKER_HARD_BLOCK=1`): once past the threshold, further identical calls are denied via `permissionDecision: "deny"` with the same reason text.

Inspired by Gemini-CLI's `loopDetectionService.ts` (≥5 identical tool calls → halt). Fills the gap left by [claude-code#4277](https://github.com/anthropics/claude-code/issues/4277).

## Why it exists

The single most expensive agent-drift symptom in token-economy terms: the agent retries the same failing command 8, 12, 20 times. Each retry burns full main-context tokens. `verify-before-completion` runs once at the end. `plan-first-execute` runs once at the start. Neither watches the mid-run loop.

## Compatibility

**Claude Code only.** `PreToolUse` is a Claude-Code-specific hook event — the other catalog hosts (Codex/Cursor/Gemini) don't fire it, so the skill is a no-op there. The top-level `./install.sh` still symlinks the folder into all four host dirs so the description shows up in skill indexes; only the Claude Code installer wires the actual hook.

## Install

Claude Code (project-local):

```bash
bash skills/loop-breaker/tools/install.sh --project
```

Wires `tools/hook.sh` into `.claude/settings.json` under `PreToolUse` with matcher `*` (fires on every tool).

## Tuning

Environment variables (all optional):

- `LOOP_BREAKER_THRESHOLD` — consecutive-identical count that triggers the signal. Default `5`.
- `LOOP_BREAKER_HARD_BLOCK` — when set to `1`, deny further identical calls after threshold. Default off (warn-only).
- `LOOP_BREAKER_ALLOWLIST_TOOLS` — comma-separated tool names that never trigger (e.g. `Read,LS`). Default empty.
- `LOOP_BREAKER_STATE_DIR` — where session-scoped state lives. Default `.token-economy/loop-breaker/`.

## Rules

- Reset the counter on the first different signature; loops only count when truly consecutive.
- Never raise — the hook must exit 0 on every input, just like context-keeper. A failing PreToolUse hook would block the agent.
- Don't log args verbatim — store a 200-char preview only, hash the full input.
- State updates are guarded by an `fcntl.flock` against a sibling `.lock` file — parallel tool calls in the same session would otherwise race and under-count.

## Files

```
tools/
├── hook.sh        # PreToolUse shell shim (settings.json points here)
├── hook.py        # detection logic + JSON output (flock-guarded state)
├── install.sh     # wires PreToolUse into project-local .claude/
└── test.sh        # 17-case self-test; run after editing hook.py
```

## Reliability contract

The hook MUST exit 0 on every input. Verified edge cases:

- empty stdin payload
- malformed JSON
- missing `tool_name` field
- state-file unreadable or corrupt
- state dir unwritable (falls back to no-op)

Errors are logged to stderr with an ISO timestamp prefix; the tool call proceeds normally.

## Known gaps (v1)

- No PostToolUse exit-tracking. The "agent runs slightly different commands that all fail with the same error" pattern isn't caught yet. Add in v2.
- No agent-text-loop detection (Gemini-CLI also detects identical sentences ≥ 10×). Out of scope for a hook — needs transcript scanning.

## Lineage

- [google-gemini/gemini-cli](https://github.com/google-gemini/gemini-cli) `loopDetectionService.ts` — production reference; same ≥5 threshold.
- [anthropics/claude-code#4277](https://github.com/anthropics/claude-code/issues/4277) — open feature request, no first-party implementation yet.
- [rohitg00/pro-workflow](https://github.com/rohitg00/pro-workflow) — adjacent pattern: failed-correction rules auto-injected at SessionStart (cross-session, not in-loop).
