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
4. Classify quarantined bodies by whether they contain generic model patches,
   compact role guidance, or actual private/tool/workflow capability.
5. Prove carrier-free native loading with fresh fixtures before any outcome
   run, then evaluate only the compact protection bundle against `OFF`.

The sibling audit is useful but observational: it selected one session for its
reported headline, manually labelled five examples for several mechanisms, and
measured immediate reaction rather than task-outcome lift. Preserve those
limitations alongside its positive and negative findings.

## 2026-07-16 scope decision

The 8,300-run four-arm matrix remains a frozen preregistration and must not be
launched. It is useful design evidence, but its exact-body carriers are not
native lazy loading and its longitudinal hook arms lack a resumable two-turn
protocol. More runs do not repair that construct mismatch.

The replacement outcome experiment was `FRONTIER` versus `OFF`: 19 frozen task
families, current Codex and Claude frontier lanes, native delivery, and a
preregistered materiality threshold. The 14 experimental/manual bodies did not
each receive N=50. Their current decisions are hash-pinned in
`eval/skills_effectiveness/quarantine_classification.json` and reviewed again
if a body changes.

The carrier-free feasibility smoke is a prerequisite, not an outcome verdict.
After Claude authentication was restored, both native host lanes cleared it.
The focused v2 campaign then completed 76 valid outcomes (19 cases × two arms ×
two hosts) with zero blockers. Both arms passed all 19 cases in both lanes, with
zero scope violations and paired median token overhead of +1.20% on Codex and
+1.74% on Claude. The preregistered expansion gate failed on zero observed
pass-rate lift. See
`eval/results/skills-effectiveness/focused-pilot-v2-analysis.md`.

## Frozen full-matrix contract

The preserved preregistration assigned each suspect capability 50 frozen cases in four arms: `OFF`, `FULL`,
`COMPACT`, and a length-matched neutral `PLACEBO`. Coding sets contain 15
trivial, 20 normal, and 15 long or compound cases. Workflow skills use their own
50-case artifact-gated sets. Codex and Claude run in separate ephemeral,
nonpersistent sessions, and no fixture or worktree is reused between arms.

Record deterministic task pass, material scope violations, unrequested writes,
total tokens across agents, wall time, tool calls, subprocesses, delegated
calls, and correction or rework count. Use a blind cross-family judge only for
criteria that cannot be deterministic. Analyze paired binary outcomes with
McNemar or exact sign tests and paired bootstrap confidence intervals.

## Preserved full-matrix verdict gates

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
runs. The focused result is a ceilinged null for the static compact body, not a
verdict on longitudinal hooks or the minimum protection mechanisms. No
persistent wiki lesson is authorized until the final quarantine verdict passes
the write gate.
