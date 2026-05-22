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

## Session-level replay — two configurations

Replay of a real 970-event transcript with 8 user prompts via `runner_session.py`. The prompts are imperative bug-fix / planning / short-question style — typical of a working session, not designed to provoke verbose answers.

### Config A: descriptions only (pessimistic baseline)

`runner_session.py <transcript> --max-prompts 8` (no `--triggered` flag).

| Metric | No catalog | With catalog (13 descriptions in system) | Δ |
|---|---:|---:|---:|
| input tokens | 270 | 7,510 | +2,681% |
| output tokens (mean per call) | 254.9 | 347.8 | **+36%** |
| total tokens | 2,309 | 10,292 | +346% |

### Config B: descriptions + caveman-ultra + lean-execution bodies active

`runner_session.py <transcript> --max-prompts 8 --triggered caveman-ultra,lean-execution`.

| Metric | No catalog | With catalog (descriptions + 2 active bodies) | Δ |
|---|---:|---:|---:|
| input tokens | 368 | 12,744 | +3,363% |
| output tokens (mean per call) | 255.5 | 284.1 | **+11%** |
| total tokens | 2,412 | 15,017 | +522% |

### Interpretation — the catalog is workload-dependent

The session-replay numbers look bad in isolation. They're honest data; the catalog **does not universally reduce tokens** on every session. Three things explain the gap between this and the per-skill A/B numbers:

1. **The per-skill A/B prompts are deliberately verbose-prone** ("Explain a binary search tree", "How does X work", "Plan a refactor of …"). On those, caveman-ultra cuts 85%. The real-session prompts here are imperative ("fix all the issues", "commit and push") with baseline outputs already near the minimum reasonable response — there's little room to cut.

2. **Config A inflates output by +36%**: when 13 skill descriptions land in the system message but no skill body actually fires, the model treats them as soft guidelines (consider all 13) and writes longer, more structured responses. **Active skill bodies (Config B) reverse this**: caveman + lean bodies pull the output back down — +36% becomes +11%. They're fighting the description-inflation effect.

3. **Input overhead is mostly prompt-cacheable.** The +2,681% / +3,363% input deltas are computed on uncached tokens. Real hosts (Claude, Codex, OpenAI cache control) bring cached tokens to ~10% of base rate after the first call. Effective per-turn input overhead drops from ~900 tok to ~90 tok.

### What this means for the catalog

- The catalog's headline savings (caveman −85%, lean −56%) apply where the workload IS verbose. They're not universal.
- For sessions dominated by short imperative prompts, **expect +5–15% output overhead from description visibility**, partially offset by trigger-fired skill bodies if the right ones load.
- **Prompt caching is essential to the catalog's economics.** Without it, the always-on description tax becomes a real cost. With it, the tax amortizes to negligible after turn one.
- **Selectively install** — drop skills you don't need. Each skill you don't load is description tokens not spent. The lint at `scripts/lint_skill_md.py` enforces description discipline; the install matrix lets you select subsets.
- The strongest per-call wins remain the discipline skills triggered on the right prompts. The catalog's value is highest when the agent's default workload skews toward planning, explanation, code review, and multi-step bug fixing — where verbose baselines exist and caveman/lean/verify cut them.

The takeaway isn't "the catalog saves tokens" or "the catalog costs tokens" — it's **"the catalog moves the per-call output distribution"**: tighter when relevant skills fire, slightly looser when only descriptions are visible. Net depends on workload mix.

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
