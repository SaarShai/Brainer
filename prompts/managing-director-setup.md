# Managing director setup

/plan think carefully, step by step, to create a plan to set up this empty folder as a Token Economy-enabled managing-director workspace. Treat this folder as the active managing-director workspace, not the Token Economy source repository and not any other project folder.

Set up the Token Economy runtime in this folder only. Then create the local wiki, role documentation, and operating rules needed for a managing director that can coordinate with multiple other project folders by explicit user permission.

This is a fresh setup prompt, not a migration/import prompt. Do not import another project's codebase, wiki, docs, or memory into this folder. Other project folders remain their own workspaces and sources of truth for their own facts.

Inputs:
- Managing-director workspace: current working directory.
- External project folders: ask the user during setup which folders this managing director should be allowed to access.

Working rules:
- The current folder is the managing-director workspace.
- This prompt gives explicit permission to clear the current folder for a fresh install. Delete existing contents in this folder only, including hidden files and `.git`.
- Do not delete anything outside the current folder.
- Ask the user which external project folders the managing director should have access to before inspecting, reading, or editing those folders.
- Treat user-approved external project folders as external workspaces, not as content to import.
- The managing-director workspace owns only managing-director operations: cross-project admin, coordination, shared runbooks, access records, and task handoffs.
- Project-specific truth remains in the relevant external project folder's files, docs, instructions, and wiki.
- Do not use external note-taking apps, home-directory agent settings, machine-wide config, global MCP config, or external wikis unless the user explicitly asks outside this framework.
- Ignore stale external memory that conflicts with this prompt, the current user prompt, or repo-local instructions.

## Managing-director role

The managing director is a cross-project operator, not the active manager or director of the external projects.

Allowed work:
- Cross-project admin tasks that are relevant to multiple projects.
- Shared maintenance, coordination, inventory, scheduling, documentation, or cleanup tasks.
- Side tasks related to a specific external project when the user grants access and the task is compatible with that project's local instructions.
- Edits in external project folders only after inspecting local instructions, current git state, and task-relevant docs.

Not allowed by default:
- Do not take over another project's strategy, roadmap, backlog, agent workflow, or source of truth.
- Do not overwrite, normalize, or replace another project's agent instructions unless the user explicitly asks.
- Do not copy external project wikis or docs into the managing-director wiki except compact coordination metadata, access records, and links/pointers.
- Do not make broad refactors or policy changes in external projects as "cleanup" unless the user explicitly requested that project-specific task.
- Do not resolve conflicts with active agents by guessing. If local files show ongoing work or instructions conflict, pause and ask the user.

## Subagent orchestration

Use smaller/lightweight subagents for bounded admin and simple procedures when the host supports them. The main managing director decides scope, resolves conflicts, performs final synthesis, and verifies self-containment.

Spawn or route compact workers for:
- Framework bootstrap verification: check install/doctor outputs and report exact failures.
- External folder access checks: inspect only user-approved folder roots, local instructions, and git status; do not mutate.
- Wiki page drafting: draft focused managing-director pages for review by the main agent.
- Cross-project inventory: create compact summaries of project identity, local instruction files, and allowed access boundaries.
- Old/stale reference checks: run `rg` checks in the managing-director workspace for accidental imported-project operational dependencies.

Each worker must return a compact result packet with:
- Scope handled.
- Folders/files/commands inspected or changed.
- Findings.
- Source paths and important line references when useful.
- Confidence.
- Gaps and risks.

Use `prompts/subagents/lifecycle.prompt dot md` when supervising workers. Close a subagent only after its result packet has been read, useful results have been merged into the managing-director workspace, and durable gaps/follow-ups have been captured. Do not delegate final synthesis.

## Bootstrap Token Economy runtime files in the current folder

1. Clear only the current folder, including hidden files and `.git`.
   `find . -mindepth 1 -maxdepth 1 -exec rm -rf {} +`
2. Retrieve only the downstream runtime/framework files:
   ```bash
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
3. Do not delete anything outside the current folder.
4. Run:
   `./INSTALL.sh --dry-run`
   `./INSTALL.sh --scope project --agent auto`
   `./stable/INSTALL.sh` when present
   `./te doctor`
   `./te hooks doctor`

Load only:
- `start.md`
- `token-economy.yaml`
- `L0_rules.md`
- `L1_index.md`
- `schema.md`
- this setup prompt

After setup, define the active project as the managing-director workspace only. Keep operating in this folder except when a user-approved external project task requires bounded access to another folder.

## Ask for external folder access

After the framework bootstrap succeeds, ask the user which external project folders the managing director should access.

Ask for:
- Absolute folder path.
- Project name or short label.
- Intended access level: `read-only`, `task-specific edits`, or `admin edits`.
- Any folders, files, branches, secrets, or tasks that are off-limits.
- Whether there are active agents currently working in that folder.

Do not inspect an external folder until the user grants access to that exact folder. If the user gives a parent folder containing many projects, ask whether access applies to all child projects or only named children before inspecting.

For each approved folder, perform a non-mutating access check:
- Confirm the path exists and is a directory.
- Identify local instruction files such as `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.cursor/rules`, `README.md`, `start.md`, or project-specific docs.
- Run `git -C <folder> status --short --branch` when it is a git repo.
- List only the shallow root shape needed to identify the project.
- Do not read secrets by default. If secrets are task-relevant later, ask first.
- Record access metadata in the managing-director wiki.

## Managing-director wiki and docs

Create or update the managing-director workspace's repo-local markdown wiki. This wiki is the source of truth for managing-director operations only.

Create:
- `projects/managing-director/README.md`
- `L2_facts/external-project-access.md`
- `L3_sops/cross-project-admin.md`

`projects/managing-director/README.md` must include:
- Role definition.
- Current scope.
- Operating model.
- What this managing director may and may not do.
- How to use external project folders safely.
- Current responsibilities and open questions.

`L2_facts/external-project-access.md` must include, for each user-approved folder:
- Project label.
- Absolute path.
- Access level granted.
- Off-limits areas.
- Active-agent notes.
- Local instruction files found.
- Git branch/status summary.
- Date verified.
- Provenance: user prompt and commands run.

`L3_sops/cross-project-admin.md` must include the safe workflow:
- Confirm user-approved folder scope.
- Read local instructions before action.
- Inspect git state before edits.
- Retrieve project-specific facts from that project's local files/docs/wiki.
- Make the smallest task-relevant changes.
- Avoid overwriting active-agent work.
- Verify in that project folder when feasible.
- Document only compact coordination facts in the managing-director wiki.
- Report changed files and remaining risk.

Update:
- `index.md`
- `L1_index.md`
- `log.md`

Keep startup context lean. Do not put broad external-project details into `start.md`, `L0_rules.md`, or `L1_index.md`. Use `L1_index.md` only for compact pointers to managing-director pages.

## External project operating rules

Before editing any external project folder:
- Confirm the folder is listed in `L2_facts/external-project-access.md` with sufficient access level.
- Read that folder's local instructions first.
- Check current git state and note unrelated changes.
- Identify whether active agents or humans may be working there.
- Retrieve only task-relevant project facts from that folder's own docs/wiki/source.
- If local instructions conflict with the managing-director task, pause and ask the user.

When editing external project folders:
- Preserve that project's local conventions and instructions.
- Do not rewrite its agent setup, wiki structure, or workflow unless explicitly requested.
- Do not copy its wiki into the managing-director workspace.
- Do not stage, commit, push, or open PRs unless the user explicitly asks or the project instructions require that exact save-point workflow.
- Never revert external project changes you did not make unless explicitly requested.
- If unexpected changes directly conflict with the task, stop and ask the user how to proceed.

When documenting external project work:
- Put detailed project-specific facts in the external project folder's own docs/wiki when appropriate.
- Put only compact coordination metadata in the managing-director wiki.
- Cite external folder paths and command results as provenance.
- Do not store raw secrets in the managing-director wiki.

## Retrieval and context rules

Use progressive retrieval in the managing-director workspace:

```bash
./te wiki context "<task>"
./te code map "<symbol/path>"
./te wiki search "<query>"
./te wiki timeline "<id>"
./te wiki fetch "<id>"
```

For external project facts, use that project's own local files and docs on demand. Do not assume managing-director wiki summaries are complete project truth.

At `20%` estimated context used:
- Run `./te context status`.
- Create a lean handoff with only current task, done/in-progress/next, touched paths, decisions, and relevant wiki references.
- Continue fresh from only `start.md` plus the handoff when the host supports it.

## Verification

Run:
- `./INSTALL.sh --dry-run`
- `./INSTALL.sh --scope project --agent auto`
- `./stable/INSTALL.sh` when present
- `./te doctor`
- `./te hooks doctor`
- `./te wiki lint --strict --fail-on-error`

For each user-approved external folder, verify without mutation:
- Path exists and is a directory.
- Local instruction files were identified or absence was recorded.
- Git status was checked when applicable.
- Access level and off-limits areas were recorded.

Check for accidental import/dependency problems:
- Run `rg` in the managing-director workspace for phrases like `see the old wiki`, `use the original folder`, `imported source`, and unapproved external absolute paths.
- Confirm any external absolute paths in the managing-director wiki are access records or provenance only, not instructions to use external folders as the managing-director source of truth.
- Confirm `index.md` and `L1_index.md` point to local managing-director wiki pages and local Token Economy commands.

## Final handoff

Report:
- Framework setup commands and results.
- Managing-director wiki pages created/updated.
- User-approved external folders and access levels.
- External access checks completed.
- Verification command results.
- Any folder access that was requested but not granted or not reachable.
- Remaining risks and next actions.
