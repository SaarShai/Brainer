# Agent Onboarding

Use Token Economy in the current target repo only. The repo-local markdown wiki is the source of truth.

## Fresh Setup

For a fresh target folder, clear the current folder only, including hidden files and `.git`, then retrieve the downstream runtime/framework files:

```bash
find . -mindepth 1 -maxdepth 1 -exec rm -rf {} +
git clone --depth 1 --filter=blob:none --sparse https://github.com/SaarShai/token-economy.git .
git sparse-checkout set --no-cone \
  '/.gitignore' '/AGENTS.md' '/CLAUDE.md' '/GEMINI.md' \
  '/INSTALL.md' '/INSTALL.sh' '/LICENSE' \
  '/L0_rules.md' '/L1_index.md' '/index.md' '/models.yaml' '/schema.md' \
  '/start.md' '/te' '/token-economy.yaml' \
  '/token_economy/*' '/adapters/*' '/hooks/*' '/hooks/output-filter/*' '/templates/*' \
  '/prompts/*.md' '/prompts/subagents/*' \
  '/projects/agents-triage/*' '/projects/compound-compression-pipeline/*' \
  '/projects/context-keeper/*' '/projects/semdiff/*' \
  '/skills/caveman-ultra/*' '/skills/context-refresh/*' \
  '/skills/lean-execution/*' '/skills/personal-assistant/*' \
  '/skills/plan-first-execute/*' '/skills/relay-sessions/*' \
  '/skills/subagent-orchestrator/*' '/skills/verification-before-completion/*' \
  '/skills/wiki-retrieve/*' '/skills/wiki-write/*' \
  '/stable/INSTALL.sh' '/stable/*'
rm -rf .git
git init
```

Do not delete anything outside the current folder.
Start by writing a short step-by-step plan in chat, then execute it.

Then run:

```bash
./INSTALL.sh --dry-run
./INSTALL.sh --scope project --agent auto
command -v claude >/dev/null && ./stable/INSTALL.sh   # registers ComCom + semdiff MCP servers
./te doctor
./te hooks doctor
./te wiki lint --strict --fail-on-error
./te wiki search "start"
./te context status
```

## Rules

- Work only inside the current working folder.
- Do not edit home-directory agent settings, machine-wide config, global MCP config, or external wikis.
- After install, `start.md` is the operating contract — load it for retrieval, /pa routing, summ refresh, and delegation.

## After Setup

Drop setup-only details from context. Keep only the repo root, `start.md`, `token-economy.yaml`, and the `./te` command surface. Report changed files, verification results, and remaining risk.
