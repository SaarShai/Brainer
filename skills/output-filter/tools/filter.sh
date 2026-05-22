#!/usr/bin/env bash
set -euo pipefail

# Generic output filter with raw-output recovery and savings metrics.

ROOT="${TOKEN_ECONOMY_ROOT:-$(pwd)}"
PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 -m token_economy.output_filter --repo "$ROOT" filter "$@"
