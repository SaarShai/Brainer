# Install Token Economy Framework

Token Economy is a framework of tools, skills, and operating rules that a project uses to optimize token consumption. The framework is **scaffolding** — the project that uses it (whatever you build, write, or work on) is **not part of Token Economy**.

Project-local install (in an existing project that already contains the framework files):

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

In a new empty target project folder, retrieve only the downstream runtime/framework files. Refuse to run if this folder already contains the framework itself.

```bash
# Refuse to install if this folder is already the Token Economy framework
if [ -f "token-economy.yaml" ] || git remote get-url origin 2>/dev/null | grep -q "SaarShai/token-economy"; then
  echo "ABORT: folder already contains the Token Economy framework. Use a different folder."
  exit 1
fi

# Python version note (core works on 3.9+; stable bundle MCP install needs 3.10+)
python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" || \
  echo "WARNING: Python <3.10 detected. ./stable/INSTALL.sh needs 3.10+ for ComCom + semdiff MCP deps."

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
command -v claude >/dev/null && ./stable/INSTALL.sh   # registers ComCom + semdiff MCP servers (skipped if claude CLI missing)
./te doctor && ./te hooks doctor && ./te wiki lint --strict --fail-on-error
```

This permission applies only to the current target folder named by the user. Do not delete parent folders or files elsewhere. The framework does not install global agent settings.
