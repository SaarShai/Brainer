---
name: delegate
description: Route work to subagents with cost preflight, model choice, and lifecycle management. Use when the task has independent subtasks, research, codegen, review, or anything reusable across a cheap model. Single contract: orchestration policy + cost preflight + model registry. Replaces the old subagent-orchestrator and delegate-router skills.
model: any
effort: medium
tools: [Bash, Read]
---

# delegate

Use cheapest capable worker. Keep main context clean.

## Trigger

- task has >3 steps OR research OR codegen OR review OR independent subtasks
- a subtask is reusable across sessions/projects (cache value)
- main context is filling and parts of the task are delegatable

## Protocol

1. `python skills/delegate/tools/delegate.py plan "<task>"` — returns suggested decomposition + per-step model.
2. Delegate **only** when saved main-context/tool cost exceeds orchestration overhead. Run `python ... cost-preflight "<task>"` to check.
3. Send each subagent minimal context: task, refs, budget, expected output. No full transcript.
4. Require compact packet from each subagent:
   - outcome
   - sources/evidence
   - confidence
   - verification
   - changed files
   - risks
5. Run independent subtasks in parallel **only** when outputs are distinct and the merge step stays small.
6. Reject reports that miss the contract.
7. Orchestrator keeps final synthesis and final plan authorship — never delegate synthesis.
8. Manage worker lifecycle: capture result, document/feed forward, close completed idle workers. Do not close active workers just to free thread capacity.

## Model registry (default)

| Task type | Default model |
|---|---|
| extraction, classification, lint, simple edit | haiku / local |
| search, summary, codegen of routine code | haiku / sonnet |
| architecture, ambiguity, high-risk reasoning, synthesis | opus / sonnet |

Override per call via `python ... classify "<task>"`.

## Cost preflight (hook)

Optional `UserPromptSubmit` hook emits an `[delegate] estimated cost: $X.XX, suggested model: <m>` directive before the main model thinks. Wire via:

```bash
bash skills/delegate/tools/install.sh --with-preflight
```

## Result budget

- Per-subagent summary ≤ 1500 tokens unless explicitly requested.
- No transcripts or raw logs unless needed as evidence.
- Include URLs/paths instead of pasted source when possible.

## Never

- send full transcript to a subagent
- use high-effort reasoning for simple extraction
- delegate final synthesis
- close active workers prematurely
- hardcode model names — use the registry

## Cross-host subagents

Where supported (Claude Code's Task tool, Codex SDK, Cursor agents, Gemini Code Assist), the skill emits adapter calls. For unsupported hosts, falls back to a shell-launched persistent successor via `context-refresh relay`.

## Repo maintenance

If the active repo has a GitHub remote, route save-points to a lightweight repo-maintainer worker. See `tools/prompts/repo-maintainer.prompt.md`.

## Files

```
tools/
├── delegate.py            # plan/classify/cost-preflight
├── cost.py                # token-cost estimator
├── models.yaml            # model registry
├── prompts/
│   ├── lifecycle.prompt.md
│   └── repo-maintainer.prompt.md
└── INSTALL.md
```

## Lineage

shinpr/sub-agents-skills (cross-LLM dispatch via `run-agent` frontmatter); RouteLLM (ICLR 2025) for model routing; VoltAgent/awesome-claude-code-subagents for the subagent-definition pattern.
