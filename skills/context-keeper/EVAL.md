# EVAL — `context-keeper`

## Static cost (measured)

| field | tokens / size |
|---|---|
| description (always resident) | **80 tokens** (281 chars) |
| body (loaded on trigger)      | **360 tokens** (1261 chars) |
| tools/ payload                 | 14.3 KB |
| model pin                      | `haiku` |
| effort pin                     | `low` |

agentskills.io budget reference: description ≤ 1,536 chars (1% of a 200K context window).

## Live measurement (extraction fidelity, N=1 real transcript)

Harness: `eval/runner_keeper.py` — feeds the extract.py script a transcript JSONL and counts (a) compression vs raw transcript, (b) per-category recall against a regex ground-truth count.

Input: 970-event transcript at `7523878a-45a4-4402-b4f1-2021683b7d51.jsonl`.

| metric | value |
|---|---|
| raw transcript | **493.7 KB** (970 events) |
| extracted sidecar | **11.3 KB** |
| **compression vs raw** | **2.3% of original (-97.7%)** |
| extract latency | 973 ms |
| URL recall | **100%** of 22 distinct URLs |
| Number-fact recall | **67%** of 63 numeric facts |
| Command recall | 46% of 87 distinct `Bash` cmds |
| Error recall | 25% of 111 error lines (de-duped) |
| File recall | 22% of 264 path mentions (top-N) |

Interpretation: the sidecar is **~44× smaller** than the raw transcript while capturing the high-leverage tail (URLs, measurements, frequent commands) that a generic `/compact` summariser drops. The full raw transcript wouldn't survive compaction; this sidecar does.

Raw: [`eval/results/context-keeper.json`](../../eval/results/context-keeper.json)


## Methodology

- Sample size: N=3-10 local smoke; N≥50 on Kaggle T4 for any >20% savings claim.
- Tasks: 3–5 representative prompts in `eval/tasks/context-keeper.yaml`.
- Backends supported: `ollama`, `anthropic`, `mimo`, `mlx` (`--backend` arg).
- Judge: Xiaomi MiMo via `https://api.xiaomimimo.com/v1` (preferred for quality) or local Ollama.
- Rubric: per-task rubric embedded in the YAML.

## Failure modes

To be filled in after analysis of result outputs (see raw JSON for individual trial outputs).
