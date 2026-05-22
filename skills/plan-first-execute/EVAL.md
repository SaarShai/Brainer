# EVAL — `plan-first-execute`

## Static cost (measured)

| field | tokens / size |
|---|---|
| description (always resident) | **70 tokens** (246 chars) |
| body (loaded on trigger)      | **176 tokens** (617 chars) |
| tools/ payload                 | 0.0 KB |
| model pin                      | `any` |
| effort pin                     | `medium` |

agentskills.io budget reference: description ≤ 1,536 chars (1% of a 200K context window).

## A/B savings (pending live run)

Run:

```bash
python3 eval/runner.py --task eval/tasks/plan-first-execute.yaml --n 10 --backend ollama
python3 eval/judge.py eval/results/plan-first-execute.json
```

Once Ollama (or Anthropic API) is wired, fill this table:

| metric | without skill | with skill | Δ | 95% CI |
|---|---|---|---|---|
| input tokens (mean)  |   |   |   |   |
| output tokens (mean) |   |   |   |   |
| latency (ms)         |   |   |   |   |
| judge score (0–5)    |   |   |   |   |

## Methodology

- Sample size: N=10 local smoke; N≥50 on Kaggle T4 for any >20% savings claim.
- Tasks: 3–5 representative prompts in `eval/tasks/plan-first-execute.yaml`.
- Judge: Xiaomi MiMo-7B via HF inference (or local Gemma fallback).
- Rubric: per-task rubric embedded in the YAML.

## Failure modes

To be filled in after live runs.
