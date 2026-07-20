#!/usr/bin/env bash
# Full deterministic offline test entrypoint — exit code is the verdict.
#
# Runs every offline test the repo ships: SKILL.md lint, per-skill unit
# tests, hook self-tests, carrier sync. Model-dependent evals (eval/exp*,
# eval/longrun) are NOT here — they need ollama/GPU and live behind their
# own runners.
#
# Usage: bash scripts/run_all_tests.sh [--quiet] [--group core|tail|all|e3]
#
# --group e3 is NON-CORE and opt-in only: it runs scripts/e3_gauntlet.py +
# scripts/test_e3_gauntlet.py, which each do a REAL `install.sh --project`
# (git init + symlinks + hook-merge) into a fresh temp project — a few
# seconds per run, too slow for the default core/tail/all path and never
# folded into --group all. Run it explicitly: bash scripts/run_all_tests.sh
# --group e3.
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
  core|tail|all|e3) ;;
  *) echo "unknown group: $GROUP (core|tail|all|e3)" >&2; exit 2 ;;
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

# Single declarative source of truth for deterministic suite entrypoints.
# Row schema: kind|group|runner|path|requires_module|label/reason/owner
#   S = executable suite; D = suite delegated to a registered owner; X = exclusion.
test_roster() {
  cat <<'BRAINER_TEST_ROSTER'
# brainer:test-roster:start
# kind|group|runner|path|requires_module|label/reason/owner
S|core|python3|skills/_shared/test_knowledge_liveness.py|-|-
S|core|python3|eval/test_judge.py|-|-
S|core|python3|skills/_shared/test_model_roster.py|-|-
S|core|python3|skills/_shared/test_brief_header.py|-|-
S|core|python3|tests/test_frontier_defaults.py|-|-
S|core|python3|skills/compliance-canary/tools/test_profiles.py|-|-
S|core|python3|skills/_shared/test_orchestration_trace.py|-|-
S|core|python3|skills/_shared/test_activation_trace.py|-|-
S|core|python3|skills/team-lead/tools/test_team_lead_eval.py|-|-
S|core|python3|skills/think/tools/test_think_contract.py|-|-
S|core|python3|skills/cache-lint/tools/test_cache_lint.py|-|-
S|core|python3|skills/brainer-audit/tools/test_brainer_audit.py|-|-
S|core|python3|skills/brainer-audit/tools/test_antigravity_sidecar.py|-|-
S|core|python3|skills/brainer-audit/tools/test_hooks.py|-|-
S|core|python3|skills/brainer-audit/tools/test_path_confinement.py|-|-
S|core|python3|skills/brainer-audit/tools/test_redaction.py|-|-
S|core|python3|skills/brainer-audit/tools/test_detector_precision.py|-|-
S|core|python3|skills/brainer/eval/test_reference.py|-|-
S|core|python3|skills/loop-engineering/tools/test_loop_lint.py|-|-
S|core|python3|skills/loop-engineering/tools/test_loop_run_monitor.py|-|-
S|core|python3|skills/context-keeper/tools/tests/test_extract.py|-|-
S|core|python3|skills/output-filter/tools/test_output_filter.py|-|-
S|core|python3|skills/prompt-triage/tools/test_classify.py|-|-
S|core|python3|skills/write-gate/tools/test_write_gate.py|-|-
S|core|python3|skills/task-retrospective/tools/test_task_audit.py|-|-
S|core|python3|skills/wiki-memory/tools/test_consolidate.py|-|-
S|core|python3|skills/wiki-memory/tools/test_decay.py|-|-
S|core|python3|skills/wiki-memory/tools/test_link_nav.py|-|-
S|core|python3|skills/wiki-memory/tools/test_lint_hygiene.py|-|-
S|core|python3|skills/wiki-memory/tools/test_provenance.py|-|-
S|core|python3|skills/wiki-memory/tools/test_belief_propagation.py|-|-
S|core|python3|skills/wiki-memory/tools/test_schema_evolution.py|-|-
S|core|python3|skills/wiki-memory/tools/test_refresh.py|-|-
S|core|python3|skills/wiki-memory/tools/test_resolve.py|-|-
S|core|python3|skills/wiki-memory/tools/test_write_path_gate.py|-|-
S|core|python3|skills/wiki-memory/tools/test_okf.py|-|-
S|core|python3|skills/wiki-memory/tools/test_claim_grade.py|-|-
S|core|python3|skills/wiki-memory/tools/test_sim_eval.py|-|-
S|core|python3|skills/wiki-memory/tools/test_config.py|-|-
S|core|python3|skills/wiki-refresh/tools/test_staleness.py|-|-
S|core|python3|skills/wiki-refresh/tools/test_artifact_guard.py|-|-
S|core|python3|skills/wiki-refresh/tools/test_disuse.py|-|-
S|core|python3|skills/wiki-memory/tools/test_wiki_adoption.py|-|-
S|core|python3|skills/index-first/tools/test_augment.py|-|-
S|core|python3|skills/compliance-canary/tools/test_hook_safety.py|-|-
S|core|python3|skills/_shared/test_adversarial_regression.py|-|-
S|core|python3|skills/eval-gate/tools/test_panel.py|-|-
S|core|python3|skills/eval-gate/tools/test_validate_case.py|-|-
S|core|python3|skills/impact-of-change/tools/test_impact.py|-|-
S|core|python3|skills/security-oversight/tools/test_security_scan.py|-|-
S|core|python3|skills/security-oversight/tools/test_skill_audit.py|-|-
S|core|python3|skills/compliance-canary/tools/test_coherence_drift_meter.py|-|-
S|core|python3|skills/learn-skill/tools/test_learn.py|-|-
S|core|python3|skills/learn-skill/tools/test_telemetry.py|-|-
S|core|python3|skills/learn-skill/tools/test_nomination.py|-|-
S|core|python3|skills/learn-skill/tools/test_hooks.py|-|-
S|core|python3|skills/learn-skill/tools/test_install_merge.py|-|-
S|core|python3|skills/_shared/test_transcript_norm.py|-|-
S|core|python3|scripts/test_gen_hooks_map.py|-|-
S|core|python3|scripts/test_plugin_hook_precedence.py|-|-
S|core|python3|scripts/test_test_roster.py|-|-
S|core|python3|scripts/test_mine_transcripts.py|-|-
S|core|python3|scripts/test_sibling_sync_audit.py|-|-
S|core|python3|scripts/test_sibling_sync_gitignore.py|-|-
S|core|python3|scripts/test_project_install_preflight.py|-|-
S|core|python3|skills/_shared/test_lane_guard.py|-|-
S|core|python3|eval/harness_acceptance/test_run.py|-|-
S|core|python3|eval/exp8_trigger/test_run_trigger_offline.py|-|-
S|core|python3|skills/semantic-diff/tools/tests/test_basic.py|tree_sitter|-
S|core|python3|skills/semantic-diff/tools/tests/test_multilang.py|tree_sitter|-
S|core|python3|skills/semantic-diff/tools/tests/test_rename.py|tree_sitter|-
S|core|python3|skills/semantic-diff/tools/tests/test_syntax_error.py|tree_sitter|-
S|core|python3|skills/semantic-diff/tools/tests/test_whitespace.py|tree_sitter|-
S|core|python3|skills/semantic-diff/tools/tests/test_realistic.py|tree_sitter|-
S|core|python3|skills/semantic-diff/tools/tests/test_classlevel.py|tree_sitter|-
S|tail|bash|skills/compliance-canary/tools/test.sh|-|hook:compliance-canary
S|tail|bash|skills/eval-gate/tools/test.sh|-|tool:eval-gate
S|tail|bash|skills/verify-before-completion/tools/test.sh|-|tool:verify-artifact
S|e3|python3|scripts/e3_gauntlet.py|-|e3:gauntlet
S|e3|python3|scripts/test_e3_gauntlet.py|-|e3:selftest
X|-|-|scripts/test_skill.sh|-|parameterized helper requiring a skill name; registered suites are tracked directly
# brainer:test-roster:end
BRAINER_TEST_ROSTER
}

run_registered_suites() {
  local wanted_group="$1"
  local kind row_group runner path requirement label effective_label in_registry
  in_registry=0
  while IFS='|' read -r kind row_group runner path requirement label; do
    case "$kind" in
      "# brainer:test-roster:start") in_registry=1; continue ;;
      "# brainer:test-roster:end") break ;;
    esac
    [ "$in_registry" -eq 1 ] || continue
    case "$kind" in
      ""|\#*) continue ;;
      D|X) continue ;;
      S) ;;
      *)
        echo "FAIL test-roster:unknown-row:$kind"
        FAIL=$((FAIL+1)); FAILED+=("test-roster:unknown-row:$kind")
        continue ;;
    esac
    [ "$row_group" = "$wanted_group" ] || continue
    if [ "$requirement" != "-" ] && ! python3 -c \
      'import importlib.util,sys; sys.exit(0 if importlib.util.find_spec(sys.argv[1]) else 1)' \
      "$requirement"; then
      echo "SKIP $path ($requirement not importable)"
      continue
    fi
    if [ ! -f "$path" ]; then
      echo "FAIL missing:$path"
      FAIL=$((FAIL+1)); FAILED+=("missing:$path")
      continue
    fi
    case "$runner" in
      python3|bash) ;;
      *)
        echo "FAIL test-roster:unsupported-runner:$runner:$path"
        FAIL=$((FAIL+1)); FAILED+=("test-roster:unsupported-runner:$runner:$path")
        continue ;;
    esac
    effective_label="$label"
    [ "$effective_label" != "-" ] || effective_label="unit:${path%.py}"
    run "$effective_label" "$runner" "$path"
  done < <(test_roster)
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

# 5. Per-skill unit tests (plain-python, no pytest dep), from the roster above.
run_registered_suites core

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

# 6. Hook self-test suites, from the same declarative roster.
run_registered_suites tail

# 7. Triage replay audit — re-classifies every historically-routed prompt with
# the current classifier; fails on local-model / low-conf / length-gate
# violations. Needs real session transcripts, so skip where none exist (CI).
if ls ~/.claude/projects/-Users-za-Documents-Brainer/*.jsonl >/dev/null 2>&1; then
  run "audit:triage-replay" python3 scripts/replay_triage.py
else
  echo "SKIP triage replay audit (no local transcripts)"
fi

fi

if [ "$GROUP" = "e3" ]; then

# E3 lifecycle gauntlet (LEARNING_CONTRACT.md §8): a lesson banked in Brainer
# must be VISIBLE AND ENFORCED in a fresh consuming repo after install.sh, not
# just inside the Brainer checkout. NON-CORE / opt-in only — each of these does
# a real `install.sh --project` (git init + symlinks + hook-merge) into a fresh
# temp project, too slow for the default core/tail/all path.
run_registered_suites e3

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
