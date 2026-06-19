#!/usr/bin/env bash
# Optional brainer-audit hook installer. Hooks are inert until marker files exist.
set -euo pipefail

TOOLS_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$TOOLS_DIR/../../.." && pwd)"
CLAUDE_SETTINGS="$REPO/.claude/settings.json"
CODEX_HOOKS="$REPO/.codex/hooks.json"
CLAUDE_CMD="python3 ./.claude/skills/brainer-audit/tools/hook.py --host claude"
CODEX_CMD="python3 ./.codex/skills/brainer-audit/tools/hook.py --host codex"

python3 - "$CLAUDE_SETTINGS" "$CODEX_HOOKS" "$CLAUDE_CMD" "$CODEX_CMD" <<'PY'
import json
import sys
from pathlib import Path

claude_path = Path(sys.argv[1])
codex_path = Path(sys.argv[2])
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
    for rule in rules:
        existing = rule.setdefault("hooks", [])
        if any(item.get("type") == "command" and item.get("command") == cmd for item in existing):
            return
    rules.append({"matcher": "*", "hooks": [{"type": "command", "command": cmd}]})

def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

claude = read_json(claude_path)
for event in events:
    add_hook(claude, event, claude_cmd)
write(claude_path, claude)

codex = read_json(codex_path)
for event in events:
    add_hook(codex, event, codex_cmd)
write(codex_path, codex)
PY

echo "Installed optional brainer-audit hooks for Claude and Codex."
echo "Hooks write only while .brainer/brainer-audit/current.json or .brainer/task-retrospective/current.json exists."
