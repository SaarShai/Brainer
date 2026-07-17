# Quarantined skill classification

Reviewed: 2026-07-16. Scope: 14 experimental/manual prompt bodies.
No body is default-on. Hash changes invalidate the classification and require re-review.

## Candidate disposition summary

- Proposed retire, pending a candidate-specific gate: 4
- Proposed demotion into compact role briefs: 5
- Retain as explicit tool/workflow skills: 4
- Proposed split of prose from retained mechanisms: 1

These are content-taxonomy hypotheses, not causal outcome verdicts.

| Skill | Class | Candidate disposition | Reason |
|---|---|---|---|
| `caveman-ultra` | generic-model-patch | **retire** | A generic output-style override with no private context, tool, or workflow; its word-count probe was ignored in the sibling audit. |
| `fable-mode` | generic-work-discipline | **demote-role-brief** | Its five gates largely restate frontier execution defaults; the useful scope, adversarial, and verification rules fit the builder and verifier briefs. |
| `lean-execution` | generic-work-discipline | **demote-role-brief** | The prose is generic frontier guidance; surgical-scope and stop rules belong in the builder brief while deterministic drift probes can be judged independently. |
| `learn-skill` | custom-tool-workflow | **retain-manual** | Brainer-specific dedup, scaffold, lint, telemetry, promotion, and demotion tools implement a concrete workflow unavailable from model weights. |
| `loop-engineering` | custom-tool-workflow | **retain-manual** | The loop-spec schema, linter, resolved snapshot, diagram, and runtime monitor are executable domain tooling rather than a style prompt. |
| `plan-first-execute` | generic-work-discipline | **demote-role-brief** | Planning, scoping, and verification are generic frontier capabilities; only the compact spec and stop rules merit residence in the builder brief. |
| `prompt-triage` | generic-model-router | **retire** | A per-prompt cache-busting router with stale host/model assumptions and added failure paths; frontier delegation can select roles directly without an injected classifier directive. |
| `requirements-ledger` | generic-compliance-wrapper | **retire** | A visible per-turn file and task-list protocol duplicates the retained silent pending-intent state and imposes compulsory writes and closeout nags. |
| `standing-orders` | generic-compliance-wrapper | **retire** | Broad regex-triggered orchestration and deep-thinking directives are the measured prompt-surface failure mode and duplicate compact role briefs and explicit user requests. |
| `task-retrospective` | custom-tool-workflow | **retain-manual** | An explicitly armed Brainer learning workflow produces governed artifacts and routes durable lessons through project-specific write gates. |
| `team-lead` | generic-work-discipline | **demote-role-brief** | Generic orchestration doctrine is already supported by native agents; the useful ownership, independence, and verification constraints fit the builder brief. |
| `think` | generic-work-discipline | **demote-role-brief** | First-principles, simplify, research, and falsify instructions are generic frontier reasoning guidance with no private context or executable mechanism. |
| `verify-before-completion` | mixed-generic-and-tooling | **split** | The full prose repeats frontier verification habits, but the compliance-aware compact probe and mechanical artifact verifier supply distinct enforceable behavior. |
| `wayfinder` | custom-artifact-workflow | **retain-manual** | It defines a specific sourced decision-map and ticket artifact protocol for multi-session ambiguity, including concurrency and human-input gates. |

## Review rule

Re-review after 30 days. Time alone never deletes a body. Removal requires candidate-specific evidence that clears the preregistered retirement or harmfulness gate, plus an explicit implementation change.

Executable tools and compact canary mechanisms are retained or removed independently from their explanatory prose. No classification here authorizes propagation to consumer repositories.
