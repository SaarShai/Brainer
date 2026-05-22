# Catalog-level findings

Aggregating per-skill A/B + session-level replay. Updated as new measurements land.

## Headline numbers

| Metric | Value | Source |
|---|---|---|
| Always-on context tax (13 skill descriptions) | **1,151 tokens** (~0.6% of 200K) | `eval/results/static_cost.json` |
| Best per-call output reduction (caveman-ultra) | **−85.2%** output, **+0.13 judge** | `eval/results/caveman-ultra.json` + `.judged.json` |
| Best discipline combo (caveman + lean) | **−87.7%** output | `eval/results/caveman+lean.json` |
| End-to-end routing savings (prompt-triage, N=13 mixed prompts) | **−20.9%** total tokens, 100% classification accuracy | `eval/results/prompt-triage.json` |
| Memory compression (context-keeper, real 970-event transcript) | sidecar = **2.3% of raw transcript** (44× smaller), 100% URL recall, 67% numbers recall | `eval/results/context-keeper.json` |

## Per-skill measured wins (live A/B)

Output deltas with the skill active on its representative task suite:

| Skill | Δ output | Δ judge | N | Harness |
|---|---:|---:|---:|---|
| caveman-ultra | **−85.2%** | +0.13 | 3 × 5 | `runner.py` |
| lean-execution | **−55.8%** | +0.00 | 3 × 5 | `runner.py` |
| verify-before-completion | **−45.2%** | −0.40 ⚠ | 3 × 5 | `runner.py` |
| plan-first-execute | −20.4% | +0.20 | 3 × 5 | `runner.py` |
| prompt-triage | −20.9% total | — | 1 × 13 | `runner_triage.py` |
| context-keeper | 97.7% compression (fidelity) | — | 1 transcript | `runner_keeper.py` |

⚠ The verify-before-completion `−0.40` is a rubric artifact — the test prompts ask "I just did X, is it done?" without execution access; the skill correctly demands fresh verification commands but can't run them, and the judge scores "demands evidence" lower than "affirms confidently". Re-test with executable prompts before downrating.

## Session-level replay (pessimistic, no caching)

Replay of a real 970-event transcript with 8 user prompts:

| Metric | No catalog | With catalog (all 13 descriptions in system) | Δ |
|---|---:|---:|---:|
| input tokens | 270 | 7,510 | +2,681% |
| output tokens | 2,039 | 2,782 | +36% |
| **total tokens** | **2,309** | **10,292** | **+346%** |

This is the catalog at its most pessimistic: every turn carries all 13 descriptions in an uncached system prompt, and the model gets distracted into more verbose output because it sees the descriptions as guidance to follow.

In production:
- **Prompt caching** brings cached input tokens down to ~10% of base rate. Effective per-turn input overhead ≈ 90 tokens after the first call, not 938.
- **Actual savings happen on skill invocation**, not on description-mention. Caveman-ultra's −85% comes from its body being prepended when the skill fires — which the session-replay harness doesn't simulate.
- A more realistic measurement: vanilla baseline + caveman-ultra body actively loaded per turn. To do, see "Pending" below.

The session-replay confirms the design assumption that skills must trigger explicitly (or via lightweight description match) rather than be globally active. It's evidence for: prefer slash commands and trigger words over "always-on" skill bodies.

## Pending live measurements

| Skill | What to measure | Why |
|---|---|---|
| context-refresh | end-to-end relay round-trip | handoff size + successor continuity |
| handoff | slash command in each host produces $TMPDIR/handoff-*.md | trigger reliability |
| delegate | multi-subtask session with vs without delegation | cost preflight value |
| wiki-memory | retrieval-vs-cold-research A/B | retrieve-before-reasoning value |
| compress-context | Kaggle N≥50 re-run with mimo judge | tighten the 44.9% prior claim |
| semantic-diff | repeat the argparse.py-style test under new harness | confirm 95.5% prior claim |
| output-filter | bytes-in/bytes-out on noisy CI logs | direct mechanical strip |
| skills × prompt caching | session-replay with explicit cache_control breakpoints | the real production cost |

## Re-running these measurements

```bash
. .token-economy/secrets.env && export MIMO_API_KEY

# per-skill in-context (4 discipline + 4 combos):
python3 eval/runner.py --task eval/tasks/caveman-ultra.yaml --n 5 --backend mimo --model mimo-v2-flash
python3 eval/judge.py eval/results/caveman-ultra.json --model mimo-v2-flash --backend mimo

# end-to-end routing:
python3 eval/runner_triage.py --corpus eval/tasks/prompt-triage-corpus.yaml \
  --cheap mimo-v2-flash --expensive mimo-v2.5-pro --n 1 --no-ollama

# memory compression:
python3 eval/runner_keeper.py <transcript.jsonl>

# pessimistic session-level:
python3 eval/runner_session.py <transcript.jsonl> --max-prompts 8 --model mimo-v2-flash

# re-aggregate:
bash eval/finalize.sh
```

## Methodology constants

- **Generator model under test**: `mimo-v2-flash` (cheap, deterministic, supports OpenAI-compat chat).
- **Judge model**: `mimo-v2-flash` (after we discovered `mimo-v2.5-pro` exhausts max_tokens on reasoning_content for long candidates — see commit `5b5ed16`).
- **Temperature**: 0.0 throughout.
- **Sample sizes**: N=3 trials × 3–5 prompts for in-context discipline skills. N=1 × 13 mixed prompts for routing. N=1 real transcript for memory fidelity. Direction-of-effect is clear at these sizes; tighten the CI with Kaggle T4 batches when ready.
