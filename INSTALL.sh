#!/usr/bin/env bash
# Token Economy skill-set installer.
# Symlinks skills/ into the per-host loader path. Idempotent.
# Usage:
#   ./install.sh                           # all detected hosts
#   ./install.sh --host claude-code        # one host
#   ./install.sh --host claude-code,codex  # comma-separated
#   ./install.sh --dry-run                 # show what would happen
#   SKILLS_DIR=skills.new ./install.sh     # alternate canonical dir (Phase A/B)

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="${SKILLS_DIR:-skills}"
SRC="$REPO_ROOT/$SKILLS_DIR"

HOSTS_REQUESTED=""
DRY_RUN=0

while (( "$#" )); do
  case "$1" in
    --host) HOSTS_REQUESTED="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help)
      grep -E '^# ' "$0" | sed 's/^# //'
      exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ ! -d "$SRC" ]; then
  echo "skills dir not found: $SRC" >&2
  echo "set SKILLS_DIR or run from repo root." >&2
  exit 2
fi

[ -z "$HOSTS_REQUESTED" ] && HOSTS_REQUESTED="claude-code,codex,cursor,gemini"

run() {
  if [ "$DRY_RUN" = "1" ]; then echo "DRY: $*"; else eval "$@"; fi
}

link() {
  local target="$1" linkname="$2"
  if [ -L "$linkname" ] && [ "$(readlink "$linkname")" = "$target" ]; then
    echo "    [skip] $linkname (already linked)"
    return 0
  fi
  if [ -e "$linkname" ] && [ ! -L "$linkname" ]; then
    echo "    [warn] $linkname exists and is not a symlink — leaving it" >&2
    return 0
  fi
  run "ln -sfn '$target' '$linkname'"
  echo "    [link] $linkname → $target"
}

install_claude_code() {
  echo "[claude-code]"
  run "mkdir -p '$REPO_ROOT/.claude/skills'"
  for skill in "$SRC"/*/; do
    name=$(basename "$skill")
    [ "$name" = "_shared" ] && continue
    link "$skill" "$REPO_ROOT/.claude/skills/$name"
  done
}

install_codex() {
  echo "[codex]"
  run "mkdir -p '$REPO_ROOT/.codex/skills'"
  for skill in "$SRC"/*/; do
    name=$(basename "$skill")
    [ "$name" = "_shared" ] && continue
    link "$skill" "$REPO_ROOT/.codex/skills/$name"
  done
}

install_cursor() {
  echo "[cursor]"
  run "mkdir -p '$REPO_ROOT/.cursor/skills' '$REPO_ROOT/.cursor/rules'"
  for skill in "$SRC"/*/; do
    name=$(basename "$skill")
    [ "$name" = "_shared" ] && continue
    link "$skill" "$REPO_ROOT/.cursor/skills/$name"
    local mdc="$REPO_ROOT/.cursor/rules/${name}.mdc"
    if [ "$DRY_RUN" = "1" ]; then
      echo "DRY: write $mdc"
    else
      local desc
      desc=$(grep -m1 '^description:' "$skill/SKILL.md" | sed 's/^description: *//')
      cat > "$mdc" <<MDC
---
description: $desc
globs: ["**/*"]
alwaysApply: false
---

@$SKILLS_DIR/$name/SKILL.md
MDC
      echo "    [write] $mdc"
    fi
  done
}

install_gemini() {
  echo "[gemini]"
  run "mkdir -p '$REPO_ROOT/.gemini/skills'"
  for skill in "$SRC"/*/; do
    name=$(basename "$skill")
    [ "$name" = "_shared" ] && continue
    link "$skill" "$REPO_ROOT/.gemini/skills/$name"
  done
  local settings="$REPO_ROOT/.gemini/settings.json"
  if [ "$DRY_RUN" = "1" ]; then
    echo "DRY: ensure $settings has skills path"
  elif [ ! -f "$settings" ]; then
    cat > "$settings" <<'JSON'
{
  "skills": {
    "dirs": [".gemini/skills"]
  }
}
JSON
    echo "    [write] $settings"
  fi
}

IFS=',' read -ra HOST_LIST <<< "$HOSTS_REQUESTED"
for h in "${HOST_LIST[@]}"; do
  case "$h" in
    claude-code) install_claude_code ;;
    codex)       install_codex ;;
    cursor)      install_cursor ;;
    gemini)      install_gemini ;;
    *) echo "unknown host: $h (claude-code|codex|cursor|gemini)" >&2; exit 2 ;;
  esac
done

for f in CLAUDE.md AGENTS.md GEMINI.md; do
  shim="$REPO_ROOT/$f"
  if [ ! -f "$shim" ] || ! grep -q 'SKILLS_INDEX' "$shim" 2>/dev/null; then
    if [ "$DRY_RUN" = "1" ]; then
      echo "DRY: write root shim $f"
    else
      cat > "$shim" <<EOF
# Token Economy

Skills catalog: see [\`$SKILLS_DIR/SKILLS_INDEX.md\`]($SKILLS_DIR/SKILLS_INDEX.md).

Each skill loads on its own trigger; full bodies are not in the boot context. Run \`./install.sh\` to wire skills into the current host.
EOF
      echo "[root] wrote $shim"
    fi
  fi
done

echo
echo "done. host(s): $HOSTS_REQUESTED"
