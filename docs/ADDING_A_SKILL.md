# Adding a skill

This checklist is for future agents and the user. It is not contributor ceremony; it is how Brainer avoids skill and carrier drift.

## Rule 1: edit the canonical skill

Create or edit:

```text
skills/<name>/SKILL.md
```

The directory name is the skill id. Use lowercase kebab-case, and keep frontmatter `name` equal to the directory name.

## Rule 2: declare the contract

Existing skills currently use the transitional contract enforced by `scripts/check_skill_contracts.py`: `name` and `description` are required. New skills should also declare the richer fields from `schema/skill.schema.json` so the repo can tighten enforcement later without another migration.

Recommended frontmatter:

```yaml
---
name: example-skill
description: Use when a concrete trigger condition applies; say what the skill does in one sentence.
trigger_type: model
risk_level: low
host_support: [claude, codex, cursor, gemini]
side_effects: [none]
requires_tools: [none]
---
```

Allowed `trigger_type`: `slash`, `model`, `hook`, `manual`.

Allowed `risk_level`: `low`, `medium`, `high`.

## Rule 3: include examples

In the body, include:

- when to use it
- what to do
- at least one positive trigger example
- at least one negative example or non-trigger case

For hook or tool skills, include the command or hook entry point.

## Rule 4: update derived surfaces through generators or checks

Do not hand-edit generated blocks. If a skill changes the resident catalog or hook wiring:

- refresh host carriers with `./install.sh --dry-run`, then `./install.sh` when intended
- refresh hook docs with `python3 scripts/gen_hooks_map.py`
- update `.claude-plugin/marketplace.json` if the plugin skill set changes
- update `schema/skill_conflicts.json` if the new skill overlaps existing instructions

## Rule 5: add tests

At minimum, the new skill must pass:

```bash
python3 scripts/lint_skill_md.py skills/<name>/SKILL.md
python3 scripts/check_skill_contracts.py
```

If the skill ships tools, add deterministic tool tests under `skills/<name>/tools/` and wire them into `scripts/run_all_tests.sh` when they are part of the offline gate.

## Rule 6: run verification

Run:

```bash
make check
```

## Checklist

- [ ] `skills/<name>/SKILL.md` exists.
- [ ] Directory name is lowercase kebab-case.
- [ ] Frontmatter `name` equals the directory name.
- [ ] `description` is present and trigger-oriented.
- [ ] `trigger_type` is declared for new skills.
- [ ] `risk_level` is declared for new skills.
- [ ] `host_support` is declared for new skills.
- [ ] `side_effects` is declared for new skills.
- [ ] `requires_tools` is declared for new skills.
- [ ] Positive and negative trigger examples exist.
- [ ] Skill appears in `skills/SKILLS_INDEX.md`.
- [ ] Hook behavior appears in `skills/HOOKS_MAP.md` if relevant.
- [ ] `.claude-plugin/marketplace.json` is updated when the plugin skill set changes.
- [ ] `schema/skill_conflicts.json` is updated when instructions overlap.
- [ ] Tests are added or updated.
- [ ] `make check` passes.
