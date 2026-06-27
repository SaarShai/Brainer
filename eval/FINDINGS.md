# Catalog-level findings

Aggregating per-skill A/B + session-level replay. Updated as new measurements land.

> **As-of note (catalog drift):** the static-cost and default-install figures below
> (16-skill default path, ~1080-token tax, the `skill-pulse` hook) were measured for
> the **v1.6–v1.7-era catalog** and are kept as the **historical measurement record** —
> the *deltas and mechanisms* (canary +0.44 ×2 families, prompt-triage −20.9%, memory>cold)
> still hold. The **current catalog is 21 skills (v1.13)**; `skill-pulse` was absorbed into
> `compliance-canary` at v1.10, and `learn-skill` (v1.13) + `brainer-audit` ship `auto-install: false`.
> Re-measuring the static cost for the 21-skill catalog is tracked in GOAL.md; until then read
> the absolute token counts as that era's, not today's.

## Stacking & anti-patterns (read before tuning install)

Skills compound across axes (output × input × routing × memory) but **diminish within the same axis** — two output-reducers don't sum, they compound on the remainder.

**Workload → which bodies actually earn their cost:**

| Signal in the user's prompt | Load body |
|---|---|
| Asks for explanation / summary / answer | `caveman-ultra` |
| Asks for plan / refactor / multi-step task | `plan-first-execute` + `lean-execution` |
| Claims something is done ("I just fixed X, is it done?") | `verify-before-completion` |
| Re-reading a file already loaded this session | `semantic-diff` (automatic via `read_file_smart`) |
| References past work, decisions, "have we done X?" | `wiki-memory` |
| Approaching `/compact` (session continuity) | nothing — `context-keeper` PreCompact hook fires automatically |
| Noisy terminal output | `output-filter` (wire by hand — pipe form or a PostToolUse/Bash hook; ships no auto-installer) |

**Anti-patterns** (most are agent-internal, but you want to know them when deciding what to install):

- Don't sum percentages. caveman (−85%) + lean (−56%) ≠ −141%. Measured stack: **−87.7%**. Gains compound on the remaining, not on the original.
- Don't expect savings on short imperative prompts ("commit and push", "fix the typo"). The catalog can be net-cost-positive on workloads dominated by terse imperatives.
- Don't add an output-reducer to a prompt that already has minimal output room. caveman cuts long explanations 85%; on a 50-token answer it can't do much.

**Where the wins are bimodal:**

- **Verbose-prone workloads** (planning, explanation, code review, multi-step bug fixing): catalog is a clear net win. Stack output reducers on top of the input reducers and expect −60% to −85% total tokens.
- **Short imperative workloads** (commits, fixes, one-line answers): catalog adds marginal cost without proportional savings. Even with prompt caching, expect roughly flat to +10% total.

**Workload-aware install:** keep the auto-wired hook skills (`prompt-triage`, `context-keeper`) and `caveman-ultra` everywhere; `output-filter` is worth wiring on noisy-Bash workloads but ships no auto-installer — wire it by hand (pipe form or a PostToolUse/Bash hook). Trim the discipline skills (`plan-first-execute`, `lean-execution`, `verify-before-completion`) on machines that mostly do quick imperative work.

**Default install path:** all 16 skills are default-installed since v1.7. `skill-pulse` and `compliance-canary` (anti-drift UserPromptSubmit hooks) were opt-in until the cross-model long-run replicated their uplift on a second model family (canary +0.44 ×2 families, pulse +0.27; see *Cross-model long-run*) — promoted to `auto-install: true` in `bc2ec0d` alongside the caveman-ultra drift-hardening they enforce. Exp9's "canary > pulse, `both` ≯ canary" still holds: on constrained installs keep canary, drop pulse first. The default hook path: `prompt-triage` (UserPromptSubmit, measured −20.9%), `context-keeper` (PreCompact, measured), `skill-pulse` + `compliance-canary` (UserPromptSubmit). The former auto-wired `loop-breaker` (PreToolUse) and the opt-in `compress-context` were **cut at v1.6.0** (see *Catalog cuts*).

## Headline numbers

| Metric | Value | Source |
|---|---|---|
| Always-on context tax (16 skill descriptions) | **~1080 tokens** (~0.54% of 200K) — the 998 15-skill figure plus `think` (+94, added v1.6.2) and net description edits (canary trigger-first rewrite). Down from 1642 (−34%) via trigger-verified trims + six catalog cuts (see *Catalog cuts*). Reduction path: SkillReducer-style audit (GOAL.md backlog) | `eval/results/static_cost.json` · `eval/exp8_trigger/` |
| Best per-call output reduction (caveman-ultra) | **−86.4%** output (N=50), **+0.13 judge** (prior N=15) | `eval/results/caveman-ultra.json` + `.judged.json` |
| Best discipline combo (caveman + lean) | **−87.7%** output | `eval/results/caveman+lean.json` |
| End-to-end routing savings (prompt-triage, N=13 mixed prompts) | **−20.9%** total tokens, 100% classification accuracy | `eval/results/prompt-triage.json` |
| Memory compression (context-keeper, real 970-event transcript) | sidecar = **2.3% of raw transcript** (44× smaller), 100% URL recall, 67% numbers recall | `eval/results/context-keeper.json` |

## Evaluation Methodology — External Validity

This is the methodology *framework* added by the eval-methodology upgrade
(`specs/eval-methodology.md`). It governs **how cases are authored going
forward**; it does not re-measure any existing skill. The historical per-skill
numbers above and below remain valid where they cleared the N≥50 gate.

### Question provenance — Sillito anchor

Skill A/B cases authored under the upgrade are anchored to a **citable question
taxonomy** rather than authored ad-hoc: the Sillito/Murphy/De Volder *"Questions
Programmers Ask During Software Evolution Tasks"* (IEEE TSE 2008, 44 types in 4
groups). Each case declares a `sillito_dim` (D1 definition/discovery · D2
relationship/call-graph · D3 targeted retrieval · D4 architecture/structure · D5
cross-cutting/semantic). This removes author bias on "is this a typical
question?" — the dimension is a property of the case, not a post-hoc label.

### Ground-truth audit policy

Before a case-set clears the N≥50 gate, `skills/eval-gate/tools/validate_case.py`
confirms that every case target (the fact the question asks about) originates from
an **independently-verifiable source** — `file` / `git` / `lsp_symbol` / `config`
/ `api_contract` — and **never** from a model-generated answer. This breaks the
"author writes both the question and the grading key" circularity. The validator
is static-only: it runs no skill and no model.

**eval-gate is exempt (design-by-intent).** A rubric-grading gate encodes human
taste, not a fact recoverable from git/file/LSP, so there is no verifiable target
for the audit to check and N≥50 is not a meaningful bar for it. eval-gate is
scoped as load-bearing-by-design, not empirically measured. (Decision Q1.)

### Benchmark cross-check policy (opportunistic)

For skills that touch code/repository understanding (retrieval, comprehension,
recall): **if** a published set (SWE-QA arXiv 2509.14635, CoReQA 2501.03447) has
an overlapping question on the same repo, Brainer's A/B is reported alongside the
published baseline. Matching is **opportunistic, not systematic** (decision Q2,
option A): Brainer keeps its own full case-set; the benchmark is a cross-check,
not a replacement, and is noted in the case's provenance when it applies.

> **Deferred — incremental re-measurement manifest.** The CBM `manifest.json`
> checkpoint/resume pattern (per-unit done/sha/started/finished, skip
> already-measured units) is documented but **not implemented** (decision Q3).
> Revisit if a re-measurement campaign grows past ~20 skills; until then each
> N≥50 re-run is full.

### Same-family judge self-preference

Brainer's judge (`eval/judge.py`) defaults to a **different model family** from
the answer-writer, which removes documented self-preference inflation. If a future
re-measurement uses a same-family judge (e.g. a Claude judge on Claude-generated
answers) as a cost measure, that run must carry an explicit caveat.

### Aggregation by Sillito dimension — template (no data yet)

The dimensional rollup below is the **proposed reporting format**; there is no
dimensional aggregation measured yet, so every data cell is a TODO. Populate it
from real per-skill case results once skills are re-measured under the upgrade —
do **not** fill it with illustrative numbers.

| Dimension | Type | Skills tested | Avg judge score | N cases | Notes |
|---|---|---|---|---|---|
| D1 | Definition / API discovery | _TODO_ | _TODO_ | _TODO_ | _TODO_ |
| D2 | Relationship / call graph | _TODO_ | _TODO_ | _TODO_ | _TODO_ |
| D3 | Targeted retrieval | _TODO_ | _TODO_ | _TODO_ | _TODO_ |
| D4 | Architecture / structure | _TODO_ | _TODO_ | _TODO_ | _TODO_ |
| D5 | Cross-cutting / semantic | _TODO_ | _TODO_ | _TODO_ | _TODO_ |

When populated: small N per dimension means no CIs, and cross-dimension
differences reflect both skill design and question difficulty — not skill merit
alone. Read as direction, not magnitude.

## Catalog cuts (v1.6.0–1.6.1 — 19 → 15 skills)

Trimmed the unproven-gain tail. Principle: a skill stays only if it's either **measured-positive** or **cheap + load-bearing-by-design** (operational utility, no gain claim). A skill that is *both* ❌/🟡 on measured benefit *and* redundant with a kept skill is dead weight — cut it.

| Cut | Why | Covered now by |
|---|---|---|
| `compress-context` | −35.6% (n=3, degraded); barely beat free observation-masking; heavy torch+llmlingua dep | host `/compact` + `context-keeper` (extraction) + `caveman` (output) |
| `session-recall` | no end-to-end Δ; A/B unmeasured | `context-keeper` (auto) + `wiki-memory` (curated) |
| `loop-breaker` | no token A/B; always-on PreToolUse cost vs. unproven benefit | host loop-protection |
| `handoff` *(v1.6.1)* | operational-only — no measured token/quality gain; 3/3 integ but it's a utility, not a win | host `/compact` + `context-keeper` (PreCompact extraction); durable facts via `wiki-memory` + `write-gate` |
| `handoff-from` *(earlier)* | redundant pull-direction of `handoff` | `context-keeper` + `wiki-memory` |
| `memory-decay` *(earlier)* | verified **no-op** — retrieval ranking never read its decayed `confidence`; only lint did | n/a (was inert) |

**Kept, against the "bottom-5" framing** (the source table predated Exp10):
- **`cache-lint`** — Exp10 measured detection **F1 1.0** (recall 1.0 / FP 0.0, 18-case labeled corpus). Pillar-1 (cache/token economy), distinct value. Not unproven. *(`handoff` was kept here at v1.6.0 on operational-utility grounds, then cut at v1.6.1 — see the table above — once the host's `/compact` + `context-keeper` were judged sufficient for session continuity.)*

Effect: always-on tax 1642 → **998 (−39.2%)**; `eval/exp8_trigger/` top-1 fidelity was measured at the 19-skill snapshot (corpus since trimmed to the live set). Installer (`install.sh`) now prunes broken symlinks + orphan cursor rules on re-install, so cuts self-heal instead of stranding dangling links.

## Gap-closure & long-run tests (2026-06-07)

Closing the "what's NOT tested" column from the catalog table, plus multi-hour cross-model runs on networked Apple-silicon nodes.

### Deterministic scale tests (M3 host, local, no model)

| Skill | Gap it had | New test | Result |
|---|---|---|---|
| `semantic-diff` | "only ~2 source files" | full multi-lang suite — Python/JS/TS/Rust + rename / syntax-error / whitespace / realistic | **6/6 pass** (the `realistic` test prints, doesn't assert — weaker than the other 5); genuine **changed-file** re-read savings **95.5%** (867/19296 tok; argparse.py, 2 edits) — *not* the 99.4% sometimes cited, which is the no-change "stubs only" re-read (`skills/semantic-diff/tools/tests/`) |
| `output-filter` | "N=4 samples" | **exp12**: 40 generated noisy samples, error lines embedded at *adversarial* positions (inside dup-spam + progress bars) with known ground truth | error preservation **50/50 = 100%** (verbatim *after* ANSI-strip — exp12's error templates are plain text, so unaffected; a line carrying inline ANSI survives only in stripped form); byte reduction mean **−89.9%** (range −79.6…−95.5%), confirmed genuine (real ANSI-strip + dup-collapse, not passthrough; errors survive even when duplicated/buried — adversarially reproduced) (`eval/exp12_filter_scale/`) |
| `wiki-refresh` | "tiny N (reconcile 3/3)" | **exp14**: 30 pages, known citation health (incl. paths to skills deleted this session); score `audit-refs` drift detection | drift **P/R/F1 = 1.0**; all/some-refs-gone signal **18/18**. (Reconcile *decision* Keep/Update/Replace/Delete remains model-judgment — only the deterministic detection core is scaled here.) (`eval/exp14_wiki_refresh_scale/`) |
| `prompt-triage` | "N=13" | already validated at **N=48** (exp3 labeled corpus) — re-ran | routing **100%**, tier **96.8%**, **0/18 complex prompts misrouted to a cheap model** — but caveat the safety property: 7/18 hold via conservative *default-to-opus* (`source=default`, conf 0), not positive classification, and this deterministic run has the Ollama fallback **off** (so the LLM path production uses for those 7 is untested here); corpus is in-distribution; "cheap" = haiku (mid-tier sonnet over-economy not counted). The "N=13" was the stale end-to-end token figure. (`eval/exp3_classifiers/`) |
| `cache-lint` | "in-distribution corpus" | **exp13**: new-shape OOD fixtures built *blind to the detector regexes* + a run on this repo's **real** configs | precision **1.0**, recall **0.8** OOD (up from 0.6); **0 false-FAILs on the real repo** (auditor proven *not* blind — it discovers `.claude/settings.json`, follows hook scripts, and FAILs on a planted prefix-writing hook). The **2 genuine recall gaps the adversarial pass flagged (`${VAR}` braced-env + raw jinja `{{…}}`/`{%…%}`) are now CLOSED** — added a braced-only `${VAR}` detector and a generic-jinja detector; both yield **0 FPs** on the negatives (`o_r2_neg_price`, `o_r2_neg_inline`) and the lone real-repo `{{env.X}}` is backtick-suppressed. The remaining **2 misses are by-design** precision-preservation — backtick = markdown *inline code* (correctly static), bare `$VAR` = prose-ambiguous (`$500`, `$variable`, `$PATH`) so deliberately not detected. cache-lint reliably fires on `$(…)`/`{{env.…}}`/`${VAR}`/jinja/interpolation. (`eval/exp13_cache_lint_ood/`) |

_All five rows above were re-derived by an independent adversarial pass (5 skeptics, each instructed to refute): every number reproduced, but the pass corrected two overstatements folded in here — semantic-diff's "99.4%" was the no-change re-read (genuine changed-file = 95.5%), and cache-lint's "all 4 misses by-design" was half-true (2 were real recall gaps — since CLOSED, see row above; OOD recall 0.6→0.8). exp14 survived clean (non-vacuous + non-circular, verified path-by-path)._

### Cross-model long-run (networked Apple-silicon nodes, local ollama, multi-hour)

- **M3** (Apple M3 Max, **llama3.1:8b**, **5 reps**): the cross-model close — a 2nd model family vs the original qwen2.5, via `eval/longrun/longrun.py` + `analyze.py`. **Drift replicates:** compliance-canary uplift **+0.44 (sd 0, n=5)** — matches qwen2.5's +0.44 almost exactly — skill-pulse **+0.27**, control decays **5/5**, `both` does *not* beat canary (0/5, consistent with the original), canary efficiency 1.36 /1k tok. **Compounding replicates:** memory−cold dependent-acc lift **+1.0 (sd 0, n=5)**, memory>cold **5/5** (memory 1.0 vs cold 0.0 on lesson-dependent tasks). Effectively deterministic at temp 0 → the "2nd model" caveat on `skill-pulse` / `compliance-canary` / wiki-memory compounding is **closed**; the effects are not qwen-specific.
- **M1** (Apple M1 Max, gemma4:26b): **abandoned** — gemma4:26b ran ~90+ min/rep (0 completed reps in ~2 h). Grinding to a handful would have cost ~5 h for marginal CI-tightening, so it was killed in favour of the fast llama3.1 reps above (the deliberate "stop churning" call).
- **M2** (Apple M2 Pro, 17 GB): **UNAVAILABLE** — severe memory pressure (compressor ~26 GB-equiv, ~14 MB free); an 8-token generation timed out >180 s. Honest non-result. (ollama IS present on both nodes; the earlier "absent" reading was a non-interactive-SSH `PATH` artifact.)

**verify-before-completion — judge-family robustness (the +0.92 stress test):** re-judged the same 250×2 candidates with two more families. Across 3 judges the delta is **qwen3.6 +0.92, gemma2:9b +0.37, llama3.1:8b +0.04** — **the sign holds 3/3 (the skill helps), but the magnitude is heavily judge-dependent.** +0.92 is the most generous judge; a weaker one barely separates the arms. Honest reading: verify-before-completion is net-positive on evidence-interrogation, with an effect size of **+0.04 to +0.92 depending on the evaluator** — the single-judge +0.92 headline is the optimistic end, not a firm number. (`eval/results/verify_rejudge_{gemma2,llama31}.judged.json`.)

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

**Caveats (honest — sharpened after an adversarial audit of this harness, `verify-memory-findings`):**
1. **Small N, no CI** — failure n=2, feedback n=3, success n=2 dependents. The per-source point estimates reproduce but at n≤3 they have **no meaningful confidence interval** — read them as direction, not magnitude.
2. **The poison arm here is NOT a robustness result — claim struck.** Its `NOISE_PAGES` are inert filler with no competing wrong answer, so the "poisoned does not degrade (Δ +0.0)" outcome is *true by construction*, not earned. The ungated poisoned arm tying gated memory exactly (both 0.857) means the write-gate made **zero outcome difference** in this experiment — so this run does **not** show "the gate earns its slot." The gate's real job is filtering low-signal noise (exp3), not truth/poison defense. The genuine adversarial-poison test is **Exp5**, where confident poison *does* flip the answer.
3. **Mechanism is "introducer convention propagates," not "every task teaches."** Most *dependent*-task lessons are gate-rejected; the lift comes from retrieving the *introducer* lessons (gate 3.5–5.0). Real compounding, narrower than the phrase suggests.
4. **Memory costs ~5× tokens** (6,358 vs 1,276): accuracy bought with retrieval-injection context. Real win, real price.
5. **Substring scoring slightly *under*-states the lift** — cold's `project_helios_queue_name` is credited against gold `HELIOS_QUEUE_NAME`, inflating the cold baseline, so the true memory−cold lift is **≥ +0.571** (the artifact works against the claim).

**Write quality is measured by RECALL fidelity, not a subjective judge.** The right test of "was this a good write?" is "can it be recalled and used correctly later" — which is exactly what these experiments measure: Exp1's +0.571 lift = written lessons recalled → correct answer; Exp6 = recall holds at 405-page scale; Exp4/Exp5 = recall under contradiction / adversarial poison. So wiki-memory's write quality is objectively covered by the recall-driven accuracy across Exp1/4/5/6 — there is no separate "judge the prose" gap.

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
- **Reconcile (Replace the stale page) recovers the current fact 3/3**: reconcile − stale = **+1.0** (on 3 binary trials — read as direction, not a tight 100%). First passing reading for the previously-untested `wiki-refresh` (Replace) skill, via the `wiki overlap` dedup-at-write primitive. (`memory-decay` was later cut — a verified no-op: retrieval never consumed its decayed `confidence` field.) Verified by the audit: `replace_lesson` genuinely deletes the v1 text from disk, and dep prompts leak no gold.
- **Append also hit 3/3** — the real model read the supersession cues in the v2 lessons (`moved to` / `migrated to` / `now` / `lowered to`) and picked the new fact even with the old still retrievable. Honest caveat: append's success *depends* on the contradicting lesson carrying explicit recency cues; reconcile is robust regardless (it removes the stale page) and costs fewer retrieval tokens (one page, not two).

### Exp5 — adversarial poison (`eval/exp5_adversarial/`)

Exp1's "poisoned" arm used vague benign noise (Δ +0.0 = no harm). The real test is a
confident, well-formed, WRONG lesson. 4 topics; the correct and adversarial lessons are
**form-matched** (identical structure, differ only in the value).

- **The write-gate is NOT a truth filter: 8/8 confident-wrong lessons PASSED, mean gate score 4.88** — *identical* to their correct twins. The gate scores signal/form, not truth, by construction.
- True-fact accuracy: **clean=1.0, poison-only=0.0** (serves the planted wrong value 100%), **both-present=0.5** (truth + poison coexisting). poison − clean = **−1.0**. (N=4 per arm; the 0.5 is partly a BM25 retrieval-order coin-flip, not a stable robustness number.)
- **Implication (a real, named limitation):** a single well-formed false memory fully flips the answer, and the quality gate offers *zero* defense. Poisoning defense must come from a different layer — provenance / verification / recency / source-trust — not from `write-gate`, which is correctly doing its actual job (filter low-signal noise, not adjudicate truth).

**The defense (`skills/wiki-memory/tools/provenance.py`): trust tiers + conflict-aware write + hedged retrieval.** Two `defended-*` arms run the same scenarios through it (real qwen2.5:7b):

| case | undefended | defended | what the defense did |
|---|---|---|---|
| coexistence (truth+poison stored) | acc 0.5, poison-served 0.5 | **acc 1.0, poison-served 0.0** | rejected the lower-trust poison at write; only truth reached the model |
| poison-only (no truth ever learned) | poison-served 1.0 | poison-served 1.0, **flagged-unverified 1.0** | can't recover truth it never had; flags 100% as unverified instead of asserting |

- **Honest scope (audit-flagged):** the "verified" trust tier that beats the poison is assigned by `verify_against_oracle`, and in this harness the oracle is the **answer key** (the true Helios facts). So defended-both 0.5→1.0 proves *trust-tiered routing works given a sound verifier* — not that the layer can verify truth on its own. In production the verifier is the filesystem / code / a test run (cf. `wiki audit-refs`); where no verifier exists, the layer falls back to corroboration + the hedge. Honest, not magic.
- **Productized (#8):** the defense is now enforced in the live tool, not just the eval — `wiki.py resolve --title … --trust <tier>` runs `overlap` to find a same-subject page, reads its `trust:` frontmatter, and returns **create / replace / reject / dispute** by the trust policy (higher wins, lower rejected, equal disputed). Pages stamp their tier via `new --trust`; `trust:` is optional frontmatter (default `asserted`, not in `V2_REQUIRED`, so existing pages + `lint --strict` are unaffected). 6 unit tests (`test_resolve.py`) + the 0.5→1.0 eval cover it.
- The poison-only "flagged-unverified" win is a *framing* win (model output unchanged, still emits the value) — it stops the lie being served as *confident* truth, nothing more.

### Exp6 — retrieval at scale (`eval/exp6_retrieval_scale/`)

Does top-k retrieval keep finding the right lesson as the store grows? 5 needle lessons +
D well-formed distractors (distinct Helios-ish subjects), sweep D ∈ {0,10,25,50,100,200,400}.

- **Robust to UNRELATED store growth: hit@3 = 1.0 and accuracy = 1.0 from 5 → 405 pages, zero decay.** But this is the *easy case* (audit-flagged): the distractors share only the token "helios" while each needle query carries 4–6 unique discriminators, so at D=400 the needle scores 10–14 vs distractors 3–6.5 and stays rank 1. It measures retrieval against *lexically-separable* noise.
- The harder frontier — near-duplicate distractors sharing the needle's keywords but carrying different values — is the same-topic collision Exp5's `both` arm exposed (co-located truth+poison → 0.5). So "retrieval scales" holds for *unrelated* growth; *same-topic* collisions remain the open risk.

### Exp7 — live-trigger wiring (`eval/exp7_wiring/`)

Exp1/4 test the python; this tests whether the SKILL.md **prose**, loaded into context, makes a model decide to harvest *correctly*. **Detector v2 (after the audit):** the model must emit an explicit `HARVEST: yes|no` line and we parse THAT — the original keyword detector (sniffing for "wiki"/"write-gate") was an artifact, because a model *declining* to harvest still says those words while discussing the loaded skills. 10 scenarios (5 should-fire: failure/feedback/success/build-fix/decision; 5 should-not: thanks/arithmetic/greeting/general-knowledge/date), treatment (real `verify-before-completion`+`wiki-memory` bodies) vs control (bare one-line definition).

- **Decision accuracy (treatment): qwen2.5:7b 0.8, llama3.1:8b 0.8, gemma2:9b 1.0**; vs control (one-liner) 0.9 / 1.0 / 0.9 — i.e. **the elaborate prose does not beat a one-line rule for the WHEN decision** (a lean signal — the prose earns its keep on the *sources* + *how*, not the binary trigger).
- **False-fire = 0.0 on all three families.** The earlier "over-fire on trivial prompts" was **purely a detector artifact** — corrected. With an explicit decision, no model spuriously harvested thanks/arithmetic/greeting/date. The skills do **not** pollute memory with junk.
- **Residual, model-dependent:** gemma 10/10 perfect; qwen declined 2 raw should-fire (`failure`, `success` — read "I fixed my script" as one-off, arguably defensible); llama got every *decision* right but **abstained 5×** (ignored the format marker under the long skill context). So the real weaknesses are *conservative under-firing* + *format non-compliance under long context*, not over-firing. Single run, temp 0, n=10.

### Observation-masking baseline (`eval/baselines/observation_masking.py`)

The required compaction control, made runnable (was only cited; arXiv 2508.21433). Same 972-event transcript + same recall probes as context-keeper; URL gold deduped (prefix-nested URLs were over-credited by substring scoring — audit fix).

| | masking (keeps args, suppresses outputs) | context-keeper sidecar | winner |
|---|---:|---:|---|
| size vs raw | 38.1% | **2.3%** (16.8× smaller¹) | CK |
| urls | 54.5% | **100%** | CK |
| nums | 31.7% | **66.7%** | CK |
| files | **45.5%** | 24.6% | masking |
| cmds | **100%** | 46.0% | masking |
| errors | **38.7%** | 25.2% | masking |

context-keeper wins compression + its *target* fact-types (URLs, numbers); masking wins files/cmds/errors because it keeps 16× more raw text (all call-args + assistant text verbatim). **Not a clean sweep — a real trade.** This *corrects a prior FINDINGS overclaim* ("100% URLs, which masking cannot" — masking actually gets 54.5%). ¹ "16.8× smaller" compares an 11 KB sidecar to a 192 KB masked transcript — different compaction regimes, not like-for-like budgets.

**Combined:** memory is robust to *unrelated* GROWTH (Exp6) and recovers from CHANGE *if you reconcile* (Exp4); confident FALSE memories flip it (Exp5) and the write-gate is the wrong defense layer — `provenance.py` recovers the coexistence case *given a verifier* but not the verifier-less poison-only case; the SKILL prose does induce the harvest (Exp7).

### Cross-model replication — 3 families (`qwen2.5:7b` · `llama3.1:8b` · `gemma2:9b`)

The N-gap backstop: every experiment re-run on three different-vendor families (Alibaba · Meta · Google), all local, temp 0. Are the findings general or qwen-specific?

| finding | qwen2.5:7b | llama3.1:8b | gemma2:9b | verdict |
|---|---|---|---|---|
| exp1 memory−cold lift (dependent) | +0.571 | +1.0 | +0.714 | **robust** — always large-positive |
| exp4 reconcile / stale (current-fact acc) | 1.0 / 0.0 | 1.0 / 0.0 | 1.0 / 0.0 | **robust** — identical |
| exp5 gate passes adversarial poison | 8/8 | 8/8 | 8/8 | **robust** (deterministic gate) |
| exp5 poison flips answer (both-arm acc) | 0.5 | 0.25 | 0.0 | **robust** direction; gemma worst-hit |
| exp5 defense recovers coexistence | 0.5→1.0 | 0.25→1.0 | 0.0→1.0 | **robust** — always →1.0 |
| exp6 retrieval hit@3 @405 pages | 1.0 | 1.0 | 1.0 | **robust** (gemma gen-acc dipped to 0.8) |
| exp7 harvest decision-accuracy (treat) | 0.8 | 0.8 | 1.0 | skill ≈ control (no clear win) |
| exp7 false-fire on should-not | 0.0 | 0.0 | 0.0 | **robust** — no over-firing (artifact corrected) |

- **Robust across all three families:** the memory *mechanisms* — compounding lift, contradiction-recovery via reconcile, the gate's truth-blindness, poison degradation, the trust defense (always recovers coexistence to 1.0), and retrieval hit@3 at scale. **These are not qwen artifacts.**
- **Exp7 is the soft spot, but milder than first reported.** The original cross-model read claimed over-firing (false-fire 0.5 on llama/gemma); a follow-up with an explicit-decision detector showed that was a **measurement artifact** — true false-fire is 0.0 everywhere. The genuine residuals are *conservative under-firing* (qwen declines some raw should-fire) and *format non-compliance under long context* (llama abstains), and the elaborate harvest prose doesn't beat a one-line decision rule. Model-dependent, but not the "pollutes memory" failure first feared. (2nd-model attempt on `qwen3.6:35b-a3b` was discarded — reasoning model returned empty outputs via `/api/generate`; `gemma4:26b` was an unusable orphaned manifest; `gemma2:9b` pulled fresh.)

**Portfolio caveat:** still single-run, temp 0, tiny binary N (3–5) per experiment, so no CIs — but the 3-family replication removes the "single-model artifact" risk for every finding except Exp7, whose model-dependence is now itself a documented result. The Kaggle N=50 discipline run remains the within-model variance backstop.

## Exp9 — anti-drift hook efficiency (`eval/exp9_drift/`)

Closes the gain-gap on **skill-pulse** + **compliance-canary** (both were correctness-tested but effect-unmeasured). LIFBench-style instruction-adherence: an arbitrary ack-rule (`[ack: HELIOS-7]`) is stated ONCE at turn 0, the system prompt is neutral, and the context window is bounded — so the rule scrolls out and adherence decays. Drift signal = ack present per turn. qwen2.5:7b, temp 0, 26 turns.

**Phase-1 gate: control DECAYS** — adherence early 0.75 → late 0 (complies ~4 turns, then collapses once the rule leaves the window). Real drift to fix. Efficiency = adherence-uplift ÷ tokens injected.

| arm | adherence | inj-tokens | uplift vs control | efficiency (uplift/1k tok) |
|---|---:|---:|---:|---:|
| control | 0.12 | 0 | — | — |
| pulse (periodic, every 4 turns) | 0.36 | 174 | +0.24 | 1.38 |
| **canary (reactive)** | **0.56** | 297 | **+0.44** | **1.48** |
| both | 0.60 | 309 | +0.48 | 1.55 |

- **Both hooks deliver a real measured gain** — they restore decayed instruction-adherence. The "effect-unmeasured" gap is closed: neither is useless.
- **Canary (reactive) beats pulse (periodic)** on absolute adherence (0.56 vs 0.36) AND token-efficiency (1.48 vs 1.38 /1k) — confirms the "reactive > unconditional" prior with numbers.
- **`both` barely beats canary alone** (+0.04 adherence for +12 tokens) → stacking has diminishing returns; **canary is the sweet spot**.
- **Implication:** supports the lean call — keep the reactive canary, fold/retire the periodic pulse (it adds little once canary fires). *(Resolved: the replication condition was met by the M3 llama3.1 long-run — canary +0.44 on a 2nd family — so both were promoted to default-on at v1.7; on constrained installs drop pulse first.)*
- Caveats: single model (qwen2.5:7b), single run, n=26 turns; the ack-token is a clean *proxy* for "a skill rule the agent must keep following," not the skills' actual filler/verbosity probes. Direction is clear; not a tight CI. (The Phase-1 gate first mis-reported "floor" — an early-third window diluted the fast decay; fixed to use the first scored turns.)

## Exp10 — cache-lint detection accuracy (`eval/exp10_cache_lint/`)

Closes the **TP≥80% / FP≤10%** target cache-lint's EVAL.md listed as unrun (only fuzz/robustness was measured). 18-case labeled fixture-directory corpus (the exp3 pattern, but units are project trees since cache-lint audits a dir) over the 4 single-run rules — **2** dynamic-content, **4** model-switch, **5** sizing, **6** fork-safety — balanced with FP-guards (inline-code prose, dynamic-inside-a-fence, read-only `grep/cat` hooks).

**Result: recall 1.0, false-alarm 0.0, F1 1.0 (18/18); per-rule P/R/F1 all 1.0.** Every near-miss negative was correctly NOT flagged. Meets both targets with margin.

Honest caveats (so the perfect score isn't oversold):
- **In-distribution corpus** — the fixtures are built from the same rule-trigger patterns the tool was written against, so 1.0 reflects *clean detection on well-formed cases*, not messy/adversarial real-world configs. A harder corpus (obfuscated dynamic content, indirect hook writes via invoked scripts) would be the next stress.
- **Rules 1 & 3 (ordering / tool-stability) out of scope** — they're stateful (diff against a stored baseline across runs), needing a 2-run protocol.
- **The ≥30% cache-hit *uplift* target remains unmeasured** — that needs a cache-aware host (MiMo `cached_tokens` / Claude); detection ≠ dollar savings.

So: cache-lint reliably *catches the cache-busts it targets without false alarms* (detection gain now measured); whether fixing them saves money is still open.

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
| verify-before-completion | **−33.5%** output | **+0.92** (qwen3.6); **+0.04–0.92** across 3 judge families — sign robust, magnitude judge-dependent | **50 × 5** | `runner.py` |
| **compress-context** *(cut v1.6.0)* | **−35.6%** mean token reduction (n=3 long contexts) | — | 3 samples | `runner_compress.py` |
| prompt-triage | **−20.9%** total tokens, 100% routing accuracy | — | 1 × 13 | `runner_triage.py` |
| plan-first-execute | **−20.45%** output | +0.20 (prior N=15) | **3 × 5** | `runner.py` |
| **handoff** *(cut v1.6.1)* | 3/3 integration pass, 4/4 sections, ~50 ms / call, ~2.5 KB doc | — | 3 focus arguments | `runner_handoff.py` |

✓ **The verify-before-completion judge question is now settled.** Re-run on `judge.py --backend ollama --model qwen3.6:35b-a3b-q4km` over all N=50×5 candidates (250 with-skill + 250 without, **0 parse failures** — `judge.py` now strips `<think>` blocks before score-parsing): **with-skill 4.936 vs without-skill 4.012 on the 0–5 evidence-interrogation rubric → delta +0.92.** This *reverses* the prior `−0.40` (which was on the old "I just did X, is it done?" prompts — a rubric artifact where the judge scored "demands fresh evidence" below "affirms confidently"). The reworked prompts embed verification artifacts (test output, build log, install record, env state, migration log) so the rubric fairly rewards "examined the evidence + named the gap"; on those, the skill is clearly net-positive. Candidates were generated by `mimo-v2-flash` and judged by a different family (qwen3.6), so no self-judging bias. (`eval/results/verify-before-completion.ollama.judged.json`.) **Judge-family robustness (added 2026-06-07):** re-judging the same candidates with gemma2:9b → **+0.37** and llama3.1:8b → **+0.04**. The sign replicates across all 3 families, but the magnitude is judge-dependent (qwen3.6 is the most generous; weaker judges barely separate the arms). So the skill is genuinely net-positive on evidence-interrogation, but the honest effect size is **+0.04 to +0.92** depending on the evaluator — *not* a firm +0.92.

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
- `context-keeper` — must beat masking the pre-compact transcript (sidecar already retains 100% URLs / 67% numbers, which masking cannot)
- any future compaction / summarization skill

Adding observation-masking as a runnable baseline harness is a separate eval task; until it lands, skills should at minimum *cite the baseline they're competing against* in their EVAL.md.

## Pending live measurements

| Skill | What to measure | Why |
|---|---|---|
| skills × prompt caching at scale | explicit cache_control breakpoints in cache-aware hosts | the −94% effective Δtotal in Config B suggests per-host caching tuning has more room |

_(Dropped rows: `context-refresh`, `delegate`, `compress-context` — all cut from the catalog; their pending measurements are moot.)_

## Re-running these measurements

```bash
. .brainer/secrets.env && export MIMO_API_KEY

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
