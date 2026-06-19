#!/usr/bin/env bash
# SessionEnd hook entry. Thin shim around archive.py.
# Always exit 0 — a SessionEnd hook failure must not disrupt the host.
set -uo pipefail

TOOLS_DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "$TOOLS_DIR/archive.py" || true
exit 0
