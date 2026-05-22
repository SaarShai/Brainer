---
name: skill-creator
description: Create or edit skills in this catalog. Use when the user asks to add a new skill, rewrite an existing skill, improve a skill's description, lint frontmatter, or audit the catalog for triggering accuracy. Enforces agentskills.io schema (name + description ≤1536 chars, optional tools/model/effort/context/host_compat), front-loaded trigger keywords, and the standard folder layout (SKILL.md + tools/ + EVAL.md + optional README.md). Suggests rather than auto-writes durable artifacts.
model: any
effort: medium
tools: [Read, Write, Edit, Bash, Grep, Glob]
---

# skill-creator

Helps add or improve skills in this repo.

## Trigger

- "create a new skill"
- "edit / rewrite / rename a skill"
- "audit the skill catalog"
- "improve this skill's description"
- "lint SKILL.md"
- "convert this protocol into a skill"

## Schema (agentskills.io)

Each skill is a folder under `skills/<name>/`:

```
skills/<name>/
├── SKILL.md         # required: frontmatter + protocol body
├── tools/           # optional: bundled scripts (py/sh)
├── EVAL.md          # required if the skill claims measured savings
└── README.md        # optional: extended docs
```

Frontmatter:

```yaml
---
name: <kebab-case>
description: <≤1536 chars; front-load trigger keywords>
tools: [Read, Write, Bash]      # optional, per-skill scoping
model: haiku|sonnet|opus|local|any
effort: low|medium|high          # optional
context: fork                    # optional, for read-heavy skills
host_compat: [claude-code, codex, cursor, gemini, copilot]   # optional
---
```

`description` is the ONLY field always resident in the agent's context across sessions. Front-load the trigger words. Mention anti-triggers ("do not use when X") inside the cap.

## Protocol

### Create a new skill

1. Search the existing catalog with `grep -l "<topic>" skills/*/SKILL.md` — don't duplicate.
2. Propose a name (kebab-case) and a one-paragraph description draft. Show to user for review.
3. Scaffold: `mkdir -p skills/<name>/tools && touch skills/<name>/{SKILL.md,EVAL.md}`.
4. Write SKILL.md with the schema above. Bullet-list the trigger keywords in the description first sentence.
5. If the skill claims any measured savings, add an `EVAL.md` template referencing `eval/runner.py` and the bench task.
6. Lint: `python skills/skill-creator/tools/lint.py skills/<name>/SKILL.md`.

### Edit an existing skill

1. Read the current SKILL.md.
2. Identify what changed (scope? trigger? bundled tool?).
3. Propose the diff to the user (unified format) before applying.
4. Update SKILL.md in place. Edit EVAL.md only if measurements changed.
5. Re-lint.

### Audit the catalog

1. `python skills/skill-creator/tools/lint.py skills/*/SKILL.md` — checks description length, trigger keywords up front, required fields.
2. `python skills/skill-creator/tools/overlap.py` — flags pairs of skills with overlapping trigger keywords.
3. Report findings; suggest merges or rename targets. Do not auto-merge.

## What this skill does NOT do

- Auto-write skills from heuristics. Skill creation is reviewed by a human.
- Auto-promote drafts to default. Each new skill ships as opt-in until EVAL.md has measured numbers.
- Modify or delete existing skills without explicit instruction.

## Files

```
tools/
├── lint.py            # frontmatter + description-cap linter
├── overlap.py         # trigger-keyword overlap detector
└── templates/
    ├── SKILL.md.template
    └── EVAL.md.template
```

## Lineage

anthropics/skills/skill-creator (Apache-2.0) for the schema and prompts; agentskills.io for the open standard; muratcankoylan/Agent-Skills-for-Context-Engineering for the catalog discipline.
