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
exact name). Dispatch instructions always speak in tiers.

## 5. The dispatch contract (any host, any vendor)

Every cross-agent dispatch is **synchronous, scoped, and returns findings in its
final message** — fire-and-forget returns nothing a gate can read. Verifiers are
**read-only**. Sub-agents get the relevant skill directives inlined in the brief
(hooks don't fire inside subagents), and their output is re-verified in the main
loop. Cross-vendor egress goes through redaction + consent
(`model_roster.render_prompt`; loop_lint R12).

## 6. Architect cost discipline (frontier-tier orchestrator)

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

- **A code block longer than an interface signature is a spec that hasn't been
  delegated yet** — stop and delegate it. Fixing a cheap lane's bug by hand is
  the same failure in disguise: send back a corrected spec instead.
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
  already trigger consults; this adds the *pre-decision* trigger.)
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

(Adapted from DannyMac180/fable-advisor, MIT — generalized from concrete
models to tiers.)
