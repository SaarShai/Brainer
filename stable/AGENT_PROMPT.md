# Agent Prompt

Set up the Token Economy runtime in this folder, then use it for the user's target project. Canonical source: `https://github.com/SaarShai/token-economy.git`. Retrieve only downstream runtime/framework files via sparse checkout.

Start in plan mode. Write a short step-by-step plan in chat (no scratch files), then execute.

Rules:
- The current folder is the active workspace. This prompt gives explicit permission to clear the current folder for a fresh install, including hidden files and `.git`. Do not delete anything outside the current folder.
- Determine the active target project only from the user's prompt, uploaded summary, handoff, or project-specific wiki pages.
- Ignore stale external memory or global wiki entries that conflict with this prompt.
- Do not edit `MEMORY.md`, home-directory agent settings, machine-wide config, global MCP config, or any external wiki.

After install, `start.md` carries the operating contract (retrieval, /pa routing, summ refresh, delegation). Load it first.

## Bootstrap

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

if command -v claude >/dev/null 2>&1; then
  ./stable/INSTALL.sh
else
  echo "Skipping stable/INSTALL.sh: 'claude' CLI not on PATH. Run ./stable/INSTALL.sh later to register ComCom + semdiff MCP servers."
fi

./te doctor && ./te hooks doctor && ./te wiki lint --strict --fail-on-error && ./te bench run --suite framework-smoke
```

`./INSTALL.sh` wires project-local hooks (`agents-triage`, `context-keeper`, `semdiff`) and the agent adapter. `./stable/INSTALL.sh` adds ComCom and semdiff MCP servers (needs `claude` CLI). See `stable/README.md` for measured savings per tool.

Drop setup-only details from context after install.
