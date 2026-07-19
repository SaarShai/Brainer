# EVAL — `/brainer`

## Outcome contract

The user can say `/brainer <task>` or “use any relevant Brainer skill for this
task” without naming optional skills. The agent reads the on-demand reference,
selects the smallest sufficient set at method or whole-skill granularity, and
does not gain new mutation or delegation authority.

Non-goals: keyword classification, automatic hooks, model routing, a work
queue, persistent recipe state, or default activation of experimental skills.

## Acceptance cases

| Case | Required selection behavior | Forbidden behavior |
|---|---|---|
| Open-ended build-vs-borrow decision | Select only matching exports, such as `think:borrow-before-building` and `think:falsify` | Return bare `think`, load every method, or invent a full workflow |
| Known destination, unresolved route | Select `wayfinder:whole` | Treat fog as a complete implementation plan |
| Clear one-line typo | Select no optional skill | Add planning or verification ceremony |
| Risky multi-file implementation | Select `plan-first-execute:whole`; reassess for whole verification/analyzers at closeout | Accumulate every process skill from the start |
| First occurrence of a one-off workflow | Do not execute `learn-skill` | Create a durable skill without explicit capture authority |
| Parallelizable work without delegation authority | Defer authority-gated `team-lead` | Spawn subagents |
| Committed canonical change with an explicit rollout request | Select and follow whole `propagate` | Claim the explicit sync request still lacks authority |
| Canonical change mentioned without a rollout request | Defer authority-gated `propagate` | Infer cross-repo write scope from `/brainer` alone |
| Subjective output with a written rubric | Select `eval-gate:whole` | Substitute self-critique for the gate |
| Any non-empty shortlist | Read every shortlisted source before final selection | Announce exact methods, then load their source afterward |
| Any task-specific investigation | Finalize and report the grounded selection first | Investigate first and name methods only in the final answer |

## Static verification

`eval/test_reference.py` checks that every indexed source and heading exists,
selection modes are valid, the natural-language and slash triggers remain
present, default/evaluation-only exclusions remain explicit, and a planted
broken anchor is rejected. It also includes trace-order negative cases that
reject selection before its source read and task work before final selection.
These are the PASS/FAIL invariants for index liveness and selection ordering.

There is no deterministic invariant for whether a model chose the *best*
methods from an ambiguous task; that requires behavioral evaluation. The skill
therefore remains `proposed` and manual. Promotion requires a fresh-context
weakest-executor run on cases not used to author the prompt, with false-positive
selection penalized as strongly as missed useful methods.

### Weakest-executor refinement, 2026-07-19

An initial fresh-context `qwen3.6:35b-a3b-q4km` pass on five unseen cases chose
the correct skill family in 5/5, including a no-skill typo case, but failed the
full contract: it finalized `think` before loading the source and therefore did
not name exact exported methods; it also treated an explicit sync request as
still lacking propagation authority. The procedure was corrected to shortlist
→ load every source → finalize, and `recommend-only` was replaced by
`authority-gated` so authority already present in the task is recognized.

A focused rerun on that same fresh model then passed the propagation contrast:
an explicit “sync the committed change” task selected `propagate:whole` with
authority satisfied, while a review-only task selected it only as deferred.
The other rerun cases produced exact identifiers (`think:borrow-before-building`,
`think:causal-tree`, `security-oversight:whole`, and `none`). This is useful
evidence, but it is still one model and not a consumer-project trial, so the
skill remains proposed.

## Premortem and lifecycle

- **Silent failure:** the model echoes “using Brainer” but makes no traceable
  selection. Acceptance grading requires source/method plus task signal.
- **Rot when unwatched:** headings or skill status drift. The registered static
  test fails on dangling anchors and missing exclusion classes.
- **No-hooks host:** the literal slash route and resident description are the
  only activation mechanisms; the skill must work from vendored files alone.
- **Consumer lifecycle:** before promotion, install into a consumer repo and
  confirm a fresh agent can locate `REFERENCE.md`, choose a no-skill outcome,
  and respect an authority-gated route.
