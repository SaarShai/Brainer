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
