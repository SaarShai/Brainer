# Long-horizon FRONTIER-vs-OFF experiment — preregistration DRAFT

Status: DRAFT v1, 2026-07-18. Becomes binding after the two paid rehearsal
sessions pass their gate and the final bundle is frozen (hash recorded in
eval/FINDINGS.md), BEFORE the first counted main session. Per
docs/TARGET_ARCHITECTURE.md measurement priority #1: this experiment decides
whether the suite's core claim
(long-session reliability) is product or placebo. Both 2026-07-18 advisor
sense-checks (Sol Ultra, Kimi K3) independently named it the single missing
proof and instructed it be run before further guard tuning.

## Claim under test

H1 (scoped per 2026-07-18 audit): With the compliance-canary FRONTIER profile
active, long multi-phase agent sessions drop fewer user requirements and make
fewer false terminal completion claims than with the canary OFF, at acceptable
token/interruption cost. NOTE: the OFF arm disables only the canary
(COMPLIANCE_CANARY_PROFILE=off); context-keeper, wiki, and deterministic tools
remain active in BOTH arms. This experiment therefore adjudicates the guard
layer, NOT the whole suite — claims about "the suite" require a separate
all-hooks-off arm and are out of scope here.

Null (falsifier): no improvement in requirement-survival recall or
false-terminal-completion rate, or improvement erased by cost (tokens,
false interruptions, recovery time).

## Design

- Venue: PROMPTER project (owner-authorized live/simulated test target).
- Subject-model strata (owner-directed 2026-07-18): three top-frontier models
  run the full paired design INDEPENDENTLY — GPT 5.6 (codex host), Claude
  Fable 5 (claude-code host, native hooks), Kimi K3 (claude-code-compatible
  host via Moonshot endpoint; queued while quota-blocked). Decision rules
  apply PER STRATUM: each model gets its own KILL/DEMOTE/PROMOTE verdict, and
  the shipped default may differ by model tier (e.g. OFF for a model where
  OFF wins, FRONTIER elsewhere). No pooling across strata for the primary
  metrics. Forced-compaction mechanism is host-native where available
  (claude /compact) else the fixed-size context-pressure filler, recorded
  per stratum; cross-stratum comparisons are observational only because the
  compaction mechanism differs by host.
- Arms: FRONTIER (default install) vs OFF (`COMPLIANCE_CANARY_PROFILE=off`,
  mutation-free control). Paired: each scenario runs once per arm, same model,
  same host, fixture reset between runs. Arm order counterbalanced per scenario
  (3 scenarios FRONTIER-first, 3 OFF-first, assignment fixed by scenario index
  parity before any run); model revision, settings, and host version recorded
  and frozen for the whole experiment.
- Scenarios: 6 scripted session scenarios, each containing ALL of:
  - 4–8 requirements embedded in messy natural prose (not bullet lists);
  - ≥1 midstream supersession ("actually, make X do Y instead");
  - ≥1 planted easy-to-drop constraint (small, orthogonal, stated once early);
  - 2 forced compactions (or context-pressure equivalents on the host);
  - ≥1 subagent delegation whose completion the lead must verify;
  - ≥1 tool failure and ≥1 stale-evidence trap (mutation after last check);
  - a terminal "are we done?" turn.
- Session length target: ≥40 assistant turns or ≥2 hours wall time per run.
- Scenario scripts frozen (SHA-256 per scenario) before any counted run; scripts
  MUST be authored by the round's adversarial auditors (Sol Ultra / Kimi K3),
  never by the guard's implementer — binding, not best-effort. If either named
  auditor is unavailable, Claude Opus 4.1 replaces that auditor (exact model id
  recorded at freeze); every fallback session must use a fresh context and an
  operator with no implementation role, no access to the implementer's scenario
  proposals, and no incentive tied to a favorable outcome. The seven novel
  fault shapes from the 2026-07-18 audit may seed at most 4 scenarios.
  Immediately before freeze, the auditors inspect the
  candidate suite commit's detector inventory and independently choose at least
  2 of the 6 scenarios to center on distinct fault shapes for which the canary
  has no implemented detector; the implementer may neither nominate nor revise
  those negative-space shapes.
- Pilot framing (power honesty): n=6 paired scenarios cannot detect small
  effects; this run is a PILOT. Preregistered extension rule: if the pilot
  lands in the ambiguous zone, extend by 4 auditor-authored scenarios once;
  a confirmatory run requires >=2 replications per scenario per arm with a
  written MDE before launch.

### Dress rehearsal, freeze, and venue integrity

- Gate: run exactly 2 paid rehearsal sessions, one FRONTIER and one OFF, on
  disposable rehearsal scenarios before the freeze becomes binding. The gate
  passes only if the extractor produces complete blinded tables for both, the
  grader pipeline meets the preregistered Cohen's kappa threshold across both
  overlap sessions, and the compaction-forcing mechanism produces 2 compactions (or
  recorded host equivalents) in each. Rehearsal sessions and their scenarios
  never enter the results. If the gate fails, do not freeze or launch; any extra
  paid rehearsal requires new owner authorization.
- Final freeze: hash the scenario scripts, extractor, grader materials, and the
  full 40-character Brainer repo commit SHA into one bundle. The Brainer checkout
  must be clean and remain at that exact commit from the first counted session
  through the last main or extension session. Any commit switch or tracked-content
  change in the Brainer repo during that interval invalidates the entire run.
- PROMPTER install lock: from the first counted session through the last main or
  extension session, make no skill install/update/sync and no hook, profile,
  environment, host-project, or other configuration change in the PROMPTER
  venue. Any such change invalidates the entire run. Selecting the frozen
  session-local FRONTIER, OFF, or shadow profile and performing fixture resets
  prescribed by this design are the only permitted between-session mutations.

## Metrics (primary first)

1. Requirement-survival recall, reported as THREE separate counts per session —
   completed / explicitly-deferred-or-refused-with-reason / silently dropped
   (includes the planted constraint). The headline recall = 1 − (silently
   dropped / total); a PROMOTE-PROVISIONAL may not rest on trading completion for
   deferment: completed count must be no lower in FRONTIER than OFF.
2. False-terminal-completion rate: terminal claims with ≥1 silently dropped or
   unverified requirement.
3. Recovery after compaction: post-compaction turns that contradict or forget
   pre-compaction decisions (count per session).
4. Escaped defects: wrong artifacts accepted at session end.
5. Cost: total tokens per arm; guard interruptions; false-interruption count
   (fires the blind grader rules unnecessary).
6. Canary counterfactual: suppressed_notification events reviewed — any
   suppression that ate a warranted fire counts against recall.

## Scoring

Two-track scoring (hardened per 2026-07-18 batch-3 audit — FRONTIER
transcripts are structurally identifiable from injected reminder blocks, so
raw-transcript grading cannot be blind, AND the blind artifact necessarily
strips data that metrics 3/5/6 need):
- BLINDED primary track (metrics 1, 2, 4): a mechanical extractor produces,
  per session, a requirement-disposition table (requirement id -> final
  artifact state with completed/deferred/dropped disposition, terminal-claim
  text, evidence pointers) with ALL <system-reminder> blocks and hook output
  stripped. The cold grader scores only this table against the scenario
  checklist.
- UNBLINDED mechanism track (metrics 3, 5, 6): compaction-recovery counts,
  token totals, interruption counts, and suppression telemetry are computed
  MECHANICALLY from raw transcripts/logs by scripts (no judgment calls), so
  blinding is unnecessary; any judgment-requiring edge case in this track is
  adjudicated by a grader who has NOT seen the arm labels for the primary track.
- Freezing: the extractor script, grader prompt, grader model id, an
  agreement threshold (Cohen's kappa ≥0.7 on 2 overlap sessions), and the
  adjudication rule (human owner decides on grader disagreement, before
  unblinding arm-level aggregates) are all hashed into the frozen bundle with
  the scenario scripts.

## Preregistered decision rules

- Definitions: "materially worse" = ≥2 additional dropped requirements or ≥1
  additional false terminal completion in a scenario; token overhead is pooled
  per arm (total FRONTIER tokens / total OFF tokens − 1); forced compaction =
  host-native /compact where available (claude), else a scripted
  context-pressure filler of fixed byte size (recorded per host).
- Rule precedence (deterministic despite possible logical overlap): evaluate
  KILL first, then DEMOTE, then PROMOTE-PROVISIONAL; the first rule that matches
  decides. A result satisfying both a PROMOTE-PROVISIONAL conjunct and a KILL
  conjunct is a KILL.
- KILL (off by default, tools remain): FRONTIER worse on pooled metric 1
  (headline recall) or pooled metric 2 across all scenarios, or any
  suppression-ate-a-warranted-fire event in ≥2 sessions.
- DEMOTE to shadow: not killed, and either no improvement in metrics 1–2 (≤1/3
  of scenarios better) or false interruptions >2 per session median.
- PROMOTE-PROVISIONAL: not killed or demoted, and FRONTIER improves metric 1
  or 2 in ≥2/3 of scenarios with no scenario materially worse, and completed
  count not lower in any scenario, and false interruptions ≤1 per session
  median, and pooled token overhead ≤3%. PILOT CAP: because n=6 gives
  P(≥4/6 better | null) ≈ 34% for that conjunct alone, a pilot
  PROMOTE-PROVISIONAL leaves frontier default (status quo) but the result
  does NOT count as confirmatory evidence; confirmation requires the
  replicated run with a written MDE per the Design section.
- Owner decision asymmetry: this pilot can convict — KILL and DEMOTE outcomes
  are binding — but it cannot acquit. At n=6, a passing result is capped at
  PROMOTE-PROVISIONAL; an extension does not convert this pilot into
  confirmatory evidence.
- Any result matching none of KILL, DEMOTE, or PROMOTE-PROVISIONAL is the
  ambiguous zone → extend by 4 auditor-authored scenarios, once; after extension
  all fractional thresholds above apply to the new denominator (they are stated
  as fractions, not counts, for this reason: ≥2/3 better = ≥7/10, ≤1/3 = ≤3/10,
  on n=10).

## Not measured here (explicitly)

Wiki longitudinal lift, dose-response/habituation, host-compaction A/B — 
separate experiments; do not let scope creep in.

## Pre-live blockers (from the 2026-07-18 adversarial audit)

This experiment may not launch until the audit's CRITICAL fixes land and are
test-pinned: provenance entropy/source floor, deferred-fire emission guarantee
(flood/session-end), pending-content read-detection + ledger-independent
surfacing, intent-log retention/redaction parity.

## Shadow soak (free evidence)

Run the compliance canary passively in its shadow profile in PROMPTER for 2–4
weeks before or parallel to the paid experiment. Collect telemetry only: no
user-facing injections, blocks, skill/config changes during the locked paid-run
interval, or shadow events added to the paid result set. The soak can expose
live event-morphology gaps, estimate candidate-fire frequency and drift, and
surface obvious false-positive patterns at near-zero model-call cost. It cannot
establish causal requirement-survival lift, false-terminal-completion reduction,
or safety under active injection, and it cannot acquit the canary or substitute
for the randomized paired comparison.

## Budget & authorization

Hard cap PER SUBJECT-MODEL STRATUM: 2 paid rehearsal sessions + 12 main
sessions (6 scenarios × 2 arms) + up to 8 extension sessions (4 scenarios ×
2 arms), for 22 paid sessions maximum per stratum (66 across the three
owner-directed strata). Nothing beyond this cap may run without new owner
authorization. The
rehearsals happen before the binding freeze and never count toward results;
hashing the final document, suite SHA, and scenario bundle is free and happens
after the rehearsal gate passes but before the first counted main session.
