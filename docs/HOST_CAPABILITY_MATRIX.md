# Host capability matrix (honest degradation)

Relocated out of the resident skills-catalog block (see
`render_skills_catalog()` in `install.sh`) to shrink the always-loaded
CLAUDE.md/AGENTS.md/GEMINI.md carrier size. The catalog block keeps a
one-line pointer to this doc plus the always-binding rule; the detail below
is reference material an agent pulls on demand, not something that needs to
occupy resident context on every boot.

- **claude-code** — full: hooks (PreCompact/SessionEnd/UserPromptSubmit/SessionStart) + Agent-tool subagents (builder/verifier lanes).
- **codex** — hook commands are packaged in `.codex/hooks.json` for session
  archive and canary. Configuration is not proof of event delivery: `Stop`
  archive and a fresh-task `UserPromptSubmit` capture have both been observed
  in Codex Desktop; a fresh native Codex CLI consumer also delivered
  `UserPromptSubmit` exactly once. Unsupported `PreCompact` is not wired. Codex CLI lacks
  Claude's `Agent` tool; Codex
  Desktop may expose its own collaboration tools, and otherwise `team-lead`
  uses CLI dispatch (§2 fallback). **Gotcha:** the codex CLI must run
  UNSANDBOXED — a sandboxed shell segfaults on macOS keychain access
  (`SecItemCopyMatching` -50) mid-dispatch; invoke `codex exec` /
  `model_roster.py --run` outside the plugin sandbox. (Harvested from
  screenery-lean, 2026-07-06.)
- **claude-desktop Code** — this is the Brainer target within the consumer app.
  It uses Claude Code's native plugin surface for skills, hooks, and sub-agents;
  no separate MCPB/Desktop Extension is needed merely to carry those
  components. The installed plugin's `/think` skill, `UserPromptSubmit`, and
  `PreCompact` delivery are live-observed in the Desktop UI. The marker produced
  exactly one capture and `/compact` produced a project-local checkpoint. When
  equivalent Brainer project hooks coexist, a plugin-side
  precedence router lets the valid project hook run and suppresses only the
  duplicate plugin execution; plugin-only projects retain the packaged hook.
  A cache-only native Claude run with user settings disabled live-proved that
  fallback from the installed 22 MB artifact: one prompt event, one intent row,
  one ledger row, and one raw `SessionEnd` archive.
  The underlying Claude Code engine delivers the packaged `SessionEnd` hook,
  but the Desktop UI exposes no required end-session step and Command-W only
  closes the UI surface. Use `/compact` whenever a durable checkpoint matters.
  Chat and Cowork are outside this matrix's current acceptance scope.
- **gemini** — hooks are NOT auto-wired by the installer: run `gemini hooks migrate --from-claude` once (move `.claude/settings.local.json` aside first — see context-keeper SKILL) for the PreCompress checkpoint, SessionEnd archive, and BeforeAgent canary/triage; verify on first live session.
- Any host: skills are text-portable; tools are plain python3/bash. If a rule references a hook this host lacks, the RULE still binds — you enforce it manually.

## Known parity limits

- A valid consumer `.codex/hooks.json` proves installation, not native event
  delivery. Keep live evidence per event; do not infer an entire lifecycle from
  one observed `Stop` archive.
- Claude plugin packaging must pass `claude plugin validate .` before any
  Claude Desktop Code install claim. Catalog synchronization alone is
  insufficient.
- `prompt-triage` and the `index-first` augment hook install only into Claude
  Code. `output-filter` has only a Claude Code hook recipe; its shell-pipe mode
  remains portable.
- `semantic-diff`'s slim CLI is portable, but its optional installer registers
  the MCP server through `claude mcp`, not Codex or Claude Desktop.
- `cache-lint` intentionally audits Claude Code cache/config/transcript surfaces;
  it is not a Codex or Claude Desktop cache audit.
- `brainer-audit` can normalize synthetic Codex hook payloads, but its installer
  writes events beyond the smallest consistently documented Codex lifecycle
  set. Treat native delivery of every audit event as unverified until a live
  host smoke test records each event.
- Repo-local Markdown/Python/Bash skills generally remain usable manually in
  Codex and Claude Code. A passing unit test proves the tool logic, not that a
  desktop host loaded the skill or delivered its hook. In Claude Desktop, a
  plugin may load a skill while a local CLI dependency used by that skill is
  still unavailable; classify those features separately.

## Skill disposition (all 31)

“Operational” below covers the skill body and bundled local tools. Optional
external dependencies still degrade exactly as documented by the skill.

| Skills | Codex Desktop | Claude Desktop Code | Simplest disposition |
|---|---|---|---|
| `baton`, `brainer`, `caveman-ultra`, `eval-gate`, `impact-of-change`, `loop-engineering`, `output-filter`, `propagate`, `security-oversight`, `semantic-diff`, `task-retrospective`, `team-lead`, `think`, `verify-before-completion`, `wiki-memory`, `wiki-refresh`, `write-gate` | Operational; host-native collaboration is used where available | Operational through the native plugin; `/think` UI visibility is live-observed | Keep the shared skill/tool implementation; capability-detect optional models, graph/MCP, and subagents |
| `brainer-audit` | Offline normalization works; full native event delivery is unverified | Skill/tools packaged; broad automatic audit hooks remain opt-in and are not in the default plugin hooks | Keep explicit/manual audit mode; do not auto-wire unproved events |
| `compliance-canary` | Consumer hook is installed and exact-once delivery is live-observed in both native Codex CLI and a fresh Codex Desktop task | Default `UserPromptSubmit` plugin hook is live-observed through the installed Claude Code carrier; mixed project/plugin delivery is single-shot | Retain one effective host-specific command and require per-host live evidence |
| `context-keeper` | `Stop` archive is live-observed; unsupported `PreCompact` is not wired | Desktop `/compact` checkpoint is live-observed; the Claude Code engine delivers `SessionEnd`, while closing the Desktop UI is not a session-end event | Use `/compact` when a durable Desktop checkpoint matters; no watcher or transcript scraper |
| `index-first` | Skill and CLI operational; automatic `PreToolUse` augmentation is not installed | Skill and CLI operational; plugin does not enable augmentation by default | Keep index-first as an explicit rule/CLI until a host event is deliberately enabled and tested |
| `learn-skill`, `prompt-triage` | Explicit/manual and opt-in as designed | Packaged as explicit/manual skills; no default hooks | Preserve `auto-install: false`; never turn evaluation arms into defaults for parity |
| `cache-lint` | Intentionally unsupported: it audits Claude Code-specific cache/config surfaces | Operational for the embedded Claude Code surface | Keep the limitation explicit; do not build a fake cross-host cache audit |
