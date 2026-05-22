# Skills — Rated Index

All 13 skills, rated on efficiency, gain, reliability, and quality loss.
Static columns are deterministic. Live columns require a live A/B run via `eval/runner.py`.

### Rating scale

- **Efficiency**: net token savings (output cut weighted high, input cost weighted low). A ≥ 60%, B ≥ 30%, C ≥ 10%, D ≥ 0, F < 0.
- **Gain**: percentage output-token reduction when the skill is loaded. A ≥ 60%, B ≥ 30%, C ≥ 10%, D ≥ 0, F < 0 (worse).
- **Reliability**: qualitative, based on body length + bundled tools + EVAL.md presence. A = comprehensive, F = minimal.
- **Quality loss**: Δjudge score from A/B (negative = worse). A = 0 or positive, B ≥ −0.25, C ≥ −0.5, D ≥ −1.0, F < −1.0.

`?` = pending live measurement.

## Ranked table

| Rank | Skill | Eff | Gain | Reliab | Quality | desc tok | body tok | Δin% | Δout% | Δjudge | N |
|---:|---|:-:|:-:|:-:|:-:|---:|---:|---:|---:|---:|---:|
| 1 | [context-keeper](../skills/context-keeper/SKILL.md) | **A** | **A** | **A** | **?** | 80 | 360 | +0% | -98% | — | 1 |
| 2 | [caveman-ultra](../skills/caveman-ultra/SKILL.md) | **A** | **A** | **B** | **A** | 81 | 235 | +560% | -85% | +0.13 | 3 |
| 3 | [lean-execution](../skills/lean-execution/SKILL.md) | **B** | **B** | **B** | **A** | 63 | 409 | +722% | -56% | +0.00 | 3 |
| 4 | [verify-before-completion](../skills/verify-before-completion/SKILL.md) | **B** | **B** | **B** | **C** | 49 | 260 | +539% | -45% | -0.40 | 3 |
| 5 | [plan-first-execute](../skills/plan-first-execute/SKILL.md) | **C** | **C** | **C** | **A** | 70 | 176 | +377% | -20% | +0.20 | 3 |
| 6 | [prompt-triage](../skills/prompt-triage/SKILL.md) | **D** | **D** | **A** | **?** | 89 | 922 | +0% | -4% | — | 1 |
| 7 | [context-refresh](../skills/context-refresh/SKILL.md) | **?** | **?** | **A** | **?** | 89 | 1125 | — | — | — | — |
| 8 | [handoff](../skills/handoff/SKILL.md) | **?** | **?** | **B** | **?** | 143 | 881 | — | — | — | — |
| 9 | [delegate](../skills/delegate/SKILL.md) | **?** | **?** | **A** | **?** | 97 | 872 | — | — | — | — |
| 10 | [wiki-memory](../skills/wiki-memory/SKILL.md) | **?** | **?** | **A** | **?** | 108 | 764 | — | — | — | — |
| 11 | [compress-context](../skills/compress-context/SKILL.md) | **?** | **?** | **A** | **?** | 127 | 551 | — | — | — | — |
| 12 | [semantic-diff](../skills/semantic-diff/SKILL.md) | **?** | **?** | **A** | **?** | 99 | 484 | — | — | — | — |
| 13 | [output-filter](../skills/output-filter/SKILL.md) | **?** | **?** | **A** | **?** | 99 | 370 | — | — | — | — |

## What the columns mean

- **desc tok**: always-resident description size; sum across the catalog = the context tax for having the skill available.
- **body tok**: skill protocol size; loaded only when the skill triggers.
- **Δin%**: change in input tokens per call with the skill loaded (positive = skill adds context cost).
- **Δout%**: change in output tokens per call (negative = skill makes output tighter — usually what we want).
- **Δjudge**: change in judge quality score (0–5 scale).
- **N**: live-run sample size.

## Notes

- **caveman-ultra, lean-execution, plan-first-execute, verify-before-completion**: in-context A/B (`eval/runner.py`). Δout% is output-token reduction per call.
- **prompt-triage**: end-to-end routing A/B (`eval/runner_triage.py`). Δout% maps to **delta_total_pct** — total input+output tokens summed across the corpus when the cheap/expensive router is active.
- **context-keeper**: fidelity test (`eval/runner_keeper.py`), not a per-call A/B. Δout% maps to **compression of the extracted sidecar vs. the raw transcript** — the sidecar at 2.3% of raw size IS the value, since it survives compaction and the raw transcript usually doesn't. See its `EVAL.md` for per-category recall (URLs 100%, numbers 67%, commands 46%, errors 25%).
- **handoff, context-refresh, output-filter, wiki-memory, delegate, compress-context, semantic-diff**: live measurement pending. See each skill's `EVAL.md` for the methodology and any prior numbers.
- Hook skills (`prompt-triage`, `context-keeper`, `output-filter`) do NOT prepend to the system message in normal use; their cost is the hook script's transcript footprint, not in-context tokens.
- A `?` in any column means the live A/B hasn't been run for that skill yet; the static cost is always populated.