# Agent Onboarding

Token Economy is a framework of tools, skills, and operating rules that a project uses to optimize token consumption. The framework is **scaffolding** — the project that uses it (whatever the user is building) is **not part of Token Economy**. Use Token Economy in the current target repo only. The repo-local markdown wiki is the source of truth.

## Fresh Setup

For a fresh target folder, clear the current folder only, including hidden files and `.git`, then retrieve the downstream runtime/framework files. Refuse to run if this folder is already the framework itself.

```bash
# Refuse to install if this folder already contains the Token Economy framework
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
- If no target project is specified in the user's prompt/handoff/summary, ask what they're building in this folder. Do not invent a project; the framework is just scaffolding. "Use this folder for Token Economy framework development" is **not** an option — framework dev is done by cloning the framework repo directly, not by running this onboarding flow.

## After Setup

Drop setup-only details from context. Keep only the repo root, `start.md`, `token-economy.yaml`, and the `./te` command surface. Report changed files, verification results, MCP servers wired vs pending, Python version warning if any, and the target project (or stop and ask if none was named).
