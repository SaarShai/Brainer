#!/usr/bin/env bash
# loop-breaker installer. Project-local only — wires PreToolUse hook.
set -euo pipefail

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=1
  shift
fi
if [ "${1:-}" != "" ] && [ "${1:-}" != "--project" ]; then
  echo "loop-breaker installs project-locally only. Use --project, --dry-run, or no flag." >&2
  exit 2
fi

TOOLS_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_SRC="$(cd "$TOOLS_DIR/.." && pwd)"
REPO="$(cd "$TOOLS_DIR/../../.." && pwd)"
CLAUDE_DIR="$REPO/.claude"
SKILL_DIR="$CLAUDE_DIR/skills"
SETTINGS="$CLAUDE_DIR/settings.json"
HOOK_CMD="bash ./.claude/skills/loop-breaker/tools/hook.sh"

merge_settings() {
  python3 - "$SETTINGS" "$HOOK_CMD" <<'PY'
import json
import sys
from pathlib import Path

settings_path = Path(sys.argv[1])
hook_cmd = sys.argv[2]
settings_path.parent.mkdir(parents=True, exist_ok=True)
if settings_path.exists():
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        data = {}
else:
    data = {}

hooks = data.setdefault("hooks", {})
rules = hooks.setdefault("PreToolUse", [])
target = {"matcher": "*", "hooks": [{"type": "command", "command": hook_cmd}]}
for rule in rules:
    if rule.get("matcher") != "*":
        continue
    existing = rule.get("hooks", [])
    if any(item.get("type") == "command" and item.get("command") == hook_cmd for item in existing):
        break
else:
    rules.append(target)

settings_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

if [ "$DRY_RUN" = "1" ]; then
  echo "dry-run: would symlink $SKILL_SRC → $SKILL_DIR/loop-breaker"
  echo "dry-run: would update $SETTINGS with PreToolUse * -> $HOOK_CMD"
  exit 0
fi

mkdir -p "$SKILL_DIR"
chmod +x "$TOOLS_DIR/hook.sh" "$TOOLS_DIR/hook.py"
ln -sfn "$SKILL_SRC" "$SKILL_DIR/loop-breaker"
merge_settings

echo "Installed loop-breaker into repo-local .claude."
echo
echo "Tune via env vars:"
echo "  LOOP_BREAKER_THRESHOLD=5          # consecutive-identical count that warns"
echo "  LOOP_BREAKER_HARD_BLOCK=1         # also deny further identical calls past threshold"
echo "  LOOP_BREAKER_ALLOWLIST_TOOLS=Read,LS  # never trigger on these tools"
