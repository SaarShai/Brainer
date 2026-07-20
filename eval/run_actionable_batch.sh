#!/usr/bin/env bash
# Run only the eval steps whose results would actually drive a catalog change.
#
# Scope (each step answers a specific "should we change something?" question):
#   1. verify-before-completion @ N=50 with the new executable-prompt YAML
#      → does the rubric rework flip the -0.40 judge artifact?
#
# Skipped (already known / non-actionable):
#   - caveman-ultra (just ran at N=50, -86.4% confirmed)
#   - lean-execution (-56% already strong)
#   - wiki-memory (token-positive overall is a known trade-off)
#   - triage (regex fast-path is deterministic; 100% holds where it matters)
#   - 4 combos (different "stacking" claim, no N-tightening asked for)
#   - runner_semdiff / _filter / _handoff (fixture-based, N doesn't scale)
#
# Wall clock: dominated by the MiMo A/B runners.
#
# Usage:
#   nohup bash eval/run_actionable_batch.sh > /tmp/te-eval-actionable.log 2>&1 &
set -uo pipefail
cd "$(dirname "$0")/.."

# shellcheck disable=SC1091
. .brainer/secrets.env
export MIMO_API_KEY
if [ -z "${MIMO_API_KEY:-}" ]; then
  echo "FATAL: MIMO_API_KEY not set after sourcing .brainer/secrets.env" >&2
  exit 2
fi

N="${N:-50}"
echo "==== Brainer actionable batch, N=$N ===="
date

run_step() {
  local label="$1"; shift
  echo
  echo "==== $label ===="
  echo "+ $*"
  if "$@"; then echo "[OK] $label"; else echo "[FAIL] $label (continuing)" >&2; fi
}

run_step "verify-before-completion (executable prompts, N=$N)" \
  python3 eval/runner.py --task eval/tasks/verify-before-completion.yaml \
    --n "$N" --backend mimo --model mimo-v2-flash

# Judge the new A/B result files (skip already-judged).
run_step "judge: verify-before-completion" \
  python3 eval/judge.py eval/results/verify-before-completion.json \
    --model mimo-v2-flash --backend mimo

# Refresh docs (cheap; runs over all results, only the deltas matter).
run_step "static_cost" bash -c \
  "python3 eval/static_cost.py --json > eval/results/static_cost.json"
run_step "populate EVAL.md per skill" python3 eval/populate_eval_md.py

echo
echo "==== actionable batch complete ===="
date
