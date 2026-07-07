#!/usr/bin/env bash
# Brainer skill-set installer.
# Symlinks skills/ into the per-host loader path. Idempotent.
# Usage:
#   ./install.sh                           # all detected hosts + graphify
#   ./install.sh --host claude-code        # one host
#   ./install.sh --host claude-code,codex  # comma-separated
#   ./install.sh --project /path/to/proj   # install skills INTO an external
#                                          # project (abs symlinks) instead of
#                                          # the Brainer checkout itself
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
PROJECT_DIR=""

while (( "$#" )); do
  case "$1" in
    --host) HOSTS_REQUESTED="$2"; shift 2 ;;
    --project) PROJECT_DIR="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --no-graphify) INSTALL_GRAPHIFY=0; shift ;;
    -h|--help)
      awk 'NR==1{next} !/^#/{exit} {sub(/^# ?/,"");print}' "$0"
      exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ ! -d "$SRC" ]; then
  echo "skills dir not found: $SRC" >&2
  echo "set SKILLS_DIR or run from repo root." >&2
  exit 2
fi

[ -z "$HOSTS_REQUESTED" ] && HOSTS_REQUESTED="claude-code,codex,gemini"

# Install base. Defaults to the Brainer checkout itself (skills load only when
# cwd is the repo). --project <dir> retargets the skill symlinks + resident
# catalog into an EXTERNAL project so its agent sees the skills. External
# installs use absolute symlink targets (the project moves independently of the
# Brainer clone, so a relative link would break).
DEST_ROOT="$REPO_ROOT"
LINK_ABS=0
if [ -n "$PROJECT_DIR" ]; then
  if [ ! -d "$PROJECT_DIR" ]; then
    echo "--project dir not found: $PROJECT_DIR" >&2
    exit 2
  fi
  DEST_ROOT="$(cd "$PROJECT_DIR" && pwd)"
  LINK_ABS=1
fi

run() {
  if [ "$DRY_RUN" = "1" ]; then echo "DRY: $*"; else eval "$@"; fi
}

link() {
  local target="$1" linkname="$2"
  # Write a RELATIVE symlink so the repo stays portable across checkouts/
  # machines (an absolute target like /Users/you/proj/skills/x breaks on any
  # other clone). target is an absolute path under the repo; express it
  # relative to the link's own directory. Falls back to absolute only if
  # python3 is unavailable.
  local rel
  if [ "${LINK_ABS:-0}" = "1" ]; then
    # External --project install: absolute target (relative would break if the
    # project and the Brainer clone move independently).
    rel="${target%/}"
  else
    rel=$(python3 -c "import os,sys;print(os.path.relpath(sys.argv[1].rstrip('/'), os.path.dirname(sys.argv[2])))" "$target" "$linkname" 2>/dev/null) || rel="$target"
  fi
  if [ -L "$linkname" ] && [ "$(readlink "$linkname")" = "$rel" ]; then
    echo "    [skip] $linkname (already linked)"
    return 0
  fi
  if [ -e "$linkname" ] && [ ! -L "$linkname" ]; then
    echo "    [warn] $linkname exists and is not a symlink — leaving it" >&2
    return 0
  fi
  run "ln -sfn '$rel' '$linkname'"
  echo "    [link] $linkname → $rel"
}

# --- Resident skills catalog ---------------------------------------------
# Skill bodies are lazy-loaded on trigger, which means a freshly booted (or
# post-compaction) agent doesn't know a model-invokable skill (say `wiki-memory`) even exists
# so it can't recognize the trigger. We fix this by compiling a 1-line-per-
# skill catalog and injecting it between sentinels into each host's
# always-resident doc (CLAUDE.md / AGENTS.md / GEMINI.md).
# Slash-triggered skills (disable-model-invocation: true) get their own
# section so the agent knows to dispatch on the literal token.

CATALOG_START='<!-- brainer:skills-catalog:start -->'
CATALOG_END='<!-- brainer:skills-catalog:end -->'

# Strip trigger-boilerplate prefix sentences from a description, return the
# first remaining sentence.
short_desc() {
  printf '%s' "$1" \
    | sed -E 's/^Fires [^.]*\. *//; s/^Do NOT fire[^.]*\. *//' \
    | awk -F'\\. ' '{print $1}'
}

# Extract a single frontmatter field value from a SKILL.md.
# Quote-aware: a value wrapped in YAML double/single quotes is UNquoted (and
# `\"` / `\\` unescaped for double-quoted scalars) so the extracted text is the
# logical value, never the surrounding quote characters. Required because the 7
# descriptions containing `: ` (colon-space) must ship as quoted YAML scalars;
# a naive `sub(/^[^:]+: */, "")` would otherwise leak the quotes into the
# resident catalog and break check_carrier_sync.py. Uses python3 (already a hard
# dependency of this installer, see ensure_global_output_style_hooks).
skill_field() {
  local file="$1" field="$2"
  FIELD="$field" python3 - "$file" <<'PY'
import os, sys
field = os.environ["FIELD"]
text = open(sys.argv[1], encoding="utf-8", errors="replace").read()
if not text.startswith("---"):
    sys.exit(0)
end = text.find("\n---", 3)
block = text[3:end] if end >= 0 else text[3:]
for line in block.splitlines():
    s = line.strip()
    if not s or s.startswith("#") or ":" not in line:
        continue
    k = line.split(":", 1)[0].strip()
    if k != field:
        continue
    v = line.split(":", 1)[1].strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        inner = v[1:-1]
        if v[0] == '"':
            inner = inner.replace('\\"', '"').replace("\\\\", "\\")
        v = inner
    sys.stdout.write(v)
    break
PY
}

skill_is_slash_only() {
  local file="$1"
  grep -q '^disable-model-invocation: *true' "$file"
}

# Opt-in skills (frontmatter `auto-install: false`) are still symlinked and
# listed in the resident catalog, but their per-skill tools/install.sh is NOT
# run by a bare ./install.sh — so they never auto-wire a hook or pull a heavy
# dependency. Enable one explicitly with: bash skills/<name>/tools/install.sh
# Rationale: only measured-win or cheap load-bearing skills belong on the
# default install path (see eval/FINDINGS.md).
# compliance-canary is the DEFAULT-ON output-style drift defense (auto-install:
# true since 2026-06-09; absorbed skill-pulse at v1.10, so it is now the SINGLE
# drift watcher). One UserPromptSubmit hook runs both halves — a periodic
# re-anchor of active skill rules every N turns AND symptomatic drift probes —
# keeping caveman-ultra (and any pulse_reminder/drift_probes skill) from decaying
# over a long session. Turn off per-project via env without uninstall:
# COMPLIANCE_CANARY_DISABLED=1 (both) — SKILL_PULSE_DISABLED=1 still disables
# just the re-anchor (back-compat alias).
# NOTE: per-skill installers MERGE into .claude/settings.json (append-only).
# A bare ./install.sh now AUTO-PRUNES hooks whose script is GONE (a skill that
# was cut — see prune_dead_hooks below), so removed skills fully self-heal. But
# a hook whose script still exists is kept: to fully DISABLE a default-on hook,
# drop its entry from .claude/settings.json by hand — the prune won't touch a
# live script.
skill_is_optin() {
  local file="$1"
  grep -q '^auto-install: *false' "$file"
}

render_skills_catalog() {
  printf '%s\n' "$CATALOG_START"
  cat <<'HEADER'
## Repo-local trigger skills (resident at boot)

Skill bodies under `skills/<name>/` lazy-load on trigger; the 1-line
descriptions below stay resident so a freshly booted (or post-compaction)
agent still recognises a trigger on sight instead of re-deriving it.

### Slash-triggered (user types literally; model cannot auto-invoke)

Literal tokens you recognise yourself — NOT host-registered commands. If the
user's message starts with one, load `skills/<name>/SKILL.md` and follow it
yourself even if this host has no such command (e.g. Codex, Antigravity) or
shows "unknown command". Treat the rest of the message as the task; don't
improvise a hand-rolled equivalent:

HEADER
  local any_slash=0
  for skill in "$SRC"/*/; do
    name=$(basename "$skill")
    [ "$name" = "_shared" ] && continue
    local sm="$skill/SKILL.md"
    [ -f "$sm" ] || continue
    if skill_is_slash_only "$sm"; then
      any_slash=1
      local desc; desc=$(skill_field "$sm" description)
      printf -- '- `/%s` — %s\n' "$name" "$(short_desc "$desc")"
    fi
  done
  [ "$any_slash" = "0" ] && echo "_(none currently)_"
  cat <<'MID'

### Model-invokable (host fires on matching context)

No manual dispatch needed — but knowing these exist helps you notice a
context match (e.g. `wiki-memory` for "have we done X").

MID
  for skill in "$SRC"/*/; do
    name=$(basename "$skill")
    [ "$name" = "_shared" ] && continue
    local sm="$skill/SKILL.md"
    [ -f "$sm" ] || continue
    if ! skill_is_slash_only "$sm"; then
      local desc; desc=$(skill_field "$sm" description)
      printf -- '- `%s` — %s\n' "$name" "$(short_desc "$desc")"
    fi
  done
  # Discoverability (GRAFT 3): a curated memory store only compounds if a fresh
  # or plugin-less agent knows it exists, how to query it, and when. Surface it
  # in the resident doc — but only when this repo has actually adopted a wiki,
  # so downstream adopters without one aren't nagged.
  if [ -d "$REPO_ROOT/wiki" ]; then
    cat <<'STORE'

### Durable memory store (`wiki/`)

Curated why/decision/failure-lesson layer at `wiki/`. Query before re-deriving
(e.g. "have we done X"): read `wiki/L1_index.md`, then
`python3 skills/wiki-memory/tools/wiki.py search "<q>"` → `timeline` → `fetch`.
Maintained by `wiki-memory` (write) / `wiki-refresh` (reconcile vs code).
STORE
  fi
  cat <<'CRAFT'

### Code-craft directives (resident at boot)

Always-on rules for writing code — they apply on every coding turn, not only when
a skill happens to trigger:

- **Surgical diffs.** Smallest reversible change; touch only what the ask needs;
  match local style; never reformat code you didn't change. Justify every changed
  line by the task — revert "while I was in there" edits. (`lean-execution` covers
  this when invoked; this is the always-on copy. The `whitespace_only_edit` +
  `dependency-manifest-changed` `compliance-canary` probes enforce it mechanically.)
- **Failure-mode interrupt.** If mid-task you slide into scope-creep (Kitchen
  Sink), premature abstraction (abstract only on the 3rd repeat — rule of three),
  happy-path-only (error path ignored), or a fix cascading across files (Runaway
  Refactor) — STOP, restate the goal, narrow scope.
CRAFT
  cat <<'MATRIX'

### Host capability matrix (honest degradation)

Host capability & degradation matrix (claude/codex/gemini): see
`docs/HOST_CAPABILITY_MATRIX.md` — the RULE still binds on a host lacking a
hook; enforce it manually.
MATRIX
  cat <<'FOOT'

_Auto-generated by `./install.sh` — do not hand-edit between sentinels._
FOOT
  printf '%s\n' "$CATALOG_END"
}

# Inject (or refresh) the catalog block into a markdown file. Idempotent.
inject_catalog_into_doc() {
  local target="$1"
  if [ "$DRY_RUN" = "1" ]; then
    echo "    DRY: inject skills catalog into $target"
    return 0
  fi
  local block_tmp; block_tmp=$(mktemp)
  render_skills_catalog > "$block_tmp"

  if [ ! -f "$target" ]; then
    {
      printf '# Brainer\n\n'
      printf 'Skills catalog: see [`%s/SKILLS_INDEX.md`](%s/SKILLS_INDEX.md).\n\n' "$SKILLS_DIR" "$SKILLS_DIR"
      printf 'Each skill loads on its own trigger; full bodies are not in the boot context. Run `./install.sh` to wire skills into the current host.\n\n'
      cat "$block_tmp"
    } > "$target"
    echo "    [write] $target (created with catalog)"
    rm -f "$block_tmp"
    return 0
  fi

  if grep -q 'brainer:skills-catalog:start' "$target" && ! grep -q 'brainer:skills-catalog:end' "$target"; then
    # Start sentinel present but END sentinel missing (hand-edit removed it /
    # interrupted write). The awk replace below sets skip=1 at the start and
    # only clears it at the end sentinel — with no end sentinel, skip stays 1
    # to EOF and ALL content after the start sentinel (including real user
    # prose) is silently dropped. Refuse to rewrite; warn instead of truncate.
    echo "    [skip] $target has catalog start sentinel but no end sentinel — refusing to rewrite (would truncate everything after it). Restore the end sentinel ($CATALOG_END) or remove the start sentinel, then re-run." >&2
    rm -f "$block_tmp"
    return 0
  fi

  if grep -q 'brainer:skills-catalog:start' "$target"; then
    local out; out=$(mktemp)
    awk -v blockfile="$block_tmp" -v start="$CATALOG_START" -v end="$CATALOG_END" '
      index($0, start) {
        while ((getline line < blockfile) > 0) print line
        close(blockfile)
        skip = 1
        next
      }
      index($0, end) {
        if (skip) { skip = 0; next }
      }
      !skip { print }
    ' "$target" > "$out"
    mv "$out" "$target"
    echo "    [update] $target (catalog refreshed)"
  else
    printf '\n' >> "$target"
    cat "$block_tmp" >> "$target"
    printf '\n' >> "$target"
    echo "    [append] $target (catalog appended)"
  fi
  rm -f "$block_tmp"
}

# Remove symlinks in a host skills dir whose target no longer exists — i.e.
# skills deleted from the catalog. Idempotent and safe: only ever removes
# BROKEN symlinks (never real files or live links), so a re-install self-heals
# after a skill is cut instead of stranding a dangling link (and, for hooks
# wired off it, a dead hook command).
prune_stale_skill_links() {
  local dir="$1"; [ -d "$dir" ] || return 0
  local l
  # Portable broken-symlink detection: -L (is a symlink) AND ! -e (target does
  # not resolve). NOT `find -xtype l` — that is a GNU extension and silently
  # errors out on BSD/macOS find, which would make this prune a no-op.
  for l in "$dir"/*; do
    if [ -L "$l" ] && [ ! -e "$l" ]; then
      if [ "$DRY_RUN" = "1" ]; then echo "DRY: prune stale link $l"
      else rm -f "$l"; echo "    [prune] $(basename "$l") (removed from catalog)"; fi
    fi
  done
}

# Remove hook entries from a settings.json whose command script no longer
# exists — i.e. hooks left behind by a cut skill (e.g. a PreToolUse hook whose
# loop-breaker/tools/hook.sh was deleted). The settings.json counterpart of the
# symlink prune, so a re-install self-heals the hooks side too. Only removes
# hooks whose script is GONE; a hook for a still-present skill (incl. an opt-in
# you enabled) is untouched. Safe + idempotent.
# SCOPED + CONSERVATIVE: only ever considers Brainer-managed hooks (script path
# under `.claude/skills/`). App hooks (any other path) are NEVER touched. And a
# path it can't positively resolve — an unexpanded $VAR or ~ — is always kept,
# never pruned: prune must prove a hook is a removed Brainer skill before
# deleting it, or it would silently eat a live app hook like a $CLAUDE_PROJECT_DIR
# Stop gate.
prune_dead_hooks() {
  local settings="$1" root="$2"
  [ -f "$settings" ] || return 0
  DRY_RUN="$DRY_RUN" python3 - "$settings" "$root" <<'PY' 2>/dev/null
import json, os, shlex, sys
settings, root = sys.argv[1], sys.argv[2]
dry = os.environ.get("DRY_RUN") == "1"
try:
    d = json.load(open(settings))
except Exception:
    sys.exit(0)
hooks = d.get("hooks", {})
removed = []
for event in list(hooks.keys()):
    new_groups = []
    for g in hooks[event]:
        kept = []
        for h in g.get("hooks", []):
            cmd = h.get("command", "")
            script = next((t for t in shlex.split(cmd) if t.endswith((".sh", ".py"))), None)
            # Only Brainer-managed hooks are prune candidates, and only when the
            # path is concrete (no unexpanded $VAR/~). Everything else is kept.
            managed = (script is not None and ".claude/skills/" in script
                       and "$" not in script and "~" not in script)
            if not managed or os.path.exists(os.path.join(root, script)):
                kept.append(h)
            else:
                removed.append(cmd)
        if kept:
            g["hooks"] = kept
            new_groups.append(g)
    if new_groups:
        hooks[event] = new_groups
    else:
        del hooks[event]
if removed and not dry:
    d["hooks"] = hooks
    json.dump(d, open(settings, "w"), indent=2)
    open(settings, "a").write("\n")
for cmd in removed:
    print("    [prune-hook] %s%s (skill removed)" % ("DRY: " if dry else "", cmd))
PY
}

# Output-style skills (frontmatter `output_style: true`) inject their rule at
# SessionStart so terse/style guidance is set from turn 1. That injection must
# fire in EVERY project where Brainer is installed and NOWHERE else, so — unlike
# every other hook here — it lives as a GUARDED hook in the user-global
# ~/.claude/settings.json, guarded on the per-project marker
# `.claude/skills/<skill>`. This is the ONLY place install.sh writes user-global
# (not repo-local) config. Idempotent + convergent: reads the canonical injected
# text from each skill's session_start.md, rebuilds the guarded command, and
# converges any prior copy in place (upgrading an old unguarded/global hook to
# the guarded form). Skills with output_style but no session_start.md are
# skipped; a non-JSON global settings file is left untouched with a warning.
ensure_global_output_style_hooks() {
  local gsettings="$HOME/.claude/settings.json"
  if [ "$DRY_RUN" = "1" ]; then
    echo "    DRY: ensure guarded SessionStart output-style hook(s) in $gsettings"
    return 0
  fi
  GS="$gsettings" python3 - "$SRC" <<'PY'
import json, os, shlex, sys
from pathlib import Path

src = Path(sys.argv[1])
gpath = Path(os.environ["GS"])

def frontmatter(text):
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    out = {}
    for line in text[3:end].splitlines():
        s = line.strip()
        if not s or s.startswith("#") or ":" not in line:
            continue
        k, _, v = line.partition(":")
        k, v = k.strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        out[k] = v
    return out

styles = []
for d in sorted(src.iterdir()):
    sm, ss = d / "SKILL.md", d / "session_start.md"
    if not sm.is_file() or not ss.is_file():
        continue
    fm = frontmatter(sm.read_text(encoding="utf-8", errors="replace"))
    if str(fm.get("output_style", "")).strip().lower() != "true":
        continue
    styles.append((fm.get("name") or d.name, ss.read_text(encoding="utf-8").strip()))

if not styles:
    sys.exit(0)

if gpath.exists():
    try:
        data = json.loads(gpath.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print("    [warn] %s not valid JSON — leaving global hooks untouched" % gpath)
        sys.exit(0)
else:
    data = {}

before = json.dumps(data, sort_keys=True)
ss_rules = data.setdefault("hooks", {}).setdefault("SessionStart", [])

for name, text in styles:
    marker = ".claude/skills/%s" % name
    payload = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}
    echo_arg = shlex.quote(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    command = 'p="${CLAUDE_PROJECT_DIR:-$PWD}"; if [ -e "$p/%s" ]; then echo %s; fi' % (marker, echo_arg)
    existing = [h for g in ss_rules for h in g.get("hooks", []) if marker in h.get("command", "")]
    if existing:
        for h in existing:               # converge in place (no-op if identical)
            h["type"], h["command"] = "command", command
    else:
        ss_rules.append({"hooks": [{"type": "command", "command": command,
                                    "statusMessage": "Applying %s output style" % name}]})

if json.dumps(data, sort_keys=True) == before:
    print("    [skip] global output-style hook(s) already current")
    sys.exit(0)
gpath.parent.mkdir(parents=True, exist_ok=True)
gpath.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("    [global] ensured guarded SessionStart hook(s): %s" % ", ".join(n for n, _ in styles))
PY
}

install_claude_code() {
  echo "[claude-code]"
  run "mkdir -p '$DEST_ROOT/.claude/skills'"
  prune_stale_skill_links "$DEST_ROOT/.claude/skills"
  for skill in "$SRC"/*/; do
    name=$(basename "$skill")
    [ "$name" = "_shared" ] && continue
    link "$skill" "$DEST_ROOT/.claude/skills/$name"
  done
  # Prune dead hooks AFTER (re)creating the skill symlinks: prune decides a
  # managed hook is dead via os.path.exists(.claude/skills/<name>/...), which
  # only resolves through those symlinks. Running it first (or with a
  # settings.json rsync'd from another machine before its symlinks exist) made
  # every live Brainer hook look missing and wiped it. With symlinks in place,
  # prune removes only hooks whose skill is genuinely gone.
  prune_dead_hooks "$DEST_ROOT/.claude/settings.json" "$DEST_ROOT"
  inject_catalog_into_doc "$DEST_ROOT/CLAUDE.md"
  ensure_global_output_style_hooks
  # Regenerate the hooks map (pre-built index for hook-wiring questions;
  # see skills/HOOKS_MAP.md + index-first). Non-fatal: map is an optimization.
  run "python3 '$REPO_ROOT/scripts/gen_hooks_map.py'" || echo "    [warn] gen_hooks_map failed (non-fatal)"
}

install_codex() {
  echo "[codex]"
  run "mkdir -p '$DEST_ROOT/.codex/skills'"
  prune_stale_skill_links "$DEST_ROOT/.codex/skills"
  for skill in "$SRC"/*/; do
    name=$(basename "$skill")
    [ "$name" = "_shared" ] && continue
    link "$skill" "$DEST_ROOT/.codex/skills/$name"
  done
  inject_catalog_into_doc "$DEST_ROOT/AGENTS.md"
}

install_gemini() {
  echo "[gemini]"
  run "mkdir -p '$DEST_ROOT/.gemini/skills'"
  prune_stale_skill_links "$DEST_ROOT/.gemini/skills"
  for skill in "$SRC"/*/; do
    name=$(basename "$skill")
    [ "$name" = "_shared" ] && continue
    link "$skill" "$DEST_ROOT/.gemini/skills/$name"
  done
  local settings="$DEST_ROOT/.gemini/settings.json"
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
  inject_catalog_into_doc "$DEST_ROOT/GEMINI.md"
}

IFS=',' read -ra HOST_LIST <<< "$HOSTS_REQUESTED"
for h in "${HOST_LIST[@]}"; do
  case "$h" in
    claude-code) install_claude_code ;;
    codex)       install_codex ;;
    gemini)      install_gemini ;;
    *) echo "unknown host: $h (claude-code|codex|gemini)" >&2; exit 2 ;;
  esac
done

# Per-skill tools/install.sh — for skills with Python/MCP deps (best-effort).
# Export the requested host list so a per-skill installer that merges HOST-
# specific config (e.g. context-keeper's merge_codex writing .codex/hooks.json)
# only touches hosts actually requested here — a `--host gemini` run must not
# also merge an inert codex/claude-code hook entry nobody asked for. Unset/empty
# in a direct `bash skills/x/tools/install.sh` run (back-compat: all hosts).
export BRAINER_HOSTS="$HOSTS_REQUESTED"
echo
echo "[skill-tools] running per-skill installers (Python deps, MCP servers)"
for tool_installer in "$SRC"/*/tools/install.sh; do
  [ -f "$tool_installer" ] || continue
  skill_name="$(basename "$(dirname "$(dirname "$tool_installer")")")"
  skill_md="$(dirname "$(dirname "$tool_installer")")/SKILL.md"
  if [ -f "$skill_md" ] && skill_is_optin "$skill_md"; then
    echo "  → $skill_name [skip] opt-in (auto-install: false) — enable with: bash $tool_installer"
    continue
  fi
  echo "  → $skill_name"
  if [ "$DRY_RUN" = "1" ]; then
    echo "    DRY: bash $tool_installer"
  else
    # Tolerate per-skill installer failures (e.g. stale paths in other skills)
    # so a broken sibling never aborts the whole install.
    { bash "$tool_installer" 2>&1 | sed 's/^/    /'; } || echo "    [warn] $skill_name installer exited nonzero — see above"
  fi
done

# --- --project: wire hooks into the CONSUMER project, not just $REPO_ROOT ---
# Every per-skill tools/install.sh above derives its target root from ITS OWN
# script location ($TOOLS_DIR/../../..), not from an argument or env var — so
# the loop above, even when run via a --project invocation, only ever wires
# hooks into $REPO_ROOT/.claude/settings.json. A consumer project got the
# skill symlinks + CLAUDE.md catalog but NONE of the drift/liveness hooks
# (compliance-canary, context-keeper, prompt-triage, brainer-audit, learn-skill,
# index-first) — LEARNING_CONTRACT §4's "gate silently dead" class, in our own
# installer (found by the E3 gauntlet). None of those installers expose a
# retarget parameter, and adding one to six scripts is surgery beyond this
# fix's scope — so instead we wire the known single-command/single-event
# non-opt-in hook skills (compliance-canary, context-keeper, prompt-triage)
# directly here, extracting each one's own already-portable *_CMD shell
# string (run-time-expanded, no machine-specific path) from its installer
# source and reusing the exact same idempotent JSON-merge idiom every
# per-skill installer already uses (hooks.setdefault(event, []).append a
# {matcher:"*", hooks:[{type:"command", command:cmd}]} rule; never touch a
# non-Brainer hook; never overwrite a corrupt settings.json). Opt-in skills
# (brainer-audit, learn-skill, index-first) and any future hook skill this
# table doesn't yet name are reported via a loud [warn], never silently
# skipped.
# claude-code only (--host constrains): the .codex/hooks.json / .gemini
# equivalents follow the same script-location limitation and are named in the
# loud warn below rather than silently skipped.
project_wire_skill_hooks() {
  if [ "$DRY_RUN" = "1" ]; then
    echo "    DRY: wire per-skill hooks into $DEST_ROOT/.claude/settings.json (claude-code)"
    return 0
  fi
  case ",$HOSTS_REQUESTED," in *",claude-code,"*) ;; *)
    echo "    [warn] --project + --host without claude-code: skipping consumer hook-wiring (only claude-code is supported by this generic pass)"
    return 0 ;;
  esac
  SRC="$SRC" DEST_ROOT="$DEST_ROOT" python3 - <<'PY'
import json, os, re, sys
from pathlib import Path

src = Path(os.environ["SRC"])
dest_root = Path(os.environ["DEST_ROOT"])
settings_path = dest_root / ".claude" / "settings.json"

def skill_is_optin(skill_md_text):
    return bool(re.search(r'^auto-install:\s*false', skill_md_text, re.M))

# Declarative (skill, event, *_CMD var name) table for every non-opt-in skill
# whose own tools/install.sh wires a SINGLE claude-code command/event pair
# into .claude/settings.json (hand-verified against each installer's source —
# see the shell VARNAME='...' assignment named below — not re-derived by a
# generic glob/regex, which previously mis-wired hook.py directly alongside
# hook.sh for skills that ship hook.py only as a thin exit-0-safety internal
# used BY hook.sh, e.g. compliance-canary/context-keeper). Skills with no
# single-command claude-code hook this generic pass can safely reconstruct
# (brainer-audit, learn-skill: opt-in; index-first: opt-in) are excluded here
# and named in the loud warn the caller prints either way.
KNOWN_HOOK_INSTALLERS = {
    # skill_name: [(event, shell_var_name_in_that_installer), ...]
    "compliance-canary": [("UserPromptSubmit", "HOOK_CMD")],
    "context-keeper":    [("PreCompact", "HOOK_CMD"), ("SessionEnd", "ARCHIVE_CMD")],
    "prompt-triage":     [("UserPromptSubmit", "HOOK_CMD")],
}

def extract_cmd(installer_text, var_name):
    m = re.search(r"^%s='([^']*)'" % re.escape(var_name), installer_text, re.M)
    return m.group(1) if m else None

wired = []
skipped_optin = []
skipped_unknown = []
for skill_dir in sorted(src.iterdir()):
    tools = skill_dir / "tools"
    if not skill_dir.is_dir() or not tools.is_dir():
        continue
    hook_files = [f for f in tools.iterdir() if f.name in ("hook.sh", "hook.py")]
    if not hook_files:
        continue
    skill_md = skill_dir / "SKILL.md"
    md_text = skill_md.read_text(encoding="utf-8", errors="replace") if skill_md.exists() else ""
    if skill_is_optin(md_text):
        skipped_optin.append(skill_dir.name)
        continue
    spec = KNOWN_HOOK_INSTALLERS.get(skill_dir.name)
    if not spec:
        skipped_unknown.append(skill_dir.name)
        continue
    installer = tools / "install.sh"
    installer_text = installer.read_text(encoding="utf-8", errors="replace") if installer.exists() else ""
    for event, var_name in spec:
        cmd = extract_cmd(installer_text, var_name)
        if cmd is None:
            skipped_unknown.append("%s (%s not found — installer changed shape)" % (skill_dir.name, var_name))
            continue
        wired.append((skill_dir.name, event, cmd))

if not wired:
    print("    [warn] no known hook-shipping skills discovered under %s — nothing to wire" % src)
    if skipped_unknown:
        print("    [warn] unrecognized hook installer shape, not wired: %s" % ", ".join(skipped_unknown))
    sys.exit(0)

if settings_path.exists():
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print("    [warn] %s exists but is not valid JSON (%s) — leaving consumer hooks untouched" % (settings_path, e))
        sys.exit(0)
else:
    data = {}

hooks = data.setdefault("hooks", {})
for name, event, cmd in wired:
    rules = hooks.setdefault(event, [])
    for rule in rules:
        if rule.get("matcher") != "*":
            continue
        existing = rule.get("hooks", [])
        if any(h.get("type") == "command" and h.get("command") == cmd for h in existing):
            break
    else:
        rules.append({"matcher": "*", "hooks": [{"type": "command", "command": cmd}]})

settings_path.parent.mkdir(parents=True, exist_ok=True)
settings_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
for name, event, cmd in wired:
    print("    [hook] %s: %s -> %s" % (name, event, cmd))
if skipped_optin:
    print("    [skip] opt-in (auto-install: false), not wired: %s" % ", ".join(skipped_optin))
if skipped_unknown:
    print("    [warn] unrecognized hook installer shape, not wired: %s" % ", ".join(skipped_unknown))
PY
}

if [ -n "$PROJECT_DIR" ]; then
  echo
  echo "[project-hooks] wiring per-skill hooks into consumer project ($DEST_ROOT/.claude/settings.json)"
  project_wire_skill_hooks
  echo "    NOTE: only the claude-code UserPromptSubmit/SessionStart/PreCompact/... hooks this"
  echo "    generic pass can discover are wired. Every per-skill tools/install.sh derives its target"
  echo "    root from ITS OWN script path (\$TOOLS_DIR/../../..), not an argument or env var — so it"
  echo "    ALWAYS targets the Brainer checkout, even if you cd into $DEST_ROOT first or symlink the"
  echo "    script there. Anything beyond a single command/event (e.g. .codex/hooks.json merges, MCP"
  echo "    server registration, prompt-triage's agents/*.md copy) is NOT retargeted by this pass and"
  echo "    has no safe manual workaround short of editing that skill's install.sh to accept a target"
  echo "    root — do that only for the specific skill you need in the consumer project."
fi

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

# Root shim docs are created (or refreshed) by each install_<host> via
# inject_catalog_into_doc. We additionally ensure all three exist so a host
# the user hasn't explicitly installed today still finds a usable doc the
# next time it boots — the docs are cheap and idempotent.
echo
echo "[root] ensure resident-context docs exist for all hosts"
for f in CLAUDE.md AGENTS.md GEMINI.md; do
  inject_catalog_into_doc "$REPO_ROOT/$f"
done

echo
# Gate-substrate liveness (LEARNING_CONTRACT.md §4): a dead gate (unparseable
# drift_probes.json, dangling SKILL.md tool/link reference, broken hooks-map
# entry) is worse than none. Checks the Brainer checkout itself (repo-wide,
# host-independent). Non-fatal — install already ran; report so the finding
# gets fixed, don't abort a completed install over it.
run "python3 '$REPO_ROOT/skills/_shared/knowledge_liveness.py'" || echo "    [warn] knowledge_liveness found dead-gate findings (see above; non-fatal)"

# --project: also run the PORTABLE subset of knowledge_liveness's checks
# against the CONSUMER's installed skills/ tree (gate-json parse, SKILL.md
# frontmatter + tool paths, markdown links) — the same gap this whole
# --project retarget fix closes for hooks. --project installs only
# .claude/skills/ (+ root docs), never scripts/ or wiki/, so the full
# knowledge_liveness.run() would spuriously fail on the wiki/hooks-map
# extensions that depend on scripts/*.py the consumer never received; those
# two checks are Brainer-repo-only by design (see knowledge_liveness.py's own
# CHECKS tuple vs. its wiki/hooks-map extensions) — same reasoning
# scripts/e3_gauntlet.py's check_c_substrate_liveness already documents.
# Module-import (not a new CLI flag): knowledge_liveness.py stays untouched,
# same approach e3_gauntlet.py uses to avoid touching a file outside this
# fix's scope.
if [ -n "$PROJECT_DIR" ] && [ "$DRY_RUN" != "1" ]; then
  echo
  echo "[project-liveness] portable substrate liveness check on consumer tree ($DEST_ROOT/.claude/skills)"
  KL_PATH="$REPO_ROOT/skills/_shared/knowledge_liveness.py" DEST_ROOT="$DEST_ROOT" python3 - <<'PY'
import importlib.util, os, sys
from pathlib import Path

kl_path = Path(os.environ["KL_PATH"])
dest_root = Path(os.environ["DEST_ROOT"])

spec = importlib.util.spec_from_file_location("brainer_install_knowledge_liveness", kl_path)
kl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kl)

kl.REPO = dest_root
kl.SKILLS = dest_root / ".claude" / "skills"
kl.SCRIPTS = dest_root / "scripts"  # not installed by --project; unused by the portable subset

errors = []
for _label, fn in kl.CHECKS:
    fn(errors)

if errors:
    print("    [warn] consumer substrate liveness: %d finding(s) (non-fatal):" % len(errors))
    for e in errors:
        print("    - %s" % e)
    sys.exit(1)
print("    consumer substrate liveness: clean — %d portable checks (gate-json, skill-md-tool-paths, markdown-links)" % len(kl.CHECKS))
PY
  [ $? -eq 0 ] || echo "    [warn] consumer knowledge_liveness found dead-gate findings (see above; non-fatal)"
fi

echo
echo "done. host(s): $HOSTS_REQUESTED"
