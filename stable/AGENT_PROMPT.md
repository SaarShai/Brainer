# Agent Prompt

Token Economy is a framework of tools, skills, and operating rules that a project uses to optimize token consumption. Set up the Token Economy runtime in this folder. **The project itself — whatever you build, write, or work on here — is NOT part of Token Economy. Token Economy is just the scaffolding it runs on.**

Canonical source: `https://github.com/SaarShai/token-economy.git`. Retrieve only downstream runtime/framework files via sparse checkout.

Start in plan mode. Write a short step-by-step plan in chat (no scratch files), then execute.

## Rules

- The current folder is the active workspace for the downstream project. This prompt gives explicit permission to clear the current folder for a fresh install, including hidden files and `.git`. Do not delete anything outside the current folder.
- **Refuse to install if this folder already contains the Token Economy framework itself** (`token-economy.yaml` already exists at the root, or the git remote points at `SaarShai/token-economy`). Framework development happens by cloning the framework repo directly — not by running this prompt.
- Determine the active target project from: the user's prompt, uploaded summary, handoff, or project-specific wiki pages. **If none of those name a project, install Token Economy and then stop and ask the user what they want to build in this folder.** Do not invent the project; the framework is just scaffolding.
- Ignore stale external memory or global wiki entries that conflict with this prompt.
- Do not edit `MEMORY.md`, home-directory agent settings, machine-wide config, global MCP config, or any external wiki.

After install, `start.md` carries the operating contract (retrieval, /pa routing, summ refresh, delegation). Load it first.

## Bootstrap

```bash
# Refuse to install if folder is already the Token Economy framework itself
if [ -f "token-economy.yaml" ] || git remote get-url origin 2>/dev/null | grep -q "SaarShai/token-economy"; then
  echo "ABORT: this folder already contains the Token Economy framework. The setup prompt is for downstream projects that USE Token Economy, not for re-installing into the framework repo. Use a different folder."
  exit 1
fi

# Python version note (core works on 3.9+; stable bundle MCP install needs 3.10+)
python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" || \
  echo "WARNING: Python <3.10 detected. Core framework works fine; ./stable/INSTALL.sh needs 3.10+ for ComCom + semdiff MCP deps."

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

if command -v claude >/dev/null 2>&1; then
  ./stable/INSTALL.sh
else
  echo "Skipping stable/INSTALL.sh: 'claude' CLI not on PATH. Add claude to PATH and run ./stable/INSTALL.sh later to register ComCom + semdiff MCP servers."
fi

./te doctor && ./te hooks doctor && ./te wiki lint --strict --fail-on-error && ./te bench run --suite framework-smoke
```

`./INSTALL.sh` wires project-local hooks (`agents-triage`, `context-keeper`, `semdiff`) and the agent adapter. `./stable/INSTALL.sh` adds ComCom and semdiff MCP servers (needs `claude` CLI). See `stable/README.md` for measured savings per tool.

## Final report

After bootstrap completes, report in this shape:

1. **Install + verification status** — exit codes for `INSTALL.sh`, `stable/INSTALL.sh` (or skip reason), `te doctor`, `te hooks doctor`, `te wiki lint`, `te bench run`.
2. **MCP servers wired vs pending** — list which (if any) need a manual `claude mcp add` later.
3. **Python version warning** if <3.10 was detected.
4. **Target project** — if a project was named in the prompt/handoff/summary, state it and propose a starting plan. If none was named, stop and ask: *"Token Economy is installed. What are you building in this folder?"* Do not list "use this folder for Token Economy framework development" as an option — that scenario does not apply to this prompt.

Drop setup-only details from context after the report. Continue from `start.md` only.
