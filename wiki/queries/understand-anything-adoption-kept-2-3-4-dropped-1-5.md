---
trust: verified
schema_version: 2
title: "Understand-Anything adoption: kept #2/#3/#4, dropped #1/#5"
type: decision
domain: "framework"
tier: episodic
confidence: 0.7
created: "2026-06-22"
updated: "2026-06-27"
verified: "2026-06-27"
sources: ["Egonex-AI/Understand-Anything", "git a83f737"]
supersedes: []
superseded-by:
tags: [decision, adoption, understand-anything, framework-hardening]
---

# Understand-Anything adoption: kept #2/#3/#4, dropped #1/#5

## Decision

Evaluated 5 ideas from `Egonex-AI/Understand-Anything` against Brainer's actual
state (commit `a83f737`, 2026-06-22). Adopted #2, #3, #4; dropped #1; skipped #5.

## Adopted

- **#2 — wiki-refresh staleness nudge.** Added `staleness.py` + test: an opt-in
  SessionStart nudge that fires only when HEAD advanced past the last full
  reconcile (silent, exit-0 on the no-op path). Hardened vs corrupt/non-dict
  markers, unreachable marker commits (null counts, not a fake 0), and marker
  self-contamination (gitignored + path-filtered).
- **#3 — loop-engineering fleet doctrine.** "Payloads to disk, summaries to
  context" and "precompute deterministic facts once; forbid re-derivation"
  (arithmetic-justified).
- **#4 — index-first.** The inject-once-for-N-consumers point.

## Dropped / skipped

- **#1 — fingerprint change-classifier — DROPPED** because an adversarial review
  found 13 dangerous false-negatives; the safe rebuild skips only ~0.2% of real
  `.py` edits, so the token-saving premise was false.
- **#5 — tiered verifier — SKIPPED** because Brainer already ships both tiers
  (lint scripts + `eval-gate`).

## Related

- [[concepts/framework-hardening-adoption]]
- [[index]]
- [[schema]]
