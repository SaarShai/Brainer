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
bulk reads). Rules:

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
- **Verify the pin.** Hosts can silently fall back to the session model when a
  pinned lane model is unavailable — the dispatch *succeeds* on the wrong
  model, which reachability detection (rule 2) cannot catch. When the lane
  choice is load-bearing (capability or vendor diversity), have the lane echo
  its model identity in its report. A lane re-route (e.g. cross-vendor →
  in-family) is reported loudly, never absorbed — the caller may have chosen
  the lane for its failure distribution.

(Adapted from DannyMac180/fable-advisor, MIT — generalized from concrete
models to tiers.)
