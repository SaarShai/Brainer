---
name: loop-engineering
description: Use BEFORE building any multi-step agentic loop, generator→verifier pipeline, fan-out/fleet, or iterate-until-correct/retry loop — INCLUDING an automated / unattended / scheduled / nightly process that regenerates, revises, or rebuilds artifacts and keeps retrying each until it passes a check, any self-correcting or "keep going until it's good enough" automation, and any build-and-verify or generate-and-grade pipeline. Also use when auditing the agent harness under a loop (context, tools, permissions, hooks, subagents, skills, memory). If the task is "set up something that runs repeatedly and fixes its own output", this skill applies. Picks the loop shape (open/closed · inner/outer · single/fleet), pairs a generator with a SEPARATE verifier, and forces a concrete gate + stop + budget cap up front. Ships loop_lint.py to refuse no-gate / self-grading / unbounded specs and loop_run_monitor.py to gate runtime traces for stuck/costly loops. A fixed non-iterating pipeline (A→B→C, each stage runs once, no retry) is the degenerate budget=1 case — model it with a max_iterations=1 budget, a per-stage gate, and a verifier separate from each stage's producer; it lints clean as a budget=1 loop. Override with ONE SHOT.
effort: medium
tools: [Bash, Read, Write]
auto-install: true
pulse_reminder: before wiring a multi-step loop, name its generator, its SEPARATE verifier, the concrete pass/fail gate, the stop condition, and the budget cap, then run loop_lint.py. No gate or generator==verifier ⇒ not a loop, just an open-ended spin. A fixed once-through pipeline is the budget=1 case — still name a gate + a SEPARATE verifier and set the budget to max_iterations=1, don't skip the gate just because nothing retries.
---

# Loop Engineering — design the verifier, not the prompt

A loop is a **generator wired to a verifier**. The generator was never the bottleneck — the verifier is, and **output quality is capped at verifier quality, never one point higher**. The engineering act is designing the gate, not the prompt. A loop is the *iterating* species of the broader *workflow* genus; a fixed once-through *pipeline* (A→B→C, nothing retries) is the same machinery with the budget pinned to one pass — so this skill covers both, because the gate-design act is identical whether the graph iterates or runs once. (The reflex "green is not goal-level done" is already owned — see [`verify-before-completion`](../verify-before-completion/SKILL.md) and [`task-retrospective`](../task-retrospective/SKILL.md); this skill adds the part those don't: choosing the loop's **shape** and **wiring** before it runs.)

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
- **A fixed, non-iterating pipeline** (A→B→C, each stage runs exactly once, nothing retries-until-pass) is a workflow too — the **budget=1 case of a loop**, not a reason to skip the gate. Write it as a normal spec with `budget: max_iterations=1`: each stage still needs a machine `gate`, and that gate must be run by something other than the stage that produced the output (`generator ≠ verifier` holds *per stage*). It lints clean today — no new schema, no new tool. The instant any stage loops back to retry an earlier one it has become a real loop: raise the budget and re-spec. (A pipeline written without these correctly FAILs `loop_lint` R1/R2/R3 — the fix is the budget=1 spec, not a different tool.)

## Pre-flight the harness underneath

A loop is only as good as the harness it repeats. Before scheduling, fanning out, or calling something self-improving, inventory the harness surface the loop will run inside:

- **Context** — standing facts stay tiny and stable; procedures belong in skills; path-specific behavior belongs near the path or in a scoped rule. If a context file is mostly instructions for how to do a task, promote that procedure to a skill instead of paying for it every run.
- **Tools and permissions** — safe reads/checks can be allowed; destructive, irreversible, credential-shaped, deploy, merge, push, publish, charge/refund, or migration actions need deny/prompt/human approval. Unattended loops expand blast radius, so audit permissions before the timer starts.
- **Hooks** — deterministic enforcement goes in hooks/probes, not prose. Use hooks for "must happen" or "must never happen" checks; do not turn judgment calls into brittle shell gates.
- **Subagents** — isolate noisy exploration and verification from the main context. The most important subagent is a fresh-context checker or refuter; the writer does not grade its own output.
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

## Stack the runtime loops deliberately

Use the four-loop stack as a diagnosis before adding machinery:

1. **Agent loop** — model ↔ tools until a result exists — the ordinary work loop; for a single bounded task, [`plan-first-execute`](../plan-first-execute/SKILL.md) plus [`verify-before-completion`](../verify-before-completion/SKILL.md) is usually enough.
2. **Verification loop** — grader/rubric/test sends feedback back to the agent. This skill names the verifier and gate; [`eval-gate`](../eval-gate/SKILL.md) handles judgment rubrics when deterministic tests cannot express "good enough".
3. **Event loop** — a trigger (cron, webhook, inbox/channel, file watcher) starts the verified agent loop repeatedly. This is deployment wiring, not new autonomy: the same loop spec still needs harness pre-flight, a gate, stop, budget, permissions audit, and human approval before irreversible actions.
4. **Hill-climbing loop** — traces from repeated runs feed a separate analysis pass that proposes harness improvements. Never let this loop self-merge. It should produce a reviewed patch, or when project learning is armed, a lesson routed through [`task-retrospective`](../task-retrospective/SKILL.md), [`write-gate`](../write-gate/SKILL.md), and [`wiki-memory`](../wiki-memory/SKILL.md).

The outer-loop handoff artifact is the trace, not a vibe. For every scheduled or unattended loop, decide up front which fields are emitted per iteration (`command`, `error`, `metric`, `accepted`, `cost`) so the next layer can measure improvement instead of reading tea leaves.

## Add the loop memory contract

Loops that run past one context window need memory on purpose, not by accident. A loop without memory is a circle: every pass starts at day one. A loop with scoped recall/writeback becomes a spiral: each pass starts from what survived verification.

For any scheduled, event-triggered, outer, or fleet loop, add these advisory fields to the spec before it runs:

- `anchor_files` — the fixed files re-read at the start of every pass (`VISION.md`, `PROMPT.md`, `AGENTS.md`, `SKILL.md`, the task packet, or the relevant wiki index). They are the compact replacement for a bloating conversation.
- `state_store` — the durable pass state path or system (`LOOP-STATE.json`, a markdown board, a task folder, or wiki-backed state). Ephemeral attempts live here; durable lessons do not.
- `recall` — the exact pre-pass command/procedure: read the state store, run wiki-memory search/timeline/fetch, inspect the board, then act.
- `writeback` — the exact post-pass command/procedure: record attempts tried, verifier verdict, failures, changed facts, and the next action.
- `state_concurrency` — for fleets only: `single_writer`, `optimistic_revision`, or `worktree_isolated`. Shared state without a merge strategy creates parallel-agent conflicts.

Keep the boundary clean: `state_store` records run-local state; [`wiki-memory`](../wiki-memory/SKILL.md) records durable, verified lessons through [`write-gate`](../write-gate/SKILL.md) when persistence is explicitly selected; [`context-keeper`](../context-keeper/SKILL.md) preserves a compaction checkpoint; armed [`task-retrospective`](../task-retrospective/SKILL.md) decides what generalizes after verification. Do not install Mem0/Zep/etc. just because a loop needs memory; first express the contract against Brainer's repo-local stores, then measure whether an external semantic backend beats it.

## Wire the generator to a SEPARATE verifier

- Name the generator, name the verifier, and name the **channel** between them — what artifact crosses, in what format. Prefer a **typed report** (location + rule_source + suggested_fix + a failure-type enum) over a green/red bit, so the verifier's output is directly actionable by the next iteration.
- **The producer never grades its own homework.** An agent grading its own output grades generously; the verify step must be run fresh by an actor that did NOT generate the candidate. `loop_lint.py` rejects `generator == verifier` (R3). The actual pass/fail check is a [`verify-before-completion`](../verify-before-completion/SKILL.md) invocation — this skill only names *which* gate runs and *that* it is independent. A separate actor is necessary but not sufficient: the verifier must also be **blind** to the generator's reasoning/code/skill content — seeing only the task + the outputs, never the generator's self-justification, because a verifier that reads that chain of self-persuasion inherits the same bias. Declare that surface so it is auditable — `verifier_blind: true` / `verifier_inputs: task, outputs` (or a "fresh context" verifier); `loop_lint` **R13** warns when an LLM verifier on an unattended/cross-vendor loop leaves blindness undeclared or declares it non-blind.
- **Exit on recomputed gate state, never on a model's done-claim.** A "PROJECT COMPLETE" token is not the gate; re-read the artifacts and recompute pass/fail. Per-role model choice defers to [`prompt-triage`](../prompt-triage/SKILL.md) (verifying is cheaper than making → a sonnet-class read-only verifier under an opus generator).

## Two panels, one model roster: advisor (diverge) vs verifier (converge)

The verifier need not be a single actor, and the loop has a second multi-model role most specs forget. Tap **every model this host can actually reach** — `python3 skills/_shared/model_roster.py` detects which backends are live (codex · gemini · claude · ollama · glm/z.ai) and renders a **read-only, synchronous, cross-vendor** dispatch for either role. The two roles must stay strictly separate — collapsing them re-opens the LLM-judge hole R1/R3 exist to refuse:

- **Verifier panel — CONVERGENT, it IS the gate.** A cross-vendor set re-runs the *objective* check and refutes if it can; odd-N (default 3) majority, a refutation blocks ship. This is just the multi-model form of the separate verifier above — the exact mechanism [`verify-before-completion`](../verify-before-completion/SKILL.md) Part D already fires for high-stakes results. An advisor's *opinion* is never this gate; the gate stays a machine check.
- **Advisor panel — DIVERGENT, it feeds the GENERATOR.** When stuck, the same roster is asked a *different* question — *propose structurally-different approaches, other tools, other methods* — and returns fresh hypotheses, never a pass/fail. The generator picks one; the objective gate still decides. Advisors widen the search; they never lower the bar.

`model_roster.pick_panel(exclude_lane=…)` drops the orchestrator's own vendor so the panel is a real second opinion, not an echo of the stuck agent. Declare the wiring in the spec with `stuck:` (the detector that fires it) and `advisor:` (the panel); `loop_lint` **R11** warns when a stuck loop names no advisor, or when the advisor collapses into the verifier (propose-and-judge is self-grading by another door).

**Egress is a control surface, not a free wire.** A cross-vendor panel sends repo-derived content (the task + the decision brief) to a third-party model. Two controls, enforced not exhorted (borrowed from [ksimback/looper](https://github.com/ksimback/looper)'s privacy layer): (1) **redaction** — `model_roster.render_prompt` scrubs a broad secret family ([`audit_redact.py`](../_shared/audit_redact.py)) before the prompt is rendered, so a leaked key/`.env`/PEM never crosses the wire on either the copy-paste or `--run` path; (2) **consent** — `model_roster --run` refuses to egress without `--consent` / `MODEL_ROSTER_EGRESS_CONSENT=1`, so cross-vendor send is a deliberate act. Declare both in the spec (`redaction:` always, `consent:` for unattended loops) or `loop_lint` **R12** warns. And recompute a verifier panel's quorum *after* dispatch (`verifier_quorum`, R11b): members drop when a CLI is in PATH but unauthenticated, so a 1-member or even panel is a weak gate, not a passed one.

**Transport vs judgment — OpenRouter (optional).** A lane is reached either by its *native* CLI (codex/agy/claude — free subscription reuse) or, when no native CLI exists on the host, by the **OpenRouter** proxy (one OpenAI-compatible key fronting 400+ models). The roster auto-**backfills** absent lanes via OpenRouter when `~/.config/openrouter/key` (or `OPENROUTER_API_KEY`) is present; `--via openrouter` *prefers* the proxy for every eligible lane (one-provider consolidation / A/B comparison). This is a wire choice — **OpenRouter changes how a model is reached, never who judges**: the verifier gate (refute-if-you-can, odd-N majority, `holds:bool`) stays ours regardless. The `local`/ollama lane is **never** routed through the proxy — it is the on-box survivor backstop against the proxy being a single point of failure (the documented June-2025 OpenRouter 403 of Claude+Gemini). OpenRouter **Fusion** (`--fusion`, panel→judge synthesis) is available for the **advisor** role only; it is consensus-oriented and returns analysis, not a verdict, so it must never be wired as the gate (that would re-open the R1/R3 hole). Native lanes are preferred by default; OpenRouter buys reliability + model-availability, not a replacement for the gate.

## Orchestrating a fleet (fan-out · brief · synthesize)

When the task is big enough to split, the orchestrator IS the loop: **write the GOAL, split it into independent pieces, dispatch them concurrently, synthesize results as they return**, and re-issue or retire goals as findings land — don't run agents serially when the pieces don't depend on each other.

- **Brief each agent BEFORE dispatch** — a self-contained packet: the goal, in-scope files/paths, a `done means:` block, and the **explicit OUT-of-scope** line that stops scope creep. The description is all a subagent reads — keep it trigger-first, cap its turns, restrict its tools to its role.
- **Executor report contract** — every agent returns: what it changed, **attempts tried and abandoned** (approach → outcome → why), every assumption it made where the brief was silent, and ends with **"READY FOR JUDGING"**, never "done". A subagent's done-claim is an input, not a verdict.
- **Typed handoff between stages** — pass a staged chain in a shared task folder (`spec.md → changes.md → review.md`), each independently auditable, so the verifier reads exactly the right artifact and the test path derives from the **SPEC, not the implementation**.
- **Payloads to disk, summaries to context** — an agent producing a large artifact (graph fragment, extraction batch, generated set) writes it to the shared task folder and returns only a one-line pointer + counts, never the blob. A one-line pointer in place of a ~100 KB blob is ~98% smaller in context, so the orchestrator holds N summaries, not N payloads; read the artifact back only at the stage that needs it.
- **Precompute deterministic facts once; forbid re-derivation** — whatever a parser/index/script yields exactly (imports, symbols, call sites, schemas) compute ONCE in the orchestrator and inject into each brief; tell agents to use the injected facts and NOT re-derive, with a mechanical self-check (e.g. `edges_emitted == len(injected_imports)`). N agents each re-deriving the same structure is ~(N−1)/N redundant work and invites drift, and the injected facts make the LLM's job correctness-bounded. Brainer already ships the extractor: [`code_map`](../wiki-memory/tools/code_map.py).
- **Isolate writers** — when >1 agent writes, give each its own git worktree (`isolation: worktree`) and merge through a quorum/aggregation gate; never let two agents write the same tree.
- **Quarantine untrusted input** — an agent that reads untrusted content (web pages, user-supplied files, external tool output) gets read-only / no high-privilege tools; the actor that *acts* never sees the raw untrusted bytes. Untrusted-content + a write tool in one agent is the injection hole.
- **Hooks do NOT fire inside subagents.** `compliance-canary` / `prompt-triage` are main-loop-only — a spawned agent gets no drift probes, no re-anchor, no routing. (Main-loop firing *does* work: the `prompt_intent` probe in `drift_probes.json` fires this skill on loop-shaped prompts — observed live. The gap is the fleet.) So: (1) **inline the relevant skill directives verbatim into each subagent's prompt**; (2) keep subagents short-lived and single-purpose; (3) **re-verify their output in the main loop**, where the probes do fire, AND re-run the gate there on anything they touched — a subagent told "do not modify files" has been observed creating litter anyway, so trust the post-check, not the instruction. This is the one mechanical lever that reaches a fleet. The verbatim block to paste into every brief:

  ```text
  GATE (re-run, do not self-certify): your final output is judged by a SEPARATE
  verifier on a machine check — not your done-claim. Return raw findings/data, not
  "done". State attempts tried + abandoned and every assumption. If you produce a
  file/artifact, say exactly what you changed; do NOT touch anything outside the
  named scope. END with "READY FOR JUDGING", never "complete".
  ```

Pick the workflow pattern deliberately: **fan-out-and-synthesize** · **adversarial-verification** (N skeptics each try to refute a finding) · **loop-until-dry** (re-spawn finders until K rounds add nothing new) · **classify-and-act** (route by model tier — [`prompt-triage`](../prompt-triage/SKILL.md)) · **generate-and-filter** (N candidates → rubric → top-K, [`eval-gate`](../eval-gate/SKILL.md)) · **tournament** (pairwise beats absolute scoring for taste/ranking). Effort routing: frontier model orchestrates, opus-class for hard-bounded subtasks, sonnet-class for high-volume reads, haiku-class for graders/classifiers.

## Aggregating perspectives — references → one aggregator (Mixture-of-Agents)

A fleet converges two ways, and the doc above only named one. **SELECT** — a vote/quorum/judge picks the winning result (R5's `quorum`/`aggregate` gate). **SYNTHESIZE** — N *reference* runs propose and one **aggregator** reads them all and writes a new answer (Mixture-of-Agents). In synthesis the references are **read-only advisors and the aggregator is the sole writer** (the same diverge/converge split as the panels above); synthesized output still ships on the **machine gate**, never on "the aggregator combined them." Borrowed from [Hermes MoA](https://hermes-agent.nousresearch.com/docs/user-guide/features/mixture-of-agents), costs kept in view:

- **Cache-preserving fan-in.** Fold reference outputs into the aggregator context at the **tail, below the stable prefix** — never rebuild or reorder the prefix, or you invalidate the whole conversation's prompt cache (cf. [`cache-lint`](../cache-lint/SKILL.md)). Give each reference a **deterministic view** (a stable function of stable history) so its prefix caches across iterations too. You then pay only for the extra reference *completions*, not for broken caches.
- **Tool-less, bounded references.** A reference asked only for a perspective needs no tool schema and no system prompt — just the task text (cheaper; dodges strict-provider tool-call rejections). **Bound the count to the aggregator's context window**: a small offline aggregator (ollama / glm, 8–32k) truncates on 3–4 reference blocks and the lift goes *negative* — measure before trusting it on small models.
- **Tolerate partial returns.** A reference that errors is folded in as an explicit `REFERENCE_FAILED` note — never aborted-on, and never silently dropped (a silent drop hides that a perspective is missing). Mirrors fleet writer-isolation: one failed worker never sinks the turn.
- **Off-switch for ablation.** Make the fan-out one-flag-bypassable (aggregator acts alone) so the lift is measurable — the extra model-call cost is justified only by a measured delta (Hermes reports ~+6 pts, but on **one** config; a weak reference can *drag* a strong aggregator). **Selective, not a default**: reach for it only when a hard task genuinely benefits from multiple perspectives.

## The loop spec: four required fields

Declare these BEFORE the loop runs — they are `loop_lint.py`'s input contract:

1. **gate** — a concrete machine-checkable pass/fail signal the agent can call and read (a command / test id / assertion / schema), never "looks correct".
2. **stop** — the completion condition the loop runs until.
3. **budget** — a numeric iteration / token / wall-clock cap that halts a drifting loop. Unbounded is not a loop, it's a spin.
4. **generator ≠ verifier** — distinct producer and checker.

Then answer the questions the four fields don't cover:
- Against **what oracle** — test suite, spec, reference output, schema, or another agent?
- Is the loop **open or closed**, and is that intentional for THIS task (novelty wanted vs bounded shipping)?
- If the loop is scheduled/fleet/outer, where do `anchor_files`, `state_store`, `recall`, and `writeback` live — and who owns `state_concurrency`?
- If it is a fix/retry loop, what is the `stuck` detector (same command 3× / same error 2× / 2 iters no movement), and which `advisor` panel does it consult on stall? Source it from [`skills/_shared/model_roster.py`](../_shared/model_roster.py); keep it separate from the verifier (R11).
- **green ≠ correct**: does the gate cover behaviour nobody wrote a test for yet, or only reproduce what existing tests already describe? 99.8% on an existing suite is *benchmark-green*, not correct — production is the behaviour nobody tested.
- For an **outer loop**: the highest-signal, lowest-friction feedback channel is the human's **in-place override delta** — what they changed and the reason they left at the work site (a relabel + a reply), not a report you ask them to write. **Grade that feedback before acting on it**: an explicit correction/relabel is strong, a reaction is moderate, silence is weak-positive. If project learning is armed, [`task-retrospective`](../task-retrospective/SKILL.md) owns the decision about whether that lesson belongs in memory, an SOP, a checklist, or a project-specific skill. Conflicting or weak signal ⇒ no durable write.

## Instrument before you scale

**You cannot improve a loop you do not measure** — instrument the gate (iteration count, pass rate, failure reasons, per-step cost/success) BEFORE you scale, or you are just generating wrong answers faster. The metric that matters is **cost per accepted change**, not tokens spent — under ~50% accepted means the loop is making review work, not saving it. Add cheap deterministic **stuck detectors** distinct from the correctness gate, with concrete thresholds: **same command 3×, same error 2× (the `repeated_tool_error` probe), or 2 iterations with no metric movement = stuck.** Emit the iteration trace as JSON and run `loop_run_monitor.py` against it:

```bash
python3 skills/loop-engineering/tools/loop_run_monitor.py trace.json
```

On stuck, do NOT retry harder — **force entropy**: require a *structurally different* hypothesis before the next execution, **and source it from the advisor panel, not the stuck agent's own head** (it is stuck precisely because of its blind spot). The decision brief IS the advisors' input packet: hand a cross-vendor, read-only panel what was tried and why each attempt failed, take back fresh approaches, and pick the most structurally-different one — `python3 skills/_shared/model_roster.py --panel 2 --role advisor --exclude-lane <self> --task … --brief …` renders the dispatch. Caps stay small (≈2–3 for a fix loop); on hitting the cap, **escalate with that same decision brief** — the options tried and the evidence behind each, never a bare "it doesn't work". Per-cycle, ask the overfit question: *am I building the general solution, or memorizing this eval?* A recurring "ran past budget" or "no gate" violation across project tasks can be reviewed by armed [`task-retrospective`](../task-retrospective/SKILL.md), but task-retrospective must not auto-edit Brainer probes. Build the **minimum viable loop** in order — get one manual run reliable → make it a skill → wrap it in a loop → schedule it; skipping ahead ships a loop nobody understands.

## Design against the quiet failures

- **Ralph Wiggum loop** — the agent emits its "done" token early and the loop exits half-finished. The fix is the R1/R3 gate: an **objective** check (a test/build/lint exit code) that can FAIL the work — never a second agent with an opinion.
- **Goal drift** — long sessions lose "don't do X" constraints to lossy summarization. Reread a standing spec (`VISION.md` / `AGENTS.md` / the `done means:` block) each run.
- **Comprehension debt** — the faster the loop ships code you didn't write, the wider the gap between the repo and what anyone understands. **Read the diffs**; spot-check that the gate still catches the failure you care about (**gates rot**); keep the loop off architecture / auth / payments.
- **Gate integrity — never weaken the gate to pass.** A failing check is failing; a tolerance / threshold / expectation change needs explicit human approval and never happens mid-run to convert FAIL→PASS. The coverage ratchet only ever *raises* the floor. A loop that lowers its own bar to ship is lying to itself.
- **Unattended = an attack surface** — an autonomous loop merges code, installs skills, and writes logs while nobody watches. Require a **human-approval gate before any irreversible action** (merge / deploy / migrate / dependency bump), scope and re-audit its permissions, and audit any skill it auto-installs. `loop_lint.py` flags this statically (R7: an autonomous loop that deploys/merges/migrates/charges with no human gate). **Bound the *ordinary* side effects too, not just the catastrophic ones:** declare the loop's permitted outputs as a **default-deny allowlist with a per-action cap** (`close-issue max 5`, `add-label[wontfix]`) **enforced by the harness** — a prompt-level "don't" is not a control, and a drifted run ignores it (Brainer has watched subagents commit despite being told not to). `loop_lint.py` R10 flags an unattended loop that takes a side-effecting action (post / close / label / merge / email / …) with no `output_actions` allowlist; `*`/`all` is not an allowlist. Ported from GitHub Agentic Workflows `safe-outputs:` (allowed actions + per-action max). Inner loops a human watches are exempt — the human is the output gate.
- **Default harness on a timer** — no standing facts, no scoped permissions, no verifier, no memory. The loop does not add intelligence; it just repeats re-derivation faster. Run the harness pre-flight first.

## Validate the spec

Write the loop spec as a fenced ` ```loop ` block (or a `.yaml`/`.json` file) and lint it:

```bash
python3 skills/loop-engineering/tools/loop_lint.py <file>   # exit 2 = fatal gap, 1 = warn, 0 = clean
```

Exit **2** = no gate (R1) / no stop+budget (R2) / self-grading (R3). Exit **1** = open-loop-without-ack (R4) / fleet-without-quorum (R5) / no-topology declared (R6) / irreversible-action-without-human-gate (R7) / missing memory contract on scheduled/fleet/outer loops (R8) / fleet state with no concurrency strategy (R9) / unbounded output surface on an unattended side-effecting loop (R10) / stuck loop with no advisor, or advisor==verifier (R11) / cross-vendor egress with no `redaction` declared, or unattended egress with no `consent` gate (R12) / LLM verifier on an unattended/cross-vendor loop that doesn't declare blindness (R13) / degenerate zero-cap budget (R2 warn). On a non-zero exit, **fix the flagged field and re-lint until exit 0** — the spec is itself a closed inner loop with `loop_lint.py` as its gate. This is the gate-over-prose payoff: the failure modes are refused statically, not re-argued. Field reference: [`tools/schema.md`](tools/schema.md).

**Freeze the verified spec (`--resolve`).** For an outer/fleet/scheduled loop, `loop_lint.py --resolve <file>` emits an immutable `loop.resolved` snapshot (fields + lint verdict) as a replay/drift surface — *not* a resume checkpoint (no run state, no runner; the linter stays a linter). Use it so a long-lived loop can re-dispatch the exact spec it verified, and so spec-drift (editing the source while a loop runs stale logic) is detectable.

**See the loop.** `--diagram` renders the spec as a Mermaid generator→gate→verifier loop with the lint findings overlaid as coloured nodes — derived from the parsed spec (never invented), exit code still the lint verdict so it composes in CI (full node-colour mapping in [`tools/schema.md`](tools/schema.md)):

```bash
python3 skills/loop-engineering/tools/loop_lint.py --diagram <file>   # Mermaid to stdout; wrap in a ```mermaid fence to render
```

## Persisting a reusable topology

A reusable generator/verifier/budget recipe is just another durable project fact. Persist it only when explicitly requested or selected by an armed task-retrospective, then route it through [`write-gate`](../write-gate/SKILL.md) into [`wiki-memory`](../wiki-memory/SKILL.md) as a `pattern` page. loop-engineering owns no store and no write path of its own.

## Files

- [`tools/loop_lint.py`](tools/loop_lint.py) — static loop-spec linter; exit code = verdict.
- [`tools/loop_run_monitor.py`](tools/loop_run_monitor.py) — runtime trace gate: stuck + cost-per-accepted-change.
- [`tools/schema.md`](tools/schema.md) — loop-spec field reference.
- [`../_shared/model_roster.py`](../_shared/model_roster.py) — detect reachable cross-vendor backends; render read-only advisor (diverge) / verifier (converge) dispatches. Native CLIs preferred; optional **OpenRouter** transport backfills absent lanes (`--via openrouter` to prefer it) and offers **Fusion** as an advisor (`--fusion`). Shared with [`verify-before-completion`](../verify-before-completion/SKILL.md).