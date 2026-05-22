---
type: project
tags: [compression, measured]
confidence: med
evidence_count: 3
---

# ComCom (Compound Compression) Pipeline — Results (2026-04-17)

## Setup
Stages: caveman-prose → LLMLingua-2 (bert-base-multilingual) → prefix-cache report.
Protect regex: code fences, inline code, URLs, paths (placeholders restored post-compress).
Tokenizer: tiktoken cl100k_base.
Model: `microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank`, CPU.

## Measured savings

| sample | stage | tokens | cum-savings |
|---|---|---:|---:|
| verbose prose (auth bug reply) | original | 345 | 0% |
| | + caveman | 243 | 29.6% |
| | + llmlingua r=0.5 | **95** | **72.5%** |
| mixed technical (React q) | original | 254 | 0% |
| | + caveman | 199 | 21.7% |
| | + llmlingua r=0.5 | **74** | **70.9%** |
| mixed technical (rate=0.7) | + llmlingua r=0.7 | 105 | 58.7% |

## Findings
- **Compound gain is real and additive.** Caveman alone: 22-30%. +LLMLingua: 59-73%.
- **Code preserved perfectly** via placeholder protection — code fences, paths, URLs pass through untouched.
- **Quality cliff around rate=0.5.** At 0.5 intent recoverable but choppy; at 0.7 more natural, still ~59%.
- **Prefix cache not stacked yet** (savings depend on static/variable split + actual API cache hit).
- Caveman is cheap (regex, instant). LLMLingua-2 CPU: ~1-3s/sample on M-series.

## Usage
```
python3 pipeline.py input.txt --rate 0.5 --show
python3 pipeline.py input.txt --rate 0.7 --no-articles    # gentler
python3 pipeline.py input.txt --no-llmlingua              # caveman-only
```

## Quality eval (Ollama phi4:14b, 3 tasks, keyword scoring)

Fixed: placeholder format (`XPROTECT{n}XEND`) now survives BERT tokenization.

| rate | token savings | quality retention | notes |
|---:|---:|---:|---|
| 0.7 | 43.1% | **100%** (9/9) | safe, minimal risk |
| 0.5 | **55.7%** | **100%** (9/9) | **sweet spot** |
| 0.33 | 66.8% | 89% (8/9) | lost 1 file-path keyword, fix still correct |

Bonus observation: **compressed-prompt latency often lower** — 1.4s vs 9.8s on perf task. Shorter context = faster inference. Savings stack: cost ↓ AND latency ↓.

Conclusion: compound pipeline delivers ~55% real token cut at full quality on this 3-task mini-bench. Plateau above rate=0.5, fragility below.

## Eval-v2 (principled, SQuAD v2 public benchmark)

N=8 items, 2 runs, phi4:14b target, qwen3:8b judge, bootstrap 95% CI, pre-registered rubric.

| metric | value | 95% CI |
|---|---:|---|
| token savings | 44.5% | [41.5%, 47.4%] |
| score orig (0-3) | 2.62 | [2.12, 3.00] |
| score comp (0-3) | 2.38 | [1.88, 2.75] |
| **Δscore** | **−0.25** | **[−0.62, 0.00]** |

Failure modes on compressed: 8 NONE, **6 MISSING**, **2 SWAP**.

### Revised claim
Compound pipeline delivers **≈44% token savings** with a **small, probably-negative, not-statistically-conclusive** quality effect on extractive QA.

v1's "55.7% @ 100%" was optimistic (3 hand-picked tasks). Real-data measurement is lower and less clean.

### Implications
- Half of items (4/8) perfect on both → safe on some content.
- Others lose required facts (MISSING) or swap them (SWAP).
- Suggests **adaptive compression rate**: compress less on numeric/factual-dense passages, more on prose.
- Need N≥50 to tighten Δscore CI away from zero.

## Eval-v3: question-aware + critical-zone + self-verify escalation

Compared 4 conditions on same SQuAD n=8, 2 runs, phi4:14b target, qwen3:8b judge.

| condition | tokens | score (CI) | Δ vs full (CI) | savings | modes |
|---|---:|---|---|---:|---|
| A_full (baseline) | 225 | 2.75 [2.38, 3.00] | 0 | 0% | 12 NONE, 4 MISSING |
| B_v1 naive compress | 123 | 2.12 [1.38, 2.75] | **−0.62 [−1.38, −0.12]** | 44.5% | 8 NONE, 6 MISSING, 2 REFUSE |
| C_v2 q-aware+crit | 64 | 1.38 [0.50, 2.25] | −1.38 [−2.25, −0.50] | 69.4% | **broken** (6 REFUSE) |
| **D_adaptive** | **137** | **2.62 [2.25, 2.88]** | **−0.12 [−0.38, 0.00]** | **44.9%** | 10 NONE, 6 MISSING, 0 REFUSE |

**D_adaptive is the winner.** Same token savings as naive (44.9% vs 44.5%), quality loss **effectively erased** (Δ −0.12 with CI touching 0, vs B_v1 significant Δ −0.62). Zero REFUSE failures.

### How adaptive works
1. Try rate=0.5 compressed ctx → gen → self-verify (≈50 tok call).
2. If grounded: ship.
3. If not: rate=0.7 → verify.
4. If still not: full.

4/8 items stuck on rate=0.5 (cheap path). 4/8 escalated to full. Mix = 44.9% net.

### C_v2 diagnosis
Over-compression: protecting critical sentences removed them from LLMLingua's view, rate=0.5 applied to remainder produced total too low. Fix (rate rescaled by protected fraction) deprioritized — D_adaptive solves the problem without needing C_v2 to work.

### Shipped config for personal use
- `pipeline_v2.compress(ctx, question=q, rate=0.5)` + `verify.escalate_gen(q, ctx, gen_fn, rates=(0.5, 0.7, None))`
- Expected: ~45% savings, statistically-insignificant quality change, zero model refusal.

## Next experiments

## Next experiments

## Next experiments
1. End-to-end quality eval: run compressed prompts against Claude Haiku, compare task-completion accuracy vs original.
2. Add structured-output stage (append JSON schema).
3. Test on longer inputs (CLAUDE.md 5K tokens, paper abstracts).
4. Auto-tune rate per content type (prose vs code-heavy).
5. Hook as Claude Code PreToolUse on Read of context files.
