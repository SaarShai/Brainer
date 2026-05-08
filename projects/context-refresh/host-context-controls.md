---
type: project
axis: context-refresh
tags: [context-refresh, codex, claude, handoff]
confidence: high
evidence_count: 4
---

# Host context controls

## Current truth

Token Economy can prepare lean handoffs and durable wiki memory, but the host controls whether the active model context is actually cleared.

Claude Code has a native `/clear` command. The Claude `summ` procedure should summarize current work, document durable memory, create the handoff, run or ask the user to run `/clear`, then load only `start.md` plus the handoff.

Codex in the tested Desktop/App Server environment did not expose a reliable in-thread clear from inside the assistant. The direct App Server current-thread compact path was tested against `CODEX_THREAD_ID`: `thread/resume` and `thread/compact/start` succeeded, but `thread/compacted` did not emit. Root cause was the host config error:

```text
Invalid Value: 'tools.defer_loading'. Deferred tools require tools.tool_search.
```

The `./te context codex-compact-thread` subcommand and the inline `summ-codex-manual.md` launcher were both removed in 2026-05-08 because they relied on this broken path; original sources are preserved under `L4_archive/`. The verified Codex workaround is a persistent fresh successor thread via `./te context codex-fresh-thread --handoff <handoff-file> --execute`, which uses App Server `thread/start` plus `turn/start` seeded only with `start.md` and a handoff. This starts clean continuation but does not reduce the old visible thread's context meter.

## Operational rule

- For Claude: use native `/clear` for a real context clear.
- For Codex: say plainly that current-thread clear is not solved in this environment. Use `./te context codex-fresh-thread` for clean continuation (not visible-thread clearing).
