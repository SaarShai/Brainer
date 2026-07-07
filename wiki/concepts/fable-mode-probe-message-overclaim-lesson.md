---
schema_version: 2
title: "Fable-mode probe message overclaim — drift-detector must not assert unobservable semantics"
type: lesson
domain: "framework"
tier: semantic
confidence: 0.95
created: "2026-07-07"
updated: "2026-07-07"
verified: "2026-07-07"
sources:
  - "commit 2753220: fable-mode probe initial ship (claimed 'same class of failure recurred')"
  - "commit 5ce5f38: fable-mode probe message fix (downgraded claim to 'count >= 3 failures')"
  - "canary test [103d]: regression lock preventing 'same class'/'STOP retrying variations' in probe message"
tags: [fable-mode, drift-probe, failure-diagnosis, message-calibration, overclaim, failure-lesson, compliance-canary]
supersedes: []
superseded-by:
---

# Fable-mode probe message overclaim — drift-detector must not assert unobservable semantics

## The failure

Commit 2753220 shipped fable-mode's `kind=repeated_tool_error` probe with a user-facing message claiming **"the same class of failure recurred — STOP retrying variations"**. The detector works by counting `is_error` results in matching tool-call patterns. 

**Problem:** Counting matching errors does NOT observe error *class* equivalence. Adversarial review found false-diagnoses on 3 distinct failures where the probe would advise stopping variation exactly when varying is the right corrective action.

## Root cause

The probe's *observable* signal: ">=3 results with is_error=true in this pattern". The message's *claimed* signal: "we have confirmed these are the *same class* of failure, not variations". These are categorically different — the second requires semantic analysis (logs, error types, stack comparison) that the counter-based detector never performs.

**Why this matters now:** When an agent is struggling (the exact moment the probe fires), a plausible-sounding message that overclaims creates WRONG corrective advice and undermines trust in the signal.

## The fix

Commit 5ce5f38 downgraded the message to claim only what the detector observes: **">=3 failures = stalling"** (a factual restatement of the counter condition, not a diagnosis of failure class).

Regression locked by canary test [103d]: if the emitted message ever contains "same class", "STOP retrying variations", or equivalent semantic claims, the test fails. The counter-detector is now behaviorally honest.

## Lesson for drift probes

- **Emit only observed semantics.** A probe's user-facing message must map 1:1 to the detector's actual signal, not to a downstream interpretation.
- **Name the count or pattern, not the diagnosis.** If your detector counts something, say "count >= N"; do not say "we know the root cause is X" unless your code actually confirms X.
- **Plausible-sounding false advice is worse than silence.** An agent follows a confident-seeming probe message even when it contradicts the situation — especially in failure mode.
- **Mechanize the integrity lock.** Regression tests that fail if overclaim language ever reappears are the only durable control.

## Related

- [[concepts/learning-loop-hardening-2026-07]] — compliance-canary mechanisms and negative tests
- `skills/fable-mode/drift_probes.json` — probe definitions
- `skills/fable-mode/tools/test_fable_probes.py` — test [103d] implementation

## Open questions

- Are there other drift probes emitting unobservable semantics?
- Should "observed vs claimed signal" be a lint check across all drift_probes.json?
