#!/usr/bin/env bash
# Token Economy skill-set installer.
# Symlinks skills/ into the per-host loader path. Idempotent.
# Usage:
#   ./install.sh                           # all detected hosts + graphify
#   ./install.sh --host claude-code        # one host
#   ./install.sh --host claude-code,codex  # comma-separated
#   ./install.sh --no-graphify             # skip graphify auto-install
#   ./install.sh --dry-run                 # show what would happen
#   SKILLS_DIR=skills.new ./install.sh     # alternate canonical dir (Phase A/B)
#
# Graphify is the external code-graph tool paired with `index-first` and
# `wiki-memory` (see skills/index-first/EVAL.md for the measured numbers).
# By default this installer pip-installs it; pass --no-graphify to opt out.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="${SKILLS_DIR:-skills}"
SRC="$REPO_ROOT/$SKILLS_DIR"

HOSTS_REQUESTED=""
DRY_RUN=0
INSTALL_GRAPHIFY=1

while (( "$#" )); do
  case "$1" in
    --host) HOSTS_REQUESTED="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --no-graphify) INSTALL_GRAPHIFY=0; shift ;;
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

# Per-skill tools/install.sh — for skills with Python/MCP deps (best-effort).
echo
echo "[skill-tools] running per-skill installers (Python deps, MCP servers)"
for tool_installer in "$SRC"/*/tools/install.sh; do
  [ -f "$tool_installer" ] || continue
  skill_name="$(basename "$(dirname "$(dirname "$tool_installer")")")"
  echo "  → $skill_name"
  if [ "$DRY_RUN" = "1" ]; then
    echo "    DRY: bash $tool_installer"
  else
    # Tolerate per-skill installer failures (e.g. stale paths in other skills)
    # so a broken sibling never aborts the whole install.
    { bash "$tool_installer" 2>&1 | sed 's/^/    /'; } || echo "    [warn] $skill_name installer exited nonzero — see above"
  fi
done

install_graphify() {
  # Best-effort install of the `graphify` CLI. Paired by default with
  # `index-first` and `wiki-memory` per the recommended stack (see README.md).
  # Skip with --no-graphify.
  #
  # We install from our maintained fork's combined-patches branch rather than
  # PyPI. Published `graphifyy` 0.8.17 ships four bugs that affect our skill
  # flow (affected/benchmark schema crash, cluster-only silent refusal, update
  # leaving stale nodes, explain truncating connections with no expansion
  # flag). Each bug has a single-purpose PR open upstream; until merged, our
  # fork carries all four fixes layered onto v8. See skills/index-first/EVAL.md
  # for the bug list and measured impact. When upstream catches up, flip
  # GRAPHIFY_SOURCE back to the PyPI name `graphifyy` and drop the fork pin.
  local GRAPHIFY_SOURCE="git+https://github.com/SaarShai/graphify@token-economy-patches"
  echo
  echo "[graphify] external code-graph tool (fork pin: SaarShai/graphify@token-economy-patches)"

  if command -v graphify >/dev/null 2>&1; then
    local ver
    ver=$(graphify --help 2>&1 | head -1 || true)
    echo "  [skip] graphify already on PATH ($ver)"
    echo "         to upgrade to the patched fork, run:"
    echo "           pipx install --force '$GRAPHIFY_SOURCE'"
    return 0
  fi

  # Try pipx first — cleanest for a CLI install.
  if command -v pipx >/dev/null 2>&1; then
    echo "  installing via pipx..."
    run "pipx install '$GRAPHIFY_SOURCE'"
    return 0
  fi

  # Fall back to a python3.10+ -m pip install --user. graphifyy needs ≥3.10.
  local py=""
  for cand in python3.13 python3.12 python3.11 python3.10; do
    if command -v "$cand" >/dev/null 2>&1; then py="$cand"; break; fi
  done
  if [ -z "$py" ]; then
    echo "  [warn] no python3.10+ on PATH and no pipx — graphify not installed."
    echo "         install pipx (recommended) or python3.10+, then run:"
    echo "           pipx install '$GRAPHIFY_SOURCE'"
    return 0
  fi

  echo "  no pipx found; installing via $py -m pip install --user..."
  if [ "$DRY_RUN" = "1" ]; then
    echo "DRY: $py -m pip install --user '$GRAPHIFY_SOURCE'"
  else
    # Tolerate failures (--break-system-packages may be needed on some
    # Debian/Ubuntu setups; we don't want to assume that)
    if ! "$py" -m pip install --user "$GRAPHIFY_SOURCE" 2>&1 | sed 's/^/    /'; then
      echo "  [warn] graphify install failed via pip --user."
      echo "         try: pipx install '$GRAPHIFY_SOURCE'"
      return 0
    fi
  fi
}

if [ "$INSTALL_GRAPHIFY" = "1" ]; then
  install_graphify
else
  echo
  echo "[graphify] skipped (--no-graphify)"
fi

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
