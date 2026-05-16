---
type: project
axis: skill_crystallization
tags: [delegation, routing, subagents, models]
confidence: med
evidence_count: 1
---

# delegate-router

Model-agnostic routing policy for subagents and cheaper models.

## Contract

- Prefer cheapest capable worker.
- Use local/cheap models for extraction, summaries, lint, simple edits, wiki updates, and classification.
- Use medium models for bounded research and multi-step but low-risk work.
- Use frontier models for architecture, ambiguity, high-risk domains, and final synthesis.
- Spawn parallel workers only when tasks are independent and scopes are disjoint.
- Workers receive compact briefs and return compact result packets.
- For task repos with GitHub remotes, route verified save-points to the lightweight repo-maintainer worker; skip repo maintenance when no GitHub remote exists.
- Context discipline comes before model choice: search/map first, then fetch only relevant files and nearby tests.

## Commands

```bash
./te delegate models
./te delegate classify "task"
./te delegate plan "task"
./te cost preflight "task"
./te cost profile --transcript <path>
./te cost report
./te delegate cost-check "task"  # compatibility alias
```

Implementation lives in `token_economy/delegate.py`.
Local cost discipline lives in `token_economy/cost.py`.

## Cost preflight

`te cost preflight` is the practical guardrail for the common AI coding context leak:

1. refuse full-repo/full-transcript context by default;
2. use `./te code map` and `rg` before opening files;
3. load only relevant files plus nearby tests;
4. batch related reads and summarize large outputs;
5. keep stable prefix files stable so provider prompt caches can work;
6. checkpoint long sessions instead of carrying a growing transcript forever.

Use it before broad implementation or review work when the next action is not obvious.
