---
name: loop-engineering
description: Experimental/manual loop-design workflow retained for paired evaluation. Invoke explicitly with `/loop-engineering`; deterministic loop tools remain callable.
status: experimental
disable-model-invocation: true
effort: medium
tools: [Bash, Read, Write]
auto-install: false
pulse_reminder: before wiring a multi-step loop, name its generator, its SEPARATE verifier, the concrete pass/fail gate, the stop condition, and the budget cap, then run loop_lint.py. No gate or generator==verifier ⇒ not a loop, just an open-ended spin. A fixed once-through pipeline is the budget=1 case — still name a gate + a SEPARATE verifier and set the budget to max_iterations=1, don't skip the gate just because nothing retries.
---

<!-- split-justified -->

# Loop Engineering — design the verifier, not the prompt

A loop is a **generator wired to a verifier**. The generator was never the bottleneck — the verifier is, and **output quality is capped at verifier quality, never one point higher**. The engineering act is designing the gate, not the prompt. A loop is the *iterating* species of the broader *workflow* genus; a fixed once-through *pipeline* (A→B→C, nothing retries) is the same machinery with the budget pinned to one pass — so this skill covers both, because the gate-design act is identical whether the workflow iterates or runs once. (The reflex "green is not goal-level done" is already owned — see [`verify-before-completion`](../verify-before-completion/SKILL.md) and [`task-retrospective`](../task-retrospective/SKILL.md); this skill adds the part those don't: choosing the loop's **shape** and **wiring** before it runs.)

Deep-dive reference: [REFERENCE.md](REFERENCE.md) — runtime-loop stack, memory contract, multi-model advisor/verifier panels, fleet orchestration, Mixture-of-Agents synthesis, instrumentation, failure-mode catalog, and lineage.

Any frontier-tier loop lead follows the hard economy invariant in
[`ORCHESTRATION.md §6`](../_shared/ORCHESTRATION.md#6-architect-cost-discipline-frontier-tier-orchestrator): the lead owns hard reasoning and verdicts while the cheapest reachable capable lanes carry bounded volume.

## Do you even need a loop?

**The 4-condition test — miss one and a one-shot prompt beats a loop** (the loop's setup never amortizes):
1. **Repeats** — the task recurs (≈weekly+); a one-time job wants a good prompt, not a loop.
2. **Verification is automated** — a test / typecheck / lint / build can fail the work with no human in the room. No auto-gate ⇒ you are back reading every diff (the job the loop was meant to remove).
3. **Budget absorbs the waste** — loops re-read, retry, and explore; that burns tokens whether or not a run ships.
4. **Senior-engineer tools** — logs, a repro env, the ability to run what it writes; without them it iterates blind.

Then:
- Clear, low-risk, one-sentence diff → **type `ONE SHOT`, skip this skill.**
- "One closed loop, single worker" → write a plan with a `done means:` block. Use that; don't re-plan here.
- loop-engineering earns its cost only when the topology is **non-trivial**: distinct generator/verifier roles, a fleet/fan-out, open-loop-by-design, or nested inner+outer.
- **A fixed, non-iterating pipeline** (A→B→C, each stage runs exactly once, nothing retries-until-pass) is a workflow too — the **budget=1 case of a loop**, not a reason to skip the gate. Write it as a normal spec with `budget: max_iterations=1`: each stage still needs a machine `gate`, and that gate must be run by something other than the stage that produced the output (`generator ≠ verifier` holds *per stage*). It lints clean today — no new schema, no new tool. The instant any stage loops back to retry an earlier one it has become a real loop: raise the budget and re-spec. (A pipeline written without these correctly FAILs `loop_lint` R1/R2/R3 — the fix is the budget=1 spec, not a different tool.)

## Pre-flight the harness underneath

A loop is only as good as the harness it repeats. Before scheduling, fanning out, or calling something self-improving, inventory the harness surface the loop will run inside:

- **Context** — standing facts stay tiny and stable; procedures belong in skills; path-specific behavior belongs near the path or in a scoped rule. If a context file is mostly instructions for how to do a task, promote that procedure to a skill instead of paying for it every run.
- **Tools and permissions** — safe reads/checks can be allowed; destructive, irreversible, credential-shaped, deploy, merge, push, publish, charge/refund, or migration actions need deny/prompt/human approval. Unattended loops expand blast radius, so audit permissions before the timer starts.
- **Hooks** — deterministic enforcement goes in hooks/probes, not prose. Use hooks for "must happen" or "must never happen" checks; do not turn judgment calls into brittle shell gates.
- **Subagents** — isolate noisy exploration and verification from the main context. The most important subagent is a fresh-context checker or refuter; the writer does not grade its own output. **Hooks/probes do NOT fire inside a subagent** — it gets no drift probes, no re-anchor, no routing — so **inline the active skill directives into every brief** (render with [`brief_header.py`](../_shared/brief_header.py)) and **re-verify its output in the main loop**, where the probes fire; a subagent told "don't touch files" has been seen doing it anyway, so trust the post-check, not the instruction. (Full fleet mechanics: [REFERENCE.md](REFERENCE.md).)
- **Memory** — every repeated run needs a resume surface and a learning surface. Ephemeral state can live in a task folder; durable, verified lessons route through [`write-gate`](../write-gate/SKILL.md) into [`wiki-memory`](../wiki-memory/SKILL.md), then into a skill only when the procedure is repeatable.

If that pre-flight is mostly blank, do not wrap the default harness in a loop. Get one manual run reliable, add the smallest context/permission/reviewer/memory pieces, then schedule it.

## Choose the shape (three axes)

This is the net-new judgment no other skill makes. Pick each axis deliberately and know which side you are on.

| Axis | Left | Right |
|---|---|---|
| **open vs closed** | **open/explore** — fans out to novel-but-slop, no gate, expensive, drifts. Source of novelty; a slop machine on loose criteria. The freer the loop, the more it depends on what checks it. | **closed/execute** — bounds and gates each step, ships on a normal budget because paths are bounded. Closed loops ship today because of the gate, not the autonomy. |
| **inner vs outer** | **inner** (within one task) — edit → run the gate → confirm green THEN answer; fix and rerun on fail. Mature. | **outer** (across sessions) — preserve traces so the next session starts ahead. If the user armed project learning, hand the learn/measure/escalate mechanic to [`task-retrospective`](../task-retrospective/SKILL.md); don't re-implement it inside the loop. |
| **single vs fleet** | **single** — one agent rewrites its own draft (draft → check → fix → repeat). | **fleet** — an orchestrator splits the goal, every level runs discover/plan/execute/verify, only verified results bubble up. |

Both layers are verification. Native tooling: `/goal` encodes the stop condition across turns; dynamic workflows make the fleet native (capped 16 concurrent / 1000 agents). They cost far more tokens — reach for them only when the task genuinely does not fit one pass.

## The loop spec: four required fields

Declare these BEFORE the loop runs — they are `loop_lint.py`'s input contract:

1. **gate** — a concrete machine-checkable pass/fail signal the agent can call and read (a command / test id / assertion / schema), never "looks correct".
2. **stop** — the completion condition the loop runs until. Scheduled/recurring loops type the terminal states — `done` · `no-op` (empty round is legitimate; don't invent work to fill it) · `partial` (cap hit → carry the remainder to the next round's queue head) · `blocked/escalate` — so a quiet week and a silent drop stop looking identical.
3. **budget** — a numeric iteration / token / wall-clock cap that halts a drifting loop. Unbounded is not a loop, it's a spin.
4. **generator ≠ verifier** — distinct producer and checker. **The producer never grades its own homework.** `loop_lint.py` rejects `generator == verifier` (R3); the deep mechanics (typed report channel, verifier-blindness declaration, egress/redaction/consent controls) are in the deep-dive.

Then answer the questions the four fields don't cover:
- Against **what oracle** — test suite, spec, reference output, schema, or another agent? **No obvious oracle** (perceptual / creative / "matches the original" goals)? Delegate metric-invention: have the agent propose a concrete, machine-checkable proxy derived from the real target (record the real thing → derive a comparable artifact → diff against it), then approve the proxy BEFORE it becomes the gate — an unapproved self-invented gate is self-grading by construction (R3).
- Is the loop **open or closed**, and is that intentional for THIS task (novelty wanted vs bounded shipping)?
- If the loop is scheduled/fleet/outer, where do `anchor_files`, `state_store`, `recall`, and `writeback` live — and who owns `state_concurrency`? (Full memory-contract field reference in the deep-dive.)
- For a scheduled/recurring loop: **freeze the check across rounds** (a changed check makes this round's score incomparable with last round's) and **change ONE thing per round** — single-change rounds keep attribution clean. Over a noisy signal, set an **evidence floor**: act only on ≥N independent, cited instances (one loud instance is not a trend); below the floor the round is a `no-op`, not a smaller action. Acceptance checks/gates are committed (frozen) BEFORE the generator runs and live outside the worker's editable blast radius; any worker edit to a frozen check is an automatic FAIL regardless of results — visible iterate-against-the-check loops measurably raise gaming (ImpossibleBench 33%→38%).
- If it is a fix/retry loop, what is the `stuck` detector (same command 3× / same error 2× / 2 iters no movement), and which `advisor` panel does it consult on stall? Source it from [`skills/_shared/model_roster.py`](../_shared/model_roster.py); keep it separate from the verifier (R11).
- Does the **first** gate check land early in the budget? A loop whose first verification runs only after most of the budget is spent is a once-through in disguise — early misreadings ossify into design later iterations build around. Size iterations so verification starts at iteration 1.
- **green ≠ correct**: does the gate cover behaviour nobody wrote a test for yet, or only reproduce what existing tests already describe? 99.8% on an existing suite is *benchmark-green*, not correct — production is the behaviour nobody tested.
- For an **outer loop**: the highest-signal, lowest-friction feedback channel is the human's **in-place override delta** — what they changed and the reason they left at the work site (a relabel + a reply), not a report you ask them to write. **Grade that feedback before acting on it**: an explicit correction/relabel is strong, a reaction is moderate, silence is weak-positive. If project learning is armed, [`task-retrospective`](../task-retrospective/SKILL.md) owns the decision about whether that lesson belongs in memory, an SOP, a checklist, or a project-specific skill. Conflicting or weak signal ⇒ no durable write.

## Validate the spec

Write the loop spec as a fenced ` ```loop ` block (or a `.yaml`/`.json` file) and lint it. **Unattended loop? Declare `on_error` and `output_actions` up front** (R14/R10; field details in the deep-dive) — measured 2026-07: core-only subjects skipped both unless told here.

```bash
python3 skills/loop-engineering/tools/loop_lint.py <file>   # exit 2 = fatal gap, 1 = warn, 0 = clean
```

Exit **2** = no gate (R1) / no stop+budget (R2) / self-grading (R3) / irreversible-action-without-human-gate on an **unattended** loop (R7). Exit **1** = open-loop-without-ack (R4) / fleet-without-quorum (R5) / no-topology declared (R6) / irreversible-action-without-human-gate on an **attended** loop (R7) / missing memory contract on scheduled/fleet/outer loops (R8) / fleet state with no concurrency strategy (R9) / unbounded output surface on an unattended side-effecting loop (R10) / stuck loop with no advisor, or advisor==verifier (R11) / cross-vendor egress with no `redaction` declared, or unattended egress with no `consent` gate (R12) / LLM verifier on an unattended/cross-vendor loop that doesn't declare blindness (R13) / degenerate zero-cap budget (R2 warn). On a non-zero exit, **fix the flagged field and re-lint until exit 0** — the spec is itself a closed inner loop with `loop_lint.py` as its gate. This is the gate-over-prose payoff: the failure modes are refused statically, not re-argued. Field reference: [`tools/schema.md`](tools/schema.md).

**Freeze the verified spec (`--resolve`).** For an outer/fleet/scheduled loop, `loop_lint.py --resolve <file>` emits an immutable `loop.resolved` snapshot (fields + lint verdict) as a replay/drift surface — *not* a resume checkpoint (no run state, no runner; the linter stays a linter). Use it so a long-lived loop can re-dispatch the exact spec it verified, and so spec-drift (editing the source while a loop runs stale logic) is detectable.

**See the loop.** `--diagram` renders the spec as a Mermaid generator→gate→verifier loop with the lint findings overlaid as coloured nodes — derived from the parsed spec (never invented), exit code still the lint verdict so it composes in CI (full node-colour mapping in [`tools/schema.md`](tools/schema.md)):

```bash
python3 skills/loop-engineering/tools/loop_lint.py --diagram <file>   # Mermaid to stdout; wrap in a ```mermaid fence to render
```

## Files

- [`tools/loop_lint.py`](tools/loop_lint.py) — static loop-spec linter; exit code = verdict.
- [`tools/loop_run_monitor.py`](tools/loop_run_monitor.py) — runtime trace gate: stuck + cost-per-accepted-change.
- [`tools/schema.md`](tools/schema.md) — loop-spec field reference.
- [`../_shared/model_roster.py`](../_shared/model_roster.py) — detect reachable cross-vendor backends; render read-only advisor (diverge) / verifier (converge) dispatches. Native CLIs preferred; optional **OpenRouter** transport backfills absent lanes (`--via openrouter` to prefer it) and offers **Fusion** as an advisor (`--fusion`). Shared with [`verify-before-completion`](../verify-before-completion/SKILL.md).
