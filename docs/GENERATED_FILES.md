# Generated files and sources of truth

Brainer must not drift. This page defines which files are canonical, which files are generated, derived, synchronized, or local runtime state, and which check guards each surface.

## Rules

1. Edit canonical sources first.
2. Do not hand-edit generated sections between sentinels.
3. Regenerate or run the checker named below before claiming consistency.
4. `make check` is the repo-wide gate.
5. Do not delete local runtime or audit artifacts just because they look generated; classify first.

## File map

| Path | Role | Source of truth | Generator or checker | Manual edits? | Drift action |
|---|---|---|---|---|---|
| `skills/*/SKILL.md` | Canonical skill bodies | Skill authoring | `scripts/lint_skill_md.py`, `scripts/check_skill_contracts.py` | Yes | Fix metadata/body, then run `make check`. |
| `schema/skill.schema.json` | Skill metadata contract | This schema and `docs/ADDING_A_SKILL.md` | `scripts/check_skill_contracts.py` | Yes | Keep checker and docs aligned. |
| `schema/skill_conflicts.json` | Conflict resolution registry | Known skill interaction decisions | `scripts/check_skill_conflicts.py` | Yes | Add accepted/resolved conflicts; unresolved entries fail. |
| `skills/SKILLS_INDEX.md` | Skill catalog index | `skills/*/SKILL.md` | `scripts/check_skill_contracts.py` | Yes, until a generator owns it | Ensure every disk skill and indexed skill agree. |
| `skills/HOOKS_MAP.md` | Generated hook map | Hook-capable skills and hook tooling | `scripts/gen_hooks_map.py`, `scripts/check_skill_contracts.py` | No | Regenerate with `python3 scripts/gen_hooks_map.py` if hook tooling changes. |
| `AGENTS.md` | Codex/Copilot host carrier | `skills/*/SKILL.md` and `install.sh` catalog renderer | `install.sh`, `scripts/check_carrier_sync.py` | Avoid edits inside sentinels | Run `./install.sh --dry-run`, then `./install.sh` if catalog drift is intended. |
| `CLAUDE.md` | Claude host carrier | `skills/*/SKILL.md` and `install.sh` catalog renderer | `install.sh`, `scripts/check_carrier_sync.py` | Avoid edits inside sentinels | Regenerate with installer when the catalog changes. |
| `GEMINI.md` | Gemini host carrier | `skills/*/SKILL.md` and `install.sh` catalog renderer | `install.sh`, `scripts/check_carrier_sync.py` | Avoid edits inside sentinels | Regenerate with installer when the catalog changes. |
| `.codex/hooks.json` | Codex hook config | Hook decisions in repo config | `scripts/check_generated_files.py` | Only when changing hook wiring | Keep documented and valid JSON. |
| `.codex/skills/` | Per-machine install target | `skills/*` symlinks | `install.sh` | No | Re-run installer; do not treat symlink fanout as canonical. |
| `.gemini/settings.json` | Gemini skill-dir config | Installer settings model | `install.sh`, `scripts/check_generated_files.py` | Only intentional host config edits | Keep minimal and valid JSON. |
| `.gemini/skills/` | Per-machine install target | `skills/*` symlinks | `install.sh` | No | Re-run installer; do not treat symlink fanout as canonical. |
| `.cursor/rules/` | Cursor rule shims | `skills/*/SKILL.md` descriptions | `install.sh` | No | Re-run installer after skill catalog changes. |
| `.claude/settings.json` | Repo-local Claude hook state | Per-skill installers and user hook choices | `install.sh`, hook installers | Cautious, host-specific | Back up or dry-run before changing; live hook state may be machine-local. |
| `.claude-plugin/marketplace.json` | Claude plugin metadata | Skill list and package metadata | `scripts/check_marketplace_sync.py` | Yes, when plugin metadata changes | Keep `skills[]` and prose counts in sync with disk. |
| `.github/workflows/framework_ci.yml` | CI check carrier | `Makefile` and repo test policy | GitHub Actions, `make check` | Yes | CI must run the same canonical local command. |
| `wiki/*.md` | Canonical durable memory | Reviewed markdown decisions, procedures, and facts | `scripts/check_wiki_hygiene.py`, wiki tooling | Yes | Update markdown first; derived indexes follow. |
| `.brainer/wiki.sqlite3` | Derived wiki index | `wiki/*.md` | wiki tooling | No | Rebuild from wiki tooling if stale; never treat as canonical memory. |
| `.brainer/` | Local runtime state umbrella | Hook/tool runtime state and audit outputs | `.gitignore`, runtime tools | No | Ignored local state; classify durable findings into docs or `wiki/`. |
| `.brainer/audit_results.json` | Local audit output | Audit workflow run | Documented as local runtime state | Usually no | Keep local unless intentionally promoted into docs or wiki. |
| `.brainer/audit_workflow.js` | Local audit workflow output | Audit workflow run | Documented as local runtime state | Usually no | Keep local unless intentionally promoted into docs or wiki. |
| `.brainer/verify_results.json` | Local verification output | Verification workflow run | Documented as local runtime state | Usually no | Keep local unless intentionally promoted into docs or wiki. |
| `.brainer/verify_workflow.js` | Local verification workflow output | Verification workflow run | Documented as local runtime state | Usually no | Keep local unless intentionally promoted into docs or wiki. |
| `.brainer/ledger/` | Local requirements ledger state | Per-session requirements-ledger runtime | requirements-ledger/compliance-canary | No | Runtime state; do not promote unless summarized into durable docs. |
| `.brainer/task-retrospective/` | Local task audit evidence | Armed task-retrospective runs | `skills/task-retrospective/tools/task_audit.py` | No | Runtime state; keep ignored, then promote accepted durable lessons through project memory/SOP/checklist/skill targets. |
| `.brainer/brainer-audit/` | Local Brainer audit events/reports | Brainer audit mode | `skills/brainer-audit/tools/` | No | Runtime state; keep ignored unless an accepted candidate improvement is promoted into a reviewed PR. |
| `.brainer/sessions/` | Local session state | Hook/runtime sessions | runtime tools | No | Runtime state; keep ignored. |
| `.cache-lint-fingerprint.json` | Local cache-lint fingerprint | Last cache-lint run | `skills/cache-lint/tools/cache_lint.py` | No | Ignored runtime state; regenerate by running cache-lint. |
| `.deepeval/` | Local telemetry/cache | DeepEval runs | Eval tooling | No | Ignored runtime state. |
| `scratch/` | Local scratch outputs | The command or session that produced them | None | No, unless promoted | Ignored runtime state; promote durable findings into `wiki/` or docs. |
| `eval/results/` | Committed evaluation baselines plus ignored run logs | Eval harness | Eval scripts | Yes, when updating baselines | Keep committed baselines intentional; ignore transient run logs. |
| `.gitignore` | Local artifact classification | Repo policy | `scripts/check_generated_files.py` doc coverage | Yes | Add only future-noise patterns; do not untrack artifacts without a decision. |

## How to check

Run:

```bash
make check
```

The generated-file part is:

```bash
python3 scripts/check_generated_files.py
```

That checker verifies this page covers the high-risk generated or synchronized surfaces, confirms required files exist, and checks that `README.md` points future agents to the source-of-truth docs.

## How to regenerate

- Host carrier catalogs: `./install.sh --dry-run`, then `./install.sh` when the planned changes are correct.
- Hook map: `python3 scripts/gen_hooks_map.py`.
- Per-host symlink/rule fanout: `./install.sh --host <claude-code|codex|cursor|gemini>`.
- Wiki indexes: use the `wiki-memory` tooling documented in `docs/MEMORY_MODEL.md`.

## What not to delete

Do not delete `.brainer/`, `scratch/`, `.deepeval/`, or eval artifacts during drift cleanup unless you have evidence they are disposable and the user has approved deletion. Classify first, then promote durable facts into `wiki/` or docs.
