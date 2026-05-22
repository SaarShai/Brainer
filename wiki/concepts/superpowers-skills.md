---
schema_version: 2
title: Superpowers Skills
type: concept
domain: framework
tier: semantic
confidence: 0.75
created: 2026-04-25
updated: 2026-04-25
verified: 2026-04-25
sources: [https://github.com/obra/superpowers, raw/2026-04-17-research-brief.md, raw/2026-04-18-karpathy-wiki-spinoffs.md]
supersedes: []
superseded-by:
tags: [skills, superpowers, agents, workflow]
---

# Superpowers Skills

## Summary

Superpowers is useful to Token Economy less as a dependency and more as a workflow pattern: small named skills, mandatory skill checks before action, evidence before completion, and staged development loops.

## Lessons To Keep

- Make behavior contracts discoverable as `SKILL.md` files, not buried in one large startup prompt.
- Keep skill content on demand. Startup should carry pointers and triggers, not full playbooks.
- Treat skills as mandatory when they match a task. Optional discipline decays under pressure.
- Prefer explicit phase gates: brainstorm/spec, plan, implement, verify, review, finish.
- Use fresh context for reviewers or workers; do not hand them the whole transcript.
- Verification claims need fresh evidence from commands or direct inspection.

## Applied In This Repo

- `start.md` points to skills on demand instead of loading every workflow.
- `skills/context-refresh/SKILL.md` and `prompts/summ.md` keep handoff behavior behind a trigger.
- `prompts/subagents/repo-maintainer.prompt.md` and `prompts/subagents/wiki-documenter.prompt.md` use compact result packets instead of transcripts.
- `tests/test_universal_framework.py` pins startup and prompt contracts so workflow drift is caught.

## Still Useful To Import

- Add a lightweight "skill check before action" rule to startup and tests.
- Add a verification-before-completion skill based on the evidence-before-claims pattern.
- Keep `DONE_WHEN` style criteria for project pages where they define readiness.

## Related

- [[raw/2026-04-17-research-brief]]
- [[raw/2026-04-18-karpathy-wiki-spinoffs]]
- [[concepts/wiki-governance]]
- [[projects/delegate-router/README]]
