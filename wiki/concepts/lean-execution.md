---
schema_version: 2
title: "Lean Execution"
type: concept
domain: "agent-operations"
tier: semantic
confidence: 0.9
created: "2026-04-26"
updated: "2026-04-26"
verified: "2026-04-26"
sources: [start.md, L0_rules.md, skills/lean-execution/SKILL.md, skills/wiki-write/SKILL.md, skills/subagent-orchestrator/SKILL.md, https://github.com/addyosmani/agent-skills, https://github.com/openai/skills, https://github.com/memodb-io/Acontext, https://agilemanifesto.org/principles, https://global.toyota/en/company/vision-and-philosophy/production-system/, https://www.martinfowler.com/bliki/Yagni.html, https://basecamp.com/shapeup/2.2-chapter-08, https://developers.openai.com/cookbook/examples/agents_sdk/session_memory, https://code.claude.com/docs/en/best-practices]
supersedes: []
superseded-by:
tags: [lean, planning, delegation, context, process-rot]
---

# Lean Execution

## Summary

Token Economy should treat plans, context, delegation, and process artifacts as inventory: useful only when they reduce risk, produce value/evidence, or preserve durable learning.

## Evidence

- `start.md` already established "excellent work, minimal context," progressive retrieval, compact delegation, and Caveman Ultra output.
- `L0_rules.md` already required terse output, relevant-skill loading only, repo-local work, and cheapest capable delegation.
- Research lanes on 2026-04-26 found the gap: the framework lacked an explicit step to prune task plans and process overhead before execution.
- Deep pass on 2026-04-26 ranked the earlier repo candidates by live GitHub signals. Top three: `addyosmani/agent-skills` (23.3k stars, 2.9k forks, 27 open PRs), `openai/skills` (17.5k stars, 1.1k forks, 161 open PRs), and `memodb-io/Acontext` (3.3k stars, 314 forks, 18 open PRs).
- Agile principles frame simplicity as maximizing work not done.
- Toyota Production System frames improvement around eliminating waste, inconsistency, and unreasonable burden before automation.
- Fowler's YAGNI argues against speculative features/abstractions because they add build cost, delay, and carrying cost.
- Shape Up's circuit-breaker/appetite model supports capped downside and scope cutting over runaway projects.
- OpenAI and Claude Code context-management guidance supports trimming stale context, using subagents for isolated investigation, and keeping main-thread synthesis compact.
- Addy Osmani's `agent-skills` adds concrete simplification guardrails: preserve behavior, follow project conventions, understand before changing, scope simplification to changed code, run tests after each simplification, and compare orchestration cost against direct invocation.
- `openai/skills` confirms Codex-native skill design: concise frontmatter drives triggering, SKILL.md should stay lean, details move to scripts/references/assets, extra README-style files inside skills add clutter, and validation scripts catch drift.
- Acontext confirms the memory side: skip trivial learnings, distinguish facts/procedures/failure lessons, avoid over-generalization with `applies_when`, update existing broad skills before creating new thin ones, and use name/description discovery plus on-demand skill-file loading.

## Adopted

- Add `skills/lean-execution/SKILL.md` as a tiny on-demand skill.
- Add a startup trigger for simplification/process-rot checks.
- Add an L0 rule to prune plans before execution.
- Update `plan-first-execute` with a simplification pass and low-risk planning bypass.
- Update `subagent-orchestrator` with an overhead gate and compact result budget.
- Update `wiki-write` to prefer enriching existing pages, skip trivial learnings, and record applicability/prevention for reusable procedures and failures.

## Not Imported

- No Lean/Scrum/Kanban ceremony.
- No external repo clone.
- No vendor SDK adoption.
- No always-on multi-agent workflow.
- No broad backlog or ritual process.
- No automatic memory backend; the repo-local wiki remains the source of truth.

## Related

- [[start]]
- [[L0_rules]]
- [[concepts/caveman-output-compression]]
- [[concepts/framework-hardening-adoption]]

## Open Questions

- Should future write-gate tooling enforce unrelated-file/small-diff warnings, or is current guidance sufficient?
