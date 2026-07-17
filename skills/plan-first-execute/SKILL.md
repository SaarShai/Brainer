---
name: plan-first-execute
description: Experimental/manual planning protocol retained for paired evaluation. Invoke explicitly for a FULL evaluation arm; frontier leads do not auto-load it.
status: experimental
disable-model-invocation: true
auto-install: false
effort: medium
---

# Plan First Execute

Use for tasks with >3 steps, unclear scope, multiple files, risk, user-visible behavior, or architecture.

**Confidence pre-flight** (before committing): name what you're confident about and what you're not (understanding, info sufficiency, approach, risk). If under-confident, make the gap-closing action concrete and retrieval-shaped (read file X, `wiki.py search/fetch Y`, `graphify explain Z`) — never "gather more data". Then proceed / proceed-with-caveat / pause-to-close-the-gap.

## Spec-First Checkpoint

For feature work, product behavior, migrations, shared contracts, or any task likely to outlive one turn, create a compact spec before implementation. If a repo already has a spec/task packet (`specs/...`, `PLAN.md`, issue body, design doc), read and update that instead of creating a parallel artifact.

If the destination is nameable but the route is too foggy to produce a complete,
gradeable spec in one session, do not counterfeit completeness with speculative
tasks. Invoke [`wayfinder`](../wayfinder/SKILL.md) automatically: it maps precise
decision questions separately from still-unformulated in-scope fog, then hands
the cleared route back here. A user may also invoke it directly with
`/wayfinder`. Do not invoke it when this skill can already produce a complete,
gradeable `done means:` block.

Minimum spec contract:
- **WHAT/WHY**: user-visible outcome, scope, non-goals, assumptions, dependencies.
- **Testable requirements**: each requirement can be verified without guessing.
- **Acceptance/success criteria**: measurable enough to become the `done means:` block.
- **Clarifications**: use `[NEEDS CLARIFICATION: question]` only for decisions that materially change scope, UX, data, security, or validation. Ask at most 1-3 load-bearing questions; make safe defaults explicit as assumptions.

Only after the WHAT is stable enough do the HOW work:
- Map technical choices back to requirements.
- If a design choice makes the code hard to test, treat that as design feedback — surface the coupling before building, don't skip the test.
- Check governing docs (`AGENTS.md`, `README`, existing skill docs, wiki pages, or an explicit constitution) before adding architecture.
- Derive tasks from acceptance criteria/user stories, ordered by dependency, with independent test points where possible.
- Before claiming done, converge code against the spec/plan/tasks: every requirement is covered, every task is done or intentionally deferred, and unexpected extra behavior is called out.

Steps:
1. Inspect discoverable facts. Read the files you'll touch; reuse existing capabilities/conventions before introducing new surface area.
2. Identify unknowns. Ask the user only the 1–3 **load-bearing** questions whose answer changes the plan's shape; resolve nice-to-knows during execution. On **unfamiliar territory** (new part of the codebase, new domain), the load-bearing questions themselves are unknown — run a **blindspot pass** first: enumerate the unknown unknowns (what does good look like here, what prior art exists, which potholes recur) via a quick delegated survey before drafting anything; questions you didn't know to ask are where the plan fails.
3. Draft plan with phases and verification. **Lead with the decisions most likely to change on review** — data models, interfaces, anything user-facing — and put mechanical work last: the reviewer's attention goes where their answer would alter the build, not where the plan is already safe. End it with a `done means:` block — ≤5 verifiable exit criteria derived from the user's ask. Completion is judged against THIS block, re-read at the end, not against your memory of it. For multi-session or multi-agent work the plan lives on disk (PLAN.md / task packet) and outranks any in-context restatement. Before you trust it, sanity-check the block is **complete and gradeable** — right target, and covers the obvious degenerate/edge inputs; a blind verifier grades *against* this block, so an omitted case silently passes work that misses it.
4. Simplify (see `lean-execution`): drop ceremony, duplicate checks, speculative docs, any step that doesn't reduce risk or produce evidence.
5. Get approval if host workflow requires it.
6. Execute.
7. Verify.
8. Document durable facts.

Do not assume APIs exist. Retrieve docs or code first.

Bypass for tasks that are clear, low-risk, and describable as a one-sentence diff: inspect reality, execute, verify.
