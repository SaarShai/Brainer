# self-improvement-loops — EVAL

**Posture: proposed and slash-only.** This is a policy layer over existing
Brainer engines, not evidence that autonomous self-improvement is safe or
effective.

## Why it earns a separate skill

`loop-engineering` owns generic loop topology, `learn-skill` owns source
ingestion and skill lifecycle, and `eval-gate` owns evaluation design. None owns
the decision boundary created when the optimized artifact includes the prompt,
context mechanism, workflow, harness, or optimizer itself. This skill adds only
that boundary and delegates the mechanics back to those owners.

## Evidence limits

The external source's 2026 results are directional evidence from recent,
mostly single-lab systems. They are not treated here as replicated benchmark
claims, universal uplift estimates, or proof that recursion helps every model.
Brainer adopts the falsifiable controls—outside-the-loop enforcement, two-split
acceptance, artifact lineage, no-op detection, and model-specific revalidation—
without importing the source's population-search machinery or numeric claims.

## Acceptance before promotion

Promotion requires both:

1. **Local negative tests:** known-bad self-modifying specs and traces must trip
   the existing loop linter/monitor, while an ordinary-loop fixture remains
   unaffected. Skill lint and the loop spec must also pass cleanly.
2. **Weakest-executor use:** in fresh context, the weakest executor tier expected
   to invoke this skill must correctly route an independent self-modifying case,
   choose the lowest adequate rung, preserve locked surfaces, and demand
   held-in/held-out artifact-bound evidence before accepting a candidate.

That use must be on a case not used to author this skill. A material executor
model change invalidates the behavioral acceptance result until it is rerun.
Human approval remains required for evaluator/gate changes, editable-surface
expansion, and production promotion.

## Current weakest-executor evidence

The fresh `gemma4:26b-mlx` transfer run scored 11 of n = 16 required criteria,
so the promotion gate did not pass and this skill remains proposed. The bound
record is [`eval/2026-07-16-gemma4-26b-mlx.json`](eval/2026-07-16-gemma4-26b-mlx.json).
