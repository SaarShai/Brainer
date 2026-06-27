#!/usr/bin/env bash
# OPT-IN installer for the index-first PreToolUse augment hook.
#
# This skill is opt-in (auto-install:false). It is NOT wired into the repo's
# default ./install.sh — you run THIS script by hand when you want grep/glob
# calls augmented with index hits. Merges a single PreToolUse entry into
# .claude/settings.json, then leaves everything else untouched.
#
# The settings-merge guard (never overwrite a corrupt/truncated settings.json)
# is copied verbatim-in-spirit from skills/context-keeper/tools/install.sh.
set -euo pipefail

DRY_RUN=0
UNINSTALL=0
while [ "$#" -gt 0 ]; do
  case "${1:-}" in
    --dry-run) DRY_RUN=1 ;;
    --uninstall) UNINSTALL=1 ;;
    --project) ;;  # accepted for parity with other Brainer installers (project-local only)
    *) echo "index-first installer: unknown flag '$1'. Use --dry-run, --uninstall, or no flag." >&2; exit 2 ;;
  esac
  shift || true
done

TOOLS_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$TOOLS_DIR/../../.." && pwd)"
CLAUDE_DIR="$REPO/.claude"
SETTINGS="$CLAUDE_DIR/settings.json"
# Relative command so the entry is portable across checkouts.
HOOK_CMD="python3 ./.claude/skills/index-first/tools/augment.py"

if [ "$DRY_RUN" = "1" ]; then
  if [ "$UNINSTALL" = "1" ]; then
    echo "dry-run: would REMOVE PreToolUse -> $HOOK_CMD from $SETTINGS"
  else
    echo "dry-run: would add PreToolUse -> $HOOK_CMD to $SETTINGS"
  fi
  exit 0
fi

python3 - "$SETTINGS" "$HOOK_CMD" "$UNINSTALL" <<'PY'
import json
import sys
from pathlib import Path

settings_path = Path(sys.argv[1])
hook_cmd = sys.argv[2]
uninstall = sys.argv[3] == "1"
settings_path.parent.mkdir(parents=True, exist_ok=True)
if settings_path.exists():
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        # NEVER write back over a corrupt/truncated settings.json — that
        # silently erases the user's other hooks/permissions (guard copied from
        # context-keeper/tools/install.sh). Abort; the human fixes the file.
        sys.stderr.write(
            f"ABORT: {settings_path} exists but is not valid JSON ({e}).\n"
            f"Fix or remove it, then re-run this installer.\n")
        sys.exit(1)
else:
    data = {}

hooks = data.setdefault("hooks", {})
rules = hooks.setdefault("PreToolUse", [])

# Matcher Grep|Glob so the host only fires the hook on the tools we augment.
MATCHER = "Grep|Glob"


def find_rule():
    for rule in rules:
        if rule.get("matcher") == MATCHER:
            return rule
    return None


if uninstall:
    for rule in list(rules):
        if rule.get("matcher") != MATCHER:
            continue
        rule["hooks"] = [
            i for i in rule.get("hooks", [])
            if not (i.get("type") == "command" and i.get("command") == hook_cmd)
        ]
        if not rule["hooks"]:
            rules.remove(rule)
    msg = f"Removed index-first PreToolUse hook from {settings_path}."
else:
    rule = find_rule()
    if rule is None:
        rule = {"matcher": MATCHER, "hooks": []}
        rules.append(rule)
    existing = rule.setdefault("hooks", [])
    if any(i.get("type") == "command" and i.get("command") == hook_cmd for i in existing):
        msg = f"index-first PreToolUse hook already present in {settings_path}."
    else:
        existing.append({"type": "command", "command": hook_cmd})
        msg = f"Installed index-first PreToolUse hook into {settings_path}."

settings_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
sys.stderr.write(msg + "\n")
PY

chmod +x "$TOOLS_DIR/augment.py"
echo "index-first augment hook: opt-in install complete (run with --uninstall to remove)."
