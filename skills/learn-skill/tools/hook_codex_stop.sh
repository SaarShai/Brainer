#!/usr/bin/env bash
# Codex Stop hook (per-turn) for learn-skill. Codex has no SessionEnd, so this runs the
# telemetry scan in DEFER-TRAILING mode: the just-fired invocation (whose reply doesn't
# exist yet) is skipped and picked up next turn, so hit/abort isn't judged prematurely.
# APPEND-only; never mutates a skill. Always exit 0.
set -uo pipefail
TOOLS_DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "$TOOLS_DIR/hooks.py" turn-scan || true
exit 0
