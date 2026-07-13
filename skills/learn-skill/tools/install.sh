#!/usr/bin/env bash
# learn-skill installer — wires the UNATTENDED half of the self-improvement loop:
#   SessionEnd   -> telemetry scan   (append-only usage log)
#   SessionStart -> promote/demote/stale nudge (read-only; surfaces, never mutates)
# The skill-MUTATING steps (promote / demote / staleness --apply) stay agent-run by
# design (loop-engineering: an unattended write path needs a gate — so the unattended
# path here is append/read-only only). The root installer runs this by default.
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
# Run-time-expanded project root, not cwd-relative './' (which breaks on cwd drift).
END_CMD='bash "${CLAUDE_PROJECT_DIR:-$PWD}/.claude/skills/learn-skill/tools/hook_session_end.sh"'
START_CMD='bash "${CLAUDE_PROJECT_DIR:-$PWD}/.claude/skills/learn-skill/tools/hook_session_start.sh"'

merge_settings() {
  python3 "$TOOLS_DIR/hook_merge.py" settings "$SETTINGS" "$END_CMD" "$START_CMD"
}

# Codex parity: Codex has no SessionStart/SessionEnd, but Stop (end of turn) and
# UserPromptSubmit map cleanly. Stop -> scan (idempotent), UserPromptSubmit -> nudge.
CODEX_HOOKS="$REPO/.codex/hooks.json"
# Codex Stop is per-turn → defer-trailing scan (hook_codex_stop.sh), not the finalize
# scan Claude SessionEnd uses, so hit/abort isn't judged before the reply lands.
# Same portable run-time-expanded form (.codex/hooks.json is committed, so no machine path).
CODEX_END_CMD='bash "${CLAUDE_PROJECT_DIR:-$PWD}/.codex/skills/learn-skill/tools/hook_codex_stop.sh"'
CODEX_START_CMD='bash "${CLAUDE_PROJECT_DIR:-$PWD}/.codex/skills/learn-skill/tools/hook_session_start.sh"'

# Host-scoping: root install.sh exports BRAINER_HOSTS with the requested host
# list before running per-skill installers, so a single-host run doesn't also
# merge another host's inert hook config. Unset/empty (a direct
# `bash skills/learn-skill/tools/install.sh` run) means all hosts — unchanged
# back-compat behavior.
host_enabled() { [ -z "${BRAINER_HOSTS:-}" ] && return 0; case ",$BRAINER_HOSTS," in *",$1,"*) return 0;; esac; return 1; }

merge_codex() {
  python3 "$TOOLS_DIR/hook_merge.py" codex "$CODEX_HOOKS" "$CODEX_END_CMD" "$CODEX_START_CMD"
}

if [ "$DRY_RUN" = "1" ]; then
  echo "dry-run: would symlink $SKILL_SRC → $SKILL_DIR/learn-skill"
  if host_enabled claude-code; then
    echo "dry-run: would add SessionEnd   * -> $END_CMD"
    echo "dry-run: would add SessionStart * -> $START_CMD"
  fi
  { [ -e "$REPO/.codex/skills/learn-skill" ] && host_enabled codex; } && { echo "dry-run: would add Codex Stop -> $CODEX_END_CMD"; echo "dry-run: would add Codex UserPromptSubmit -> $CODEX_START_CMD"; }
  exit 0
fi

mkdir -p "$SKILL_DIR"
chmod +x "$TOOLS_DIR"/hook_session_end.sh "$TOOLS_DIR"/hook_session_start.sh "$TOOLS_DIR"/hooks.py 2>/dev/null || true
REL_SRC=$(python3 -c "import os,sys;print(os.path.relpath(sys.argv[1],sys.argv[2]))" "$SKILL_SRC" "$SKILL_DIR" 2>/dev/null || echo "$SKILL_SRC")
ln -sfn "$REL_SRC" "$SKILL_DIR/learn-skill"
if host_enabled claude-code; then
  merge_settings
  echo "Installed learn-skill unattended hooks into repo-local .claude."
  echo "  SessionEnd   -> telemetry scan (append-only)"
  echo "  SessionStart -> promote/demote/stale nudge (read-only)"
fi

# Wire Codex too, if this repo has a .codex/skills/learn-skill symlink (from ./install.sh)
# AND codex is one of the requested hosts.
if [ -e "$REPO/.codex/skills/learn-skill" ] && host_enabled codex; then
  chmod +x "$TOOLS_DIR"/hook_session_end.sh "$TOOLS_DIR"/hook_session_start.sh "$TOOLS_DIR"/hook_codex_stop.sh 2>/dev/null || true
  merge_codex
  echo "Wired Codex hooks (.codex/hooks.json):"
  echo "  Stop             -> telemetry scan (Codex has no SessionEnd)"
  echo "  UserPromptSubmit -> promote/demote/stale nudge (Codex has no SessionStart)"
fi
echo
echo "Tune via env: LEARN_SKILL_PROMOTE_MIN=3  LEARN_SKILL_DEMOTE_MIN=3"
echo "Skill-mutating steps stay manual: learn.py promote|demote|staleness --apply"
