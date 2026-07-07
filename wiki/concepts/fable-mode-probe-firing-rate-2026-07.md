---
schema_version: 2
title: "Fable-mode probe domain firing rate — measured 2026-07 in product-images repo"
type: concept
domain: "framework"
tier: episodic
confidence: 0.85
created: "2026-07-07"
updated: "2026-07-07"
verified: "2026-07-07"
sources:
  - "product-images repo real-session data (2026-07-07)"
  - "783 is_error texts sampled from live sessions"
  - "32 session runs analyzed for probe threshold crossing"
tags: [fable-mode, drift-probe, firing-rate, measurement, domain-data, false-positive-calibration]
supersedes: []
superseded-by:
---

# Fable-mode probe domain firing rate — measured 2026-07 in product-images repo

## Measurement summary

**Dataset:** product-images repo, real sessions, 2026-07-07 run.

**Corpus:** 783 `is_error` texts extracted from live tool_call results.

**Measured firing patterns:**

| Metric | Value | Interpretation |
|--------|-------|-----------------|
| Pattern match rate | 87.7% | Of the 783 texts, 87.7% match fable-mode's `kind=repeated_tool_error` detector pattern |
| Session fire rate | ~66% | In 32 sessions analyzed, ~66% crossed the min_count threshold and would trigger a probe warn |
| False-positive exposure | High | High proportion of real errors match the pattern, so false-positives from pattern mis-tuning are plausible |

## Interpretation

The detector pattern is **over-inclusive in this domain** — it catches a large fraction of all real tool errors. This is not inherently bad (high recall), but it means:

1. **False-positive risk is real:** If the min_count threshold is too low (e.g., min_count=2), the probe fires frequently on transient errors (network hiccup, retry-able races) that are not "stalling".
2. **Proportionality decision:** The probe severity should calibrate to domain expectations. A warn level (advisory, does not stop agent) is appropriate for 87.7% domain match rate *if the min_count gate is tuned conservatively*.
3. **Tuning path:** Consumer repos (screenery, product-images, etc.) that experience probe fatigue can raise `min_count` in their own fork copies without waiting for a canonical change.

## Decision

**Canonical severity: warn (unchanged).** The high-match rate justifies keeping the probe active (high recall is the design goal — catch stalling when it happens). The cost of false-positives is an advisory message the agent can read and dismiss; the cost of a false-negative is an agent spinning in an undetectable loop.

**Consumer tuning:** Product-images repo and other high-noise consumer codebases should fork `skills/fable-mode/drift_probes.json` and set `min_count: 4` or higher (vs canonical 3) to reduce false-positive fire rate while keeping the probe armed.

## Related

- [[concepts/fable-mode-probe-message-overclaim-lesson]] — message calibration after overclaim fix
- [[concepts/learning-loop-hardening-2026-07]] — compliance-canary and probe architecture
- `skills/fable-mode/drift_probes.json` — probe configuration
- `skills/fable-mode/tools/test_fable_probes.py` — detector tests

## Open questions

- What is the "acceptable false-positive rate" for a drift probe in production? Is 66% session-fire rate acceptable if most are transient errors?
- Should canonical min_count be data-driven from a corpus of known-stalling vs known-transient sequences?
- Can we measure false-negative rate (stalls that the probe *missed*) in this domain?
