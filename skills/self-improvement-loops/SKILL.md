---
name: self-improvement-loops
description: Govern loops that optimize their own agent machinery.
status: proposed
source: "https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering/blob/main/skills/self-improvement-loops/SKILL.md"
learned_at: 2026-07-16
disable-model-invocation: true
auto-install: true
---

# self-improvement-loops

Proposed, slash-only policy for the special case where the optimization target
is agent machinery: prompts, structured context, context-producing skills,
workflows, harness code, or the optimizer itself. It adds self-modification
controls to [`loop-engineering`](../loop-engineering/SKILL.md); it is not a
runner, linter, evaluator, or candidate store.

## When to Use

Invoke `/self-improvement-loops` when a loop may propose changes to its own
prompt, context mechanism, skill, workflow, harness, or optimizer, or when such
a loop is stagnant, gaming its metric, or regressing after executor changes.

Do not invoke it for:

- an ordinary loop whose optimization machinery is fixed — use
  [`loop-engineering`](../loop-engineering/SKILL.md);
- turning a source into a skill — use [`learn-skill`](../learn-skill/SKILL.md);
- designing metrics, regression suites, or model judges — use
  [`eval-gate`](../eval-gate/SKILL.md).

## Procedure

1. **Choose the lowest adequate rung.** Try, in order: prompt → structured
   context → context-producing skill → workflow → harness → optimizer. Move up
   only when verified failures persist and the lower rung cannot express the
   fix. Deeper rungs enlarge both leverage and gaming surface.
2. **Load the existing engines.** Specify the generic topology, separate
   verifier, machine gate, stop, budget, memory, blindness, error policy, and
   output allowlist through `loop-engineering`. For skill ingestion or
   refinement, use `learn-skill`; for evaluation design, use `eval-gate`.
3. **Pass readiness before recursion.** Require a fast automatable evaluator, a
   proposer-hidden held-out set, runtime-enforced budgets and permissions,
   declared edit boundaries, candidate lineage, and wired human decisions. Run
   a bounded capability probe on held-out work; declining trajectories make
   recursion ineligible for that executor and task family.
4. **Freeze the self-modifying contract.** Set `self_modifying: true` and
   declare `editable_surfaces`, `locked_surfaces`, `held_in_gate`,
   `held_out_gate`, `artifact_binding`, and `human_approval`. Pass only opaque,
   distinct held-in/out IDs to `learn.py patch`; an operator-owned regular,
   single-link JSON registry beneath a stable operator-controlled non-symlink
   parent hierarchy maps those IDs to shell-free argv. Evaluator code,
   instrumentation, permissions, budget enforcement, and both acceptance gates
   stay outside every editable surface.
5. **Bind evidence to the candidate.** Each iteration records `candidate_id`,
   `artifact_hash`, `evaluator_revision`, `diff_size`, and `trace_refs`. Scores
   without that binding are inadmissible. An accepted empty or trivial diff is
   stagnation, not improvement.
6. **Accept empirically.** Freeze both gates before proposing. The held-in gate
   tests the targeted weakness; the proposer-hidden held-out gate tests
   regressions. Accept only when neither regresses and at least one strictly
   improves. Preserve rejected candidates and their raw evidence so failures
   are not rediscovered.
7. **Revalidate on executor change.** Treat a material executor-model or seed
   change as a new capability and held-out validation boundary. Do not inherit
   a prior model's acceptance result.
8. **Keep three decisions human.** Changing the evaluator or acceptance gate,
   expanding editable surfaces, and promoting a candidate to production require
   explicit human approval. The optimizer may recommend; it may not authorize.

The declarative example in [`LOOPS.md`](LOOPS.md) uses the existing linter,
monitor, learned-skill telemetry, and patch gate. Do not add a parallel runner,
linter, or store for this policy.

## Pitfalls

- **Metric ownership leaks inward** — mutable evaluator, instrumentation, or
  permissions let the candidate improve its score instead of the artifact.
- **Rung escalation becomes the default** — rewriting a harness for a context
  defect spends more and creates a wider regression surface.
- **Rationale substitutes for evidence** — a persuasive proposed edit cannot
  replace held-in and held-out measurements.
- **Flat scores look stable** — inspect `diff_size` and artifact hashes; a no-op
  improver may be broken rather than converged.
- **Old winners transfer across models** — executor-specific behavior requires
  revalidation after a material model or seed change.

## Verification

```bash
python3 skills/learn-skill/tools/learn.py lint --file skills/self-improvement-loops/SKILL.md
python3 skills/loop-engineering/tools/loop_lint.py skills/self-improvement-loops/LOOPS.md
python3 skills/loop-engineering/tools/loop_lint.py --resolve skills/self-improvement-loops/LOOPS.md > loop.resolved
python3 skills/loop-engineering/tools/loop_run_monitor.py --resolved-spec loop.resolved TRACE.json
```

The first two commands verify this policy and its declarative spec. The monitor
is the runtime gate for an actual self-modifying trace; it must see artifact-bound
lineage and reject or loudly warn on an accepted empty/trivial diff. Before this
skill is promoted from `proposed`, run local negative tests and a fresh-context
use on an independent case with the weakest executor tier that will use it, as
defined in [`EVAL.md`](EVAL.md).

## Failure modes

- **Silent-failure path** — this proposed skill is slash-only. A self-modifying
  loop started without the literal invocation can omit the supplemental contract;
  the generic loop linter remains the prevention layer only when the spec declares
  `self_modifying: true`.
- **Rot-when-unwatched** — held-out sets, evaluator revisions, and executor
  identities drift. Stale gates can approve benchmark-shaped edits unless every
  result records its evaluator revision and model changes trigger revalidation.
- **No-hooks host** — prose cannot enforce locked surfaces, trace binding, or
  approval boundaries. On a host without the linter/monitor/harness enforcement,
  stop before recursion and report the missing control; do not simulate safety
  with prompt instructions.

<!-- Rationale (why this earns a skill): ordinary loop topology, skill ingestion,
and evaluator design already have owners. Self-modification adds a distinct
decision boundary: choose the mutable rung, prove the executor can improve it,
keep the steering signal outside the mutation surface, bind every score to an
artifact, and reserve evaluator/surface/promotion changes for humans. Keeping
that boundary in one slash-only policy prevents generic loop guidance from
silently authorizing recursive mutation while avoiding a second engine. -->
