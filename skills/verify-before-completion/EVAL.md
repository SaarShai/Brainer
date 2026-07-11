# EVAL — `verify-before-completion`

## Static cost (measured)

| field | tokens / size |
|---|---|
| description (always resident) | **34 tokens** (170 chars) |
| body (loaded on trigger)      | **652 tokens** (2833 chars) |
| tools/ payload                 | 18.5 KB |
| model pin                      | `any` |
| effort pin                     | `low` |

agentskills.io budget reference: description ≤ 1,536 chars (1% of a 200K context window).

## A/B savings (output deltas N=50 × 5 prompts; judge only N=15 — N=50 judge pending), model=mimo-v2-flash

| metric | without skill | with skill | Δ | 95% CI |
|---|---|---|---|---|
| input tokens (mean)  | 118 | 326 | +176.6% | n/a |
| output tokens (mean) | 316 | 210 | -33.5% | n/a |
| latency (ms)         | 5349 | 4764 | n/a | n/a |
| judge score (0–5)    | 4.07 | 3.67 | **-0.40 (N=15 only)** | n/a |

> ⚠ The judge row is **N=15, not N=50**: the N=50 judge pass died on `MiMo 402: Insufficient balance` and was never re-run (see `eval/FINDINGS.md`). The committed `verify-before-completion.judged.json` is the N=15 partial. Treat −0.40 as a provisional, small-N signal (and a likely rubric artifact — the rubric scored "demands fresh evidence" below "affirms confidently"), not a settled N=50 result.


Raw: [`eval/results/verify-before-completion.json`](../../eval/results/verify-before-completion.json)


## Methodology

- Sample size: N=3-10 local smoke; N≥50 on Kaggle T4 for any >20% savings claim.
- Tasks: 3–5 representative prompts in `eval/tasks/verify-before-completion.yaml`.
- Backends supported: `ollama`, `anthropic`, `mimo`, `mlx` (`--backend` arg).
- Judge: Xiaomi MiMo via `https://api.xiaomimimo.com/v1` (preferred for quality) or local Ollama.
- Rubric: per-task rubric embedded in the YAML.

## Failure modes

Premortem ([`LEARNING_CONTRACT`](../_shared/LEARNING_CONTRACT.md) §8):

- **Silent-failure path** — the checklist (steps 1-6) and `tools/verify_artifact.py` are both
  invoked by choice, in-band; a done-claim that skips the tool entirely produces ordinary
  prose with no distinguishing shape from a gated one — there is no mechanical trace that the
  rubric-vs-evidence match never ran. The `claim_without_evidence` / `early_stop` /
  `completion_without_closure` probes in `compliance-canary` are the only thing that can catch
  this after the fact, and only inside a host where that hook is wired.
- **Rot-when-unwatched** — the anti-patterns list ("don't claim tests pass without a fresh
  run", etc.) is prose that ages as new claim-shapes emerge (a new tool, a new kind of
  artifact) that the list never named; nothing re-derives the list from real failures, so it
  drifts toward covering yesterday's mistakes while a new done-claim shape ships unchecked.
- **No-hooks host** — the two mechanical backstops (`early_stop`, `completion_without_closure`
  drift probes) live in `compliance-canary`'s hook and require it wired; on Codex/Gemini this
  needs the explicit hook-porting step in `docs/HOST_CAPABILITY_MATRIX.md`
  (`.codex/hooks.json` / `gemini hooks migrate --from-claude`). Absent that, this skill's
  rules still bind (they're prose instructions, portable to any host) but nothing mechanically
  interrupts an agent that starts writing "next I'll…" instead of doing the work now.
