---
type: project
axis: skill_crystallization
tags: [delegation, routing, subagents, models, glm, zai]
confidence: med
evidence_count: 2
---

# delegate-router

Model-agnostic routing policy for subagents and cheaper models.

## Contract

- Prefer cheapest capable worker.
- Use local/cheap models (ollama via `local-ollama`) for extraction, summaries, lint, simple edits, wiki updates, and classification.
- Use **GLM-5.2 via z.ai** (`glm-executor` agent) for bounded summarize/rewrite/classify/extract over SUPPLIED content — frontier-capable, 1M ctx, cheap, out-of-platform. Sits between local-ollama (too weak) and opus (overkill).
- Use medium models for bounded research and multi-step but low-risk work.
- Use frontier models for architecture, ambiguity, high-risk domains, and final synthesis.
- Spawn parallel workers only when tasks are independent and scopes are disjoint.
- Workers receive compact briefs and return compact result packets.
- For task repos with GitHub remotes, route verified save-points to the lightweight repo-maintainer worker; skip repo maintenance when no GitHub remote exists.
- Context discipline comes before model choice: search/map first, then fetch only relevant files and nearby tests.

## Commands

```bash
./te delegate models
./te delegate classify "task"
./te delegate plan "task"
./te cost preflight "task"
./te cost profile --transcript <path>
./te cost report
./te delegate cost-check "task"  # compatibility alias
```

Routing/classification now lives in `skills/prompt-triage/SKILL.md`; delegation pruning in `skills/lean-execution/SKILL.md`. (The `./te delegate`/`./te cost` commands above reflect the former Brainer CLI surface.)

## Cost preflight

`te cost preflight` is the practical guardrail for the common AI coding context leak:

1. refuse full-repo/full-transcript context by default;
2. use `./te code map` and `rg` before opening files;
3. load only relevant files plus nearby tests;
4. batch related reads and summarize large outputs;
5. keep stable prefix files stable so provider prompt caches can work;
6. checkpoint long sessions instead of carrying a growing transcript forever.

Use it before broad implementation or review work when the next action is not obvious.

## 2026-06-19 — z.ai / GLM-5.2 integration

- **Key store:** canonical at `~/.config/zai/key` (mode 600). `~/.zshrc` exports `ZAI_API_KEY` from it + `ZAI_ANTHROPIC_BASE_URL` / `ZAI_OPENAI_BASE_URL`. Agents read env → fall back to the file. NOT auto-routed globally (opt-in).
- **Endpoints:** Anthropic wire `https://api.z.ai/api/anthropic` (Claude Code, `glm` launcher fn); OpenAI wire `https://api.z.ai/api/coding/paas/v4` (Codex `--profile glm`, glm-executor). Model id `glm-5.2`.
- **glm-executor agent** (`skills/prompt-triage/tools/agents/glm-executor.md`): thin haiku coordinator that shells out to z.ai (mirrors `local-ollama`). A Claude subagent CANNOT reroute its own inference out-of-platform, so the only working pattern is call-out-via-Bash.
- **GOTCHA — GLM-5.2 is a reasoning model.** It emits a large `reasoning_content` field that wastes the token budget AND truncates the JSON (invalid-JSON failure) when `max_tokens` is hit mid-reasoning. ALWAYS pass `"thinking":{"type":"disabled"}` for bounded executor tasks. Verified: clean output, ~42 vs reasoning-heavy tokens.
- prompt-triage routes summarize/rewrite + classify/extract verbs → `glm-executor` (overrode the 2026-06-12 in-platform-only policy, scoped to bounded self-contained content tasks).

## 2026-06-19 — routing revised from production-router research

Researched how production routers decide (RouteLLM, IPR, FrugalGPT, RouterBench/RouterArena, kNN). Evidence-backed changes to `skills/prompt-triage/tools/classify.py`:

- **Don't route on the local LLM's verbalized confidence** — it is ~random as a signal (arXiv:2502.00409 citing Xiong et al. ICLR 2024 / 2306.13063; 2502.04428). FIX: Ollama-fallback verdicts now require **regex corroboration** (same agent/tier) to clear the 0.7 emit gate; uncorroborated → confidence forced to 0.5 → defers to the main (strongest) model. Sources `ollama+regex-corroborated` / `ollama-uncorroborated`.
- **Fall back to strongest on no clear winner** — IPR's empty-feasible-set→predicted-best pattern (arXiv:2509.06274). Already present (low-conf → opus); validated.
- **Regex/domain layer = the OOD-robust first pass** — query-level complexity beats domain routing in-distribution but generalizes worse OOD; hedge across both (arXiv:2502.00409 §4.2.2). Keep regex as first pass, refine with the (corroborated) LLM signal.
- **NOT done: size-aware GLM split.** Input length / context size were NOT confirmed as small-model-sufficiency predictors (capability-gap claim refuted 1-2). The strongest confirmed signal is a learned per-prompt quality/win-probability estimate — not built (needs labeled data).
- **Open methodological debt:** no cost-quality eval harness yet. Research is unanimous (3-0): benchmark a simple baseline (best-single / kNN) with an AIQ-style cost-quality curve before fancier routers (RouterBench arXiv:2403.12031; kNN arXiv:2505.12601). The current verifier is the unit suite (`test_classify.py`), not a routing-quality benchmark.

## Related

- [[patterns/tiny-model-router]] — the routing pattern this project implements.
