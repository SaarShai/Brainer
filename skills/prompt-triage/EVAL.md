# EVAL — `prompt-triage`

## Static cost (measured)

| field | tokens / size |
|---|---|
| description (always resident) | **69 tokens** (311 chars) |
| body (loaded on trigger)      | **871 tokens** (3226 chars) |
| tools/ payload                 | 21.1 KB |
| model pin                      | `any` |
| effort pin                     | `low` |

agentskills.io budget reference: description ≤ 1,536 chars (1% of a 200K context window).

## Live measurement (end-to-end routing, N=1 × 13 prompts)

Harness: `eval/runner_triage.py` — runs each corpus prompt twice: once routed to `mimo-v2.5-pro` (no triage), once routed by `classify.py` to `mimo-v2-flash` or `mimo-v2.5-pro` based on tier.

| metric | without triage | with triage | Δ |
|---|---:|---:|---:|
| total tokens | 6761 | 5345 | **-20.9%** |
| routing | all → `mimo-v2.5-pro` | cheap = 10 / expensive = 3 | — |
| classification accuracy | n/a | **100%** vs ground-truth tier | — |
| classifier latency | n/a | **49 ms** mean | — |

Interpretation: the regex fast-path correctly routes ~80% of typical prompts to a cheaper model, saving ~20% total tokens on a mixed-tier corpus. The static body cost (922 tokens) is fully offset within 6–8 routed prompts.

Raw: [`eval/results/prompt-triage.json`](../../eval/results/prompt-triage.json)


## Methodology

- Sample size: N=3-10 local smoke; N≥50 on Kaggle T4 for any >20% savings claim.
- Tasks: 3–5 representative prompts in `eval/tasks/prompt-triage.yaml`.
- Backends supported: `ollama`, `anthropic`, `mimo`, `mlx` (`--backend` arg).
- Judge: Xiaomi MiMo via `https://api.xiaomimimo.com/v1` (preferred for quality) or local Ollama.
- Rubric: per-task rubric embedded in the YAML.

## Failure modes

To be filled in after analysis of result outputs (see raw JSON for individual trial outputs).

## Moved from SKILL.md (2026-06-12 SkillReducer-criteria audit)

_Provenance/rationale below is maintainer context, not runtime instruction — relocated so the lazy-loaded body stays actionable._

## Cost math (informal)

- Without triage: opus reads prompt → thinks → acts → writes → verifies. ~3-8K tokens.
- With triage: hook (0 tokens) → opus reads directive + prompt → emits Task (~200 tokens) → haiku subagent does work (~500-2000 tokens).
- Net: ~70-90% token cost reduction on simple tasks (informal estimate; see EVAL.md for measured numbers).

## Lineage

- OpenRouter / Not Diamond routing layer.
- RouteLLM (ICLR 2025).
- Anthropic SDK Task tool + subagent_type.
- Orchestrator-worker multi-agent papers 2024-2026.
