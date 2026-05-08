# Complete migrate import

/plan think carefully, step by step, to create a plan to import a complete-migrate export into a new target working folder that will use Token Economy as local scaffolding. Treat this folder as the active workspace, not the Token Economy source repository.

Import a complete-migrate export into the current new working folder. The result must be self-contained: after import, all operational project files, local wiki pages, instructions, skills/adapters, config templates, and runbooks needed to continue the project must live in this folder, except external tools/services/models/APIs that intentionally remain outside the project folder.

Inputs:
- Complete-migrate export file: the uploaded file, usually `[project-name]_complete_migrate_export.md`
- New target folder: current working directory

Working rules:
- Set everything you need in this working folder, and nothing you do not need.
- Use the export's `Source Location Index` and `Transfer Manifest` as the migration source of truth.
- Clone, copy, recreate, or adapt any file or information from referenced or linked folders that is needed to make the working folder self-sufficient.
- Exclude anything that is not relevant to continuing the project.
- After importing, operational instructions must not require the old folder or old wiki.
- Actively learn from the uploaded file and adapt the information to the Token Economy setup in this working folder.
- Understand the processes and systems described or implied in the uploaded file, then create a similar system for yourself that is adapted to the way you work.

## Subagent orchestration

Use smaller/lightweight subagents for bounded admin and simple procedures when the host supports them. The main agent decides project structure, resolves conflicts, performs final synthesis, and verifies self-containment.

Spawn or route compact workers for:
- Framework bootstrap verification: check install/doctor outputs and report exact failures.
- Safe file copying: copy only `copy` items from the `Transfer Manifest`, preserve relative paths where safe, and do not overwrite Token Economy framework paths.
- Simple wiki page drafting: draft focused pages from export sections for review by the main agent.
- Old-path reference search: run `rg` checks for old root/source-wiki paths and classify remaining hits.
- Manifest coverage checks: compare imported files/wiki pages against the `Transfer Manifest` and import manifest.

Each worker must return a compact result packet with:
- Scope handled.
- Files/pages/commands inspected or changed.
- Findings.
- Source paths and important line references when useful.
- Confidence.
- Gaps and risks.

Use `prompts/subagents/lifecycle.prompt.md` when supervising workers. Close a subagent only after its result packet has been read, useful results have been merged into the import, and durable gaps/follow-ups have been captured. Do not delegate final synthesis.

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
   `./stable/INSTALL.sh`
   `./te doctor`
   `./te hooks doctor`
   The MCP install step is required, not optional: install ComCom, semdiff, and context-keeper when those files are present.

Load only:
- `start.md`
- `token-economy.yaml`
- `L0_rules.md`
- `L1_index.md`
- `schema.md`
- the uploaded file

After setup, define the active project only from the uploaded complete-migrate export and the user's current instructions. Keep operating in this working folder.

Use the uploaded file as the migration source of truth. It may contain raw secrets. Keep the uploaded file, `.env`, raw secret files, credentials, and any copied secret material out of the wiki and committed guidance.

## Self-contained project transfer

Use the export's `Transfer Manifest`:
- `copy`: copy the source item into the new working folder.
- `adapt`: rewrite the source item into Token Economy wiki/docs/config or adjust paths/settings for the new folder.
- `regenerate`: recreate it from commands, templates, package managers, or build steps.
- `reference-only`: use it as evidence during import but do not carry it forward operationally.
- `secret-local`: recreate it locally outside wiki/committed guidance with raw value handled only in local secret/config files.
- `archive`: keep only as cold history/warning under `L4_archive/` when useful.
- `discard`: omit it and record why in the import manifest.

Preserve relative paths where safe. Do not overwrite Token Economy framework paths such as `start.md`, `te`, `token_economy/`, framework `prompts/`, framework `skills/`, `templates/`, `schema.md`, `L0_rules.md`, `L1_index.md`, `index.md`, or wiki scaffolding. If a source-project file conflicts with framework paths, adapt it into local project docs/wiki pages or place sealed source evidence under `raw/imported-source/`.

Rewrite operational references from old absolute paths to the new working folder. Old project paths and old wiki paths may appear only as sealed provenance in `raw/` source notes or the import manifest, not as operational instructions.

Create or update local setup files, config templates, project-specific instructions, adapters, scripts, and README content so the new project can continue without reading the old folder.

## Rebuild the wiki directly in repo-local markdown

This is a wiki transplant, not a pointer back to the source wiki:
- Treat the original wiki as source evidence only. After import, project facts must come from this working folder's repo-local wiki.
- Create `raw/YYYY-MM-DD-import-manifest.md` from `templates/import-manifest.template.md`.
- The import manifest must cover every original wiki item listed in the uploaded file: original page/path, summary, target local page, status (`adapted`, `archived`, or `discarded`), rationale, and provenance.
- Put source summaries and imported source evidence under `raw/`.
- Put active project state under `projects/`.
- Put verified durable facts under `L2_facts/`.
- Put reusable workflows and runbooks under `L3_sops/`.
- Put decisions into decision/project pages.
- Put durable Q&A into `queries/`.
- Put cold stale material into `L4_archive/` only when it is useful as warning/history.
- Create or update `README.md` for the imported target project from the uploaded summary.
- Update `index.md`, `L1_index.md`, and `log.md`.

## Adapt the source wiki to Token Economy

- Convert existing wiki links/naming into repo-local markdown wikilinks such as `[[projects/example/README]]`.
- Rewrite source-wiki information into better organized Token Economy pages instead of copying a flat dump.
- Preserve provenance from the complete-migrate export in every material page.
- Split large notes into focused pages when that improves retrieval and combine tiny duplicates when that improves access.
- Keep startup context lean; do not move broad target-project details into `start.md`, `L0_rules.md`, or `L1_index.md`.
- Import raw secrets into local config/env files only as appropriate for the project. Keep secret files local and out of the wiki.
- Preserve working commands, exact paths, setup steps, known failure fixes, durable decisions, facts, SOPs, and reusable lessons.
- Discard context rot listed in the summary only when the import manifest records why; archive stale material only when it is useful as a warning.
- Never leave synthesized pages that tell the next agent to "see the old wiki", "use the original wiki", "use the original folder", or follow external/home-directory wiki rules.
- Original wiki paths may appear only as sealed provenance in `raw/` source notes or the import manifest, not as operational instructions.

## Verification

- Run `./te wiki lint --strict --fail-on-error`.
- Run `./te wiki import-audit --manifest raw/YYYY-MM-DD-import-manifest.md`.
- Run `./te doctor`.
- Run any project-specific smoke checks listed in the uploaded file when they are safe and do not require unavailable external services.
- Run `rg` checks for the old project root and old source-wiki root.
- Confirm remaining old-path hits are provenance-only under `raw/` or the import manifest.
- Confirm required copied/adapted source files, config templates, docs, scripts, and wiki pages exist in the new folder.
- Confirm copied/adapted instructions point to the new working folder.
- Confirm no secret files or the uploaded file were written into the wiki or committed guidance.
- Confirm `index.md` and `L1_index.md` point to the new local wiki only.

## Final handoff

- What was imported.
- What was intentionally discarded.
- Import manifest path and coverage count.
- Transfer Manifest coverage: copied, adapted, regenerated, archived, discarded, secret-local, and reference-only counts.
- Where secrets now live locally.
- Wiki pages created/updated.
- Self-containment verification results.
- Verification command results.
- Remaining gaps and next actions.
