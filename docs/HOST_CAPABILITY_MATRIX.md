# Host capability matrix (honest degradation)

Relocated out of the resident skills-catalog block (see
`render_skills_catalog()` in `install.sh`) to shrink the always-loaded
CLAUDE.md/AGENTS.md/GEMINI.md carrier size. The catalog block keeps a
one-line pointer to this doc plus the always-binding rule; the detail below
is reference material an agent pulls on demand, not something that needs to
occupy resident context on every boot.

- **claude-code** — full: hooks (PreCompact/SessionEnd/UserPromptSubmit/SessionStart) + Agent-tool subagents (builder/verifier lanes).
- **codex** — hooks ported via `.codex/hooks.json` (compaction checkpoint, session archive, canary); NO Agent tool → team-lead lanes go through CLI dispatch (team-lead §2 fallback). **Gotcha:** the codex CLI must run UNSANDBOXED — a sandboxed shell segfaults on macOS keychain access (`SecItemCopyMatching` -50) mid-dispatch; invoke `codex exec` / `model_roster.py --run` outside the plugin sandbox. (Harvested from screenery-lean, 2026-07-06.)
- **gemini** — hooks are NOT auto-wired by the installer: run `gemini hooks migrate --from-claude` once (move `.claude/settings.local.json` aside first — see context-keeper SKILL) for the PreCompress checkpoint, SessionEnd archive, and BeforeAgent canary/triage; verify on first live session.
- Any host: skills are text-portable; tools are plain python3/bash. If a rule references a hook this host lacks, the RULE still binds — you enforce it manually.
