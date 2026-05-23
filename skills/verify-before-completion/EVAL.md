# EVAL — `verify-before-completion`

## Static cost (measured)

| field | tokens / size |
|---|---|
| description (always resident) | **34 tokens** (170 chars) |
| body (loaded on trigger)      | **209 tokens** (910 chars) |
| tools/ payload                 | 0.0 KB |
| model pin                      | `any` |
| effort pin                     | `low` |

agentskills.io budget reference: description ≤ 1,536 chars (1% of a 200K context window).

## A/B savings (measured, N=3 × 5 prompts, model=mimo-v2-flash)

| metric | without skill | with skill | Δ | 95% CI |
|---|---|---|---|---|
| input tokens (mean)  | 39 | 247 | +538.9% | n/a |
| output tokens (mean) | 426 | 233 | -45.2% | n/a |
| latency (ms)         | 7080 | 4876 | n/a | n/a |
| judge score (0–5)    | +4.07 | +3.67 | -0.40 |   |


Raw: [`eval/results/verify-before-completion.json`](../../eval/results/verify-before-completion.json)


## Methodology

- Sample size: N=3-10 local smoke; N≥50 on Kaggle T4 for any >20% savings claim.
- Tasks: 3–5 representative prompts in `eval/tasks/verify-before-completion.yaml`.
- Backends supported: `ollama`, `anthropic`, `mimo`, `mlx` (`--backend` arg).
- Judge: Xiaomi MiMo via `https://api.xiaomimimo.com/v1` (preferred for quality) or local Ollama.
- Rubric: per-task rubric embedded in the YAML.

## Failure modes

To be filled in after analysis of result outputs (see raw JSON for individual trial outputs).
