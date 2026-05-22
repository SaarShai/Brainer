# EVAL — `prompt-triage`

## Static cost (measured)

| field | tokens / size |
|---|---|
| description (always resident) | **89 tokens** (311 chars) |
| body (loaded on trigger)      | **922 tokens** (3226 chars) |
| tools/ payload                 | 21.1 KB |
| model pin                      | `local` |
| effort pin                     | `low` |

agentskills.io budget reference: description ≤ 1,536 chars (1% of a 200K context window).

## A/B savings (measured, N=1 × 13 prompts, model=?)

| metric | without skill | with skill | Δ | 95% CI |
|---|---|---|---|---|
| input tokens (mean)  | — | — | — | n/a |
| output tokens (mean) | — | — | — | n/a |
| latency (ms)         | — | — | n/a | n/a |
| judge score (0–5)    | —   |   |   |   |


Raw: [`eval/results/prompt-triage.json`](../../eval/results/prompt-triage.json)


## Methodology

- Sample size: N=3-10 local smoke; N≥50 on Kaggle T4 for any >20% savings claim.
- Tasks: 3–5 representative prompts in `eval/tasks/prompt-triage.yaml`.
- Backends supported: `ollama`, `anthropic`, `mimo`, `mlx` (`--backend` arg).
- Judge: Xiaomi MiMo via `https://api.xiaomimimo.com/v1` (preferred for quality) or local Ollama.
- Rubric: per-task rubric embedded in the YAML.

## Failure modes

To be filled in after analysis of result outputs (see raw JSON for individual trial outputs).
