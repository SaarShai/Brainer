# EVAL — `wiki-refresh`

## Static cost (measured)

| field | tokens / size |
|---|---|
| description (always resident) | **76 tokens** (350 chars) |
| body (loaded on trigger)      | **1691 tokens** (7036 chars) |
| tools/ payload                 | 0.0 KB |
| model pin                      | `any` |
| effort pin                     | `medium` |

agentskills.io budget reference: description ≤ 1,536 chars (1% of a 200K context window).

## A/B savings (pending live run)

```bash
. .brainer/secrets.env && export MIMO_API_KEY
python3 eval/runner.py --task eval/tasks/wiki-refresh.yaml --n 10 --backend mimo --model mimo-v2-flash
python3 eval/judge.py eval/results/wiki-refresh.json --model mimo-v2-flash --backend mimo
```

| metric | without skill | with skill | Δ | 95% CI |
|---|---|---|---|---|
| input tokens (mean)  |   |   |   |   |
| output tokens (mean) |   |   |   |   |
| latency (ms)         |   |   |   |   |
| judge score (0–5)    |   |   |   |   |


## Methodology

- Sample size: N=3-10 local smoke; N≥50 on Kaggle T4 for any >20% savings claim.
- Tasks: 3–5 representative prompts in `eval/tasks/wiki-refresh.yaml`.
- Backends supported: `ollama`, `anthropic`, `mimo`, `mlx` (`--backend` arg).
- Judge: Xiaomi MiMo or local Ollama.

## Failure modes

To be filled in after analysis of result outputs.
