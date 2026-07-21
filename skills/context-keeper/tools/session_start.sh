#!/usr/bin/env bash
# SessionStart hook entry. Thin shim around session_start.py.
# Always exit 0 — a SessionStart hook failure must not disrupt the host.
set -uo pipefail

TOOLS_DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "$TOOLS_DIR/session_start.py" || true
exit 0
