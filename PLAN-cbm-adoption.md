# GOAL — Adopt codebase-memory-mcp patterns into Brainer (#1,2,3,7,8,9 build; #4,5 spec)

Source of truth for this multi-agent task. Outranks any in-context restatement.

**Posture:** branch + worktrees, review before merge. New hooks ship opt-in
(`auto-install: false`) per Brainer convention. Every agent must keep
`scripts/run_all_tests.sh` green. Shared index files (`skills/SKILLS_INDEX.md`,
root `install.sh`, `CLAUDE.md`, `HOOKS_MAP.md`) are OUT-of-scope for agents —
they emit a patch-suggestion block; the orchestrator (main loop) integrates.

**Loop contract:** generator (writer agent) ≠ verifier (main loop runs tests
fresh in the worktree + adversarial probe). Gate = the item's test script exits 0
AND `scripts/run_all_tests.sh` stays green. Stop = gate passes OR 2 iterations.
Budget cap = 6 dispatch agents + ≤2 adversarial verifiers = ≤8 total.

## Work items

### A — wiki-core (writer, worktree). Files: `skills/wiki-memory/**`
- **#2 degraded-write**: after a write/index op, re-count persisted vs expected;
  return `status:"degraded"` (not silent ok) when persisted < ratio×expected.
  Nodes/pages-only, floor to skip tiny stores, env-tunable ratio. Lineage: cbm
  `dump_verify.h` (#334).
- **#3 loud unsupported-query**: `wiki.py search` distinguishes an unsupported/
  malformed query from a valid zero-match — explicit `error:"unsupported: …"`,
  not `[]`. Lineage: cbm `cypher.c` unsupported-feature errors.
- **#8 ADR**: extend the `decision` template to full ADR (status/context/
  decision/**consequences**); `wiki.py` ingest of `DECISIONS.md` + `docs/adr/*`
  as decision pages. Lineage: cbm `manage_adr` / `store.c:5869`.
- **done means:** `python3 tools/test_wiki_adoption.py` exit 0 covering: degraded
  triggers on under-persist + stays ok on normal; malformed query → error not
  []; valid zero-match → empty (distinct); ADR template has 4 fields; ingest of
  a fixture `docs/adr/0001-x.md` creates a page. `run_all_tests.sh` green.

### B — index-augment-hook (writer, worktree). Files: `skills/index-first/**`
- **#1 grep-augment PreToolUse hook**: on Grep/Glob, extract longest ≥4-char
  identifier token; if valid, query the available index (graphify/wiki search)
  and inject top hits as `additionalContext`. NEVER intercept Read. Cardinal
  rule: exit 0 + no stdout on every error/timeout/short-token/missing-index.
  Hard deadline (`signal.alarm` Unix / `threading.Timer` fallback). Opt-in
  `tools/install.sh` that merges a PreToolUse entry into `.claude/settings.json`
  (never overwrite corrupt settings — copy context-keeper's merge guard).
- **done means:** `python3 tools/test_augment.py` exit 0 covering: valid token →
  additionalContext JSON on stdout, exit 0; Read tool → no-op exit 0; <4-char/
  glob/regex-only token → no-op exit 0; simulated index error → no-op exit 0;
  simulated slow query past deadline → exit 0 no partial stdout. SKILL.md +
  EVAL.md updated. `run_all_tests.sh` green.

### C — hook-safety (writer, worktree). Files: `skills/compliance-canary/**`,
  `skills/context-keeper/**`, `scripts/**`
- **#7 hook-safety lint + hard deadline**: `tools/hook_validate.sh` (or .py)
  static-checks every Brainer hook for: exits 0 on all paths, no partial stdout
  on error, subprocess timeout guards, stdout=payload/stderr=logs. Add a
  `compliance-canary` `drift_probes.json` probe `hook_output_anomaly`. Add a
  reusable deadline wrapper module. Also add a `degraded` manifest line to
  context-keeper extract (persisted vs expected). Lineage: cbm `hook_augment.c`
  cardinal rule + SIGALRM deadline.
- **done means:** `python3 tools/test_hook_safety.py` exit 0 covering: validator
  PASSES on the 3 existing real hooks; FAILS on a crafted hook that exits 1 /
  emits partial stdout. New probe parses in `check_drift_probes.py`.
  `run_all_tests.sh` green.

### D — artifact-merge (writer, worktree, may use cheaper model). Files: a new
  helper under `skills/_shared/` or `skills/wiki-refresh/tools/`
- **#9 merge=ours + integrity-gated import**: helper that, when a regenerated
  artifact is committed, writes `.gitattributes` `<path> merge=ours` and gates
  import on an integrity sidecar (presence + checksum of both blob and meta).
  Patch-suggestion only for root `install.sh`. Lineage: cbm `artifact.c:351`.
- **done means:** `python3 tools/test_artifact.py` exit 0: export→import roundtrip
  ok; truncated/missing-sidecar import rejected (loud); `.gitattributes` line
  written idempotently. `run_all_tests.sh` green.

### E — spec-impact (spec only, GLM, read-only). Output: `specs/impact-of-change.md`
- **#4 NEW skill `impact-of-change` SPEC**: map working diff → downstream
  callers/dependents/affected symbols + risk class, pre-edit or pre-done. WHAT/
  WHY, testable requirements, acceptance criteria, test-design, how it leans on
  graphify edges. NO code into `skills/`. Lineage: cbm `detect_changes`.

### F — spec-eval (spec only, GLM, read-only). Output: `specs/eval-methodology.md`
- **#5 eval methodology SPEC**: anchor eval questions to Sillito FSE-2006 dev-
  question taxonomy + reuse SWE-QA; blind LLM-judge; two-condition A/B; question
  targets from independent ground truth, never the model-under-test. Map onto
  `eval-gate`/`suite-health`/FINDINGS. Test-design = how we'd validate the
  methodology change. NO code. Lineage: cbm `docs/EVALUATION_PLAN.md`.

## done means (overall) — re-read at the end
1. A,B,C,D worktree branches each have their item test passing (fresh main-loop run) + `scripts/run_all_tests.sh` green.
2. E,F specs exist, are reviewed, and carry a test-design section.
3. Shared-file patches (SKILLS_INDEX/install.sh/CLAUDE.md) integrated by orchestrator, run_all_tests green post-integration.
4. New hooks are opt-in; nothing auto-wired to default install.
5. Synthesized diff presented for review on an integration branch; nothing merged to main without approval.
