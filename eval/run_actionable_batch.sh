#!/usr/bin/env bash
# Run only the eval steps whose results would actually drive a catalog change.
#
# Scope (each step answers a specific "should we change something?" question):
#   1. verify-before-completion @ N=50 with the new executable-prompt YAML
#      → does the rubric rework flip the -0.40 judge artifact?
#   2. plan-first-execute @ N=50
#      → is the -20% claim real at scale? if not, reconsider keeping it.
#   3. compress-context QUALITY @ N=50 on SQuAD with MiMo judge
#      → does compressed answer quality survive? drives rate=0.5 vs 0.7.
#
# Skipped (already known / non-actionable):
#   - caveman-ultra (just ran at N=50, -86.4% confirmed)
#   - lean-execution (-56% already strong)
#   - wiki-memory (token-positive overall is a known trade-off)
#   - triage (regex fast-path is deterministic; 100% holds where it matters)
#   - 4 combos (different "stacking" claim, no N-tightening asked for)
#   - runner_compress mechanical (deterministic at fixed rate)
#   - runner_semdiff / _filter / _handoff (fixture-based, N doesn't scale)
#
# Wall clock: ~3.5 h (LLMLingua compression in compress_quality dominates).
#
# Usage:
#   nohup bash eval/run_actionable_batch.sh > /tmp/te-eval-actionable.log 2>&1 &
set -uo pipefail
cd "$(dirname "$0")/.."

# shellcheck disable=SC1091
. .token-economy/secrets.env
export MIMO_API_KEY
if [ -z "${MIMO_API_KEY:-}" ]; then
  echo "FATAL: MIMO_API_KEY not set after sourcing .token-economy/secrets.env" >&2
  exit 2
fi

N="${N:-50}"
echo "==== Token Economy actionable batch, N=$N ===="
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

run_step "plan-first-execute (N=$N)" \
  python3 eval/runner.py --task eval/tasks/plan-first-execute.yaml \
    --n "$N" --backend mimo --model mimo-v2-flash

run_step "compress-context quality (SQuAD A/B, N=$N, MiMo judge)" \
  python3 eval/runner_compress_quality.py --n "$N" --rate 0.5 \
    --target mimo-v2-flash --judge mimo-v2-flash

# Judge the new A/B result files (skip already-judged).
run_step "judge: verify-before-completion" \
  python3 eval/judge.py eval/results/verify-before-completion.json \
    --model mimo-v2-flash --backend mimo

run_step "judge: plan-first-execute" \
  python3 eval/judge.py eval/results/plan-first-execute.json \
    --model mimo-v2-flash --backend mimo

# Refresh docs (cheap; runs over all results, only the deltas matter).
run_step "static_cost" bash -c \
  "python3 eval/static_cost.py --json > eval/results/static_cost.json"
run_step "populate EVAL.md per skill" python3 eval/populate_eval_md.py
run_step "rebuild SKILLS_INDEX_RATED.md" python3 eval/build_rated_index.py

echo
echo "==== actionable batch complete ===="
date
