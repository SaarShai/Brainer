#!/usr/bin/env bash
# Run the full N=50 eval batch locally (every >=20% claim).
#
# Wall clock: ~5-6 hours dominated by MiMo round-trips. compress-context's
# pipeline_v2 also burns local CPU for LLMLingua-2 inference.
#
# Usage:
#   bash eval/run_full_batch.sh                       # foreground
#   nohup bash eval/run_full_batch.sh > /tmp/te-eval-batch.log 2>&1 &
#
# Continues past individual runner failures so one broken backend doesn't
# nuke the rest of the batch.
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
LOG="${LOG:-/tmp/te-eval-batch.log}"
echo "==== Token Economy full batch, N=$N, log=$LOG ===="
date

run_step() {
  local label="$1"; shift
  echo
  echo "==== $label ===="
  echo "+ $*"
  if "$@"; then
    echo "[OK] $label"
  else
    echo "[FAIL] $label (continuing)" >&2
  fi
}

# 1) Generic A/B runner — caveman, lean, plan, verify (prompt-triage handled below)
for t in eval/tasks/*.yaml; do
  case "$(basename "$t")" in
    prompt-triage-corpus.yaml) continue ;;
  esac
  run_step "runner.py $(basename "$t")" \
    python3 eval/runner.py --task "$t" --n "$N" --backend mimo --model mimo-v2-flash
done

# 2) Combos (if any)
if [ -d eval/combos ]; then
  for c in eval/combos/*.yaml; do
    [ -f "$c" ] || continue
    run_step "runner.py combo $(basename "$c")" \
      python3 eval/runner.py --combo "$c" --n "$N" --backend mimo --model mimo-v2-flash
  done
fi

# 3) Specialty runners
run_step "runner_compress.py (mechanical N=$N)" \
  python3 eval/runner_compress.py --max-samples "$N" --rate 0.5

run_step "runner_compress_quality.py (SQuAD A/B N=$N, MiMo judge)" \
  python3 eval/runner_compress_quality.py --n "$N" --rate 0.5 \
    --target mimo-v2-flash --judge mimo-v2-flash

run_step "runner_wiki.py (N=$N)" \
  python3 eval/runner_wiki.py --n "$N" --model mimo-v2-flash

run_step "runner_triage.py (N=$N)" \
  python3 eval/runner_triage.py \
    --corpus eval/tasks/prompt-triage-corpus.yaml \
    --cheap mimo-v2-flash --expensive mimo-v2.5-pro \
    --n "$N" --no-ollama

run_step "runner_semdiff.py" python3 eval/runner_semdiff.py
run_step "runner_filter.py"  python3 eval/runner_filter.py
run_step "runner_handoff.py" python3 eval/runner_handoff.py

# 4) Static cost (always cheap, always re-run)
run_step "static_cost.py" bash -c \
  "python3 eval/static_cost.py --json > eval/results/static_cost.json"

# 5) Judge everything that has a non-judged sibling
run_step "finalize (judge + repopulate docs)" bash eval/finalize.sh --with-judge

echo
echo "==== batch complete ===="
date
