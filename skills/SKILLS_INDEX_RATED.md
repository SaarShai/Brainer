# Skills — Rated Index

All 15 skills, rated on efficiency, gain, reliability, and quality loss.
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
| 1 | [caveman-ultra](../skills/caveman-ultra/SKILL.md) | **A** | **A** | **B** | **?** | 81 | 235 | +560% | -85% | — | 3 |
| 2 | [prompt-triage](../skills/prompt-triage/SKILL.md) | **?** | **?** | **A** | **?** | 89 | 922 | — | — | — | — |
| 3 | [skill-creator](../skills/skill-creator/SKILL.md) | **?** | **?** | **A** | **?** | 138 | 879 | — | — | — | — |
| 4 | [context-refresh](../skills/context-refresh/SKILL.md) | **?** | **?** | **A** | **?** | 89 | 876 | — | — | — | — |
| 5 | [delegate](../skills/delegate/SKILL.md) | **?** | **?** | **A** | **?** | 97 | 872 | — | — | — | — |
| 6 | [wiki-memory](../skills/wiki-memory/SKILL.md) | **?** | **?** | **A** | **?** | 108 | 764 | — | — | — | — |
| 7 | [compress-context](../skills/compress-context/SKILL.md) | **?** | **?** | **A** | **?** | 127 | 551 | — | — | — | — |
| 8 | [semantic-diff](../skills/semantic-diff/SKILL.md) | **?** | **?** | **A** | **?** | 99 | 484 | — | — | — | — |
| 9 | [memory-api](../skills/memory-api/SKILL.md) | **?** | **?** | **A** | **?** | 82 | 447 | — | — | — | — |
| 10 | [lean-execution](../skills/lean-execution/SKILL.md) | **?** | **?** | **B** | **?** | 63 | 409 | — | — | — | — |
| 11 | [output-filter](../skills/output-filter/SKILL.md) | **?** | **?** | **A** | **?** | 99 | 370 | — | — | — | — |
| 12 | [context-keeper](../skills/context-keeper/SKILL.md) | **?** | **?** | **A** | **?** | 80 | 360 | — | — | — | — |
| 13 | [personal-assistant](../skills/personal-assistant/SKILL.md) | **?** | **?** | **B** | **?** | 57 | 329 | — | — | — | — |
| 14 | [plan-first-execute](../skills/plan-first-execute/SKILL.md) | **?** | **?** | **C** | **?** | 70 | 176 | — | — | — | — |
| 15 | [verify-before-completion](../skills/verify-before-completion/SKILL.md) | **?** | **?** | **C** | **?** | 49 | 164 | — | — | — | — |

## What the columns mean

- **desc tok**: always-resident description size; sum across the catalog = the context tax for having the skill available.
- **body tok**: skill protocol size; loaded only when the skill triggers.
- **Δin%**: change in input tokens per call with the skill loaded (positive = skill adds context cost).
- **Δout%**: change in output tokens per call (negative = skill makes output tighter — usually what we want).
- **Δjudge**: change in judge quality score (0–5 scale).
- **N**: live-run sample size.

## Notes

- Hook skills (`prompt-triage`, `context-keeper`, `output-filter`) do NOT prepend to the system message; their cost is the hook script's transcript footprint, not in-context tokens. The in-context A/B harness understates their value.
- Skills with high body cost (`prompt-triage`, `skill-creator`, `delegate`) are still cheap as long as they load on trigger — the body never enters context unless invoked.
- A `?` in any column means the live A/B hasn't been run for that skill yet; the static cost is always populated.