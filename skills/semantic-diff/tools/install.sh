#!/usr/bin/env bash
# semantic-diff installer.
#
#   bash install.sh          # DEFAULT: slim CLI runtime only (~9-17M).
#                            #   tree-sitter + 4 grammars, no mcp/cryptography.
#                            #   Wires the `semdiff-cli` launcher used via Bash —
#                            #   works on every host (Claude Code, Codex, Cursor,
#                            #   Gemini). This is the non-optional default path.
#   bash install.sh --mcp    # ALSO install the optional MCP server (adds mcp +
#                            #   cryptography ~24M) and register it with Claude Code.
#
# Best-effort: exits 0 so a parent installer keeps going, BUT prints a loud
# ✗ and a one-line fix command if the CORE runtime can't be made to work — the
# whole point of "non-optional" is that a silent skip never masquerades as success.
set -uo pipefail

WANT_MCP=0
[ "${1:-}" = "--mcp" ] && WANT_MCP=1

TOOLS_DIR="$(cd "$(dirname "$0")" && pwd)"
REQS="$TOOLS_DIR/requirements.txt"
REQS_MCP="$TOOLS_DIR/requirements-mcp.txt"
SERVER="$TOOLS_DIR/semdiff_mcp/server.py"
LAUNCHER="$TOOLS_DIR/semdiff-cli"

find_py() {
  for c in python3.12 python3.11 python3.10 python3.13 python3; do
    if command -v "$c" >/dev/null 2>&1; then
      "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)' 2>/dev/null \
        && { echo "$c"; return 0; }
    fi
  done
  return 1
}

PY="$(find_py || true)"
if [ -z "$PY" ]; then
  echo "[semantic-diff] ✗ need Python >= 3.9; install one then re-run: bash $0" >&2
  exit 0
fi
echo "[semantic-diff] using $PY ($($PY --version 2>&1))"

# Pick which requirements to install (core, or core+mcp).
INSTALL_REQS="$REQS"
[ "$WANT_MCP" = "1" ] && INSTALL_REQS="$REQS_MCP"

VENV="$TOOLS_DIR/.venv"
RUN_PY="$PY"
if "$PY" -m pip install -q -r "$INSTALL_REQS" 2>/dev/null; then
  echo "[semantic-diff] deps installed (system)."
else
  echo "[semantic-diff] system pip blocked (PEP 668?); creating venv at $VENV"
  if [ ! -x "$VENV/bin/python" ]; then
    "$PY" -m venv "$VENV" || { echo "[semantic-diff] ✗ venv create failed" >&2; exit 0; }
  fi
  "$VENV/bin/python" -m ensurepip --upgrade >/dev/null 2>&1 || true
  if ! "$VENV/bin/python" -m pip install -q -r "$INSTALL_REQS"; then
    echo "[semantic-diff] ✗ pip install failed; fix: $VENV/bin/pip install -r $INSTALL_REQS" >&2
    exit 0
  fi
  RUN_PY="$VENV/bin/python"
  echo "[semantic-diff] deps installed (venv)."
fi

# CORE smoke test — the launcher must actually parse a file. Loud on failure.
if PYTHONPATH="$TOOLS_DIR" "$RUN_PY" -c 'from semdiff.core import get_parser; get_parser("python").parse(b"def f():\n  pass\n")' 2>/dev/null; then
  echo "[semantic-diff] ✓ CLI runtime OK — use: $LAUNCHER read <file> --session <id>"
else
  echo "[semantic-diff] ✗ CLI smoke test FAILED — slim grammars not importable." >&2
  echo "    debug: PYTHONPATH=$TOOLS_DIR $RUN_PY -c 'from semdiff.core import get_parser; get_parser(\"python\")'" >&2
  exit 0
fi

if [ "$WANT_MCP" != "1" ]; then
  echo "[semantic-diff] MCP server not installed (optional). Enable with: bash $0 --mcp"
  exit 0
fi

# --mcp: register the native read_file_smart tool with Claude Code.
if command -v claude >/dev/null 2>&1; then
  if claude mcp list 2>/dev/null | grep -q '^semdiff\b'; then
    echo "[semantic-diff] MCP server 'semdiff' already registered."
  elif claude mcp add semdiff --scope user -- "$RUN_PY" "$SERVER" >/dev/null 2>&1; then
    echo "[semantic-diff] ✓ registered MCP server 'semdiff' (user scope, $RUN_PY)."
  else
    echo "[semantic-diff] could not auto-register MCP — run manually:" >&2
    echo "  claude mcp add semdiff --scope user -- $RUN_PY $SERVER" >&2
  fi
else
  echo "[semantic-diff] claude CLI not found; register the MCP server manually later:"
  echo "  claude mcp add semdiff --scope user -- $RUN_PY $SERVER"
fi
