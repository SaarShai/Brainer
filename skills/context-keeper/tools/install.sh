#!/usr/bin/env bash
set -euo pipefail

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=1
  shift
fi
if [ "${1:-}" != "" ] && [ "${1:-}" != "--project" ]; then
  echo "context-keeper installs project-locally only. Use --project, --dry-run, or no flag." >&2
  exit 2
fi

TOOLS_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_SRC="$(cd "$TOOLS_DIR/.." && pwd)"
REPO="$(cd "$TOOLS_DIR/../../.." && pwd)"
CLAUDE_DIR="$REPO/.claude"
SKILL_DIR="$CLAUDE_DIR/skills"
SETTINGS="$CLAUDE_DIR/settings.json"
CODEX_HOOKS="$REPO/.codex/hooks.json"
HOOK_CMD="bash ./.claude/skills/context-keeper/tools/hook.sh"
ARCHIVE_CMD="bash ./.claude/skills/context-keeper/tools/archive.sh"
# Codex hooks run from the repo root; reuse the .claude skill symlink (no second symlink needed).
CODEX_ARCHIVE_CMD="bash ./.claude/skills/context-keeper/tools/codex_archive.sh"

merge_settings() {
  python3 - "$SETTINGS" "$HOOK_CMD" "$ARCHIVE_CMD" <<'PY'
import json
import sys
from pathlib import Path

settings_path = Path(sys.argv[1])
hook_cmd = sys.argv[2]
archive_cmd = sys.argv[3]
settings_path.parent.mkdir(parents=True, exist_ok=True)
if settings_path.exists():
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        # NEVER write back over a corrupt/truncated settings.json — that
        # silently erases the user's other hooks/permissions (codex review
        # 2026-06-12). Abort; the human fixes or removes the broken file.
        sys.stderr.write(
            f"ABORT: {settings_path} exists but is not valid JSON ({e}).\n"
            f"Fix or remove it, then re-run this installer.\n")
        sys.exit(1)
else:
    data = {}

hooks = data.setdefault("hooks", {})


def ensure(event, cmd):
    # Idempotent: add a {matcher:"*"} command rule for `event` unless present.
    rules = hooks.setdefault(event, [])
    for rule in rules:
        if rule.get("matcher") != "*":
            continue
        existing = rule.get("hooks", [])
        if any(i.get("type") == "command" and i.get("command") == cmd for i in existing):
            return
    rules.append({"matcher": "*", "hooks": [{"type": "command", "command": cmd}]})


ensure("PreCompact", hook_cmd)     # structured state before compaction
ensure("SessionEnd", archive_cmd)  # raw full-session copy into the project

settings_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

merge_codex() {
  python3 - "$CODEX_HOOKS" "$CODEX_ARCHIVE_CMD" <<'PY'
import json
import sys
from pathlib import Path

hooks_path = Path(sys.argv[1])
cmd = sys.argv[2]
hooks_path.parent.mkdir(parents=True, exist_ok=True)
if hooks_path.exists():
    try:
        data = json.loads(hooks_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        # Same guard as .claude/settings.json: never clobber a corrupt file.
        sys.stderr.write(
            f"ABORT: {hooks_path} exists but is not valid JSON ({e}).\n"
            f"Fix or remove it, then re-run this installer.\n")
        sys.exit(1)
else:
    data = {}

hooks = data.setdefault("hooks", {})
rules = hooks.setdefault("Stop", [])
for rule in rules:
    if any(i.get("type") == "command" and i.get("command") == cmd for i in rule.get("hooks", [])):
        break
else:
    rules.append({"hooks": [{"type": "command", "command": cmd}]})

hooks_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

if [ "$DRY_RUN" = "1" ]; then
  echo "dry-run: would symlink $SKILL_SRC → $SKILL_DIR/context-keeper"
  echo "dry-run: would update $SETTINGS with PreCompact -> $HOOK_CMD"
  echo "dry-run: would update $SETTINGS with SessionEnd -> $ARCHIVE_CMD"
  echo "dry-run: would update $CODEX_HOOKS with Stop -> $CODEX_ARCHIVE_CMD"
  exit 0
fi

mkdir -p "$SKILL_DIR"
chmod +x "$TOOLS_DIR/hook.sh" "$TOOLS_DIR/archive.sh" "$TOOLS_DIR/codex_archive.sh"
REL_SRC=$(python3 -c "import os,sys;print(os.path.relpath(sys.argv[1],sys.argv[2]))" "$SKILL_SRC" "$SKILL_DIR" 2>/dev/null || echo "$SKILL_SRC")
ln -sfn "$REL_SRC" "$SKILL_DIR/context-keeper"
merge_settings
merge_codex

echo "Installed context-keeper into repo-local .claude + .codex."
