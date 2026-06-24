#!/usr/bin/env bash
# SessionEnd hook entry for learn-skill. Thin shim around hooks.py session-end.
# APPEND-only (telemetry scan); never mutates a skill. Always exit 0.
set -uo pipefail
TOOLS_DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "$TOOLS_DIR/hooks.py" session-end || true
exit 0
