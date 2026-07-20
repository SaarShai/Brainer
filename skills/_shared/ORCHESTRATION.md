# Orchestration doctrine — tiers, not model names

Shared rules for any agent that dispatches another agent (routing, subagents,
panels, fleets). Skills reference this file; they do not restate it. The
implementation primitive is [`model_roster.py`](model_roster.py) (lane detection +
dispatch rendering); the fleet mechanics live in
[`loop-engineering`](../loop-engineering/SKILL.md).

## 1. Name capability tiers, never concrete models

Skill prose names a **tier**; concrete model names go stale the month a vendor
ships (Sonnet 4.6 → Sonnet 5 broke every doc that hardcoded it). Tiers:

| Tier | Job | Example lineage (illustrative, NOT a dispatch target) |
|---|---|---|
| **frontier** | orchestration, hard synthesis, deep reasoning | Opus/Fable-class, GPT-5.x, Gemini Ultra/Pro-class |
| **mid** | bounded execution, high-volume reads, verification | Sonnet-class, GPT-mini-class, GLM-class, Gemini Flash-class |
| **small** | classification, grading, extraction, mechanical edits | Haiku-class, nano/mini-class |
| **local** | free on-box work, egress-free backstop | whatever `ollama list` shows |

## 2. Resolve a tier at dispatch time, in this order

1. **Newest of tier, in-host.** Resolve to the NEWEST model of that tier the
   current host natively exposes: Claude Code → latest Sonnet/Haiku alias;
   Codex → latest GPT mini-tier; Gemini CLI → latest Flash. Host aliases
   (`sonnet`, `haiku`, `gpt-x-mini`) already track "latest" — prefer them over
   pinned version strings. Never dispatch a model name copied from a doc; ask
   the host what it has (or use `model_roster.py`, which detects live lanes).
2. **Cross-API override when clearly better.** If a reachable out-of-host model
   (API key or CLI present) is clearly better for THIS task — capability, cost,
   context size, or vendor diversity — prefer it over the in-host convenience
   choice. Example: a Codex orchestrator that knows a Gemini Flash-class model
   is best for a bulk-vision task should dispatch it via the Gemini key, not
   default to the in-host mini. "Clearly better" means you can say why in one
   line; otherwise take rule 1.
3. **Never dispatch what you can't reach.** Detection precedes dispatch
   (`model_roster.py` checks CLIs in PATH + API keys); a dispatch failure drops
   that member, it never hard-stops the task.

## 3. Judges and verifiers want vendor DIVERSITY

A verifier/judge panel prefers **distinct vendor lanes** and **excludes the
generator's own lane** (`model_roster.pick_panel(exclude_lane=…)`) — same-model
self-review inflates scores; cross-family panels measurably cut systematic bias.
Odd-N (default 3), refute-if-you-can, majority; recompute quorum after dispatch.
Advisor panels (diverge) and verifier panels (converge) never collapse into one —
see loop-engineering R11.

## 4. Where concrete names ARE allowed

Exactly three places, all machine-resolvable and refreshable:

- host agent definitions (`.claude/agents/*.md` `model:` fields — host aliases
  preferred over pinned versions),
- `model_roster.py` defaults (env-overridable per lane:
  `OPENROUTER_MODEL_<LANE>`),
- host config the user owns (settings, hooks).

A versioned model name in skill *prose* is a defect unless it is a measured-
evidence citation (e.g. "judge X false-passed on model Y" — evidence keeps its
exact name) or a clearly labelled, non-exhaustive scope example in a durable
user policy. Dispatch instructions always speak in tiers.

## 5. The dispatch contract (any host, any vendor)

Every cross-agent dispatch is **synchronous, scoped, and returns findings in its
final message** — fire-and-forget returns nothing a gate can read. Verifiers are
**read-only**. Sub-agents get the relevant skill directives inlined in the brief
(hooks don't fire inside subagents), and their output is re-verified in the main
loop. Cross-vendor egress goes through redaction + consent
(`model_roster.render_prompt`; loop_lint R12).

**Kill-safety line (external mutable state).** A brief for any lane that
holds external mutable state (open documents, GUI apps, live services) must
state what happens if the lane dies at any instant — what is stranded, and
the recovery step. No kill-safety line → the lane doesn't dispatch. (§7 is
the dispatch mechanism this pairs with; the line is the design-time check.)

## 6. Architect cost discipline (frontier-tier orchestrator)

**Frontier economy invariant (hard).** This applies whenever the driving model
is top/frontier tier — including the current Fable 5 and GPT-5.6 Sol xhigh
class, and any equal-or-better future model. Spend its context on deep
reasoning, diagnosis, architecture, decomposition, planning, synthesis, and
final judgment. Route bounded research, summarization, extraction,
classification, bulk reads, mechanical edits, boilerplate, and spec'd
execution to the cheapest reachable capable tier. Do not delegate when the task
is inseparable from live context or no suitable lane is reachable. Outside a
mandatory route below, compare end-to-end delegation cost with direct execution.
The sole cost/size exception to SPEC'D+GATED delegation is the ~<30-line
judgment-dense fix below; an expected diff of 30+ lines closes it regardless of
dispatch cost. Never delegate unresolved diagnosis or semantic invention to a
weaker lane merely to save tokens.

**End-to-end ownership invariant (hard).** For non-trivial decomposable work,
create one measurable goal covering architecture, implementation, tests,
review, and final verification. Split it into independent, non-colliding lanes;
each lane gets a goal, expected deliverable, verification gate, and done
criteria. Run the cheapest capable lanes concurrently while continuing
unblocked lead work. Track results as they return, intervene when a lane drifts
or lacks context, synthesize the outputs, resolve conflicts, and verify material
boundaries live. Use the host's goal mechanism when available; otherwise put
the goal in the plan or lane brief — a literal `/goal` command is not portable.
Commit only when authorized and ready. Partial progress is not a stopping
condition; stop only for missing authority or a genuine blocker.

When the orchestrating session itself runs a frontier-tier model, **invert the
token volume**: the expensive model emits judgment — decomposition, specs,
routing, verdicts — and cheap lanes emit the volume (code, boilerplate, tests,
bulk reads).

**Topology default.** The frontier model IS the main loop and routes DOWN
(plan → delegate → review); every surveyed production coding agent (aider
architect mode, opusplan, Devin) uses strong-leads. A cheap main loop
escalates UP only via the prompt-triage escalate-up mode
(`BRAINER_TRIAGE_ESCALATE_UP=1` → frontier-advisor / frontier-verifier
subagents) and may only EXECUTE from a frontier-authored plan — never decide
architecture or escalation timing from scratch. Model switches (`/model`)
happen only at phase boundaries (plan → execute → review), never mid-phase:
model switching splits the prompt-cache namespace (cache-lint rule 4), so
switch coarse-grained or spawn a subagent instead.

**Evidence.** Orchestrator/worker splits measure 58–74% cheaper than
end-to-end top-model (architect-loop DESIGN.md, PEAR); weak planners hurt
multi-agent output more than weak executors (PEAR) — so the plan seat gets
the strongest model, the typing seat doesn't; reasoning-effort curve: xhigh
vs high = 88% vs 69% semantic equivalence to human PR, 69% vs 38%
review-pass, at ~2.2× cost (stet.sh via architect-loop) — buy xhigh for
unattended work where review-survival matters, tier down effort for
recipe-shaped work; RouteLLM: 85% cost cut at 95% GPT-4 quality (MT Bench) —
a per-request router for one-shot queries, not a coding-agent topology, cited
for the cost-routing principle only. These are **external single-source
anchors**, not reproduced here; the one figure measured on THIS stack is 72.1%
structural savings on a 17-lane run (team-lead/EVAL.md), which lands inside the
58–74% anchor. Treat the rest as directional, not settled.

Rules:

- **Route before mutation (hard).** Before the first root or child mutation,
  record one receipt: task-defining artifacts read, `SPEC'D`, `GATED`, expected
  size, governing authority, route, execution owner, and claimed exception.
  Applicable `AGENTS.md` and project rules override a generic
  no-proactive-subagent default. Speed pressure may change lane count, brief
  size, or concurrency, never a mandatory route; retain proportionality and
  the ~<30-line judgment-dense exception. Refresh the receipt when later
  artifacts change authority. If mutation or required delegation came first,
  stop, record the breach, refresh, delegate remaining bounded work, and cold-
  review premature edits; later delegation is not retroactive compliance.
- **Route by SPEC'D × GATED, not size.** SPEC'D = a written spec states the
  root cause (for fixes) or exact construction (for features) such that
  execution needs no semantic invention — "figure out why X" is NOT a spec.
  GATED = success is mechanically checkable (tests, geometry gates, sha256,
  residuals). Routing: SPEC'D+GATED → delegate to the cheapest capable tier;
  the frontier orchestrator MUST NOT execute it beyond ~30 lines of diff.
  SPEC'D-not-GATED → delegate execution, but a different agent verifies at
  the artifact layer before any "done" claim. Not SPEC'D (diagnosis, product
  semantics, new-machinery design) → frontier-tier work: never forward a
  symptom — reproduce it at the artifact layer yourself, name the root cause,
  prescribe the fix with a borrow-checkpoint line, THEN delegate execution.
  A sub-frontier brief containing "investigate why / figure out / determine
  the cause" is malformed (the `delegated_diagnosis` canary probe flags it);
  mechanical evidence-gathering sweeps remain delegable. Exception: a small
  (~<30-line) judgment-dense fix where the diagnosis IS the fix — the
  frontier model does it directly, with a verification call in the same
  turn; writing the brief would cost more than the diff. Sub-frontier lanes
  mirror this: when a task needs semantic invention, STOP and escalate with
  gathered evidence (file:line, failing output) instead of guessing — a
  guessed implementation passing its own invented gate is verification
  theater; a frontier-written spec is always executable, and deviations go
  through a BLOCKED report, never silent "improvement". (Evidence:
  template-v29 delegation-economics review, screenery 2026-07-18 — every
  delegation failure was implicitly delegated diagnosis; every first-try
  success was frontier-spec'd + mechanically gated; size/simplicity
  adjectives were the wrong discriminator.)
- **The orchestrator's context is re-read at frontier prices every turn** —
  keep conclusions, not dumps; route broad exploration to read-only cheap
  agents; a path reference or excerpt beats a pasted file.
- **Reason once, then hand off.** Capture the architecture / hypothesis in the
  delegation brief (goal · in-scope files · interfaces the output must match ·
  constraints + out-of-scope · verification command) and let the lane carry it;
  re-deriving decisions across turns burns the premium twice. A brief you can't
  finish writing means the decision isn't made — that's orchestrator work, not
  ambiguity to hand a cheaper model.
- **Match brief altitude to lane tier.** A small/mid lane gets a *spec-shaped*
  brief — the spec fully determines the outcome, steps and all; ambiguity there
  is a defect. A frontier-tier lane (advisor, verifier, researcher, hard
  synthesis) gets a *goal-shaped* brief — goal, boundaries, done-bar, injected
  facts — and NOT a step list: each dictated step overrides the judgment you
  chose that tier to get. Same discipline as prompting the orchestrator itself;
  the orchestrator is the sub-agent's user, and it owns the sub-agent's whole
  context (inlined directives = global, injected precomputed facts = project,
  the brief = task — a subagent starts context-empty and sees nothing else).
- **User-supplied literals pass VERBATIM.** Any concrete value the user gave —
  an absolute path, filename, ID, threshold, URL — is copied into the brief
  character-for-character, never elided ("…", "..."), abbreviated, or
  paraphrased. A subagent starts context-empty: an elided literal forces it to
  re-discover (wasted calls) or guess (wrong target). Observed live 2026-07-07
  (screenery "Baton": brief carried `'…/FINAL production/birthday …'` for a
  path the user had given in full → the lane went hunting for the folder →
  user rage "i gave you the path!"). `brief_header.py --lint-brief` refuses
  briefs with elision markers next to path-like fragments — run it on every
  composed brief, not only the header it renders.
- **Commitment boundaries, not only stuckness:** before an architecture choice,
  migration, API shape, or wide-blast-radius refactor — take a read-only,
  context-fresh skeptic verdict (advisor role, preferably cross-vendor; short:
  verdict + the single deciding risk). Act on it or surface the disagreement;
  never silently ignore it. (Stuck-after-2-attempts and ship-time escalation
  already trigger consults; this adds the *pre-decision* trigger.) When the
  consult concerns bespoke machinery (a solver, cache, gate, orchestration
  primitive, pipeline), the brief MUST include the standing question "should
  this subsystem be replaced by an existing tool?" — sunk-cost framing ("fix
  this solver") without that question is how months of hand-rolled machinery
  survive advisor review (screenery 2026-07-18 handoff; borrow-checkpoint
  directive in the code-craft block).
- **Author down the ladder.** When a frontier lane keeps redoing the same task
  class, have it AUTHOR a skill for that class instead — skill-authoring
  converts recurring frontier spend into a permanent tier drop (author once at
  the top, execute forever at the bottom). Write the skill for the **weakest
  executor** that will run it, and acceptance-test it there (learn-skill step
  6), not in the author's own context.
- **Verify the pin — from the transport, not the model's word.** Hosts can
  silently fall back to the session model when a pinned lane model is
  unavailable — the dispatch *succeeds* on the wrong model, which reachability
  detection (rule 2) cannot catch. Prefer the **authoritative identity the
  transport returns** (the API response's `model` field, the CLI's
  `--version`) — a model's self-report *inside its answer* is forgeable and
  models mis-identify, so it is only the weak fallback. `model_roster._run_glm`
  enforces this today: it compares the served `model` to the requested one and
  prints `PIN MISMATCH` on divergence. A lane re-route (e.g. cross-vendor →
  in-family) is reported loudly, never absorbed — the caller may have chosen
  the lane for its failure distribution.
- **A lane failure is a BRIEF/context problem first.** Diagnose from evidence,
  fix the input, respawn at the SAME tier; move tier only on a diagnosed
  capability gap, never on failure count or predicted difficulty. A
  merge/file conflict between lanes is a DECOMPOSITION failure (kill the
  lane, re-split), not a worker failure. **Scope:** this governs the
  team-lead *multi-lane tier decision*. It does NOT override prompt-triage's
  single-shot gate: a cheap subagent routed for one task that fails its gate
  twice hands the task back to the main model (two-strike takeover) — that is
  a per-task routing fallback, not a tier move on the team-lead ladder, and
  the two rules do not conflict.
- **Cross-vendor review direction caveat.** One directional study found
  Claude-reviews-GPT helped while GPT-reviews-Claude hurt; treat direction as
  a recorded variable, not settled doctrine (single study).
- **Lane returns are digests, not dumps.** Compact-return target ≈2,500
  tokens against the artifact paths; payloads go to disk, conclusions to
  context.
- **No state-changing git inside a lane; stand down by hunks.** A worker lane
  NEVER runs `git checkout`/`restore`/`reset`/`clean`/`stash`/`add -A`/`commit`
  on the shared tree — one `git checkout -- <paths>` for a "clean baseline"
  wiped 5 concurrent lanes' uncommitted work (2026-07-06). Inline this in every
  brief (`brief_header.py`). When a lane must discard its OWN edits it removes
  ONLY its own hunks, never a whole file a sibling may share. The leader
  checkpoint-commits each verified lane BEFORE the next parallel wave, so a
  rogue revert's blast radius is one wave, not the session. (Harvested from
  screenery-lean failure #18 — independently re-derived there and in Brainer's
  own fleet incident the same day.)
- **Leader-side mechanical twin of the no-git rule** (hooks don't fire inside
  lanes, so the guard can't live there): run
  [`lane_guard.py snapshot`](../../skills/_shared/lane_guard.py) before dispatching a
  multi-lane wave, then `lane_guard.py check` after EACH lane returns — a
  stash created, HEAD moved, or a dirty file reverted-to-HEAD is a FAIL that
  quarantines that lane's report until the tree is reconciled (never
  self-absorbed as "looks fine").

## 7. Interrupt-immune (detached) lanes

**RULE (hard).** Any lane that mutates external application state (open
documents, GUI apps, live services) or runs >~2 min, on a host with the
interrupt-cascade behavior recorded in `HOST_CAPABILITY_MATRIX.md`, MUST be
dispatched via [`detached_lane.sh`](detached_lane.sh) launch/status, never as
a killable harness Agent-tool/background subagent. Results come back only
through the `.done`/`.exit`/log file contract — poll `status` from a
heartbeat, never assume harness-native progress reporting is reliable for
these lanes.

**Why.** 2026-07-20 (session af48da1c): the Claude desktop harness cascaded a
main-loop interrupt (a stray user "ping" mid-turn) to ALL running
background subagents, killing an Illustrator-mutating lane mid-work with
unsaved edits — then mislabeled it "stopped by the user" in the transcript.
`detached_lane.sh` launches via `setsid(2)` (Python `start_new_session=True`),
so the spawned process is its own session leader and survives a SIGINT/
SIGTERM/SIGHUP blast to the launcher's group.

**Respawn briefs for external-app lanes** (Illustrator, Figma, any GUI app
with unsaved state) MUST lead with a revert/recover step before resuming
work — STEP 0 = File > Revert (or the app's equivalent discard-unsaved-state
action) — never assume the last-seen state is still on disk/in-app; a killed
lane may have left partial, unsaved mutations.

(Adapted from DannyMac180/fable-advisor, MIT — generalized from concrete
models to tiers.)
