---
name: loop-engineering
description: Use BEFORE building any multi-step agentic loop, generator→verifier pipeline, fan-out/fleet, or iterate-until-correct/retry loop. Picks the loop shape (open/closed · inner/outer · single/fleet), pairs a generator with a SEPARATE verifier, and forces a concrete gate + stop + budget cap up front. Ships loop_lint.py to refuse no-gate / self-grading / unbounded specs. Override with ONE SHOT.
effort: medium
tools: [Bash, Read, Write]
auto-install: false
pulse_reminder: before wiring a multi-step loop, name its generator, its SEPARATE verifier, the concrete pass/fail gate, the stop condition, and the budget cap, then run loop_lint.py. No gate or generator==verifier ⇒ not a loop, just an open-ended spin.
---

# Loop Engineering — design the verifier, not the prompt

A loop is a **generator wired to a verifier**. The generator was never the bottleneck — the verifier is, and **output quality is capped at verifier quality, never one point higher**. The engineering act is designing the gate, not the prompt. (The reflex "green is not goal-level done" is already owned — see [`verify-before-completion`](../verify-before-completion/SKILL.md) and [`task-retrospective`](../task-retrospective/SKILL.md); this skill adds the part those don't: choosing the loop's **shape** and **wiring** before it runs.)

## Do you even need a loop?

- Clear, low-risk, one-sentence diff → **type `ONE SHOT`, skip this skill.** A loop you don't need is the over-orchestration [`lean-execution`](../lean-execution/SKILL.md) exists to prune.
- "One closed loop, single worker" → the loop body **is** a [`plan-first-execute`](../plan-first-execute/SKILL.md) plan with a `done means:` block. Use that; don't re-plan here.
- loop-engineering earns its cost only when the topology is **non-trivial**: distinct generator/verifier roles, a fleet/fan-out, open-loop-by-design, or nested inner+outer.

## Choose the shape (three axes)

This is the net-new judgment no other skill makes. Pick each axis deliberately and know which side you are on.

| Axis | Left | Right |
|---|---|---|
| **open vs closed** | **open/explore** — fans out to novel-but-slop, no gate, expensive, drifts. Source of novelty; a slop machine on loose criteria. The freer the loop, the more it depends on what checks it. | **closed/execute** — bounds and gates each step, ships on a normal budget because paths are bounded. Closed loops ship today because of the gate, not the autonomy. |
| **inner vs outer** | **inner** (within one task) — edit → run the gate → confirm green THEN answer; fix and rerun on fail. Mature. | **outer** (across sessions) — write the lesson to SKILL.md/AGENTS.md so the next session starts ahead. Hand the whole learn/measure/escalate mechanic to [`task-retrospective`](../task-retrospective/SKILL.md); don't re-implement it. |
| **single vs fleet** | **single** — one agent rewrites its own draft (draft → check → fix → repeat). | **fleet** — an orchestrator splits the goal, every level runs discover/plan/execute/verify, only verified results bubble up. Adds git-worktree isolation + a quorum/aggregation gate where parallel results merge. |

Both layers are verification. Native tooling: `/goal` encodes the stop condition across turns; dynamic workflows make the fleet native (capped 16 concurrent / 1000 agents). They cost far more tokens — reach for them only when the task genuinely does not fit one pass.

## Wire the generator to a SEPARATE verifier

- Name the generator, name the verifier, and name the **channel** between them — what artifact crosses, in what format. Prefer a **typed report** (location + rule_source + suggested_fix + a failure-type enum) over a green/red bit, so the verifier's output is directly actionable by the next iteration.
- **The producer never grades its own homework.** An agent grading its own output grades generously; the verify step must be run fresh by an actor that did NOT generate the candidate. `loop_lint.py` rejects `generator == verifier` (R3). The actual pass/fail check is a [`verify-before-completion`](../verify-before-completion/SKILL.md) invocation — this skill only names *which* gate runs and *that* it is independent.
- **Exit on recomputed gate state, never on a model's done-claim.** A "PROJECT COMPLETE" token is not the gate; re-read the artifacts and recompute pass/fail. Per-role model choice defers to [`prompt-triage`](../prompt-triage/SKILL.md) (verifying is cheaper than making → a sonnet-class read-only verifier under an opus generator).

## The loop spec: four required fields

Declare these BEFORE the loop runs — they are `loop_lint.py`'s input contract:

1. **gate** — a concrete machine-checkable pass/fail signal the agent can call and read (a command / test id / assertion / schema), never "looks correct".
2. **stop** — the completion condition the loop runs until.
3. **budget** — a numeric iteration / token / wall-clock cap that halts a drifting loop. Unbounded is not a loop, it's a spin.
4. **generator ≠ verifier** — distinct producer and checker.

Then answer the questions the four fields don't cover:
- Against **what oracle** — test suite, spec, reference output, schema, or another agent?
- Is the loop **open or closed**, and is that intentional for THIS task (novelty wanted vs bounded shipping)?
- **green ≠ correct**: does the gate cover behaviour nobody wrote a test for yet, or only reproduce what existing tests already describe? 99.8% on an existing suite is *benchmark-green*, not correct — production is the behaviour nobody tested.
- For an **outer loop**: is the failure feedback written in plain language (WHY it failed) and stored in a FILE, not the context window, at the right grain/place, so the next attempt reads it? (ReAct → Reflexion; owned by [`task-retrospective`](../task-retrospective/SKILL.md).)

## Instrument before you scale

**You cannot improve a loop you do not measure** — instrument the gate (iteration count, pass rate, failure reasons, per-step cost/success) BEFORE you scale, or you are just generating wrong answers faster. Add cheap deterministic **liveness** counters distinct from the correctness gate (repeated-decision, empty/unparseable output, no-progress) with explicit escalation. A recurring "ran past budget" or "no gate" violation across sessions is promoted by [`task-retrospective`](../task-retrospective/SKILL.md) into a [`compliance-canary`](../compliance-canary/SKILL.md) drift probe — `drift_probes.json` is the runtime home for the static checks this skill's linter makes.

## Validate the spec

Write the loop spec as a fenced ` ```loop ` block (or a `.yaml`/`.json` file) and lint it:

```bash
python3 skills/loop-engineering/tools/loop_lint.py <file>   # exit 2 = fatal gap, 1 = warn, 0 = clean
```

Exit **2** = no gate (R1) / no stop+budget (R2) / self-grading (R3). Exit **1** = open-loop-without-ack (R4) / fleet-without-quorum (R5) / no-topology declared (R6). This is the gate-over-prose payoff: the three failure modes are refused statically, not re-argued. Field reference: [`tools/schema.md`](tools/schema.md).

## Persisting a reusable topology

A reusable generator/verifier/budget recipe is just another durable fact — route it through [`write-gate`](../write-gate/SKILL.md) into [`wiki-memory`](../wiki-memory/SKILL.md) as a `pattern` page. loop-engineering owns no store and no write path of its own.

## Files

- [`SKILL.md`](SKILL.md) — this doctrine.
- [`tools/loop_lint.py`](tools/loop_lint.py) — the mechanical gate: static loop-spec linter (R1–R6, exit code = verdict).
- [`tools/test_loop_lint.py`](tools/test_loop_lint.py) — 25 tests; registered in `scripts/run_all_tests.sh`.
- [`tools/schema.md`](tools/schema.md) — loop-spec field reference.
- [`drift_probes.json`](drift_probes.json) — `claim_without_evidence` probe (loop-done claim with no gate run); auto-discovered by compliance-canary.
- [`EVAL.md`](EVAL.md) — static cost + promotion path (opt-in until measured).

## Lineage

Doctrine descends from the generator-verifier "design the verifier, not the prompt" framing (ReAct: Yao et al.; Reflexion: Shinn et al.; the five-components-plus-memory framing follows Addy Osmani). Pattern sources (inspiration, **not** imports — frameworks stay pattern sources per `GOAL.md`):
- **HarnessCode** ([yzddp/harnesscode](https://github.com/yzddp/harnesscode)) — verifier-as-gate with a typed report + failure-type routing; the **anti-false-completion guard** (exit only on independently-recomputed gate state, never a model done-claim); thin deterministic driver + liveness counters.
- **autonomy-loop** ([inferencegod/autonomy-loop](https://github.com/inferencegod/autonomy-loop)) — independent re-verification by a separate actor (Builder/Reviewer in separate worktrees); the **coverage-ratchet** monotonic-floor gate; frozen-invariant + human escalation; cheap-panel + expensive-judge-on-dissent with a bounded-rounds deadlock cap.
