# EVAL — `wiki-refresh`

## Static cost (measured)

| field | tokens / size |
|---|---|
| description (always resident) | **76 tokens** (350 chars) |
| body (loaded on trigger)      | **1691 tokens** (7036 chars) |
| tools/ payload                 | 36.8 KB |
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

Premortem ([`LEARNING_CONTRACT`](../_shared/LEARNING_CONTRACT.md) §8):

- **Silent-failure path** — reconcile is invoked manually or via the opt-in
  `staleness.py nudge` `SessionStart` hook; a repo where that hook was never wired
  gets no reminder at all, so pages can drift for months against renamed/deleted
  code with nothing surfacing the gap until an unrelated task happens to touch the
  same file and notices the citation is wrong.
- **Rot-when-unwatched** — `audit-refs` and `claim-ground` catch a cited path going
  missing, but a page whose cited path still exists yet whose *behavior* changed
  underneath it (same filename, rewritten implementation) passes the refs check
  clean while the prose is now actively wrong — the Update-vs-Replace judgment call
  depends on a human/agent reading the diff, not a mechanical check.
- **No-hooks host** — the `disuse` signal (a tenth quality-scan lens, distinct from
  the code-groundedness nine) is **detection-only by design**: it flags a
  zero-read page as a prune/review candidate but never deletes, per
  [`LEARNING_CONTRACT §8`](../_shared/LEARNING_CONTRACT.md)'s requirement that a
  detection-only control name why no prevention twin exists — a page's future
  read-value can't be verified at write time, so gating writes on predicted disuse
  would block legitimate pages; the deletion call stays a human or a scheduled
  `wiki-refresh` run's decision, never automatic.
