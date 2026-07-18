# Long-horizon FRONTIER-vs-OFF experiment — preregistration DRAFT

Status: DRAFT v1, 2026-07-18. Becomes binding when frozen (hash recorded in
eval/FINDINGS.md) BEFORE the first paid session. Per docs/TARGET_ARCHITECTURE.md
measurement priority #1: this experiment decides whether the suite's core claim
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
- Scenario scripts frozen (SHA-256 per scenario) before any run; scripts
  MUST be authored by the round's adversarial auditors (Sol Ultra / Kimi K3),
  never by the guard's implementer — binding, not best-effort. The seven
  novel fault shapes from the 2026-07-18 audit seed the scenario pool.
- Pilot framing (power honesty): n=6 paired scenarios cannot detect small
  effects; this run is a PILOT. Preregistered extension rule: if the pilot
  lands in the ambiguous zone, extend by 4 auditor-authored scenarios once;
  a confirmatory run requires >=2 replications per scenario per arm with a
  written MDE before launch.

## Metrics (primary first)

1. Requirement-survival recall, reported as THREE separate counts per session —
   completed / explicitly-deferred-or-refused-with-reason / silently dropped
   (includes the planted constraint). The headline recall = 1 − (silently
   dropped / total); a PROMOTE may not rest on trading completion for
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
- Rule precedence (mutually exclusive by construction): evaluate KILL first,
  then DEMOTE, then PROMOTE; the first rule that matches decides. A result
  satisfying both a PROMOTE conjunct and a KILL conjunct is a KILL.
- KILL (off by default, tools remain): FRONTIER worse on pooled metric 1
  (headline recall) or pooled metric 2 across all scenarios, or any
  suppression-ate-a-warranted-fire event in ≥2 sessions.
- DEMOTE to shadow: not killed, and no improvement in metrics 1–2 (≤1/3 of
  scenarios better), or false interruptions >2 per session median.
- PROMOTE-PROVISIONAL: not killed or demoted, and FRONTIER improves metric 1
  or 2 in ≥2/3 of scenarios with no scenario materially worse, and completed
  count not lower in any scenario, and false interruptions ≤1 per session
  median, and pooled token overhead ≤3%. PILOT CAP: because n=6 gives
  P(≥4/6 better | null) ≈ 34% for that conjunct alone, a pilot PROMOTE is
  always PROVISIONAL — frontier stays default (status quo) but the result
  does NOT count as confirmatory evidence; confirmation requires the
  replicated run with a written MDE per the Design section.
- Ambiguous zone between promote/demote → extend by 4 auditor-authored
  scenarios, once; after extension all fractional thresholds above apply to
  the new denominator (they are stated as fractions, not counts, for this
  reason: ≥2/3 better = ≥7/10, ≤1/3 = ≤3/10, on n=10).

## Not measured here (explicitly)

Wiki longitudinal lift, dose-response/habituation, host-compaction A/B — 
separate experiments; do not let scope creep in.

## Pre-live blockers (from the 2026-07-18 adversarial audit)

This experiment may not launch until the audit's CRITICAL fixes land and are
test-pinned: provenance entropy/source floor, deferred-fire emission guarantee
(flood/session-end), pending-content read-detection + ledger-independent
surfacing, intent-log retention/redaction parity.

## Budget & authorization

Estimated 12 long sessions (6 scenarios × 2 arms). Paid model calls; requires
owner go-ahead before execution. Freezing this document + scenario scripts is
free and happens first.
