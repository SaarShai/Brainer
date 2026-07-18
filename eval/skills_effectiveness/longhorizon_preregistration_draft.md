# Long-horizon FRONTIER-vs-OFF experiment — preregistration DRAFT

Status: DRAFT v1, 2026-07-18. Becomes binding when frozen (hash recorded in
eval/FINDINGS.md) BEFORE the first paid session. Per docs/TARGET_ARCHITECTURE.md
measurement priority #1: this experiment decides whether the suite's core claim
(long-session reliability) is product or placebo. Both 2026-07-18 advisor
sense-checks (Sol Ultra, Kimi K3) independently named it the single missing
proof and instructed it be run before further guard tuning.

## Claim under test

H1: With the Brainer frontier surface installed, long multi-phase agent
sessions drop fewer user requirements and make fewer false terminal completion
claims than with the suite off, at acceptable token/interruption cost.

Null (falsifier): no improvement in requirement-survival recall or
false-terminal-completion rate, or improvement erased by cost (tokens,
false interruptions, recovery time).

## Design

- Venue: PROMPTER project (owner-authorized live/simulated test target).
- Arms: FRONTIER (default install) vs OFF (`COMPLIANCE_CANARY_PROFILE=off`,
  mutation-free control). Paired: each scenario runs once per arm, same model,
  same host, fixture reset between runs.
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
  authored by someone other than the guard's implementer where possible
  (adversarial authorship, per sense-check).

## Metrics (primary first)

1. Requirement-survival recall: satisfied-or-explicitly-dispositioned
   requirements / total embedded requirements (includes the planted constraint).
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

Blind: graders receive transcripts with arm markers stripped (hook output
redacted from the OFF/FRONTIER label perspective where feasible; grader is a
cold model + deterministic checklist per scenario listing every embedded
requirement and its acceptable dispositions). Human spot-check on disagreements.

## Preregistered decision rules

- PROMOTE (keep frontier default): FRONTIER improves metric 1 or 2 in ≥4/6
  scenarios with no scenario materially worse, and false interruptions ≤1 per
  session median, and token overhead ≤3%.
- DEMOTE to shadow: no improvement in metrics 1–2 (≤2/6 scenarios better), or
  false interruptions >2 per session median.
- KILL (off by default, tools remain): FRONTIER worse on metric 1 or 2 overall,
  or any suppression-ate-a-warranted-fire event in ≥2 sessions.
- Ambiguous zone between promote/demote → extend by 4 scenarios, once.

## Not measured here (explicitly)

Wiki longitudinal lift, dose-response/habituation, host-compaction A/B — 
separate experiments; do not let scope creep in.

## Budget & authorization

Estimated 12 long sessions (6 scenarios × 2 arms). Paid model calls; requires
owner go-ahead before execution. Freezing this document + scenario scripts is
free and happens first.
