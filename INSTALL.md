# Install Token Economy Framework

Project-local install:

```bash
./INSTALL.sh --scope project
```

Dry run:

```bash
./INSTALL.sh --dry-run
```

What it checks:
- `te doctor`
- `te hooks doctor`
- `te wiki index`
- adapter copy via `te start`
- repo-local install helpers when their files are present

## Fresh Target Project Setup

In a new empty target project folder, retrieve only the downstream runtime/framework files:

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
./INSTALL.sh --dry-run
./INSTALL.sh --scope project --agent auto
command -v claude >/dev/null && ./stable/INSTALL.sh   # registers ComCom + semdiff MCP servers
./te doctor && ./te hooks doctor && ./te wiki lint --strict --fail-on-error
```

This permission applies only to the current target folder named by the user. Do not delete parent folders or files elsewhere.

The framework does not install global agent settings.
