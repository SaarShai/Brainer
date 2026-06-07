---
schema_version: 2
title: "cross-model-ollama-eval-gotchas"
type: concept
domain: "eval-methodology"
tier: semantic
confidence: 0.5
created: "2026-06-06"
updated: "2026-06-07"
verified: "2026-06-06"
sources: [eval/kaggle_ollama/runner_ollama_triage.py, eval/kaggle_ollama/README_OLLAMA.md]
supersedes: []
superseded-by:
tags: [eval-methodology, ollama, local-models, cross-model]
---

# cross-model-ollama-eval-gotchas

## Summary

Local cross-model Ollama scoring silently fails on reasoning models — use non-reasoning models or strip `<think>` blocks before scoring.

## Evidence

- `eval/kaggle_ollama/runner_ollama_triage.py` — the cross-model local runner.
- `qwen3.6:35b-a3b-q4km`: degenerate ~2-token generation via `/api/generate`, `eval_count=2`.
- `gemma4:26b`: orphaned manifest, 404 despite showing in `/api/tags`.
- 3-family suite (qwen/Alibaba · llama/Meta · gemma/Google) confirmed memory mechanisms aren't single-model artifacts.

## Related

- [[concepts/optimization-axes]]
- [[concepts/framework-hardening-adoption]]
- [[index]]
- [[schema]]

## Open Questions

- None yet.

## Lesson

Cross-model ollama eval fails with reasoning models: `qwen3.6:35b-a3b-q4km` returns empty outputs via /api/generate (degenerate ~2-token generation, eval_count=2); `gemma4:26b` is an orphaned manifest (404 not found despite appearing in /api/tags). The fix is to use non-reasoning models (`qwen2.5:7b-instruct`, `llama3.1:8b`, `gemma2:9b`) or strip <think> blocks before scoring. The 3-family suite (qwen/Alibaba · llama/Meta · gemma/Google) confirmed the memory mechanisms are not single-model artifacts.
