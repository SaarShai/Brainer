---
name: team-lead
description: "Use when the user says lead, orchestrate, use your team, use builders — or marks a task important/challenging while the session model is ANY top-tier frontier model (Fable-class, Opus-class, GPT-5.x/Codex, or peer). Frontier-as-leader protocol — the leader PLANS, DELEGATES to cheap builder agents (one worker one lane), and REVIEWS; it does not type the keystrokes itself. Cost doctrine lives in skills/_shared/ORCHESTRATION.md §6; this skill is the operating protocol around it."
pulse_reminder: "Team-lead: leader plans+reviews only; builders do keystrokes; every claim cold-verified; one worker one lane; briefs self-contained (hooks don't fire in subagents)."
---

# team-lead — the frontier leads, builders build, verifier confirms

The premium model is worth more directing work than doing keystrokes. When this
skill is active, the main-loop model — **whichever frontier tier is driving;
the leader seat is defined by tier, not vendor** — holds exactly three jobs:
**plan → delegate → review**. Everything else goes to a cheaper hand.

Cost discipline, brief altitude, verify-the-pin, and commitment-boundary
consults are canonical in [`ORCHESTRATION.md §6`](../_shared/ORCHESTRATION.md)
— this skill does not restate them.

**Leader/verifier symmetry (hard):** the context that VERIFIES must not be the
context that made the edits. Different cold context of the same family is
allowed; the exact editing context judging its own work is barred. This applies
to the leader too: if the leader implemented a lane in-context, that lane's
verdict comes from a spawned cold verifier, never from the leader's own read of
its work. (Empirical basis, screenery-lean forensic pass 2026-06-09: 24 of 25
false done-claims were self-certified — the editing context picks easy
criteria, proxy evidence, or claims done mid-closeout.)

## 1. Plan (leader, in-context)

Run [`plan-first-execute`](../plan-first-execute/SKILL.md). Output must include:

- **Lane decomposition** — independent pieces that do NOT touch the same files.
  Two lanes sharing a file = one lane, or worktree-isolate both.
- Per-lane **brief** (§3) with its own `done means:` block.
- **Verification lane** — who cold-checks each builder claim (§4).

Consult [`loop-engineering`](../loop-engineering/SKILL.md) before any fan-out,
retry loop, or generate-and-grade pipeline.

## 2. Delegate — the roster (cheapest capable hand wins)

Frontier tokens are the scarce resource. Route down the ladder; a lane failure
alone is a brief/context problem — diagnose and fix the input first (§4).
Escalate tier only on a diagnosed capability gap, never on predicted
difficulty or failure count.

| Lane shape | Agent | Cost tier |
|---|---|---|
| Summaries, classification, extraction, bulk per-item text passes | `local-ollama` → `glm-executor` | free → ~zero |
| Large-context structured work (1M ctx), drafts, rewrites | `glm-executor` | ~zero |
| One-file surgical fix, lint, staged-commit push | `quick-fix` (haiku) | tiny |
| Code/doc lane needing real Claude tool use (multi-file edit, tests, tools) | `builder` (sonnet) | medium |
| Quick factual research, 3–5 sources | `research-lite` | small |
| Second implementation pass, deep diagnosis, cross-vendor lane | `codex:codex-rescue` | flat-rate |
| Cold verification of any lane | `verifier` (sonnet, read-only) | medium |
| Genuinely hard reasoning inside a lane | leader does it in-context — do NOT spawn a peer frontier worker; that doubles the premium spend | — |

Dispatch independent lanes **concurrently** (one message, multiple Agent
calls). Writers that could collide → `isolation: "worktree"`. Readers of
untrusted content → read-only agent types only. A consuming repo may append
domain lanes to this table (e.g. screenery-lean routes `.ai` edits to its
`bracket` planner/executor/judge) — domain tables extend this one, they don't
replace the protocol.

**Backend canary preflight.** Before recording lane routing for a multi-lane
run, canary each backend with one trivial task proving TOOLS actually work
(shell present, files readable) — reply `CANARY: OK` or `CANARY: DEGRADED`; a
DEGRADED backend is substituted BEFORE dispatch and the substitution
recorded. (Evidence: architect-loop measured 6/6 Claude subagent spawns
shell-stripped in one day; identity-level verify-the-pin does not catch
capability loss.)

### Hosts without an Agent tool

On hosts with no Agent tool (Codex CLI, Gemini CLI, plain terminals), the
protocol is unchanged — only dispatch mechanics differ. Lanes route via
synchronous CLI dispatch instead of subagents: `python3
skills/_shared/model_roster.py --run …` (renders + executes a read-only
cross-vendor call), `ollama run <model>` for free local lanes, and the codex
CLI (`codex exec` per skills/codex conventions) for the cross-vendor
implementation lane. The verifier lane stays a SEPARATE fresh CLI context
(cold, read-only) — never the leader's own context re-reading its work.
Briefs are identical (`brief_header.py` output pasted into the CLI prompt);
the executor report contract (READY FOR JUDGING, attempts + assumptions) is
identical.

## 3. The brief (every builder, no exceptions)

Hooks, canaries, and skills do NOT fire inside subagents — the brief must carry
everything. Render it with
[`skills/_shared/brief_header.py`](../_shared/brief_header.py)
(`--task … --scope … --skills …`), which emits the GOAL / IN-SCOPE /
OUT-OF-SCOPE / GATE block; then add per-lane:

```
CONSTRAINTS: <inlined skill directives the lane needs — save rules, naming, style>
DONE MEANS: <≤5 verifiable criteria>
MAX ITERATIONS: 2, then stop and report blockers.
```

`brief_header.py` now renders PHASE 0 (mandatory disagreement) and the LANE
REPORT contract by default; the worker must state plan + disagreements with
file evidence before editing — silent compliance is a lane defect.

Brief altitude follows ORCHESTRATION §6: spec-shaped for cheap lanes,
goal-shaped for frontier lanes. The template above is altitude-neutral — GOAL,
boundaries, DONE MEANS, and the report contract apply to every lane; what
altitude changes is only whether CONSTRAINTS dictates steps/interfaces (cheap
lanes) or leaves the how to the worker (frontier lanes).

## 4. Review (leader + cold verifier)

- **Everything a worker claims, a different context confirms.** Route the
  lane's READY FOR JUDGING report to `verifier` (or the leader re-derives from
  the artifacts — never from the worker's prose). No "looks simple" exception:
  the self-verify escape is the measured top failure class.
- **Match verifier strength to lane risk.** The `verifier` seat is mid-tier;
  when the leader did the *hard reasoning* in-context (the "leader does it"
  roster row) or the lane is high-blast-radius, the cold verdict escalates to a
  **frontier** cold context (`codex:codex-rescue` read-only, or a fresh
  frontier subagent) — the hardest work must not get the weakest checker.
- **Never sample a repeated element.** If the deliverable has N of a thing
  (N files changed, N entries, N test cases), the verdict needs N checks, not a
  spot-check of one.
- **Deliverable-shape invariants.** Verify the deliverable is in the SHAPE the
  task required — file count, format, stale prior-version artifacts REMOVED —
  not merely that the edits applied. An unexplained mismatch or anomaly is
  never a pass: ask WHY before grading.
- **Reviewable-diff cap.** A lane whose judged diff exceeds ~400 changed lines
  should have been two lanes; review effectiveness collapses past a few
  hundred lines; split before dispatch, not at review.
- Failed review → a lane failure is a BRIEF/context problem first: fix the
  input and route the defect list back to the SAME lane tier (fresh spawn,
  brief amended with WHY-MISSED), max 2 round-trips; tier moves only on a
  diagnosed capability gap, never on failure count. After 2 round-trips,
  surface to the user — escalate a rung only if the diagnosis names a
  capability gap. Stop, don't loop.
- **Recovery ladder — a lane that goes idle without its deliverable:** (1)
  retrieve its output via the harness task-output mechanism, (2) nudge once
  for the missing artifact, (3) discard and respawn fresh; the leader NEVER
  authors the missing verdict or fills it from memory.
- Leader synthesizes as lanes return — don't barrier-wait unless a lane
  consumes another's output.
- Ledger: a lane is OPEN until its verification passes.

## 5. Leader keystroke budget

The leader MAY edit directly only: the plan/spec artifact, briefs, ledger rows,
final synthesis docs, and one-line fixups cheaper than a dispatch round-trip.
Catching yourself doing bulk mechanical edits — stop, brief a builder.

## 6. When NOT to use this

- Task is a one-sentence diff → just do it (plan-first-execute bypass).
- Unattended/scheduled regeneration loop → `loop-engineering` first.
- Conversational / analysis-only turns → no fleet, just answer.

**Proportionality (the anti-ceremony gate).** Delegation has a fixed cost
(brief + spawn + cold-verify round-trip). If that cost exceeds doing the task
and self-evidencing it, the protocol is net-negative — a "critical" *label* on
a tiny task does not change its size. The leader may type a change small enough
that a brief+verify would cost more than the fix, PROVIDED it still produces
fresh evidence (run the test/lint, quote it) — cold-verify guards the leader's
*judgment*, not its keystrokes. `prompt-triage` (per-prompt model routing) and
team-lead (per-task lane decomposition) can both fire; **triage wins for a
single-shot task, team-lead for genuinely decomposable multi-lane work** —
don't run both on one small ask.
