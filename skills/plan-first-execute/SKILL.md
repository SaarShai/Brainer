---
name: plan-first-execute
description: Plan before executing non-trivial or spec-worthy tasks. Trigger when the task has more than 3 steps, unclear scope, multiple files, real risk, user-visible behavior, or architecture decisions. Inspect reality first, separate WHAT from HOW, draft a phased plan with verification gates, simplify, then execute.
effort: medium
---

# Plan First Execute

Use for tasks with >3 steps, unclear scope, multiple files, risk, user-visible behavior, or architecture.

**Confidence pre-flight** (before committing): name what you're confident about and what you're not (understanding, info sufficiency, approach, risk). If under-confident, make the gap-closing action concrete and retrieval-shaped (read file X, `wiki.py search/fetch Y`, `graphify explain Z`) — never "gather more data". Then proceed / proceed-with-caveat / pause-to-close-the-gap.

## Spec-First Checkpoint

For feature work, product behavior, migrations, shared contracts, or any task likely to outlive one turn, create a compact spec before implementation. If a repo already has a spec/task packet (`specs/...`, `PLAN.md`, issue body, design doc), read and update that instead of creating a parallel artifact.

Minimum spec contract:
- **WHAT/WHY**: user-visible outcome, scope, non-goals, assumptions, dependencies.
- **Testable requirements**: each requirement can be verified without guessing.
- **Acceptance/success criteria**: measurable enough to become the `done means:` block.
- **Clarifications**: use `[NEEDS CLARIFICATION: question]` only for decisions that materially change scope, UX, data, security, or validation. Ask at most 1-3 load-bearing questions; make safe defaults explicit as assumptions.

Only after the WHAT is stable enough do the HOW work:
- Map technical choices back to requirements.
- Check governing docs (`AGENTS.md`, `README`, existing skill docs, wiki pages, or an explicit constitution) before adding architecture.
- Derive tasks from acceptance criteria/user stories, ordered by dependency, with independent test points where possible.
- Before claiming done, converge code against the spec/plan/tasks: every requirement is covered, every task is done or intentionally deferred, and unexpected extra behavior is called out.

Steps:
1. Inspect discoverable facts.
2. Identify unknowns. Ask the user only the 1–3 **load-bearing** questions whose answer changes the plan's shape; resolve nice-to-knows during execution.
3. Draft plan with phases and verification. End it with a `done means:` block — ≤5 verifiable exit criteria derived from the user's ask. Completion is judged against THIS block, re-read at the end, not against your memory of it. For multi-session or multi-agent work the plan lives on disk (PLAN.md / task packet) and outranks any in-context restatement.
4. Simplify (see `lean-execution`): drop ceremony, duplicate checks, speculative docs, any step that doesn't reduce risk or produce evidence.
5. Get approval if host workflow requires it.
6. Execute.
7. Verify.
8. Document durable facts.

Do not assume APIs exist. Retrieve docs or code first.

Bypass for tasks that are clear, low-risk, and describable as a one-sentence diff: inspect reality, execute, verify.
