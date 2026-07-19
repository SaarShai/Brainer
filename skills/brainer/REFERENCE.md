# `/brainer` optional-method reference

Read this file only after explicit `/brainer` or equivalent umbrella
authorization. It is a decision aid, not a second copy of the skills. Source
skills remain authoritative.

## Selection modes

- `method`: the source explicitly exports the named instruction for independent
  use. Read the complete source for context, then apply only the selected export
  plus any mandatory route that matches the task.
- `whole`: follow the complete source contract.
- `authority-gated`: if the task already supplies the named authority, follow
  the complete source contract; otherwise recommend the route without executing
  it. `/brainer` alone never satisfies the gate, but the task text following it
  can. For example, `/brainer Sync the committed Brainer change to all consumer
  repos` satisfies `propagate` and selects `propagate:whole`; `/brainer Review
  this Brainer change` does not authorize propagation.

## Reasoning and execution

| Need or observable signal | Source | Mode | What may be selected | Avoid when |
|---|---|---|---|---|
| A premise may be wrong; a build should be borrowed, constrained, or cheaply falsified; a causal or risky decision needs deliberate reasoning | [`think`](../think/SKILL.md#exported-methods-for-brainer) | `method` | Choose only matching IDs from **Think method exports** below | Clear mechanical work with no consequential uncertainty |
| Destination is known but unresolved decisions or unformulated fog prevent a gradeable plan | [`wayfinder`](../wayfinder/SKILL.md#when-to-use) | `whole` | Complete destination/map/ticket/frontier/handoff workflow | A complete spec or ordinary task list already exists |
| Work is unclear, risky, architectural, multi-file, or exceeds a small one-sentence change | [`plan-first-execute`](../plan-first-execute/SKILL.md#spec-first-checkpoint) | `whole` | Complete confidence, spec, plan, execution, and convergence contract | Clear low-risk one-sentence diff |
| Scope is widening, abstraction is premature, or the implementation needs aggressive pruning | [`lean-execution`](../lean-execution/SKILL.md#protocol) | `whole` | Complete pruning protocol | The requested scope is already minimal and direct |
| A meaningful completion claim needs evidence beyond the compact default check | [`verify-before-completion`](../verify-before-completion/SKILL.md#verify-before-completion) | `whole` | Complete claim-layer verification workflow | No changed artifact or externally checkable claim |
| Repeated generation/checking needs a machine gate, budget, and stop rule | [`loop-engineering`](../loop-engineering/SKILL.md#do-you-even-need-a-loop) | `whole` | Complete loop design and lint contract | One pass or a normal test command is sufficient |

### Think method exports

Use the exact `think:<id>` form in the final selection:

| ID | Use only when |
|---|---|
| `truth-before-fluency` | Facts, inferences, and unknowns could be conflated |
| `truth-before-agreement` | A material premise may need correction |
| `goal-before-solution` | The proposed solution may obscure the actual outcome |
| `smallest-safe-intervention` | Several interventions could meet the goal |
| `first-principles` | Framing or convention may be wrong |
| `borrow-before-building` | Substantial new surface area is proposed |
| `actual-constraint` | The task is optimizing a system |
| `ranges-and-thresholds` | Outcomes or evidence remain uncertain |
| `diverge-before-converging` | The solution space is genuinely open |
| `causal-tree` | Several causes plausibly explain an observed failure |
| `pre-mortem` | A plan is risky or difficult to reverse |
| `falsify` | New evidence could change the approach |
| `structural-analogy` | The current frame is stuck and a relationship-level analogy may help |
| `research` | Missing external facts could materially change the decision |
| `package-repetition` | Multiple concrete instances suggest a stable repeatable procedure |

## Explicit analyzers

| Need or observable signal | Source | Mode | What it does | Avoid when |
|---|---|---|---|---|
| A code change needs forward blast-radius analysis | [`impact-of-change`](../impact-of-change/SKILL.md#when-to-use) | `whole` | Maps changed symbols to static dependents and risk | Documentation-only work or no change under review |
| A diff or untrusted skill needs introduced-risk triage | [`security-oversight`](../security-oversight/SKILL.md#when-to-use) | `whole` | Runs the complete lexical security or pre-install audit contract | No diff/untrusted package is in scope; never claim a clean scan proves safety |
| An AI-produced artifact needs judgment against a written rubric | [`eval-gate`](../eval-gate/SKILL.md#protocol) | `whole` | Scores output and preserves failed cases | Deterministic verification can fully decide correctness |
| Prompt-cache ordering, mutation, model switching, or unused tool surface is the subject | [`cache-lint`](../cache-lint/SKILL.md#when-to-run) | `whole` | Runs the six cache rules plus tool-surface audit | Ordinary application performance work unrelated to prompt caching |

## Routes requiring additional authority

| Signal | Source | Mode | Additional authority required |
|---|---|---|---|
| Separable parallel work would benefit from builders or a cold verifier | [`team-lead`](../team-lead/SKILL.md#6-when-not-to-use-this) | `authority-gated` | The user or governing task must authorize subagents/delegation |
| A completed recurring procedure appears worth packaging | [`learn-skill`](../learn-skill/SKILL.md#when-to-use) | `authority-gated` | The user must ask to capture/create a skill; dedup and write-gate still apply |
| Work should continue in another session or agent | [`baton`](../baton/SKILL.md#when-to-use) | `authority-gated` | The task must actually request or require a handoff artifact |
| Canonical Brainer changes should reach consumer repositories | [`propagate`](../propagate/SKILL.md#preconditions-hard) | `authority-gated` | Explicit propagate/sync/rollout scope and a committed canonical change |
| The user wants an after-the-fact learning audit | [`task-retrospective`](../task-retrospective/SKILL.md#hard-boundary) | `authority-gated` | Explicit `/retro`, task-retrospective, or repeat-and-learn intent |
| The user wants Brainer usage itself audited | [`brainer-audit`](../brainer-audit/SKILL.md#trigger-model) | `authority-gated` | Explicit Brainer-audit/session-audit intent |
| The task changes prompts, skills, harnesses, or other self-improving machinery | [`self-improvement-loops`](../self-improvement-loops/SKILL.md#when-to-use) | `authority-gated` | The task must explicitly place agent machinery optimization in scope |

## Not selected by `/brainer` alone

Evaluation-arm skills require their own literal request: `caveman-ultra`,
`fable-mode`, `prompt-triage`, `requirements-ledger`, and `standing-orders`.
Their retained experimental status is not a recommendation.

Default or mechanical facilities continue under their ordinary triggers:
`compliance-canary`, `context-keeper`, `index-first`, `output-filter`,
`semantic-diff`, `wiki-memory`, `wiki-refresh`, and `write-gate`. `/brainer`
does not suppress, duplicate, or report them as discretionary selections.

## Conflict order

1. User instructions and project rules.
2. Safety and authority boundaries.
3. A selected source skill's mandatory routes and full-contract rules.
4. `/brainer` method choices.

When two optional choices address the same failure, keep the narrower one. When
their instructions conflict, do not blend them: follow the higher item above or
surface the unresolved choice.

Final identifiers are `<skill>:<export-id>`, `<skill>:whole`, or `none`; bare
skill names are invalid.
