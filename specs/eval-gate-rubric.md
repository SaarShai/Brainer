# Spec — eval-gate per-criterion rubric mode

**Status:** building (ledger R16, turn 43). **Source:** cognee adoption review (A1, top
open adopt) + external reviewer handoff §6.1. **Owner skill:** `eval-gate`.

## WHAT / WHY

`eval_gate.py score`/`suite` today emit a single holistic `0-5` + one reason. A FAIL
says *that* the output is below the line, not *which* requirement it missed. cognee's
`rubric.py` judges each criterion independently (YES/NO → fraction). Adopt that
**diagnostic granularity** — nothing else from cognee (no DB, no service, no LLM
mandate). The gate turns "fail" into actionable failure coordinates.

Non-goals: structured-output/JSON-schema backends; per-criterion *separate* judge calls
(single call, N verdicts — lean); changing holistic behavior; a new skill.

## Testable requirements

1. **Opt-in, zero-regression.** With no `--criteria-file`/`--criteria-json`, output and
   exit codes are byte-for-byte the existing holistic behavior. (existing `test.sh` green.)
2. **Criteria input.** `--criteria-file PATH` or `--criteria-json '<json>'` accepts a list
   (or `{"criteria":[...]}`) of `{id, description, weight?=1.0, required?=false}`. Bad
   criteria (missing id/description, dup id, weight≤0, empty list) → **exit 2** (fail-safe).
3. **Per-criterion judging.** Each criterion judged PASS/FAIL independently in one judge
   call; tolerant parse of `<id>: PASS|FAIL — reason` lines (accepts YES/NO/✓/✗, leading
   bullets/numbers). A criterion with **no** returned verdict → fail-safe FAIL. **All**
   criteria unparseable → exit 2 (never a fabricated pass — mirrors holistic `None`).
4. **Scoring.** `score_norm` = Σ(weight·pass)/Σweight. `blocking_criteria` = `required`
   criteria that failed. `verdict = fail` iff `blocking_criteria` non-empty **OR**
   `score_norm < threshold` — a required-criterion fail blocks even when the weighted mean
   clears the line.
5. **Output (criteria mode).** JSON: `{verdict, score_norm, threshold, blocking_criteria,
   criteria:[{id, pass, score, weight, required, reason}], latency_ms}`. Exit 0 pass / 1 fail.
6. **suite.** `--criteria-*` applies to every case; a case fails if blocked or below
   threshold; `mean_norm`/baseline/regression semantics unchanged (uses each case's norm).
7. **Offline test.** `--stub-criteria '<json>'` (or `@path`/path) injects deterministic
   `{id: pass|fail}` verdicts — no model, for CI. Mirrors `--stub-score`.

## Acceptance criteria (`done means:`)

- `bash skills/eval-gate/tools/test.sh` → ALL PASS, including new criteria cases
  (all-pass→0, required-fail→1, optional-fail-but-mean-ok→0, missing-verdict fail-safe→1,
  bad/dup criteria→2, suite criteria pass/fail, `_parse_criteria` unit shapes).
- `bash scripts/run_all_tests.sh` → 85/85 (no regression; holistic path identical).
- A required-criterion FAIL with weighted mean == threshold returns exit 1 (req. 4).
- Adversarial diff-review (independent model) finds no fabricated-pass / parse-bypass hole.
