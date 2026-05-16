---
schema_version: 2
title: AI Coding Bill Reduction Article Excerpt
type: source-summary
domain: tools
tier: episodic
confidence: 0.6
created: 2026-05-16
updated: 2026-05-16
verified: 2026-05-16
sources: ["user-provided article excerpt in Codex session 2026-05-16"]
supersedes: []
superseded-by:
tags: [routing, prompt-caching, context-discipline, cost-control]
---

# AI Coding Bill Reduction Article Excerpt

User provided a long article claiming a drop from `$4,200/month` to `$312/month` through smarter routing, prompt caching, and fixing token leaks.

## Useful claims to adopt

- Context discipline is the main lever: do not resend full repo/context when a symbol search or code map would find the needed slice.
- Route by task failure cost: premium models for architecture/security/high-risk decisions; cost-efficient coding models for routine implementation/debugging/review; lightweight/local models for lint, formatting, extraction, and boilerplate.
- Batch related tool calls and summarize large tool outputs before feeding them back to the model.
- Keep stable prompt prefixes stable so provider prompt caching can help.
- Turn repeated workflows into skills/SOPs so future agents skip rediscovery.
- Use local Ollama-style models for bounded boilerplate and classification when quality risk is low.
- Refresh/summarize long sessions instead of carrying a growing transcript forever.

## Rejected or caution-only claims

- The article's exact model names, versions, prices, and benchmark scores are provider-specific and were not independently verified in this pass.
- Do not hard-code one vendor/model, such as a Kimi default, into Token Economy universal policy without current availability, pricing, and quality evidence.
- Do not install global routers or mutate machine-wide agent settings from this adoption. Token Economy remains repo-local by default.

## Adopted locally

- `./te cost preflight "<task>"` now emits provider-free context/tool/session guidance.
- `./te cost profile --transcript <path>` flags repeated reads, oversized outputs, read-before-search order leaks, refresh pressure, and SOP candidates.
- `./te delegate cost-check "<task>"` remains as a compatibility alias for cost preflight.
- `hooks/user-prompt-submit.sh` emits a short nudge for broad work, stays quiet for small prompts, and supports `NO COST PREFLIGHT` plus `TOKEN_ECONOMY_COST_PREFLIGHT=0`.
- [[projects/delegate-router/README]] now treats cost preflight as the practical guardrail.
- [[concepts/prefix-caching]] now documents stable-prefix rules and the warning that caching is not a substitute for retrieval discipline.

## Related

- [[projects/delegate-router/README]]
- [[concepts/prefix-caching]]
- [[concepts/local-model-setup]]
- [[projects/agents-triage/SKILL]]
