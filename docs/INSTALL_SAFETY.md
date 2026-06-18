# Install safety

`install.sh` wires the canonical `skills/` catalog into host-specific places. It is intentionally idempotent, but it can still change agent behavior, so preview it before changing an install.

## What install does

- Symlinks each `skills/<name>/` folder into host loader directories such as `.claude/skills/`, `.codex/skills/`, `.cursor/skills/`, and `.gemini/skills/`.
- Refreshes the generated skills catalog blocks in `CLAUDE.md`, `AGENTS.md`, and `GEMINI.md`.
- Regenerates `skills/HOOKS_MAP.md` for hook-capable skills.
- Writes Cursor `.mdc` rule shims under `.cursor/rules/`.
- Ensures `.gemini/settings.json` points Gemini at `.gemini/skills`.
- Runs per-skill `tools/install.sh` scripts unless a skill declares `auto-install: false`.
- Optionally installs graphify unless `--no-graphify` is passed.

## Global vs repo-local changes

Most writes are repo-local, next to `install.sh`. The notable global behavior is the Claude output-style hook setup: `install.sh` may update `~/.claude/settings.json` with a guarded SessionStart hook for output-style skills. The hook is guarded on the current project marker so it only fires where Brainer is installed.

## Dry run

Preview with:

```bash
./install.sh --dry-run
```

Dry-run prints planned top-level file, symlink, and dependency actions. For per-skill installers it prints the installer command that would run; run that skill installer directly with `--dry-run` when you need byte-level hook details. Dry-run should not mutate repo files or global host config.

## Host targeting

Limit scope with:

```bash
./install.sh --host claude-code
./install.sh --host codex
./install.sh --host cursor
./install.sh --host gemini
./install.sh --host claude-code,codex
```

Use `--no-graphify` when you only want host wiring and do not want the installer to attempt a dependency install.

## Backup and restore

The installer is mostly convergent symlink and generated-section updates; it does not create a full backup bundle. Before risky install work, use Git as the safety net:

```bash
git status --short
./install.sh --dry-run
```

If a generated carrier changes unexpectedly, inspect the diff. To restore a generated carrier, revert the file with Git or re-run `./install.sh` from the intended `skills/` source.

## Conflict behavior

- Existing non-symlink files at host skill targets are left in place with a warning.
- Broken skill symlinks are pruned.
- Dead Brainer-managed Claude hooks are pruned only when their script path can be proven gone.
- App hooks and unresolved environment-variable paths are preserved.
- A carrier with a start sentinel but no end sentinel is not rewritten, to avoid truncating human prose.

## Safe verification

Use:

```bash
./install.sh --help
./install.sh --dry-run
git status --short
make check
```

Do not run a real install merely to verify a docs or checker change. Dry-run is the safe install check for this repo health pass.
