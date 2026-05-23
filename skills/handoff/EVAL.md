# EVAL — `handoff`

## Static cost (measured)

| field | tokens / size |
|---|---|
| description (always resident) | **114 tokens** (501 chars) |
| body (loaded on trigger)      | **967 tokens** (3926 chars) |
| tools/ payload                 | 28.3 KB |
| model pin                      | `any` |
| effort pin                     | `low` |

agentskills.io budget reference: description ≤ 1,536 chars (1% of a 200K context window).

## A/B savings (measured, N=3 × 0 prompts, model=?)

| metric | without skill | with skill | Δ | 95% CI |
|---|---|---|---|---|
| input tokens (mean)  | — | — | — | n/a |
| output tokens (mean) | — | — | — | n/a |
| latency (ms)         | — | — | n/a | n/a |
| judge score (0–5)    | —   |   |   |   |


Raw: [`eval/results/handoff.json`](../../eval/results/handoff.json)


## Methodology

- Sample size: N=3-10 local smoke; N≥50 on Kaggle T4 for any >20% savings claim.
- Tasks: 3–5 representative prompts in `eval/tasks/handoff.yaml`.
- Backends supported: `ollama`, `anthropic`, `mimo`, `mlx` (`--backend` arg).
- Judge: Xiaomi MiMo via `https://api.xiaomimimo.com/v1` (preferred for quality) or local Ollama.
- Rubric: per-task rubric embedded in the YAML.

## Failure modes

To be filled in after analysis of result outputs (see raw JSON for individual trial outputs).
