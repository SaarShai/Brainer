---
name: context-keeper
description: PreCompact hook that extracts structured state (files, commands, errors, numbers, decisions, failures) from the transcript before compaction. Preserves grep-able recovery memory so the summarizer can't silently drop facts. Use when the host supports project-local PreCompact hooks.
model: haiku
effort: low
tools: [Bash, Read, Write]
---

# context-keeper — structured memory before compaction

## What it does

Parses the transcript JSONL, regex-extracts structured state (goals, files touched, commands, errors, numbers, failures). Optional LLM pass (local `gemma4:31b` by default) pulls out decisions and next-steps. Writes a terse markdown packet to `.token-economy/checkpoints/<timestamp>-precompact.md` and emits a one-line pointer the summarizer must preserve.

Tested on a 150-turn session: 68 files, 21 commands, 21 errors logged into a single grep-able page.

## Install

Claude Code (project-local):

```bash
bash skills/context-keeper/tools/install.sh --project
```

Wires `tools/hook.sh` into `.claude/settings.json` under `PreCompact`.

## Rules

- Don't load the full transcript in the hook — read JSONL incrementally.
- Output stays terse.
- Preserve exact paths, commands, numbers, error strings verbatim.

## Files

```
tools/
├── extract.py     # regex extractor + optional LLM pass
├── hook.sh        # PreCompact entry
└── install.sh     # wires into project-local .claude/
```

## Lineage

Pattern aligned with coleam00/claude-memory-compiler (SessionEnd → distillation). This skill targets PreCompact specifically — intra-session memory survival, not cross-session synthesis.
