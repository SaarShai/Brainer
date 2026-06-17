---
name: loop-engineering
description: Use BEFORE building any multi-step agentic loop, generator→verifier pipeline, fan-out/fleet, or iterate-until-correct/retry loop — INCLUDING an automated / unattended / scheduled / nightly process that regenerates, revises, or rebuilds artifacts and keeps retrying each until it passes a check, any self-correcting or "keep going until it's good enough" automation, and any build-and-verify or generate-and-grade pipeline. If the task is "set up something that runs repeatedly and fixes its own output", this skill applies. Picks the loop shape (open/closed · inner/outer · single/fleet), pairs a generator with a SEPARATE verifier, and forces a concrete gate + stop + budget cap up front. Ships loop_lint.py to refuse no-gate / self-grading / unbounded specs. Override with ONE SHOT.
effort: medium
tools: [Bash, Read, Write]
auto-install: true
pulse_reminder: before wiring a multi-step loop, name its generator, its SEPARATE verifier, the concrete pass/fail gate, the stop condition, and the budget cap, then run loop_lint.py. No gate or generator==verifier ⇒ not a loop, just an open-ended spin.
---

# Loop Engineering — design the verifier, not the prompt

A loop is a **generator wired to a verifier**. The generator was never the bottleneck — the verifier is, and **output quality is capped at verifier quality, never one point higher**. The engineering act is designing the gate, not the prompt. (The reflex "green is not goal-level done" is already owned — see [`verify-before-completion`](../verify-before-completion/SKILL.md) and [`task-retrospective`](../task-retrospective/SKILL.md); this skill adds the part those don't: choosing the loop's **shape** and **wiring** before it runs.)

## Do you even need a loop?

**The 4-condition test — miss one and a one-shot prompt beats a loop** (the loop's setup never amortizes):
1. **Repeats** — the task recurs (≈weekly+); a one-time job wants a good prompt, not a loop.
2. **Verification is automated** — a test / typecheck / lint / build can fail the work with no human in the room. No auto-gate ⇒ you are back reading every diff (the job the loop was meant to remove).
3. **Budget absorbs the waste** — loops re-read, retry, and explore; that burns tokens whether or not a run ships.
4. **Senior-engineer tools** — logs, a repro env, the ability to run what it writes; without them it iterates blind.

Then:
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

## Orchestrating a fleet (fan-out · brief · synthesize)

When the task is big enough to split, the orchestrator IS the loop: **write the GOAL, split it into independent pieces, dispatch them concurrently, synthesize results as they return**, and re-issue or retire goals as findings land — don't run agents serially when the pieces don't depend on each other.

- **Brief each agent BEFORE dispatch** — a self-contained packet: the goal, in-scope files/paths, a `done means:` block, and the **explicit OUT-of-scope** line that stops scope creep. The description is all a subagent reads — keep it trigger-first, cap its turns, restrict its tools to its role.
- **Executor report contract** — every agent returns: what it changed, **attempts tried and abandoned** (approach → outcome → why), every assumption it made where the brief was silent, and ends with **"READY FOR JUDGING"**, never "done". A subagent's done-claim is an input, not a verdict.
- **Typed handoff between stages** — pass a staged chain in a shared task folder (`spec.md → changes.md → review.md`), each independently auditable, so the verifier reads exactly the right artifact and the test path derives from the **SPEC, not the implementation**.
- **Isolate writers** — when >1 agent writes, give each its own git worktree (`isolation: worktree`) and merge through a quorum/aggregation gate; never let two agents write the same tree.
- **Quarantine untrusted input** — an agent that reads untrusted content (web pages, user-supplied files, external tool output) gets read-only / no high-privilege tools; the actor that *acts* never sees the raw untrusted bytes. Untrusted-content + a write tool in one agent is the injection hole.
- **Hooks do NOT fire inside subagents.** `compliance-canary` / `prompt-triage` are main-loop-only — a spawned agent gets no drift probes, no re-anchor, no routing. So: (1) **inline the relevant skill directives verbatim into each subagent's prompt** (the verify-before-completion reflex, this loop gate, terseness, the report contract); (2) keep subagents short-lived and single-purpose; (3) **re-verify their output in the main loop**, where the probes do fire. This is the one mechanical lever that reaches a fleet.

Pick the workflow pattern deliberately: **fan-out-and-synthesize** · **adversarial-verification** (N skeptics each try to refute a finding) · **loop-until-dry** (re-spawn finders until K rounds add nothing new) · **classify-and-act** (route by model tier — [`prompt-triage`](../prompt-triage/SKILL.md)) · **generate-and-filter** (N candidates → rubric → top-K, [`eval-gate`](../eval-gate/SKILL.md)) · **tournament** (pairwise beats absolute scoring for taste/ranking). Effort routing: frontier model orchestrates, opus-class for hard-bounded subtasks, sonnet-class for high-volume reads, haiku-class for graders/classifiers.

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
- For an **outer loop**: the highest-signal, lowest-friction feedback channel is the human's **in-place override delta** — what they changed and the reason they left at the work site (a relabel + a reply), not a report you ask them to write. **Grade that feedback before acting on it**: an explicit correction/relabel is strong, a reaction is moderate, silence is weak-positive — edit the spec/SKILL.md only on a *generalizable, well-supported* lesson; conflicting or weak signal ⇒ no change (don't thrash). Then store the WHY in a FILE, not the context window, at the right grain so the next run reads it. (ReAct → Reflexion; owned by [`task-retrospective`](../task-retrospective/SKILL.md).)

## Instrument before you scale

**You cannot improve a loop you do not measure** — instrument the gate (iteration count, pass rate, failure reasons, per-step cost/success) BEFORE you scale, or you are just generating wrong answers faster. The metric that matters is **cost per accepted change**, not tokens spent — under ~50% accepted means the loop is making review work, not saving it. Add cheap deterministic **stuck detectors** distinct from the correctness gate, with concrete thresholds: **same command 3×, same error 2× (the `repeated_tool_error` probe), or 2 iterations with no metric movement = stuck.** On stuck, do NOT retry harder — **force entropy**: require a *structurally different* hypothesis before the next execution. Caps stay small (≈2–3 for a fix loop); on hitting the cap, **escalate with a decision brief** — the options tried and the evidence behind each, never a bare "it doesn't work". Per-cycle, ask the overfit question: *am I building the general solution, or memorizing this eval?* A recurring "ran past budget" or "no gate" violation across sessions is promoted by [`task-retrospective`](../task-retrospective/SKILL.md) into a [`compliance-canary`](../compliance-canary/SKILL.md) drift probe — `drift_probes.json` is the runtime home for the static checks this skill's linter makes. Build the **minimum viable loop** in order — get one manual run reliable → make it a skill → wrap it in a loop → schedule it; skipping ahead ships a loop nobody understands.

## Design against the quiet failures

- **Ralph Wiggum loop** — the agent emits its "done" token early and the loop exits half-finished. The fix is the R1/R3 gate: an **objective** check (a test/build/lint exit code) that can FAIL the work — never a second agent with an opinion.
- **Goal drift** — long sessions lose "don't do X" constraints to lossy summarization. Reread a standing spec (`VISION.md` / `AGENTS.md` / the `done means:` block) each run.
- **Comprehension debt** — the faster the loop ships code you didn't write, the wider the gap between the repo and what anyone understands. **Read the diffs**; spot-check that the gate still catches the failure you care about (**gates rot**); keep the loop off architecture / auth / payments.
- **Gate integrity — never weaken the gate to pass.** A failing check is failing; a tolerance / threshold / expectation change needs explicit human approval and never happens mid-run to convert FAIL→PASS. The coverage ratchet only ever *raises* the floor. A loop that lowers its own bar to ship is lying to itself.
- **Unattended = an attack surface** — an autonomous loop merges code, installs skills, and writes logs while nobody watches. Require a **human-approval gate before any irreversible action** (merge / deploy / migrate / dependency bump), scope and re-audit its permissions, and audit any skill it auto-installs. `loop_lint.py` flags this statically (R7: an autonomous loop that deploys/merges/migrates/charges with no human gate).

## Validate the spec

Write the loop spec as a fenced ` ```loop ` block (or a `.yaml`/`.json` file) and lint it:

```bash
python3 skills/loop-engineering/tools/loop_lint.py <file>   # exit 2 = fatal gap, 1 = warn, 0 = clean
```

Exit **2** = no gate (R1) / no stop+budget (R2) / self-grading (R3). Exit **1** = open-loop-without-ack (R4) / fleet-without-quorum (R5) / no-topology declared (R6) / irreversible-action-without-human-gate (R7) / degenerate zero-cap budget (R2 warn). On a non-zero exit, **fix the flagged field and re-lint until exit 0** — the spec is itself a closed inner loop with `loop_lint.py` as its gate. This is the gate-over-prose payoff: the failure modes are refused statically, not re-argued. Field reference: [`tools/schema.md`](tools/schema.md).

**See the loop.** `--diagram` renders the spec as a Mermaid generator→gate→verifier loop with the lint findings overlaid — a missing gate, a `generator == verifier` self-loop, or an unbounded budget shows up as a coloured node, not a line in a report. The diagram is derived from the parsed spec (never invented), and the exit code is still the lint verdict, so it composes in CI:

```bash
python3 skills/loop-engineering/tools/loop_lint.py --diagram <file>   # Mermaid to stdout; wrap in a ```mermaid fence to render
```

## Persisting a reusable topology

A reusable generator/verifier/budget recipe is just another durable fact — route it through [`write-gate`](../write-gate/SKILL.md) into [`wiki-memory`](../wiki-memory/SKILL.md) as a `pattern` page. loop-engineering owns no store and no write path of its own.

## Files

- [`SKILL.md`](SKILL.md) — this doctrine.
- [`tools/loop_lint.py`](tools/loop_lint.py) — the mechanical gate: static loop-spec linter (R1–R7, exit code = verdict).
- [`tools/test_loop_lint.py`](tools/test_loop_lint.py) — 61 tests (4 adversarial rounds + R7 verify + `--diagram`); registered in `scripts/run_all_tests.sh`.
- [`tools/schema.md`](tools/schema.md) — loop-spec field reference.
- [`drift_probes.json`](drift_probes.json) — three probes (loop-done claim with no gate run; loop-build intent; fleet-orchestration intent); auto-discovered by compliance-canary.
- [`EVAL.md`](EVAL.md) — static cost + promotion path (opt-in until measured).

## Lineage

Doctrine descends from the generator-verifier "design the verifier, not the prompt" framing (ReAct: Yao et al.; Reflexion: Shinn et al.). The five-components-plus-memory, maker/checker, comprehension-debt, and cognitive-surrender framings follow **Addy Osmani**'s loop-engineering essay; the **4-condition economics test** + minimum-viable-loop ordering + cost-per-accepted-change metric follow AlphaSignal / **Lev Deviatkin**'s prompter→loop-designer roadmap; the **Ralph Wiggum loop** failure mode is **Geoffrey Huntley**'s; the durable-project-loop / state-file-as-spine continuity framing is from the repo-as-loop writeups (Jason Liu, steipete). Pattern sources (inspiration, **not** imports — frameworks stay pattern sources per `GOAL.md`):
- **HarnessCode** ([yzddp/harnesscode](https://github.com/yzddp/harnesscode)) — verifier-as-gate with a typed report + failure-type routing; the **anti-false-completion guard** (exit only on independently-recomputed gate state, never a model done-claim); thin deterministic driver + liveness counters.
- **autonomy-loop** ([inferencegod/autonomy-loop](https://github.com/inferencegod/autonomy-loop)) — independent re-verification by a separate actor (Builder/Reviewer in separate worktrees); the **coverage-ratchet** monotonic-floor gate; frozen-invariant + human escalation; cheap-panel + expensive-judge-on-dissent with a bounded-rounds deadlock cap.
- **issue-triage-loop** ([warpdotdev-demos/issue-triage-loop](https://github.com/warpdotdev-demos/issue-triage-loop)) — a worked inner/outer self-improvement loop: inner skill fires on issue-open, outer skill reads recent runs and PRs a SKILL.md diff that **never self-merges** (R7). Source of the **grade-the-feedback-by-source-strength** rule (correction/relabel strong · reaction moderate · silence weak-positive → don't thrash) and the **in-place override delta** as the cheapest feedback channel.
