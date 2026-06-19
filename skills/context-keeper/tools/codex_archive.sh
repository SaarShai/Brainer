#!/usr/bin/env bash
# Codex Stop hook entry. Thin shim around codex_archive.py.
# Always exit 0 — a Stop-hook failure must not disrupt the host.
set -uo pipefail

TOOLS_DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "$TOOLS_DIR/codex_archive.py" || true
exit 0
