---
trust: verified
schema_version: 2
title: "DanMcInerney/architect-loop review — 9 adopts, 6 rejects"
type: concept
domain: "framework"
tier: episodic
confidence: 0.85
created: "2026-07-05"
updated: "2026-07-05"
verified: "2026-07-05"
sources: ["github.com/DanMcInerney/architect-loop (commits 118fa0d..bdd2db1)", "Brainer ORCHESTRATION.md §6", "Brainer team-lead §2 + §4", "Brainer loop-engineering SKILL", "Brainer brief_header.py (a99b009)"]
supersedes: []
superseded-by:
tags: [orchestration, loop-engineering, adoption, external-review, architect-pattern, team-lead]
---

# DanMcInerney/architect-loop review — 9 adopts, 6 rejects

**Reviewed:** 2026-07-05 (commits 118fa0d..bdd2db1). **Source:** github.com/DanMcInerney/architect-loop — autonomous software factory; orchestrator/builder/judge/watchdog roles; GitHub issues as coordination state; claims 80% token savings, 58–74% split-cost anchor.

## Adopted (9 patterns into Brainer doctrine)

1. **Timed-ruling protocol for human questions in unattended loops** → `loop-engineering` SKILL; bounded response window on advisor checkpoints.

2. **PHASE 0 mandatory disagreement + bounded LANE REPORT w/ typed STATUS line** → `brief_header.py` defaults (commit a99b009); ensures conflicting signals surface early.

3. **Recovery ladder (retrieve→nudge once→respawn, never author missing verdict)** → `team-lead` §4 + `loop-engineering`; enforces bounded escalation before failure-to-proceed.

4. **Frozen-check sharpening (worker edit = auto-FAIL, ImpossibleBench 33→38)** → `loop-engineering`; prevents gate-drift mid-round.

5. **Backend canary preflight (capability not identity; their 6/6 shell-stripped evidence)** → `team-lead` §2; model dispatch checks capability, not brand name.

6. **Failure-never-moves-tier / diagnose-input-first** → `ORCHESTRATION` §6 + `team-lead`; broken inputs stay at same tier, never escalate on bad data.

7. **~400-line reviewable-diff cap** → `team-lead` §4; enforces manageability and verification scoping.

8. **Liveness doctrine (no kill ceilings; identical-command repetition = stall)** → `loop-engineering`; prevents zombie loops.

9. **Effort-curve + cost evidence (xhigh 88/69 semantic-eq, 69/38 review-pass @2.2×; 58–74%; PEAR weak-planner dominance)** → `ORCHESTRATION` §6 evidence block. Establishes the economic anchor for tier routing. All 9 in commit 8248508 unless noted.

## Rejected (6 patterns, with rationale)

1. **GitHub-issues/factory-branch/PR machinery** — infra beyond a skills framework; `ledger`+`baton`+`wiki` cover coordination at Brainer scale.

2. **Deterministic check-runner/preflight/postflight script family** — principle already in `loop_lint`; scripts are repo-specific, not generalizable.

3. **Watchdog script** — harness notifies on background completion in Brainer; separate daemon not needed.

4. **1100-line skill guard** — `cache-lint` covers breakpoint economics; Brainer skills designed far smaller per `when-to-extract-a-skill-md-section-into-tools`.

5. **Research fan-out budgets** — `research-lite` already bounded; no new gate needed.

6. **Codex fast-mode pins** — billing knob, not doctrine; cost is tuned per session, not locked.

## Caveat

Cross-vendor review-direction caveat (Claude-reviews-GPT helped / reverse hurt, single study) recorded in §6 as a variable, not doctrine.

## Related

- [[concepts/team-lead-upstream-2026-07]]
- [[concepts/frontier-routing-topology-2026-07]]
- [[queries/external-validation]]
