---
schema_version: 2
title: "Honest re-baseline procedure for self-set byte budgets (H1a)"
type: procedure
domain: "framework"
tier: procedural
confidence: 0.9
created: "2026-07-07"
updated: "2026-07-07"
verified: "2026-07-07"
sources:
  - "Brainer harness H1a check docstring (eval/harness_acceptance/run.py)"
  - "2026-07-07 re-baseline measurement: 6964B → 7412B (26→27 skills)"
  - "structural-byte audit at old-floor commit and HEAD"
tags: [byte-budget, gate-first, re-baseline, measurement, process-integrity, framework-hardening]
supersedes: []
superseded-by:
---

# Honest re-baseline procedure for self-set byte budgets (H1a)

## The procedure

When a self-set byte budget (like Brainer's `BUDGET_BYTES`) needs adjustment after adding new content, use this three-step verification to distinguish **documented-floor correction** from **target-gaming**:

1. **Split the measured block** into two immutable categories:
   - **Immutable content**: all durable facts, decision rationale, measured numbers, code (literally, in skill bodies, test code, etc.)
   - **Structural bytes**: whitespace, comment-only lines, YAML keys, formatting, section headers with no substantive change

2. **Measure both categories at two commits:**
   - The old-floor commit (the previously-accepted baseline)
   - HEAD (the current proposal with new content)

3. **Apply the gate:**
   - If structural bytes are **unchanged** (relocation exhausted, no reformat, no optimization possible)
   - AND **100% of byte growth is immutable content** (facts, rationale, measured data)
   - THEN the budget may move to: `new-floor + same-margin`
   - OTHERWISE, the proposed floor is rejected and must be re-optimized.

## Instance: 2026-07-07 Brainer H1a re-baseline

**Setup:** 26 skills → 27 skills added. Measure Brainer's boot context.

**Result:**
- Old floor (26 skills): 6964B
- New proposal (27 skills): 7412B
- **Structural bytes:** 2353B at old commit = 2353B at HEAD (byte-identical, diff confirms)
- **Growth:** 7412 - 6964 = 448B, **100% immutable** (new skill body + decision citations)
- **Harness test:** 16/16 green on first run after re-baseline

**Approved floor adjustment:** `BUDGET_BYTES: 7220 → 7668` (new-floor 7412 + same 256B margin)

**Standing bar recorded** in `eval/harness_acceptance/run.py` docstring: H1a gate definition, procedure, and acceptance criteria are stable for future re-baselines.

## Why this procedure exists

**Failure mode:** Without this gate, teams gradually raise self-set budgets by claiming "we added important content" (often true, sometimes not), eventually drifting to arbitrary "whatever-fits" targets that lose their meaning as guardrails. The gate-first rule demands that we distinguish defensible growth from target-gaming.

**Measurement discipline:** The procedure forces an explicit audit of what changed and why. Structural-byte parity proves "we did not reformat to hide growth"; 100%-immutable growth proves "every new byte is durable content, not filler".

## Related

- [[concepts/frontier-routing-topology-2026-07]] — first measurement in gate-first rebuild
- [[concepts/learning-loop-hardening-2026-07]] — gate-first methodology overview
- `eval/harness_acceptance/run.py` — H1a check implementation
- `skills/_shared/ORCHESTRATION.md` — cost/verify doctrine

## Open questions

- Should this procedure apply to other self-set budgets (token spend, probe count, test suite size)?
- Automated structural-diff tool to support this audit on large codebases?
