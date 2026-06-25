#!/usr/bin/env bash
# compliance-canary installer. Project-local only — wires UserPromptSubmit hook.
set -euo pipefail

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=1
  shift
fi
if [ "${1:-}" != "" ] && [ "${1:-}" != "--project" ]; then
  echo "compliance-canary installs project-locally only. Use --project, --dry-run, or no flag." >&2
  exit 2
fi

TOOLS_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_SRC="$(cd "$TOOLS_DIR/.." && pwd)"
REPO="$(cd "$TOOLS_DIR/../../.." && pwd)"
CLAUDE_DIR="$REPO/.claude"
SKILL_DIR="$CLAUDE_DIR/skills"
SETTINGS="$CLAUDE_DIR/settings.json"
HOOK_CMD="bash ./.claude/skills/compliance-canary/tools/hook.sh"

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

# Codex parity: Codex has no SessionStart but fires UserPromptSubmit (with the same
# stdin payload incl. transcript_path), so the drift watcher + nomination nudge run
# there too. Codex reads the transcript via the cross-host normalizer (skills/_shared).
CODEX_HOOKS="$REPO/.codex/hooks.json"
CODEX_HOOK_CMD="bash ./.codex/skills/compliance-canary/tools/hook.sh"

merge_codex() {
  python3 - "$CODEX_HOOKS" "$CODEX_HOOK_CMD" <<'PY'
import json, sys
from pathlib import Path
hp = Path(sys.argv[1]); cmd = sys.argv[2]
if hp.exists():
    try:
        data = json.loads(hp.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.stderr.write(f"ABORT: {hp} is not valid JSON ({e}). Fix or remove it.\n"); sys.exit(1)
else:
    data = {}
hooks = data.setdefault("hooks", {})
rules = hooks.setdefault("UserPromptSubmit", [])
# Prune any stale compliance-canary command (path change) so re-install converges to
# one; keep every non-canary hook untouched.
for rule in rules:
    rule["hooks"] = [h for h in rule.get("hooks", [])
                     if not ("compliance-canary" in h.get("command", "") and h.get("command") != cmd)]
rules[:] = [r for r in rules if r.get("hooks") or r.get("matcher") not in (None, "*")]
for rule in rules:
    if rule.get("matcher") not in (None, "*"):
        continue
    if any(h.get("type") == "command" and h.get("command") == cmd for h in rule.get("hooks", [])):
        break
else:
    rules.append({"matcher": "*", "hooks": [{"type": "command", "command": cmd}]})
hp.parent.mkdir(parents=True, exist_ok=True)
hp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

if [ "$DRY_RUN" = "1" ]; then
  echo "dry-run: would symlink $SKILL_SRC → $SKILL_DIR/compliance-canary"
  echo "dry-run: would update $SETTINGS with UserPromptSubmit * -> $HOOK_CMD"
  [ -e "$REPO/.codex/skills/compliance-canary" ] && echo "dry-run: would add Codex UserPromptSubmit -> $CODEX_HOOK_CMD"
  exit 0
fi

mkdir -p "$SKILL_DIR"
chmod +x "$TOOLS_DIR/hook.sh" "$TOOLS_DIR/hook.py" "$TOOLS_DIR/measure.py" 2>/dev/null || true
REL_SRC=$(python3 -c "import os,sys;print(os.path.relpath(sys.argv[1],sys.argv[2]))" "$SKILL_SRC" "$SKILL_DIR" 2>/dev/null || echo "$SKILL_SRC")
ln -sfn "$REL_SRC" "$SKILL_DIR/compliance-canary"
merge_settings

echo "Installed compliance-canary into repo-local .claude."
# Wire Codex too, if this repo has a .codex/skills/compliance-canary symlink (from ./install.sh).
if [ -e "$REPO/.codex/skills/compliance-canary" ]; then
  chmod +x "$TOOLS_DIR/hook.sh" 2>/dev/null || true
  merge_codex
  echo "Wired Codex hook (.codex/hooks.json): UserPromptSubmit -> compliance-canary (Codex has no SessionStart)"
fi
echo
echo "Tune via env vars:"
echo "  COMPLIANCE_CANARY_DISABLED=1       # off-switch"
echo "  COMPLIANCE_CANARY_COOLDOWN=3       # suppress same probe within N turns"
echo
echo "Offline analyzer (no install required):"
echo "  python3 skills/compliance-canary/tools/measure.py PATH/TO/transcript.jsonl"
