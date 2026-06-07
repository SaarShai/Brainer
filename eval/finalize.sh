#!/usr/bin/env bash
# Finalize an eval pass: re-populate per-skill EVAL.md from the results JSON.
# Run this AFTER eval/runner.py has produced eval/results/<task>.json files.
# Optionally also runs the judge if a backend is reachable.
#
# Usage:
#   bash eval/finalize.sh                # rebuild docs from existing results
#   bash eval/finalize.sh --with-judge   # also runs judge on each result file

set -euo pipefail
cd "$(dirname "$0")/.."

WITH_JUDGE=0
[ "${1:-}" = "--with-judge" ] && WITH_JUDGE=1

if [ "$WITH_JUDGE" = "1" ]; then
  # Load MIMO_API_KEY so judge can use mimo-v2.5-pro (better quality than flash)
  [ -f .brainer/secrets.env ] && . .brainer/secrets.env && export MIMO_API_KEY
  for f in eval/results/*.json; do
    base=$(basename "$f" .json)
    case "$base" in
      static_cost|_smoke*) continue ;;
    esac
    judged="eval/results/${base}.judged.json"
    [ -f "$judged" ] && { echo "skip (already judged): $base"; continue; }
    echo "judging: $base"
    python3 eval/judge.py "$f" --model mimo-v2-flash --backend mimo 2>&1 | tail -3 || true
  done
fi

echo
echo "=== regenerate static cost (in case skills/ changed) ==="
python3 eval/static_cost.py --json > eval/results/static_cost.json
python3 eval/static_cost.py | tail -5

echo
echo "=== repopulate per-skill EVAL.md ==="
python3 eval/populate_eval_md.py
