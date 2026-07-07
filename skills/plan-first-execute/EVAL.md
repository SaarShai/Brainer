# EVAL — `plan-first-execute`

## Static cost (measured)

| field | tokens / size |
|---|---|
| description (always resident) | **62 tokens** (308 chars) |
| body (loaded on trigger)      | **625 tokens** (2852 chars) |
| tools/ payload                 | 0.1 KB |
| model pin                      | `any` |
| effort pin                     | `medium` |

agentskills.io budget reference: description ≤ 1,536 chars (1% of a 200K context window).

Static cost re-measured after the spec-first checkpoint update with
`python3 eval/static_cost.py --json`.

## A/B savings (measured, N=3 × 5 prompts, model=mimo-v2-flash)

| metric | without skill | with skill | Δ | 95% CI |
|---|---|---|---|---|
| input tokens (mean)  | 37 | 178 | +377.0% | n/a |
| output tokens (mean) | 1024 | 815 | -20.4% | n/a |
| latency (ms)         | 11235 | 10967 | n/a | n/a |
| judge score (0–5)    | +4.00 | +4.20 | +0.20 |   |


Raw: [`eval/results/plan-first-execute.json`](../../eval/results/plan-first-execute.json).
The A/B table predates the spec-first checkpoint text and should be refreshed
before making a stronger behavioral claim.


## Methodology

- Sample size: N=3-10 local smoke; N≥50 on Kaggle T4 for any >20% savings claim.
- Tasks: 3–5 representative prompts in `eval/tasks/plan-first-execute.yaml`.
- Backends supported: `ollama`, `anthropic`, `mimo`, `mlx` (`--backend` arg).
- Judge: Xiaomi MiMo via `https://api.xiaomimimo.com/v1` (preferred for quality) or local Ollama.
- Rubric: per-task rubric embedded in the YAML.

## Failure modes

Premortem ([`LEARNING_CONTRACT`](../_shared/LEARNING_CONTRACT.md) §8):

- **Silent-failure path** — the skill is a description-triggered prompt, not a hook; a
  model under time pressure can skip straight to editing a >3-step task and nothing
  anywhere records that the spec-first checkpoint was bypassed, so the omission is
  invisible until a downstream break traces back to a plan that never existed.
- **Rot-when-unwatched** — the trigger heuristics ("more than 3 steps, unclear scope,
  multiple files") are fixed thresholds written once; as the agent's own task mix
  shifts toward larger single-file refactors or smaller multi-file edits, the same
  numbers stop matching the tasks that actually need a plan, and nothing re-tunes them
  against current usage.
- **No-hooks host** — on a host without a `pulse_reminder`/re-anchor mechanism the
  confidence pre-flight and spec-first checkpoint are pure text convention with no
  enforcement; a host that drops mid-session context (long tool loop, compaction) can
  lose the plan discipline entirely with no reminder firing to restate it.
