---
type: project
axis: cross_session_memory
tags: [context-refresh, checkpoint, compaction]
confidence: med
evidence_count: 1
---

# context-refresh

Fresh-context workflow for preventing context rot.

## Contract

- Estimate context fullness with `./te context status`.
- Default max context: detected from config/env or fallback `128000`.
- Default trigger: `refresh_threshold: 0.20`.
- At threshold, run `./te context checkpoint`.
- On manual `summ`, split lean handoff from durable wiki memory.
- Durable wiki memory is handled by a lightweight documenter using `prompts/subagents/wiki-documenter.prompt.md`; this is the documentation lifecycle routing layer.
- If the host can clear context natively, use that control after creating the handoff. Claude Code's `/clear` is the known manual clear path.
- Codex current-thread clearing is not solved in the tested environment; App Server current-thread compact failed with `tools.defer_loading`. Use a fresh successor thread only as a clean-continuation workaround, not as a claim that the old visible context was cleared.

## Packet

Fresh packets are written to `.token-economy/checkpoints/` and kept under 2000 estimated tokens by default. Each packet includes:

- mandatory plan-mode instruction
- goal and current plan
- memory pointers
- touched files, commands, and errors extracted from transcript when provided
- open decisions and retrieval instructions
- links to documented durable memory instead of loading docs-only details

## Commands

```bash
./te context status
./te context checkpoint --goal "..." --plan "..." --transcript /path/to/transcript.jsonl
./te context fresh-start
```
