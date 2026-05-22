# Kaggle eval results

## v4-coqa-n50.jsonl (2026-04-18, CPU, Qwen2.5-1.5B target+judge)

| cond | mean_tok | score CI | savings | Δ vs A |
|---|---:|---:|---:|---:|
| A_full | 434 | 1.80 [1.44, 2.16] | 0% | — |
| B_v1_0.5 | 186 | 1.88 [1.52, 2.24] | **57.3%** | +0.08 [−0.18, +0.34] |
| C_v2_0.7 | 274 | 2.02 [1.68, 2.36] | 37.0% | +0.22 [−0.10, +0.58] |

N=50 items × 3 conds × 1 run. Bootstrap 95% CI (n=2000). CoQA multi-turn items (avg ctx ~1755 chars).

**Finding:** compression neutral-to-positive on quality. Δ CIs cross zero but direction suggests compression doesn't harm CoQA-style extraction + may slightly help (model sees signal-denser context).

**Caveats:** 1.5B Qwen is small; self-judging (target=judge) weakens signal; 1 run per (item,cond) = wide CIs. Repeat with 7B+ and independent judge for tighter numbers.
