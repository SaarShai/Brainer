# Hooks map (generated — do not edit; `python3 scripts/gen_hooks_map.py`)

One-page answer to "what hooks exist / what's wired / where's the entry".
Read THIS instead of walking skills/*/tools/ file by file.

| Skill | Hook event(s) | Wired here? | Entry | Installer |
|---|---|---|---|---|
| compliance-canary | UserPromptSubmit | UserPromptSubmit | `skills/compliance-canary/tools/hook.py`<br>`skills/compliance-canary/tools/hook.sh` | `skills/compliance-canary/tools/install.sh` |
| context-keeper | PreCompact | PreCompact | `skills/context-keeper/tools/hook.py`<br>`skills/context-keeper/tools/hook.sh` | `skills/context-keeper/tools/install.sh` |
| prompt-triage | UserPromptSubmit | UserPromptSubmit | `skills/prompt-triage/tools/hook.sh` | `skills/prompt-triage/tools/install.sh` |
| skill-pulse | Stop, UserPromptSubmit | UserPromptSubmit | `skills/skill-pulse/tools/hook.py`<br>`skills/skill-pulse/tools/hook.sh` | `skills/skill-pulse/tools/install.sh` |

Wiring lives in `.claude/settings.json` (repo-local). Per-skill installers
append hook entries and never delete; `./install.sh` prunes dead Brainer
hooks on re-install. `output-filter` ships tooling but no auto-installer
by design (wire as pipe or PostToolUse by hand).
