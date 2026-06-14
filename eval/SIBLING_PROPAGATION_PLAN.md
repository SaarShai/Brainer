# Sibling propagation plan (archived hand-offs, 2026-06-14)

Archived from two background-task chips so the verified plan isn't lost. Run
`python3 scripts/sibling_sync_audit.py --files` first to refresh state. Siblings
are deeply forked (50–69 files differ each) — propagate per-file, never blind rsync.

## A. PROMPTER (Alfred) — dedupe + drop dead stubs

- **Duplicate skill:** `skills/verification-before-completion/` (old) vs
  `skills/verify-before-completion/` (canonical) — 6+ near-identical directive
  lines, same description prefix. Remove one; CAUTION: `verification-before-completion`
  is referenced in INSTALL.md, GEMINI.md, AGENTS.md, start.md, stable/AGENT_PROMPT.md,
  CLAUDE.md, prompts/managing-director-setup.md, prompts/complete-migrate-import.md —
  repoint all to the chosen canonical, re-run `./install.sh`, then `bash scripts/run_all_tests.sh`.
- **Dead stubs** ("Folder kept only to preserve history; no longer loaded by start.md"):
  `skills/context-refresh/`, `skills/wiki-retrieve/`, `skills/wiki-write/` — confirm
  unloaded (grep start.md + install.sh), then delete or move out of `skills/`.
- (tokens.py dedup + BOM/twin fixes already applied to PROMPTER, commit 34697b4.)

## B. Five vendored forks — propagate the 8 Brainer bug-fix files

Bug-fix files (current fixed versions live in Brainer):
`semantic-diff/tools/semdiff/{core.py,rename_detect.py}`,
`compliance-canary/tools/{measure.py,hook.py}`, `prompt-triage/tools/hook.sh`,
`caveman-ultra/drift_probes.json`, and the brand-bearing
`wiki-memory/tools/{config.py,code_map.py}` (CONFIG_NAME / SKIP_PARTS).
Also propagate the newer COH fixes where in-sync: BOM-tolerant frontmatter regex in
`skill-pulse/tools/hook.py` + `context-keeper/tools/extract.py`; delete dead
`tokens.py` clones (keep only the one `code_map.py` imports).

Per-repo (git-archaeology-verified classification):

| repo | non-brand files | config.py / code_map.py | canary hook.py / measure.py |
|---|---|---|---|
| Hermes | safe overwrite (clean ancestors) | **pre-rebrand brand** → delta-merge, keep local brand | safe overwrite |
| animayte | safe overwrite | **brainer brand** → safe overwrite | safe overwrite |
| farey-hecke | safe overwrite | brainer brand → safe overwrite | safe overwrite |
| screenery-lean | safe overwrite | brainer brand → safe overwrite | safe overwrite |
| token-economy | safe overwrite (core, rename, hook.sh, drift_probes) | **token-economy brand** → delta-merge | **CUSTOMIZED (local `llm_judge` subsystem) → do NOT overwrite**; hand-merge deltas or skip |

For each repo: edit → run its `scripts/run_all_tests.sh` (semantic-diff needs
tree-sitter) → commit only if green → do NOT push without the user's go-ahead
(independent repos).
