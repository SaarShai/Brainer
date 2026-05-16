#!/usr/bin/env bash
set -euo pipefail

ROOT="${TOKEN_ECONOMY_ROOT:-$(pwd)}"
RAW="$(cat)"
PROMPT="$(printf '%s' "$RAW" | python3 -c '
import json, sys
raw = sys.stdin.read()
try:
    data = json.loads(raw)
    if isinstance(data, dict):
        print(data.get("prompt") or data.get("user_prompt") or data.get("message") or raw)
    else:
        print(raw)
except Exception:
    print(raw)
')"

if [[ "$PROMPT" =~ ^[[:space:]]*/(pa|btw)([[:space:]]|:|$) ]]; then
  "$ROOT/te" pa --directive "$PROMPT"
  exit 0
else
  COST_OUT=""
  if [ "${TOKEN_ECONOMY_COST_PREFLIGHT:-1}" != "0" ]; then
    COST_OUT="$(printf '%s' "$PROMPT" | PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 -c 'import sys; from token_economy.cost import preflight_nudge; print(preflight_nudge(sys.stdin.read()), end="")')"
    if [ -n "$COST_OUT" ]; then
      printf '%s' "$COST_OUT"
    fi
  fi
fi

if [ "${TOKEN_ECONOMY_CLASSIFY_ALL:-0}" = "1" ]; then
  "$ROOT/te" delegate classify "$PROMPT"
fi
