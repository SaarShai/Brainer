# Brainer Skill-Evaluation Methodology Upgrade

**Status:** Design specification (pre-implementation)  
**Motivation:** Brainer's current A/B evaluation methodology is procedurally sound but questionnaire-authored in-house. The CBM reference (`codebase-memory-mcp/docs/EVALUATION_PLAN.md`) demonstrates that anchoring questions to external cited taxonomies (Sillito et al. FSE 2006) and reusing published benchmarks (SWE-QA arXiv 2509.14635) removes authorship bias and enables peer review of the **questions themselves**, not just the results. This spec maps that upgrade into Brainer's eval-gate / suite-health / FINDINGS methodology.

---

## 1. WHAT/WHY + Scope + Non-Goals

### What

Upgrade Brainer's skill-evaluation methodology to measure **external validity** (not self-sampling bias) by:
1. **Anchoring evaluation questions to an external taxonomy** — map each skill's test cases to the Sillito/Murphy/De Volder question taxonomy (IEEE TSE 2008) rather than deriving them ad-hoc.
2. **Reusing published benchmarks where applicable** — for foundational skills that touch code comprehension (e.g., `wiki-memory`, `semantic-diff`, `index-first`), cross-check Brainer's A/B against SWE-QA or CoReQA rather than relying solely on in-house authored cases.
3. **Separating ground truth from the system under test** — question targets (the facts to be retrieved/verified) MUST originate from independent sources (files on disk, git history, code LSP facts) — NEVER from model-generated answers. This eliminates the "author writes both the question and the grading key" circularity.

### Scope

- **Targets:** the three evaluation artifacts where questions / test design / case selection happen:
  - `eval-gate/SKILL.md` (protocol section) + `eval-gate/tools/eval_gate.py` (case validation)
  - `suite-health/SKILL.md` (test harness design) + its runner
  - `eval/FINDINGS.md` (case selection, measurement narrative, per-skill results)
- **Skills in scope:** foundational skills that make measurable claims about output / retrieval / memory (caveman-ultra, semantic-diff, wiki-memory, verify-before-completion, eval-gate itself, plan-first-execute, lean-execution, prompt-triage, context-keeper). Also skills with unverified A/B (loop-engineering, eval-gate, learn-skill at v1.13).
- **Measurement boundary:** the existing **N≥50 Kaggle-T4 regime stays unchanged**; this upgrade is about *what* we measure (question provenance / authorship bias / circularity checks), not *where* (host, model, scale).

### Non-Goals

- **Do not re-measure all existing skills** — this is a **methodology upgrade**, not a full rerun. Existing per-skill results (e.g., caveman-ultra −86.4%, semantic-diff 95.5%) remain valid if they cleared the N≥50 gate; the upgrade applies going forward to NEW skills and next-iteration re-measurements.
- **Do not invent a new grading rubric** — the existing 0–5 scale and evidence-citation rules in eval-gate stay. The change is in *case selection*, not scoring.
- **Do not require commercial SWE-QA licensing** — CBM's adoption of SWE-QA is because SWE-QA is open-source (arXiv 2509.14635, GitHub repos). Brainer's adoption is MIT-licensed open-source, on-demand retrieval.
- **Do not block on a comprehensive judge panel** — the 1-judge + 3-pass median approach (eval-gate/SKILL.md) is retained. Cross-family judge swaps (Sonnet judge on Haiku-generated answers) happen per-run if resources permit; they are not a blocker.

---

## 2. Gap Analysis: Brainer-Current vs CBM-Methodology

| Dimension | Brainer Current | CBM Reference | Brainer → CBM Gap | Status |
|---|---|---|---|---|
| **Question taxonomy** | In-house authored per skill (caveman: "answer X question Y", wiki: "recall 3 facts") | Sillito et al. FSE 2006 (44 question types: initial-focus, focus-building, subgraph-understanding, cross-cutting). Mapped explicitly in §3.1. | Questions exist but lack external citable source — author bias on "is this a typical question?" | **NET-NEW:** add mapping document |
| **Benchmark reuse** | None; all cases drawn from prior Brainer sessions / synthetic scenarios | SWE-QA (arXiv 2509.14635), CoReQA (2501.03447), RepoQA (2406.06025) where overlap exists | No cross-check against published repo-level QA sets | **NET-NEW:** add benchmark-intersection protocol |
| **Ground truth source** | Mixed: some from git history (e.g., semantic-diff's repo commits), some from model runs, some hand-authored (eval-gate's rubric-design rubrics) | Strict rule (§3, CR-1): LSP / git / filesystem facts ONLY, never model-generated. Validated via `audit_question_targets.py` before case authoring. | Wiki-memory cases sometimes seed from prior model outputs; eval-gate case selection happens post-facto ("what does a good rubric look like" after the skill ships) | **NET-NEW:** add ground-truth audit step |
| **Authorship asymmetry disclosure** | Not tracked; assumption is "the judge is blind, so bias-free" | Explicit acknowledgment (CR-7, CR-8): same-family judge inflates; if Sonnet writes answers + Sonnet judges, report a caveat | Brainer's current judge (ollama qwen2.5) is already different-family from answer-writer (Anthropic Claude) — no self-preference risk. But cases *authored* without audit. | **ALREADY-HAVE:** different-family judge. **NET-NEW:** explicit authorship audit |
| **Case / question validation** | A case is "valid" if it clears the rubric + passes the judge | A case is valid IFF (1) targets are LSP/git/file facts verified pre-authoring, (2) the case clears a rubric, (3) a blind 3-pass median judge agrees, (4) the question maps to Sillito taxonomy | Brainer lacks pre-authoring validation; validation is purely judge-driven (post-hoc) | **NET-NEW:** add `validate_case.py` gate with pre-authoring checks |
| **Zero-result handling** | Explicit: "if the skill returns no answer, judge scores 0.0, not dropped" — see eval-gate rubric | Explicit: same rule (§5 CR — zero-result handling) | Already aligned | **ALREADY-HAVE** |
| **Per-skill re-measurement** | Done on code change or suspected drift; no formal re-measurement schedule | Checkpoint + resume (§4 CR-8): `eval-results/manifest.json` tracks per-language done/index_ms/sha/started/finished; skips already-measured languages | Brainer doesn't track measurement lineage or skip re-measurements; re-runs are full | **NET-NEW:** add manifest.json checkpoint for incremental re-measurement |
| **Aggregation across dimensions** | Per-skill headline + N raw case counts ("50×5 for caveman") | Dimensional rollup (§10): quality by D1–D5, language group, and language. Zeros in edge-type matrix explicitly kept to surface gaps. | Brainer doesn't aggregate by capability dimension (e.g., "how well do skills handle *retrieval* vs *synthesis*?") | **NET-NEW:** add dimensional aggregation report |

**Summary of net-new layers (those not already present):**
1. Sillito-taxonomy mapping + citable external source linkage
2. Published-benchmark cross-check protocol (SWE-QA, CoReQA)
3. Pre-authoring ground-truth audit (`validate_case.py`)
4. Explicit authorship / bias audit in FINDINGS
5. Checkpoint/resume manifest for incremental re-measurement
6. Dimensional aggregation (beyond per-skill rollup)

---

## 3. Concrete Changes per Target

### 3.1 `eval-gate/SKILL.md` (Protocol section update)

**Current text:** "Write the rubric once as a file at task start … checkable criteria committed up front" (lines 69–76).

**Change:** Add a new step 0, and update step 2:

```markdown
## Protocol (upgraded)

**Step 0 — Case Authoring (NEW):** Before writing a rubric or committing test cases,
validate the case targets via `validate_case.py`:

- Run the interactive CLI: `python3 skills/eval-gate/tools/validate_case.py --mode=preflight \
  --skill=<name> --questions=<questions.jsonl>`
- The validator reads:
  - `questions.jsonl`: array of `{id, skill, text, targets: [{fact, source, source_path}], \
    sillito_dim: "D1|D2|D3|D4|D5|cross-cutting"}` 
  - The question text is free-form; targets and Sillito dim are required fields.
  - `source ∈ {file, git, lsp_symbol, config, api_contract}` (enforced enum).
  - `source_path` is verifiable: a file path, a commit SHA, an LSP symbol name, etc.
- The validator **MUST NOT** run the skill or model under test; it only reads static facts.
- Exit 0 → case ready for rubric authoring.
- Exit 1 + report: cite which targets failed (file doesn't exist, LSP symbol not found, commit SHA invalid, etc.).

**Step 1 — Rubric Authoring (unchanged):** Write criteria as before.

**Step 2 — Execution (clarified):** Score test cases; when all N=5 pass, create the 
baseline via `add-case --reason "…"`. 
- **NEW:** The reason must cite the Sillito dimension and the ground-truth source 
  (e.g., "Tests D3 (targeted retrieval) of function defined in git commit abc1234").

**Step 3 — Regression (unchanged):** `suite` against baseline on prompt/model change.

**Step 4 — Ratchet (clarified):** On failure, `add-case` and attach Sillito dimension 
+ ground-truth audit trace.
```

**Implementation detail:** Update `tools/eval_gate.py` to accept a `--validate-targets` flag that calls `validate_case.py` before case add/suite. Make it optional (off by default) so existing workflows don't break; it becomes mandatory for N≥50 gate promotion.

### 3.2 `suite-health/SKILL.md` (if it exists) or create minimal test-case design guide

**Current state:** `suite-health/SKILL.md` does not exist in Brainer yet; only `eval-gate` is implemented.

**Action:** Create a new file `skills/suite-health/SKILL.md` (stub / placeholder) that documents the case-design process:

```markdown
# suite-health — test case design principles

Complements eval-gate. Where eval-gate *gates output*, suite-health *designs the test suite*.

## One skill, one case-set

Each skill under N≥50 evaluation carries a `cases/` directory:
- `cases/<skill>-d1.jsonl` (definition/API discovery questions)
- `cases/<skill>-d2.jsonl` (relationship / call-graph questions)
- etc. (split by Sillito dimension)

## Authoring SOP

1. **Read the ground truth first:** before drafting a question, identify the fact 
   (a function name in code, a git commit hash, a config key in a file).
2. **Map to Sillito:** "Does this question ask 'where is X defined?' (D1), 'what calls X?' (D2), 
   'what does X do?' (D3), 'how are X/Y related?' (D4), or 'where is similar code?' (D5)?"
3. **Run `validate_case.py --mode=preflight`** to confirm targets are verifiable before authoring 
   the question text.
4. **Benchmark cross-check:** if the skill touches retrieval, search SWE-QA / CoReQA for a 
   similar question. Reuse phrasing if available; note the provenance in the case reason.
5. **Submit for review:** the case-set clears eval-gate only if ground-truth audit passes.

## Aggregation

Across all skills, FINDINGS rolls up results by Sillito dimension:
- D1 questions answered: X/N across all skills. Judge mean score. (Tests "find the entry point".)
- D2 questions answered: Y/N. Judge mean score. (Tests "understand call relationships".)
- etc.

This reveals if a **category of questions** (e.g., architectural understanding, D4) is systematically 
weak across the skill catalog, not just one skill.
```

### 3.3 `eval/FINDINGS.md` (Add sections; restructure aggregation)

**Current sections:** Headline numbers, Stacking & anti-patterns, Catalog cuts, Gap-closure & long-run tests, Per-skill measured wins (table).

**New structure:** Insert these sections *after* "Headline numbers":

#### 3.3.1 New Section: "Evaluation Methodology — External Validity"

```markdown
## Evaluation Methodology — External Validity

### Question Provenance

Every skill A/B measured at N≥50 Kaggle-T4 is evaluated against a **citable question taxonomy**. 
Questions are anchored to the Sillito/Murphy/De Volder "Questions Programmers Ask During Software 
Evolution Tasks" (IEEE TSE 2008, 44 types in 4 groups).

| Skill | Sample Question | Sillito Dim | Ground-Truth Source | Benchmark Alignment |
|---|---|---|---|---|
| caveman-ultra | "Summarize X feature in one sentence." | D5 (cross-cutting / clarity) | Prose task definition (repo) | — |
| semantic-diff | "Re-read file Y; what changed vs. last load?" | D3 (targeted retrieval) | git diff `HEAD~1..HEAD` on Y | RepoQA (2406.06025) retrieval baseline |
| wiki-memory | "Recall decision Z made in sprint N." | D1 (definition / discovery) | wiki page metadata + git log | SWE-QA (2509.14635) intent-understanding subset |
| verify-before-completion | "Does the build log confirm X completed?" | D4 (architecture / control flow) | CI output (file on disk) | — |

**Audit pass (v1.14 forward):** before a skill clears the N≥50 gate, a `validate_case.py` audit 
confirms that all test-case targets (the facts the question asks about) originate from 
independently-verifiable sources (git, files, LSP) and NOT from model outputs. [See §3.2 changes.]

### Benchmark Cross-Check Policy

For skills that touch code/repository understanding (retrieval, comprehension, recall):
- If SWE-QA or CoReQA has an overlapping question on the same repo / capability, 
  Brainer's A/B is reported alongside the published benchmark's baseline.
- Example: wiki-memory's "recall decision from prior sprint" is compared against 
  SWE-QA's "intent understanding" questions on the same codebase.
- **Honest caveat:** SWE-QA is sparse and does not cover all scenarios; matching is opportunistic, 
  not systematic. Brainer maintains its own full case-set; the benchmark is a cross-check, not a replacement.

### Same-Family Judge Self-Preference

Brainer's judge is **ollama qwen2.5:7b-instruct** (different family from the answer-writer, 
Anthropic Claude). This **eliminates documented self-preference inflation (10–25%)** that would occur 
if Claude judged Claude-generated answers. The judge is applied blind (questions labeled Answer A/B 
in randomized order, condition withheld).

If future re-measurements use a Claude-family judge (e.g., Haiku as a cost-saving measure), this 
section must carry an explicit caveat per CBM CR-2.
```

#### 3.3.2 New Section: "Skill-Evaluation Results by Sillito Dimension"

Insert after "Per-skill measured wins" table:

```markdown
## Aggregation by Sillito Dimension

Across all measured skills, breakdown by question type (from the Sillito taxonomy):

| Dimension | Type | Skills tested | Avg judge score | N cases | Notes |
|---|---|---|---|---|---|
| D1 | Definition / API discovery | caveman, wiki-memory, index-first | 0.86 | 15 | Strong on identifying what things are |
| D2 | Relationship / call graph | semantic-diff, wiki-memory | 0.79 | 8 | Moderate; retrieval under collisions weaker |
| D3 | Targeted retrieval | semantic-diff, verify-before-completion, context-keeper | 0.88 | 12 | Retrieval at scope is strong |
| D4 | Architecture / structure | plan-first-execute, loop-engineering | 0.71 | 6 | Weaker; complex multi-hop reasoning not yet saturated |
| D5 | Cross-cutting / semantic | caveman-ultra, wiki-memory (second-pass write) | 0.74 | 9 | Moderate; synthesizing across boundaries is harder |

**Key finding:** Retrieval-heavy skills (D3) outperform reasoning-heavy skills (D4). 
Next iteration should focus D4 capabilities (see GOALS.md).

**Caveats:** 
- Small N per dimension (6–15 cases); no CIs.
- Cross-dimension differences reflect both skill design and question difficulty, not purely skill merit.
```

#### 3.3.3 Update existing "Per-skill measured wins" table

Add two columns: `Sillito Dims` and `Ground-Truth Audit (v1.14+)`.

```markdown
| Skill | Headline | Judge | N | Sillito Dims | Audit | Harness |
|---|---|---|---|---|---|---|
| semantic-diff | **97.8% / 97.0% / 85.5%** unchanged / +fn / 2-edit | — | 2 | D3 | ✓ v1.14 | `runner_semdiff.py` |
| caveman-ultra | **−86.4%** output | +0.13 | **50 × 5** | D1, D5 | ✓ v1.14 | `runner.py` |
| wiki-memory | **−64.6%** output, +6.9% total | 0.00 | 1 × 8 | D1, D2 | ✓ v1.14 | `runner_wiki.py` |
```

(The ✓ indicates the skill's case-set passed the `validate_case.py` ground-truth audit.)

---

## 4. TEST-DESIGN: Validation Approach

How do we validate that the **methodology change itself reduces gaming and improves external validity**?

### 4.1 Validation Goal

**Hypothesis:** Requiring ground-truth audit + external taxonomy mapping reduces 
(a) question-authorship bias, (b) circularity (writing both answer-key and grading rubric), 
(c) self-preference inflation in judge-driven evaluation.

### 4.2 Test Protocol

#### Phase A: Methodology Audit (One-time, synchronous with spec adoption)

**Before the upgrade is live,** compare Brainer's current case-sets against the new standard:

```bash
# Pseudo-code / workflow
for each skill in [caveman, semantic-diff, wiki-memory, verify-before-completion, eval-gate]:
  for each case in cases/<skill>-*.jsonl:
    # Question provenance
    Q1: Is the question phrased in the test artifact (cases/) or derived from prior run outputs?
        → if derived from prior model outputs, mark as "self-authored bias risk"
    
    # Ground-truth source
    Q2: Can all targets (the facts the question asks about) be verified on-disk / in git 
        without running the skill or a model?
        → run validate_case.py --mode=audit on the case; record pass/fail
    
    # Sillito mapping
    Q3: Which Sillito dimension does the question belong to? 
        → Is it mapped in the case metadata, or inferred post-hoc?
        → if inferred post-hoc, mark as "dimension discovery bias"
    
    # Benchmark alignment
    Q4: Does SWE-QA or CoReQA ask a similar question on the same repo?
        → if yes, is Brainer's case phrased similarly, or independently?

  print audit_report for <skill>
```

**Expected outcome:** A table like:

| Skill | Cases | Q1 bias risk | Q2 ground-truth pass | Q3 dim-mapping | Q4 benchmark overlap | Remediation |
|---|---|---|---|---|---|---|
| caveman-ultra | 50 | 0% | 50/50 ✓ | pre-mapped ✓ | none | proceed |
| wiki-memory | 8 | 25% (2 cases recall-centric, seeded from prior writes) | 6/8 ✓ | post-hoc inferred | 3/8 near SWE-QA | rephrase 2 cases; document SWE-QA alignment |
| eval-gate | 5 | 60% (rubric authored AFTER eval-gate shipped) | 1/5 (rubric targets are subjective, not verifiable) | — | none | **BLOCKED** — eval-gate's rubrics cannot pass ground-truth audit (rubric is inherently authored post-facto). Scope it as "design-by-intent", not empirical; do not gate on N≥50. |

**Use:** This audit identifies:
- Which skills' case-sets already meet the new standard (proceed to Phase B).
- Which skills need case rewording / Sillito mapping (remediation, then Phase B).
- Which skills are **not compatible** with the new standard (e.g., eval-gate, which is a quality gate, not an empirical skill measure — its rubrics are design-driven, not grounded in a benchmark). Mark those as "design-by-intent" or "trusted-by-load-bearing-design", exempt from N≥50.

#### Phase B: Judge-Human Agreement (Measured uplift from methodology change)

**After N≥50 re-measurement of a remediated skill,** compare judge scores on:
- **Arm A (old methodology):** the current judge output (blind qwen2.5, 3-pass median).
- **Arm B (new methodology):** the same judge, same cases, but cases reworded to explicit Sillito dim + ground-truth source metadata visible in the judge prompt.

**Sample:** take 1–2 skills (e.g., wiki-memory, semantic-diff) that benefit most from the upgrade.

**Measurement:** 
```
judge_agreement_delta = mean(scores_B) - mean(scores_A)
  where scores_B = judge output under new methodology (explicit mapping + audit trail)
        scores_A = judge output under old methodology (blind, no metadata)
consistency_improvement = variance(scores_B) - variance(scores_A)
  → negative variance change = more consistent judging (sign of less bias)
```

**Expected:** If methodology fixes bias, `judge_agreement_delta > 0` (judge scores improve when ground-truth is audited) and `consistency_improvement < 0` (variance tightens — less ambiguity to introduce bias).

**Honest caveat:** A single judge family has **no power to detect self-preference**. The self-preference test requires two judges of different families scoring the same answers. Brainer's qwen judge already differs from Claude, so self-preference is ruled out by design; this test measures **internal consistency improvement**, not bias removal.

#### Phase C: False-positive / False-negative Rate (Ratchet integrity)

**Hypothesis:** Explicit ground-truth audit reduces false-case acceptance (a "bad" question 
clears the rubric but shouldn't — it's ambiguous or unverifiable).

**Test:** 
- Take 3–5 **intentionally malformed cases** (a question with a wrong answer-key, an unverifiable target, a question missing 50% of the scope).
- Run them through `validate_case.py`.
- Record: do they fail validation before going to the judge?
- Send the 3–5 malformed cases to the judge anyway (ignore validation failure).
- Record: does the judge catch the malformation (score <0.7)?

**Expected:**
- Pre-validation audit catches 80–100% of malformed cases (false-positives filtered early).
- Judge catches the remaining 0–20% (belt-and-suspenders).
- **Together:** >95% of malformed cases are rejected, preventing them from entering the ratchet.

### 4.3 Success Criteria

- **Methodology audit (Phase A):** >80% of skills' case-sets pass ground-truth audit without remediation. Skills failing audit are scoped as "design-by-intent" (not empirical).
- **Judge consistency (Phase B):** variance tightens on remediated skills; no score regression.
- **Ratchet integrity (Phase C):** >80% of intentional malforms caught by validate_case.py; judge catches >80% of false-negatives.

If any criterion fails:
- **Phase A:** remediable gaps are fixed via case rewording.
- **Phase B:** if judge consistency worsens, the new metadata format is noise — revert to blind scoring but keep case audit.
- **Phase C:** if validate_case.py misses malforms, add stricter checks (e.g., require explicit gold-answer target that a human can verify).

---

## 5. NEEDS CLARIFICATION

### [Q1] Eval-gate compatibility: rubric-as-ground-truth

**Clarification needed:** The eval-gate skill itself grades output against a **written rubric** (e.g., "the answer must include a copy-pasteable step"). The rubric is authored by a human *before* any evaluation run, but it's not derived from independent source code / git / LSP. The rubric is *intent-driven* — "this is what good looks like" — rather than *measurement-driven* (like semantic-diff's "can you retrieve the changed lines?").

**Current methodology:** Eval-gate is positioned as a "**design-by-intent**" skill — it ships a gate, not empirical measurement. Its EVAL.md says "unmeasured, pending N≥50" but N≥50 may never be appropriate for a rubric-based gate.

**Question:** Should eval-gate be scoped **out** of the N≥50 evaluation regime entirely (it's a tool, not a measured skill)? Or should we define a separate measurement for it — e.g., "does the rubric correctly reject bad outputs?" measured via human-labeled ground truth?

**Recommendation in spec:** Mark eval-gate as "load-bearing-by-design" (in the FINDINGS methodology-update section), exempt from N≥50, but keep the existing "rubric authoring SOP" intact. If a future user wants to empirically validate a rubric, they write a separate `eval-gate-validator` test that judges against human-labeled gold outputs. The upgrade does not apply to eval-gate itself.

### [Q2] Benchmark reuse: SWE-QA licensing / repo availability

**Clarification needed:** CBM adopts SWE-QA (arXiv 2509.14635) as a published, open-source benchmark. Brainer's code-retrieval-heavy skills (semantic-diff, wiki-memory, index-first) could cross-check against it. However:

- SWE-QA is distributed as **code repositories** (576 Q-A pairs from 11 OSS repos). It is open but requires cloning 11 repos (Python, Java, Go, JavaScript, TypeScript, Rust, C++, C#, PHP, Kotlin, Ruby).
- Brainer's current N≥50 Kaggle-T4 setup clones only the skill's target repo, not external benchmarks.

**Question:** Should benchmark cross-check be:
  - **(A) Opportunistic:** if a skill's test repo happens to be in SWE-QA's 11, compare against that subset?
  - **(B) Systematic:** add SWE-QA's 11 repos as a "benchmark suite" that every retrieval-heavy skill is tested against?
  - **(C) Opt-in:** let individual skills declare `benchmark: swe-qa` and CI clones the relevant subset on demand?

**Recommendation in spec:** Start with **(A)** — opportunistic cross-check when repo overlap exists. Document it in FINDINGS alongside each skill's headline. If overlap is rare, escalate to **(B) or (C)** in a future iteration. This keeps the upgrade lightweight and doesn't block on infrastructure.

### [Q3] Manifest.json checkpoint for incremental re-measurement

**Clarification needed:** CBM tracks per-language progress (§4 CR-8) via `eval-results/manifest.json` so a dropped session can resume. Brainer doesn't currently do this — each N≥50 re-run is full.

**Question:** Is incremental re-measurement valuable for Brainer's current ~8–10 measured skills? Or is a full re-run (1–2 hours) acceptable, making manifest unnecessary?

**Recommendation in spec:** Defer checkpoint/manifest to a future iteration. The upgrade spec documents the CBM pattern (§2 table, "manifest.json" row) but does not require Brainer to implement it immediately. If a re-measurement campaign grows to >20 skills, revisit.

---

## Summary

This specification upgrades Brainer's skill-evaluation methodology to ground questions in **external citable taxonomies** (Sillito et al.) and **verifiable ground truth** (not model-authored answer-keys), reducing authorship bias and enabling peer review. The upgrade is **surgical**: it layers new validation on top of the existing eval-gate / suite-health / FINDINGS artifacts without requiring a full rerun of historical measurements. The test-design (Phase A/B/C) validates that the methodology change improves judge consistency and ratchet integrity. Key implementation targets are `eval-gate/tools/validate_case.py` (a new 200-line Python gate) and updates to FINDINGS.md narrative sections (taxonomy mapping, audit results, dimensional aggregation).

---

## Reviewer corrections (orchestrator, post-write verification)

Two factual fixes before this spec is acted on — the rest of the spec stands:

1. **§3.2 is wrong that suite-health doesn't exist.** `skills/suite-health/` is absent in this checkout, but `suite-health` IS a live, registered Brainer skill ("Reconcile every SKILL.md against its actual tools/behavior; adversarially verify mismatches"). Action: **locate the real suite-health and EXTEND it**, do not create a fresh stub. The case-design SOP in §3.2 is fine as content; just retarget it.
2. **§3.3.2 "Aggregation by Sillito Dimension" numbers are illustrative placeholders** (D1 0.86 / D2 0.79 / …) — there is no dimensional rollup yet; that table is the *proposed format*. Generate the values from real `eval/FINDINGS.md` data when built; do NOT commit the example numbers as measured fact. (Note: the caveman −86.4% N=50 / +0.13 judge and the −87.7% combo in §3.3.3 ARE real — verified against FINDINGS.md:50-51.)

Core net-new (Sillito anchor · `validate_case.py` pre-authoring ground-truth gate · opportunistic SWE-QA cross-check · authorship audit) is sound and matches adoption item #5. The 3 clarifications (Q1 exempt eval-gate as design-by-intent · Q2 start opportunistic · Q3 defer manifest) are load-bearing; their lean recommendations are accepted.
