---
trust: verified
schema_version: 2
title: "Hook path fragility: cwd-relative ./ in installers causes tool lockout"
type: concept
domain: "framework"
tier: semantic
confidence: 0.85
created: "2026-06-27"
updated: "2026-06-27"
verified: "2026-06-27"
sources: ["skills/brainer-audit/tools/install.sh", "install.sh"]
supersedes: []
superseded-by:
tags: [hooks, install, cwd-drift, lockout, pretooluse, claude-project-dir, fail-open, hard-rule]
---

# Hook path fragility: cwd-relative ./ in installers causes tool lockout

**Trigger / symptom:** a tool call returns no output and every subsequent tool
(Read/Bash/Write/Edit/Agent) is blocked; the hook error shows a doubled path like
`code/acute_pilot/./.claude/skills/brainer-audit/tools/hook.py` → `[Errno 2] No such
file or directory`. Onset is right after a `cd` into a repo subdir.

## Root cause

Claude Code runs hook commands from the shell's **current cwd, not the repo root**,
and the Bash tool's shell is persistent — a bare `cd subdir` sticks across later
calls. A hook command stored as `python3 ./.claude/skills/.../hook.py` then resolves
against the drifted cwd, so the interpreter **can't open the file and exits 2**.
On a `PreToolUse` hook, **exit code 2 blocks the gated tool**; with `matcher: "*"`
that blocks *every* tool — total lockout. You can't self-unlock: the shim that would
fix it is a `Write`, blocked by the same hook (only a new user turn resets cwd to root).

**Why a fail-open hook script doesn't save it:** the failure is at the interpreter
**launch** layer, *upstream* of any `try/except return 0` inside the script. The
script never runs, so its fail-open never executes. (The fail-closed-`hook.py` theory
was refuted: uncaught Python errors exit 1 = non-blocking; only exit 2 blocks, and
the only exit-2 path is the unreachable argparse error — the **path** is the cure.)

## Fix (the two defenses)

1. **Path anchoring (load-bearing).** Never store a cwd-relative `./` hook path.
   - **Claude** hooks: `bash "${CLAUDE_PROJECT_DIR:-$PWD}/.claude/skills/.../X"`
     (quoted; Claude Code injects `CLAUDE_PROJECT_DIR` = repo root, expanded at hook
     run time) **so that** the command resolves regardless of cwd.
   - **Codex** hooks live in a **committed, portable** `.codex/hooks.json`, so keep
     the same `${CLAUDE_PROJECT_DIR:-$PWD}` form (never a machine-specific absolute
     path in a tracked file). Codex doesn't set the var, so it degrades to `$PWD`
     (repo root at session start) — no regression vs `./`, but Codex cwd-drift stays
     unsolved (no portable anchor). Bake an absolute path **only** in a *gitignored*
     per-machine config.
   - Anchor a hook **script's own** relative reads (e.g. `skills_root()`,
     `_skills_dir()`) to `CLAUDE_PROJECT_DIR` too, **to avoid** silent discovery
     failure (the drift watcher going dark) on cwd drift.
2. **Fail-open (defense-in-depth).** An audit/logging/augment hook must `exit 0` on
   any internal error, **in order to** never convert its own failure into a tool block.

## Notes

- `install.sh`'s `prune_dead_hooks` treats a `$`-containing command as unmanaged
  (won't prune), so `${CLAUDE_PROJECT_DIR:-$PWD}` hooks are prune-exempt — acceptable
  for idempotent core hooks.
- Propagating this fix to vendored siblings follows [[concepts/brainer-multi-repo-topology]]:
  re-run each sibling's own `install.sh`, never blind-rsync.

## Related

- [[concepts/brainer-multi-repo-topology]]
- [[index]]
- [[schema]]
