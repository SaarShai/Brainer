#!/usr/bin/env bash
# agents-triage installer. Project-local only.

set -euo pipefail

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then
    DRY_RUN=1
    shift
fi
if [ "${1:-}" != "" ] && [ "${1:-}" != "--project" ]; then
    echo "agents-triage installs project-locally only. Use --project, --dry-run, or no flag." >&2
    exit 2
fi

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
SKILL_SRC="$REPO/projects/agents-triage"

SKILL_DIR="$REPO/.claude/skills"
AGENT_DIR="$REPO/.claude/agents"
SETTINGS="$REPO/.claude/settings.json"
HOOK_CMD="bash $SKILL_SRC/hook.sh"
AGENTS=(wiki-note quick-fix local-ollama research-lite kaggle-feeder)

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
rules = hooks.setdefault("UserPromptSubmit", [])
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
    echo "[1/3] dry-run: would symlink skill → $SKILL_DIR/agents-triage"
    echo "[2/3] dry-run: would copy agent definitions → $AGENT_DIR/"
    printf '  - %s\n' "${AGENTS[@]}"
    echo "[3/3] dry-run: would update $SETTINGS with UserPromptSubmit -> $HOOK_CMD"
    exit 0
fi

mkdir -p "$SKILL_DIR" "$AGENT_DIR"

echo "[1/3] symlinking skill → $SKILL_DIR/agents-triage"
ln -sfn "$SKILL_SRC" "$SKILL_DIR/agents-triage"

echo "[2/3] copying agent definitions → $AGENT_DIR/"
for a in "${AGENTS[@]}"; do
    cp -f "$SKILL_SRC/agents/$a.md" "$AGENT_DIR/$a.md"
done

chmod +x "$SKILL_SRC/hook.sh" "$SKILL_SRC/classify.py"

echo "[3/3] hook wiring ($SETTINGS)"
merge_settings

cat <<EOF
Installed agents-triage into repo-local .claude.

Override per-prompt: include "NO TRIAGE" anywhere in your message.

Env:
  AGENTS_TRIAGE_NO_OLLAMA=1     disable Ollama fallback (regex-only)
  AGENTS_TRIAGE_LOG=/path/log    log every classification

Test the classifier:
  python3 $SKILL_SRC/classify.py "add a note to the wiki about X"
EOF
