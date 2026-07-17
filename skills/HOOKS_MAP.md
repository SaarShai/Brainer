# Hooks map (generated — do not edit; `python3 scripts/gen_hooks_map.py`)

One-page answer to "what hooks exist / where's the entry / installer".
Read THIS instead of walking skills/*/tools/ file by file.

| Skill | Hook event(s) | Entry | Installer |
|---|---|---|---|
| brainer-audit | PostCompact, PostToolUse, PreCompact, PreToolUse, Stop, UserPromptSubmit | `skills/brainer-audit/tools/hook.py` | `skills/brainer-audit/tools/install.sh` |
| compliance-canary | UserPromptSubmit | `skills/compliance-canary/tools/hook.py`<br>`skills/compliance-canary/tools/hook.sh` | `skills/compliance-canary/tools/install.sh` |
| context-keeper | PreCompact, SessionEnd, Stop | `skills/context-keeper/tools/hook.py`<br>`skills/context-keeper/tools/hook.sh` | `skills/context-keeper/tools/install.sh` |
| prompt-triage | UserPromptSubmit | `skills/prompt-triage/tools/hook.sh` | `skills/prompt-triage/tools/install.sh` |

LIVE wiring state is machine-local: check `.claude/settings.json`.
Per-skill installers append hook entries; `./install.sh` prunes dead
hooks and managed hooks for skills now marked `auto-install: false`.
`output-filter`
ships tooling but no auto-installer by design (wire as pipe or
PostToolUse by hand).
