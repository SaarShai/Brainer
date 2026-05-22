# EVAL — `context-refresh`

## Static cost (measured)

| field | tokens / size |
|---|---|
| description (always resident) | **89 tokens** (313 chars) |
| body (loaded on trigger)      | **1125 tokens** (3937 chars) |
| tools/ payload                 | 43.8 KB |
| model pin                      | `any` |
| effort pin                     | `medium` |

agentskills.io budget reference: description ≤ 1,536 chars (1% of a 200K context window).

## A/B savings (pending live run)

```bash
. .token-economy/secrets.env && export MIMO_API_KEY
python3 eval/runner.py --task eval/tasks/context-refresh.yaml --n 10 --backend mimo --model mimo-v2-flash
python3 eval/judge.py eval/results/context-refresh.json --model mimo-v2.5-pro --backend ollama
```

| metric | without skill | with skill | Δ | 95% CI |
|---|---|---|---|---|
| input tokens (mean)  |   |   |   |   |
| output tokens (mean) |   |   |   |   |
| latency (ms)         |   |   |   |   |
| judge score (0–5)    |   |   |   |   |


## Methodology

- Sample size: N=3-10 local smoke; N≥50 on Kaggle T4 for any >20% savings claim.
- Tasks: 3–5 representative prompts in `eval/tasks/context-refresh.yaml`.
- Backends supported: `ollama`, `anthropic`, `mimo`, `mlx` (`--backend` arg).
- Judge: Xiaomi MiMo via `https://api.xiaomimimo.com/v1` (preferred for quality) or local Ollama.
- Rubric: per-task rubric embedded in the YAML.

## Failure modes

To be filled in after analysis of result outputs (see raw JSON for individual trial outputs).
