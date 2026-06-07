---
schema_version: 2
title: "cross-model-ollama-eval-gotchas"
type: concept
domain: "eval-methodology"
tier: semantic
confidence: 0.5
created: "2026-06-06"
updated: "2026-06-06"
verified: "2026-06-06"
sources: []
supersedes: []
superseded-by:
tags: []
---

# cross-model-ollama-eval-gotchas

## Summary

One compact statement.

## Evidence

- Source or command path.

## Related

- [[index]]
- [[schema]]

## Open Questions

- None yet.

## Lesson

Cross-model ollama eval fails with reasoning models: `qwen3.6:35b-a3b-q4km` returns empty outputs via /api/generate (degenerate ~2-token generation, eval_count=2); `gemma4:26b` is an orphaned manifest (404 not found despite appearing in /api/tags). The fix is to use non-reasoning models (`qwen2.5:7b-instruct`, `llama3.1:8b`, `gemma2:9b`) or strip <think> blocks before scoring. The 3-family suite (qwen/Alibaba · llama/Meta · gemma/Google) confirmed the memory mechanisms are not single-model artifacts.
