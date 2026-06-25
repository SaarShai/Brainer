#!/usr/bin/env bash
# SessionStart hook entry for learn-skill. Thin shim around hooks.py session-start.
# READ-ONLY nudge (promote-ready / demote / stale); never mutates a skill. Always exit 0.
set -uo pipefail
TOOLS_DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "$TOOLS_DIR/hooks.py" session-start || true
exit 0
