#!/usr/bin/env bash
# Full deterministic offline test entrypoint — exit code is the verdict.
#
# Runs every offline test the repo ships: SKILL.md lint, per-skill unit
# tests, hook self-tests, carrier sync. Model-dependent evals (eval/exp*,
# eval/longrun) are NOT here — they need ollama/GPU and live behind their
# own runners.
#
# Usage: bash scripts/run_all_tests.sh [--quiet] [--group core|tail|all]
set -uo pipefail
export PYTHONDONTWRITEBYTECODE=1
export BRAINER_CHECK_NO_WRITE="${BRAINER_CHECK_NO_WRITE:-1}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

QUIET=""
GROUP="all"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --quiet) QUIET="--quiet" ;;
    --group) shift; GROUP="${1:-all}" ;;
    --group=*) GROUP="${1#--group=}" ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift || true
done
case "$GROUP" in
  core|tail|all) ;;
  *) echo "unknown group: $GROUP (core|tail|all)" >&2; exit 2 ;;
esac
PASS=0; FAIL=0
declare -a FAILED

run() {
  # run <label> <cmd...>
  local label="$1"; shift
  if out=$("$@" 2>&1); then
    PASS=$((PASS+1))
    [ "$QUIET" = "--quiet" ] || echo "PASS $label"
  else
    FAIL=$((FAIL+1)); FAILED+=("$label")
    echo "FAIL $label"
    echo "$out" | tail -8 | sed 's/^/  | /'
  fi
}

if [ "$GROUP" = "core" ] || [ "$GROUP" = "all" ]; then

# 1. SKILL.md lint — every skill, one call each so the failing file is named
for f in skills/*/SKILL.md; do
  run "lint:$(basename "$(dirname "$f")")" python3 scripts/lint_skill_md.py "$f"
done

# 2. Carrier catalogs in sync (CLAUDE.md / AGENTS.md / GEMINI.md sentinels)
run "carrier-sync" python3 scripts/check_carrier_sync.py
run "marketplace-sync" python3 scripts/check_marketplace_sync.py

# 3. Tracked JSON validity (mirrors CI)
run "json-valid" bash -c "git ls-files -z '*.json' | xargs -0 -n1 python3 -m json.tool > /dev/null"

# 4. Python syntax (mirrors CI), compile in memory so the gate writes no .pyc files.
run "py-syntax" python3 scripts/check_python_syntax.py

# 4b. Gate-substrate liveness (LEARNING_CONTRACT.md §4): drift_probes/lesson_patterns
# JSON parses, SKILL.md frontmatter + referenced tool paths resolve, markdown links
# resolve, wiki links resolve, hooks-map entries resolve. A dead gate is worse than none.
run "knowledge-liveness" python3 skills/_shared/knowledge_liveness.py
run "unit:test_knowledge_liveness" python3 skills/_shared/test_knowledge_liveness.py

# 5. Per-skill unit tests (plain-python, no pytest dep)
UNIT_TESTS=(
  skills/_shared/test_model_roster.py
  skills/_shared/test_orchestration_trace.py
  skills/_shared/test_activation_trace.py
  skills/team-lead/tools/test_team_lead_eval.py
  skills/cache-lint/tools/test_cache_lint.py
  skills/brainer-audit/tools/test_brainer_audit.py
  skills/brainer-audit/tools/test_antigravity_sidecar.py
  skills/brainer-audit/tools/test_hooks.py
  skills/brainer-audit/tools/test_path_confinement.py
  skills/brainer-audit/tools/test_redaction.py
  skills/brainer-audit/tools/test_detector_precision.py
  skills/loop-engineering/tools/test_loop_lint.py
  skills/loop-engineering/tools/test_loop_run_monitor.py
  skills/context-keeper/tools/tests/test_extract.py
  skills/output-filter/tools/test_output_filter.py
  skills/prompt-triage/tools/test_classify.py
  skills/write-gate/tools/test_write_gate.py
  skills/requirements-ledger/tools/test_dropmodes.py
  skills/task-retrospective/tools/test_task_audit.py
  skills/wiki-memory/tools/test_consolidate.py
  skills/wiki-memory/tools/test_decay.py
  skills/wiki-memory/tools/test_lint_hygiene.py
  skills/wiki-memory/tools/test_provenance.py
  skills/wiki-memory/tools/test_belief_propagation.py
  skills/wiki-memory/tools/test_schema_evolution.py
  skills/wiki-memory/tools/test_refresh.py
  skills/wiki-memory/tools/test_resolve.py
  skills/wiki-memory/tools/test_write_path_gate.py
  skills/wiki-memory/tools/test_okf.py
  skills/wiki-memory/tools/test_claim_grade.py
  skills/wiki-memory/tools/test_sim_eval.py
  skills/wiki-memory/tools/test_config.py
  skills/wiki-refresh/tools/test_staleness.py
  skills/wiki-refresh/tools/test_artifact_guard.py
  skills/wiki-refresh/tools/test_disuse.py
  skills/wiki-memory/tools/test_wiki_adoption.py
  skills/index-first/tools/test_augment.py
  skills/compliance-canary/tools/test_hook_safety.py
  skills/_shared/test_adversarial_regression.py
  skills/eval-gate/tools/test_validate_case.py
  skills/impact-of-change/tools/test_impact.py
  skills/compliance-canary/tools/test_coherence_drift_meter.py
  skills/learn-skill/tools/test_learn.py
  skills/learn-skill/tools/test_telemetry.py
  skills/learn-skill/tools/test_nomination.py
  skills/learn-skill/tools/test_hooks.py
  skills/learn-skill/tools/test_install_merge.py
  skills/_shared/test_transcript_norm.py
  scripts/test_gen_hooks_map.py
  scripts/test_mine_transcripts.py
  scripts/test_sibling_sync_audit.py
  eval/harness_acceptance/test_run.py
)
# semantic-diff needs tree-sitter; SKIP (not FAIL) where the dep is absent
# (e.g. bare CI runners) — semdiff's own suite covers it on dev machines.
if python3 -c "import tree_sitter" 2>/dev/null; then
  UNIT_TESTS+=(
    skills/semantic-diff/tools/tests/test_basic.py
    skills/semantic-diff/tools/tests/test_multilang.py
    skills/semantic-diff/tools/tests/test_rename.py
    skills/semantic-diff/tools/tests/test_syntax_error.py
    skills/semantic-diff/tools/tests/test_whitespace.py
    skills/semantic-diff/tools/tests/test_realistic.py
    skills/semantic-diff/tools/tests/test_classlevel.py
  )
else
  echo "SKIP semantic-diff suite (tree_sitter not importable)"
fi
for t in "${UNIT_TESTS[@]}"; do
  [ -f "$t" ] || { echo "FAIL missing:$t"; FAIL=$((FAIL+1)); FAILED+=("missing:$t"); continue; }
  run "unit:$(basename "$t" .py)" python3 "$t"
done

# 5b. Deterministic eval sims (offline; exit code is the verdict)
run "sims" env BRAINER_CHECK_NO_WRITE="$BRAINER_CHECK_NO_WRITE" python3 eval/sims/run_all.py --quiet

# 5c. Ablation guard — fails only if a write-gate feature becomes NET-HARMFUL on
# the labeled corpus (removing it would improve accuracy). A real miscalibration
# signal; 0-flip/low-impact features are reported but never fail the gate.
run "ablation-guard" env BRAINER_CHECK_NO_WRITE="$BRAINER_CHECK_NO_WRITE" python3 eval/ablation.py --json

# 5d. Skill-corpus audit — fails if a NEW cross-skill directive conflict or a
# near-duplicate directive is introduced (standing #3 guard; suite is clean now,
# mutation-validated so the clean verdict is non-vacuous). Behavioral instruction
# -efficacy (#2, eval/inert_probe.py) is model-dependent → NOT gated.
run "skill-audit" python3 eval/skill_audit.py --check

# 5e. Hook-safety gate — every hook entrypoint must satisfy the cardinal rule
# (exit 0 on all paths, no partial stdout, subprocess timeouts, stdout=payload).
run "hook-safety" python3 skills/compliance-canary/tools/hook_validate.py

# 5f. Harness-acceptance honest report (H1a-H7, H8 excluded — model-dependent,
# tracked in eval/MEASUREMENT_QUEUE.md). --report ALWAYS exits 0 by design; it
# prints the current honest PASS/FAIL table on every suite run without gating
# it. Use `python3 eval/harness_acceptance/run.py --gate` by hand to fail on
# any H-check FAIL.
echo
echo "--- harness_acceptance (report-only; see eval/harness_acceptance/BASELINE.md) ---"
python3 eval/harness_acceptance/run.py --report

fi

if [ "$GROUP" = "tail" ] || [ "$GROUP" = "all" ]; then

# 6. Hook self-test suites
run "hook:compliance-canary" bash skills/compliance-canary/tools/test.sh
run "tool:eval-gate" bash skills/eval-gate/tools/test.sh
run "tool:verify-artifact" bash skills/verify-before-completion/tools/test.sh

# 7. Triage replay audit — re-classifies every historically-routed prompt with
# the current classifier; fails on local-model / low-conf / length-gate
# violations. Needs real session transcripts, so skip where none exist (CI).
if ls ~/.claude/projects/-Users-za-Documents-Brainer/*.jsonl >/dev/null 2>&1; then
  run "audit:triage-replay" python3 scripts/replay_triage.py
else
  echo "SKIP triage replay audit (no local transcripts)"
fi

fi

echo
if [ "$FAIL" -eq 0 ]; then
  echo "run_all_tests: $PASS/$PASS PASS"
  exit 0
else
  echo "run_all_tests: $PASS passed, $FAIL FAILED:"
  printf '  - %s\n' "${FAILED[@]}"
  exit 1
fi
