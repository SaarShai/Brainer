# Catalog-level findings

Aggregating per-skill A/B + session-level replay. Updated as new measurements land.

## Stacking & anti-patterns (read before tuning install)

Skills compound across axes (output × input × routing × memory) but **diminish within the same axis** — two output-reducers don't sum, they compound on the remainder.

**Workload → which bodies actually earn their cost:**

| Signal in the user's prompt | Load body |
|---|---|
| Asks for explanation / summary / answer | `caveman-ultra` |
| Asks for plan / refactor / multi-step task | `plan-first-execute` + `lean-execution` |
| Claims something is done ("I just fixed X, is it done?") | `verify-before-completion` |
| Re-reading a file already loaded this session | `semantic-diff` (automatic via `read_file_smart`) |
| Prompt about to be sent is > 2K tokens | `compress-context` (opt-in) |
| References past work, decisions, "have we done X?" | `wiki-memory` |
| End of session, want a fresh one | `/handoff [focus]` |
| Need one fact from a previous session | `/handoff --ask "<question>"` |
| Approaching `/compact` | nothing — `context-keeper` hook fires automatically |
| Noisy terminal output | `output-filter` (already piped via hook) |

**Anti-patterns** (most are agent-internal, but you want to know them when deciding what to install):

- Don't sum percentages. caveman (−85%) + lean (−56%) ≠ −141%. Measured stack: **−87.7%**. Gains compound on the remaining, not on the original.
- Don't expect savings on short imperative prompts ("commit and push", "fix the typo"). The catalog can be net-cost-positive on workloads dominated by terse imperatives.
- Don't add an output-reducer to a prompt that already has minimal output room. caveman cuts long explanations 85%; on a 50-token answer it can't do much.

**Where the wins are bimodal:**

- **Verbose-prone workloads** (planning, explanation, code review, multi-step bug fixing): catalog is a clear net win. Stack output reducers on top of the input reducers and expect −60% to −85% total tokens.
- **Short imperative workloads** (commits, fixes, one-line answers): catalog adds marginal cost without proportional savings. Even with prompt caching, expect roughly flat to +10% total.

**Workload-aware install:** keep the hook skills (`prompt-triage`, `context-keeper`, `output-filter`) and `caveman-ultra` everywhere; trim the discipline skills (`plan-first-execute`, `lean-execution`, `verify-before-completion`) on machines that mostly do quick imperative work.

**Default install path (since the opt-in demotion):** three skills carry `auto-install: false` so `./install.sh` does not run their `tools/install.sh` — `compress-context` (heavy torch+llmlingua dep for a −36% gain that barely beats free observation-masking, and whose 44.9%/SQuAD number is not reproduced in `eval/results`), `skill-pulse` and `compliance-canary` (anti-drift UserPromptSubmit hooks with zero in-repo token A/B that fire every turn and overlap each other). They stay symlinked and listed; enable explicitly with `bash skills/<name>/tools/install.sh`. The default UserPromptSubmit path keeps only `prompt-triage` (measured −20.9%); `loop-breaker` (PreToolUse) and `context-keeper` (PreCompact) remain auto-wired (cheap / measured).

## Headline numbers

| Metric | Value | Source |
|---|---|---|
| Always-on context tax (20 skill descriptions) | **1546 tokens** (~0.8% of 200K) | `eval/results/static_cost.json` |
| Best per-call output reduction (caveman-ultra) | **−86.4%** output (N=50), **+0.13 judge** (prior N=15) | `eval/results/caveman-ultra.json` + `.judged.json` |
| Best discipline combo (caveman + lean) | **−87.7%** output | `eval/results/caveman+lean.json` |
| End-to-end routing savings (prompt-triage, N=13 mixed prompts) | **−20.9%** total tokens, 100% classification accuracy | `eval/results/prompt-triage.json` |
| Memory compression (context-keeper, real 970-event transcript) | sidecar = **2.3% of raw transcript** (44× smaller), 100% URL recall, 67% numbers recall | `eval/results/context-keeper.json` |

## Self-improvement: compounding memory (Exp1, real-model)

Validates pillars 3+4 (wiki-memory framework + learning). Protocol borrowed from StreamBench: 12 sequential tasks, retrieve-before / gated-write-after each, longitudinal success curve. 5 introducer tasks teach a fact about fictional "Project Helios" (absent from pretraining); 7 dependent tasks can only be answered correctly by recalling a prior lesson. Three arms: **cold** (no memory), **memory** (gated wiki via `write_gate.py` + `wiki.py`), **poisoned** (ungated writes + injected garbage concepts). Each task tagged by learning source — `failure | feedback | success`.

**Backend: ollama `qwen2.5:7b-instruct`, local, temp 0, 30.5s wall** (`eval/exp1_compounding/results/summary_local_qwen25.json`). Non-reasoning model chosen to avoid `<think>` confound.

| arm | dependent acc | total acc | tokens | curve sum |
|---|---:|---:|---:|---:|
| cold (no memory) | **0.286** (2/7) | 0.50 | 1,276 | 6/12 |
| memory (gated wiki) | **0.857** (6/7) | 0.833 | 6,358 | 10/12 |
| poisoned (ungated + garbage) | 0.857 (6/7) | 0.833 | 5,709 | 10/12 |

**Memory beats cold on lesson-dependent tasks: 0.286 → 0.857, lift +0.571.** Introducer accuracy identical across all arms (0.80) — correct sanity check; tasks with no dependency must not move.

**Per-source memory−cold lift (the three learning sources, each independently positive):**

| source | cold dep acc | memory dep acc | lift | n_dep |
|---|---:|---:|---:|---:|
| failure | 0.0 | 0.5 | **+0.5** | 2 |
| feedback | 0.333 | 1.0 | **+0.667** | 3 |
| success | 0.5 | 1.0 | **+0.5** | 2 |

The failure source was **+0.0** before the `write_gate.py` `ERROR_MARKERS` fix (prose failure-lessons scored below the 3.0 threshold and were never written). After the fix it is **+0.5**, visible in-trace: `helios-retry-constant` cleared the gate at **5.0**, `helios-deploy-command` at **4.5**, both retrieved downstream. The eval harness caught this defect and the fix closed it — a genuine repair of the "learn from failures" pillar, confirmed on a real model.

**Caveats (honest):**
1. **Small N** — 2–3 dependents per source. Direction is clean; CIs are not tight. The Kaggle N=50 discipline run is the variance backstop.
2. **Poison did not degrade** (Δ +0.0 vs gated memory). Good — the gate + retrieval ranking shrugged off the injected `misc-thoughts-three` — but at this N it is "no harm observed," not "proven robust."
3. **Memory costs ~5× tokens** (6,358 vs 1,276): the accuracy is bought with retrieval-injection context. Real win, real price.

## Memory robustness sweep — contradiction / adversarial poison / scale (Exp4–6)

Exp1 proved memory *helps* on the happy path. These three stress the failure modes. All
on ollama `qwen2.5:7b-instruct`, local, temp 0. Plumbing first validated offline via each
harness's `--stub` mode before the real run.

### Exp4 — contradiction / update (`eval/exp4_contradiction/`)

When a remembered fact CHANGES (command renamed, config prefix renamed, `max_retries`
lowered after an incident), does memory serve the CURRENT fact or a stale one? 3 topics,
sequence intro(v1) → change(v2 contradicts) → post-change question. Lessons written rich
enough to clear the write-gate so the test isolates update-handling, not gate scoring.

| arm | current-fact acc | stale-answer rate |
|---|---:|---:|
| cold (no memory) | 0.0 | 0.0 |
| stale (memory, never updated) | **0.0** | **1.0** |
| append (write v2 as new page, keep v1) | 1.0 | 0.0 |
| reconcile (wiki-refresh *Replace*) | **1.0** | 0.0 |

- **Stale memory is the failure mode**: 0% correct AND serves the OLD value 100% of the time — *confidently* wrong. (Cold is also 0% but merely guesses; it doesn't assert a remembered-but-wrong fact.) So un-refreshed memory is arguably worse than none.
- **Reconcile (Replace the stale page) recovers the current fact 100%**: reconcile − stale = **+1.0**. This is the first passing reading for the previously-untested `wiki-refresh` (Replace) + `memory-decay` skills, implemented here via the `wiki overlap` dedup-at-write primitive.
- **Append also hit 1.0** — the real model read the recency cues in the v2 lessons ("BREAKING CHANGE", "moved to", "now") and picked the new fact even with the old still retrievable. Honest caveat: append's success *depends* on the contradicting lesson carrying explicit supersession cues; reconcile is robust regardless (it removes the stale page) and costs fewer retrieval tokens (one page, not two).

### Exp5 — adversarial poison (`eval/exp5_adversarial/`)

Exp1's "poisoned" arm used vague benign noise (Δ +0.0 = no harm). The real test is a
confident, well-formed, WRONG lesson. 4 topics; the correct and adversarial lessons are
**form-matched** (identical structure, differ only in the value).

- **The write-gate is NOT a truth filter: 8/8 confident-wrong lessons PASSED, mean gate score 4.88** — *identical* to their correct twins. The gate scores signal/form, not truth, by construction.
- True-fact accuracy: **clean=1.0, poison-only=0.0** (serves the planted wrong value 100%), **both-present=0.5** (truth + poison coexisting → coin flip). poison − clean = **−1.0**.
- **Implication (a real, named limitation):** a single well-formed false memory fully flips the answer, and the quality gate offers *zero* defense. Poisoning defense must come from a different layer — provenance / verification / recency / source-trust — not from `write-gate`, which is correctly doing its actual job (filter low-signal noise, not adjudicate truth).

### Exp6 — retrieval at scale (`eval/exp6_retrieval_scale/`)

Does top-k retrieval keep finding the right lesson as the store grows? 5 needle lessons +
D well-formed distractors (distinct Helios-ish subjects), sweep D ∈ {0,10,25,50,100,200,400}.

- **hit@3 = 1.0 and accuracy = 1.0 at EVERY point**, store 5 → 405 pages. **Zero decay.** The wiki's SQLite-FTS retrieval keeps the needle in the top-3 against 400 distractors and the model answers correctly.
- Honest caveat: distractors are on *distinct* subjects (lexically separable). The harder frontier — near-duplicate distractors sharing the needle's keywords but carrying different values — is exactly the same-topic collision case that Exp5's `both` arm exposed (co-located truth+poison → 0.5). So "retrieval scales" holds for *unrelated* growth; *same-topic* collisions remain the open risk.

**Combined:** the memory system is robust to GROWTH (Exp6) and recovers from CHANGE *if you reconcile* (Exp4), but is NOT robust to confident FALSE memories (Exp5) — and the write-gate is the wrong layer to expect that defense from. Small N (3–5 topics per experiment) — direction is clean, magnitudes are not tight CIs.

## Per-skill measured wins (live A/B)

Headline numbers with the skill active. Different metrics per skill type — see Harness column.

| Skill | Headline | Judge | N | Harness |
|---|---:|---:|---:|---|
| **semantic-diff** | **97.8% / 97.0% / 85.5%** on unchanged / +fn / 2-edit re-reads | — | 2 source files | `runner_semdiff.py` |
| **output-filter** | **−88.8%** bytes, 5/5 error lines preserved | — | 4 noisy samples | `runner_filter.py` |
| **context-keeper** | **97.7%** transcript compression, 100% URL / 67% measurement recall | — | 1 transcript | `runner_keeper.py` |
| caveman-ultra | **−86.4%** output | +0.13 (prior N=15) | **50 × 5** | `runner.py` |
| **wiki-memory** | **−64.6%** output, +411% input, +6.9% total, same judge | 0.00 | 1 × 8 | `runner_wiki.py` |
| lean-execution | **−55.8%** output | +0.00 | 3 × 5 | `runner.py` |
| verify-before-completion | **−33.5%** output | n/a (judge pending) ⚠ | **50 × 5** | `runner.py` |
| **compress-context** | **−35.6%** mean token reduction (n=3 long contexts) | — | 3 samples | `runner_compress.py` |
| prompt-triage | **−20.9%** total tokens, 100% routing accuracy | — | 1 × 13 | `runner_triage.py` |
| plan-first-execute | **−20.45%** output | +0.20 (prior N=15) | **3 × 5** | `runner.py` |
| **handoff** | 3/3 integration pass, 4/4 sections, ~50 ms / call, ~2.5 KB doc | — | 3 focus arguments | `runner_handoff.py` |

⚠ The verify-before-completion judge column is `n/a (pending)` because the N=50 run with the new executable-prompt YAML (`eval/tasks/verify-before-completion.yaml`, commit `caf0400`) produced the output deltas but the judge pass failed mid-batch on `MiMo 402: Insufficient balance`. Prior to the prompt rework, this skill judged at `−0.40` on the old "I just did X, is it done?" prompts — a known rubric artifact (judge scored "demands fresh evidence" lower than "affirms confidently"). The new prompts embed verification artifacts (test output, build log, install record, env state, migration log) so the rubric can fairly score "examined the evidence + named the gap" vs. "trusted the artifact" — but the judge needs to be re-run on a non-MiMo backend (e.g. `judge.py --backend ollama --model qwen3.6:35b-a3b-q4km`) before the rubric question is settled.

### Model-size sensitivity (small-instruct caveat)

One pre-existing smoke test (`eval/results/_smoke_mlx_verify.json`, MLX + `mlx-community/Llama-3.2-1B-Instruct-4bit`) shows `verify-before-completion` going in the **opposite** direction on tiny targets: **+96.17% output, +343% input**. The skill's "examine the evidence, name the gap, request the specific next check" framing requires the target to have headroom to compress — a 1B/4-bit instruct model doesn't, so the skill's prose inflates the response instead of tightening it. The catalog's −20% to −86% savings assume **Haiku-class or larger** targets. Smaller / heavily-quantised instruct models are out of scope; treat the catalog as net-cost-positive on those until separately validated.

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

### Config C: prompt caching enabled (production-realistic)

Same two configs, N=2 trials so the system prompt warms in the cache. MiMo's `prompt_tokens_details.cached_tokens` field tracks per-call hits; we compute the billed-token equivalent as `cached × 0.1 + uncached × 1.0`.

| Variant | Cache hit (with catalog) | Δtotal raw | **Δtotal effective (cached)** |
|---|---:|---:|---:|
| Descriptions only | 98% | +491% | **+110%** |
| Descriptions + caveman + lean active | 99% | +629% | **+94%** |

Surprising find: **the realistic config (with skill bodies) is slightly cheaper than descriptions-only** once caching is active, because the caveman + lean bodies cache as effectively as the descriptions and their effect pulls output down a bit. The catalog still roughly doubles token cost on these short-imperative prompts — but the discipline skills are net-helpful, not net-harmful.

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

## Required controls (must beat these baselines)

Skills that claim a compression / compaction / context-reduction effect must clear two trivial controls before counting as a measured win. If a skill can't beat these, it isn't earning its slot.

| Control | What it does | Why it's required |
|---|---|---|
| **Grep + Read** | Plain grep to locate, plain Read on hits | Sets the floor for any retrieval / index skill. `index-first` earns its slot only by beating it; we've measured graphify at −93% vs this baseline. |
| **Observation masking** | Replace tool outputs in past turns with `[output suppressed]` while keeping the call args + summary | Sets the floor for any compaction skill. On SWE-bench Verified × 5 models, plain masking **halves cost and matches LLM summarization** ([arXiv 2508.21433](https://arxiv.org/abs/2508.21433), Aug 2025). A compression / summarization skill that doesn't beat this is adding complexity for no measured gain. |

Apply to:
- `semantic-diff` — must beat masking the previously-read file (it does, by reading only the diff vs nothing)
- `compress-context` — must beat masking the raw context (current N=3 measurement is preliminary)
- `context-keeper` — must beat masking the pre-compact transcript (sidecar already retains 100% URLs / 67% numbers, which masking cannot)
- any future compaction / summarization skill

Adding observation-masking as a runnable baseline harness is a separate eval task; until it lands, skills should at minimum *cite the baseline they're competing against* in their EVAL.md.

## Pending live measurements

| Skill | What to measure | Why |
|---|---|---|
| context-refresh | end-to-end relay round-trip with the (currently broken) successor launcher | the write-doc part is covered by handoff; the relay+ask-old chain is the remaining surface |
| delegate | multi-subtask session with vs without delegation, measuring main-thread token cost | requires building a multi-subagent harness |
| compress-context (Kaggle N≥50) | re-run with mimo judge on full SQuAD adapter | tighten the prior 44.9% with-quality claim |
| skills × prompt caching at scale | explicit cache_control breakpoints in cache-aware hosts | the −94% effective Δtotal in Config B suggests per-host caching tuning has more room |

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
