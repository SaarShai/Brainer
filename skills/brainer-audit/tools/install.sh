#!/usr/bin/env bash
# Optional brainer-audit hook installer. Hooks are inert until marker files exist.
set -euo pipefail

TOOLS_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$TOOLS_DIR/../../.." && pwd)"
CLAUDE_SETTINGS="$REPO/.claude/settings.json"
CODEX_HOOKS="$REPO/.codex/hooks.json"
# Run-time-expanded project root (CLAUDE_PROJECT_DIR is injected by Claude Code =
# repo root), NOT a cwd-relative './'. The latter breaks the moment the shell cwd
# drifts into a subdir, and for a PreToolUse + matcher:'*' hook that launch failure
# (python3 can't open the file -> exit 2) BLOCKS every tool. The :-$PWD fallback
# keeps a host without the var working from the repo root. (Codex doesn't set the
# var, so it falls back to $PWD; .codex/hooks.json is committed/portable so we keep
# the same form rather than baking a machine-specific absolute path.)
# Path is derived from where THIS installer actually lives relative to the
# repo root — NOT a hard-coded .claude/skills/... path. Incident 2026-07-07
# (screenery-lean, twice): the wired .claude/skills/brainer-audit symlink
# either never existed or was wiped by the repo's own install.sh symlink
# rebuild; a missing hook file exits 2, and exit 2 on UserPromptSubmit/
# PreToolUse BLOCKS every prompt/tool → all sessions unresponsive. The real
# vendored tree (skills/... or wherever this file sits) survives rebuilds.
REL="${TOOLS_DIR#"$REPO"/}"   # e.g. skills/brainer-audit/tools
CLAUDE_CMD='python3 "${CLAUDE_PROJECT_DIR:-$PWD}/'"$REL"'/hook.py" --host claude'
CODEX_CMD='python3 "${CLAUDE_PROJECT_DIR:-$PWD}/'"$REL"'/hook.py" --host codex'

# Host-scoping: root install.sh exports BRAINER_HOSTS with the requested host
# list before running per-skill installers, so a single-host run doesn't also
# merge another host's inert hook config. Unset/empty (a direct
# `bash skills/brainer-audit/tools/install.sh` run) means all hosts —
# unchanged back-compat behavior. An empty path arg tells the python side to
# skip that host entirely.
host_enabled() { [ -z "${BRAINER_HOSTS:-}" ] && return 0; case ",$BRAINER_HOSTS," in *",$1,"*) return 0;; esac; return 1; }

CLAUDE_ARG="$CLAUDE_SETTINGS"; host_enabled claude-code || CLAUDE_ARG=""
CODEX_ARG="$CODEX_HOOKS"; host_enabled codex || CODEX_ARG=""

python3 - "$CLAUDE_ARG" "$CODEX_ARG" "$CLAUDE_CMD" "$CODEX_CMD" <<'PY'
import json
import sys
from pathlib import Path

claude_path = Path(sys.argv[1]) if sys.argv[1] else None
codex_path = Path(sys.argv[2]) if sys.argv[2] else None
claude_cmd = sys.argv[3]
codex_cmd = sys.argv[4]
events = ["UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop", "PreCompact", "PostCompact"]

def read_json(path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))

def add_hook(data, event, command):
    hooks = data.setdefault("hooks", {})
    rules = hooks.setdefault(event, [])
    cmd = f"{command} --event {event}"
    # Migrate: drop any stale brainer-audit wiring whose command differs from
    # the freshly derived path (e.g. a dead .claude/skills/... path from an
    # older install — the 2026-07-07 session-wedge incident).
    for rule in rules:
        existing = rule.setdefault("hooks", [])
        existing[:] = [
            item for item in existing
            if not (item.get("type") == "command"
                    and "brainer-audit/tools/hook.py" in str(item.get("command", ""))
                    and item.get("command") != cmd)
        ]
    rules[:] = [r for r in rules if r.get("hooks")]
    for rule in rules:
        if any(item.get("type") == "command" and item.get("command") == cmd for item in rule.get("hooks", [])):
            return
    rules.append({"matcher": "*", "hooks": [{"type": "command", "command": cmd}]})

def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

if claude_path is not None:
    claude = read_json(claude_path)
    for event in events:
        add_hook(claude, event, claude_cmd)
    write(claude_path, claude)

if codex_path is not None:
    codex = read_json(codex_path)
    for event in events:
        add_hook(codex, event, codex_cmd)
    write(codex_path, codex)
PY

# --- post-wire self-test (LEARNING_CONTRACT §4: a wired-but-dead hook is ---
# worse than none — exit 2 on UserPromptSubmit/PreToolUse blocks the session).
# Run the exact wired command once; any failure is a LOUD install failure.
if [ -n "$CLAUDE_ARG" ]; then
  for ev in UserPromptSubmit PreToolUse Stop; do
    if ! echo '{"session_id":"install-selftest","hook_event_name":"'"$ev"'"}' \
        | CLAUDE_PROJECT_DIR="$REPO" bash -c "$CLAUDE_CMD --event $ev" >/dev/null 2>&1; then
      echo "FATAL: wired brainer-audit hook FAILED self-test for $ev (command: $CLAUDE_CMD --event $ev)" >&2
      echo "       a failing UserPromptSubmit/PreToolUse hook BLOCKS every session prompt — fix before use" >&2
      exit 1
    fi
  done
  echo "brainer-audit: post-wire self-test OK (hook executes cleanly for UserPromptSubmit/PreToolUse/Stop)."
fi

if [ -n "$CLAUDE_ARG" ] && [ -n "$CODEX_ARG" ]; then
  echo "Installed optional brainer-audit hooks for Claude and Codex."
elif [ -n "$CLAUDE_ARG" ]; then
  echo "Installed optional brainer-audit hooks for Claude."
elif [ -n "$CODEX_ARG" ]; then
  echo "Installed optional brainer-audit hooks for Codex."
else
  echo "brainer-audit: no requested host (BRAINER_HOSTS=$BRAINER_HOSTS) uses hooks — nothing to install."
fi
echo "Hooks write only while .brainer/brainer-audit/current.json or .brainer/task-retrospective/current.json exists."
