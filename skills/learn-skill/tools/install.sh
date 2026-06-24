#!/usr/bin/env bash
# learn-skill installer — wires the UNATTENDED half of the self-improvement loop:
#   SessionEnd   -> telemetry scan   (append-only usage log)
#   SessionStart -> promote/demote/stale nudge (read-only; surfaces, never mutates)
# The skill-MUTATING steps (promote / demote / staleness --apply) stay agent-run by
# design (loop-engineering: an unattended write path needs a gate — so the unattended
# path here is append/read-only only). learn-skill ships auto-install:false, so this
# runs only when invoked explicitly: bash skills/learn-skill/tools/install.sh
set -euo pipefail

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then DRY_RUN=1; shift; fi
if [ "${1:-}" != "" ] && [ "${1:-}" != "--project" ]; then
  echo "learn-skill installs project-locally only. Use --project, --dry-run, or no flag." >&2
  exit 2
fi

TOOLS_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_SRC="$(cd "$TOOLS_DIR/.." && pwd)"
REPO="$(cd "$TOOLS_DIR/../../.." && pwd)"
CLAUDE_DIR="$REPO/.claude"
SKILL_DIR="$CLAUDE_DIR/skills"
SETTINGS="$CLAUDE_DIR/settings.json"
END_CMD="bash ./.claude/skills/learn-skill/tools/hook_session_end.sh"
START_CMD="bash ./.claude/skills/learn-skill/tools/hook_session_start.sh"

merge_settings() {
  python3 - "$SETTINGS" "$END_CMD" "$START_CMD" <<'PY'
import json, sys
from pathlib import Path
settings_path = Path(sys.argv[1]); end_cmd, start_cmd = sys.argv[2], sys.argv[3]
settings_path.parent.mkdir(parents=True, exist_ok=True)
if settings_path.exists():
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        # NEVER overwrite a corrupt settings.json — that would silently erase the
        # user's other hooks/permissions. Abort; the human fixes it.
        sys.stderr.write(f"ABORT: {settings_path} is not valid JSON ({e}).\n"
                         f"Fix or remove it, then re-run this installer.\n")
        sys.exit(1)
else:
    data = {}
hooks = data.setdefault("hooks", {})
for event, cmd in (("SessionEnd", end_cmd), ("SessionStart", start_cmd)):
    rules = hooks.setdefault(event, [])
    for rule in rules:
        if rule.get("matcher") not in (None, "*"):
            continue
        if any(h.get("type") == "command" and h.get("command") == cmd
               for h in rule.get("hooks", [])):
            break
    else:
        rules.append({"matcher": "*", "hooks": [{"type": "command", "command": cmd}]})
settings_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

if [ "$DRY_RUN" = "1" ]; then
  echo "dry-run: would symlink $SKILL_SRC → $SKILL_DIR/learn-skill"
  echo "dry-run: would add SessionEnd   * -> $END_CMD"
  echo "dry-run: would add SessionStart * -> $START_CMD"
  exit 0
fi

mkdir -p "$SKILL_DIR"
chmod +x "$TOOLS_DIR"/hook_session_end.sh "$TOOLS_DIR"/hook_session_start.sh "$TOOLS_DIR"/hooks.py 2>/dev/null || true
REL_SRC=$(python3 -c "import os,sys;print(os.path.relpath(sys.argv[1],sys.argv[2]))" "$SKILL_SRC" "$SKILL_DIR" 2>/dev/null || echo "$SKILL_SRC")
ln -sfn "$REL_SRC" "$SKILL_DIR/learn-skill"
merge_settings

echo "Installed learn-skill unattended hooks into repo-local .claude."
echo "  SessionEnd   -> telemetry scan (append-only)"
echo "  SessionStart -> promote/demote/stale nudge (read-only)"
echo
echo "Tune via env: LEARN_SKILL_PROMOTE_MIN=3  LEARN_SKILL_DEMOTE_MIN=3"
echo "Skill-mutating steps stay manual: learn.py promote|demote|staleness --apply"
