#!/bin/bash
# Sweep adversarial_bench over all adversarial_*.json datasets in bench/data/.
# Fails if ANY dataset regresses beyond threshold.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
THRESHOLD=${THRESHOLD:--0.5}
FAIL=0
for f in "$ROOT"/bench/data/adversarial_*.json; do
  name=$(basename "$f" .json)
  echo "=== $name ==="
  python3 "$HERE/adversarial_bench.py" --data "$f" --threshold "$THRESHOLD" || FAIL=1
  echo
done
[ $FAIL -ne 0 ] && { echo "SWEEP FAIL"; exit 1; }
echo "SWEEP OK (all adversarial sets pass)"
