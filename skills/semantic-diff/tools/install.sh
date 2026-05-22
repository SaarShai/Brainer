#!/usr/bin/env bash
set -euo pipefail

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=1
  shift
fi
if [ "${1:-}" != "" ] && [ "${1:-}" != "--project" ]; then
  echo "semdiff installs project-locally only. Use --project, --dry-run, or no flag." >&2
  exit 2
fi

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
PLUGIN_DIR="$REPO/projects/semdiff/plugin"
MCP_SERVER="$REPO/projects/semdiff/semdiff_mcp/server.py"

if [ "$DRY_RUN" = "1" ]; then
  cat <<EOF
dry-run: semdiff can be installed as either:
  - Claude plugin: claude plugin install $PLUGIN_DIR
  - MCP server:   claude mcp add semdiff --scope project -- python3 $MCP_SERVER
EOF
  exit 0
fi

if command -v claude >/dev/null 2>&1; then
  if claude plugin install "$PLUGIN_DIR"; then
    echo "Installed semdiff Claude plugin from $PLUGIN_DIR."
    exit 0
  fi
  if claude mcp add semdiff --scope project -- python3 "$MCP_SERVER"; then
    echo "Installed semdiff MCP server for project scope."
    exit 0
  fi
fi

cat <<EOF
Claude CLI not available or install failed.
Manual install options:
  claude plugin install $PLUGIN_DIR
  claude mcp add semdiff --scope project -- python3 $MCP_SERVER
EOF
