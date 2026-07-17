# Skills effectiveness verification

Status: implementation and measurement in progress on
`codex/skills-effectiveness-verification`.

## Scope boundary

Brainer is the only implementation surface for this campaign. Reports and raw
sessions in sibling projects are observational evidence only. This branch must
not edit or propagate to `screenery-design-master`, `screenery-lean`, or any
other consumer repository.

The later Screenery rollout is a separate compatibility step. It remains gated
on the order-0001 save/splits and the D31/SD-14 consolidation sequence. That
rollout must re-run consumer preflight and carrier-sync checks rather than copy
the branch blindly.

## Evidence order

1. Disable already measured noisy output behind reversible profiles while
   retaining redacted shadow telemetry.
2. Validate hook semantics on a frozen 500-case trigger corpus.
3. Reproduce the sibling fire-versus-value counts and analyze every available
   transcript without treating immediate reaction as causal lift.
4. Run paired production-condition evaluations with fresh fixtures and fresh
   sessions for every arm.
5. Apply verdicts only after deterministic acceptance tests and paired outcome
   analysis are complete.

The sibling audit is useful but observational: it selected one session for its
reported headline, manually labelled five examples for several mechanisms, and
measured immediate reaction rather than task-outcome lift. Preserve those
limitations alongside its positive and negative findings.

## Paired evaluation contract

Each suspect capability receives 50 frozen cases in four arms: `OFF`, `FULL`,
`COMPACT`, and a length-matched neutral `PLACEBO`. Coding sets contain 15
trivial, 20 normal, and 15 long or compound cases. Workflow skills use their own
50-case artifact-gated sets. Codex and Claude run in separate ephemeral,
nonpersistent sessions, and no fixture or worktree is reused between arms.

Record deterministic task pass, material scope violations, unrequested writes,
total tokens across agents, wall time, tool calls, subprocesses, delegated
calls, and correction or rework count. Use a blind cross-family judge only for
criteria that cannot be deterministic. Analyze paired binary outcomes with
McNemar or exact sign tests and paired bootstrap confidence intervals.

## Preregistered verdicts

- **Keep default-on:** pass-rate lift of at least 5 percentage points, 95%
  confidence interval above zero, no material-scope regression, and no more
  than 15% median token overhead.
- **Safety exception:** at least two distinct prevented P0/P1 failures, no
  pass-rate regression, and no more than 15% overhead.
- **Demote to role brief:** no frontier lift but at least 5 points of mid-tier
  lift with confidence interval above zero.
- **Manual quarantine:** ambiguous quality effect with no more than 10%
  overhead; retain for one release without auto-triggering.
- **Retire:** no quality lift with at least 10% overhead, or a non-positive
  upper confidence bound.
- **Disable as harmful:** at least 5 points of task-success regression or any
  attributable material scope or safety violation.

Executable tool skills are judged by their tool-specific deterministic gates,
not by whether their explanatory prose changes model style.

## Minimum protection stack

The stack-level comparison retains only silent pending-intent state, compaction
handoff, wiki trust gates, concise authority boundaries, task-specific
acceptance criteria, and compact high-risk verification. Pruning must not remove
these protections without a separate safety result.

## Result publication

Raw run records and derived summaries belong under `eval/results/`. Publish
positive, null, blocked, and harmful results; never infer a verdict from missing
runs. A persistent wiki lesson is allowed only after the N=50 verdict and must
pass `write-gate` first.
