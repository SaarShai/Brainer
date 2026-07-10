# Brainer installation instructions for agents

Use this file when a user gives you the Brainer repository link and asks you to
install or update Brainer in the project you are working on. The repository is
the source of truth; do not copy skill bodies into the consumer project.

Repository URL used by this checkout:

```text
https://github.com/SaarShai/Brainer.git
```

## 1. Identify the consumer project and host

Set `PROJECT_DIR` to the project root. If the user did not name another
directory, use the current working directory:

```bash
PROJECT_DIR="${PROJECT_DIR:-$PWD}"
```

Choose exactly one host flag based on the agent that is running:

```text
Claude Code  -> claude-code
Codex        -> codex
Gemini CLI   -> gemini
```

If the host is not one of these, stop and explain the limitation rather than
pretending that the skills were installed. Copilot/VS Code can consume the
root `AGENTS.md` guidance, but it has no dedicated installer flag.

## 2. Clone Brainer or safely update its checkout

Keep the Brainer checkout at `<project>/.brainer`. Never overwrite local
changes in that checkout. A clean checkout can fast-forward to the current
catalog before the next step classifies the target project's host-skill state.

```bash
PROJECT_DIR="${PROJECT_DIR:-$PWD}"
BRAINER_DIR="$PROJECT_DIR/.brainer"
BRAINER_URL="${BRAINER_URL:-https://github.com/SaarShai/Brainer.git}"

if [ -d "$BRAINER_DIR/.git" ]; then
  test -z "$(git -C "$BRAINER_DIR" status --porcelain)" || {
    echo "Brainer checkout has local changes; inspect before updating: $BRAINER_DIR" >&2
    exit 1
  }
  git -C "$BRAINER_DIR" pull --ff-only
elif [ -e "$BRAINER_DIR" ]; then
  echo "Refusing to use non-git path as Brainer checkout: $BRAINER_DIR" >&2
  exit 1
else
  git clone "$BRAINER_URL" "$BRAINER_DIR"
fi
```

## 3. Preflight the consumer project

This read-only command classifies the current Brainer state as `INSTALL`,
`UPDATE`, or `STOP`. It checks the `.brainer` checkout, canonical skill links,
customized files, foreign links, broken links, and the relevant host config.

```bash
HOST="codex"  # replace with claude-code or gemini when appropriate
python3 "$BRAINER_DIR/scripts/project_install_preflight.py" \
  --project "$PROJECT_DIR" \
  --host "$HOST"
```

Only continue on exit code `0` (`INSTALL` or `UPDATE`). If it returns `2`
(`STOP`), do not run the installer: report the listed local state and ask the
user whether to merge, replace, or preserve it. The preflight never edits the
consumer project.

## 4. Install after a successful preflight

Run the installer from the current Brainer checkout and target the consumer
project:

```bash
HOST="codex"  # replace with claude-code or gemini when appropriate
"$BRAINER_DIR/install.sh" \
  --project "$PROJECT_DIR" \
  --host "$HOST" \
  --no-graphify
```

`--project` is important: it puts the skill links and resident agent catalog
in the consumer project instead of only wiring the Brainer checkout itself.
The command is idempotent and self-healing: new skills are added, broken links
for removed skills are pruned, and the generated catalog is refreshed.

`--no-graphify` keeps installation limited to Brainer. Omit it only when the
project also wants Brainer's optional `graphify` dependency installed or
updated.

For Claude Code, the project-targeted install also wires the supported
consumer-side Claude hooks. Codex and Gemini receive their skill directories
and resident catalog; this installer does not claim to retarget every
host-specific hook or optional tool into those hosts.

## 5. Verify the result

Run the dry-run once to confirm the target and host, then verify the expected
skill directory and resident catalog. Do not claim success unless these checks
pass:

```bash
"$BRAINER_DIR/install.sh" \
  --project "$PROJECT_DIR" \
  --host "$HOST" \
  --no-graphify \
  --dry-run

case "$HOST" in
  claude-code) SKILL_ROOT="$PROJECT_DIR/.claude/skills"; DOC="$PROJECT_DIR/CLAUDE.md" ;;
  codex)       SKILL_ROOT="$PROJECT_DIR/.codex/skills";  DOC="$PROJECT_DIR/AGENTS.md" ;;
  gemini)      SKILL_ROOT="$PROJECT_DIR/.gemini/skills"; DOC="$PROJECT_DIR/GEMINI.md" ;;
esac

test -L "$SKILL_ROOT/verify-before-completion"
test -f "$DOC"
rg -q 'brainer:skills-catalog:start' "$DOC"
git -C "$BRAINER_DIR" rev-parse --short HEAD
```

If the consumer project tracks `.brainer/`, add it to that project's
`.gitignore` unless the user explicitly wants the checkout committed. The
`.claude/`, `.codex/`, and `.gemini/` runtime policy remains the consumer
project's decision; preserve existing files and settings.

## Updating later

Repeat sections 2–5. The clean-check and fast-forward update happen before the
preflight; the preflight must pass before the same `install.sh --project`
command. Do not manually edit generated catalog sections between
`brainer:skills-catalog:start` and
`brainer:skills-catalog:end`; rerun the installer instead.

## Maintainer checks before publishing Brainer changes

From the Brainer checkout, run:

```bash
make check
```

Then inspect `git status --short`, stage only the intended files, commit, and
push the branch. The public README links back to this file so future agents can
find this procedure from the repository landing page.
