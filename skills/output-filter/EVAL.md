# EVAL — `output-filter`

## Static cost (measured)

| field | tokens / size |
|---|---|
| description (always resident) | **70 tokens** (347 chars) |
| body (loaded on trigger)      | **589 tokens** (2536 chars) |
| tools/ payload                 | 33.9 KB |
| model pin                      | `any` |
| effort pin                     | `low` |

agentskills.io budget reference: description ≤ 1,536 chars (1% of a 200K context window).

## Savings (measured, N=4 noisy samples — deterministic, no LLM)

output-filter is a byte-level tool-stdout filter, not an LLM A/B, so the metric is **bytes filtered + error-line fidelity**, not token deltas. Re-run live via `python3 eval/runner_filter.py` (RC=0, byte-identical to committed).

| metric | raw | filtered | Δ |
|---|---|---|---|
| total bytes | 6074 | 679 | **−88.8%** |
| error lines preserved | 5 | 5 | **5/5 verbatim** |

Per-sample: ansi_progress −89.9% · ci_log −84.9% · dup_stdout −97.1% · mixed_signal −83.1%.

Raw: [`eval/results/output-filter.json`](../../eval/results/output-filter.json)


## Methodology

- Sample size: N=3-10 local smoke; N≥50 on Kaggle T4 for any >20% savings claim.
- Tasks: 3–5 representative prompts in `eval/tasks/output-filter.yaml`.
- Backends supported: `ollama`, `anthropic`, `mimo`, `mlx` (`--backend` arg).
- Judge: Xiaomi MiMo via `https://api.xiaomimimo.com/v1` (preferred for quality) or local Ollama.
- Rubric: per-task rubric embedded in the YAML.

## Failure modes

Premortem ([`LEARNING_CONTRACT`](../_shared/LEARNING_CONTRACT.md) §8):

- **Silent-failure path** — the filter's job is to preserve error lines verbatim
  while dropping everything else; if a future log format buries a failure signal in
  a line shape the `ERROR`/`FAILED` matcher doesn't recognize, that line gets
  collapsed as noise along with the progress-bar redraws, and the agent sees a
  clean, quiet stream instead of the buried failure.
- **Rot-when-unwatched** — the ANSI-stripping and dedup patterns are tuned against
  today's CI/build tool output shapes; as build tools change their progress-bar
  escape sequences or logging framework, the filter keeps running and keeps
  producing SOME reduction, masking the fact that its actual signal/noise split
  against the new format has drifted from the measured 88.8%/5-of-5 baseline.
- **No-hooks host** — output-filter is "wire as a shell pipe or PostToolUse hook,"
  not auto-installed; on a host where that wiring step was skipped, Bash stdout
  reaches the agent raw and unfiltered, with no fallback path narrowing it.

## Measured gain (2026-06-13, `eval/gains.py`)

**83.6% fewer tokens** on a realistic noisy build/test stream (redrawing progress bar + ANSI + cycling compile logs), with the `ERROR`/`FAILED` signal lines preserved verbatim (0% signal loss). Perf is locked by `eval/sims/hotpath_perf.py` (ANSI+dedupe on 10k hostile lines under a hard time budget).

## Deterministic checks

`python3 skills/output-filter/tools/test_output_filter.py` — 10 tests covering ANSI stripping, error preservation, content-aware search/log/diff summaries, raw archive rewind, `rewind --grep`, and opt-in recovery markers.
