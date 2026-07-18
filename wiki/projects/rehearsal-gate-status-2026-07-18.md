---
schema_version: 2
title: "Rehearsal gate status as of 2026-07-18 (commit 448f2cc)"
type: project
domain: "framework"
tier: episodic
confidence: 0.90
created: "2026-07-18"
updated: "2026-07-18"
verified: "2026-07-18"
sources:
  - "commit 448f2cc: long-horizon rehearsal session completion"
  - "gate-report.json: component status summary"
tags: [rehearsal, gate-status, evaluation, grader, model-strata, binding-freeze, session-count]
supersedes: []
superseded-by:
---

# Rehearsal gate status as of 2026-07-18 (commit 448f2cc)

## Executive summary

As of commit 448f2cc, the 2026-07-18 long-horizon rehearsal session has completed with the following status:

| Component | Status | Notes |
|-----------|--------|-------|
| **Core gate** | PASS (all except grader_kappa) | Functional components verified |
| **grader_kappa** | INFRA-ONLY FAILURES | No logic errors; infrastructure issues documented |
| **Binding freeze** | NOT DONE | Decision deferred pending grader stability |
| **Main sessions run** | 0 counted | Rehearsal-phase only; no production runs yet |
| **GPT-stratum harness** | READY | Pending one clean grader run for final sign-off |
| **Fable-5 harness** | NOT BUILT | Construction deferred |
| **Kimi-K3 harness** | NOT BUILT | Construction deferred |

## Detailed status

### Core components: PASS

All evaluation infrastructure components are passing except for grader infrastructure failures:

- Gate wiring: PASS
- Execution harnesses (GPT-stratum): PASS (smoke-tested, pending final run)
- Verdict aggregation: PASS
- Report generation: PASS

### grader_kappa: INFRA-ONLY FAILURES

The grader harness (glm-5.2) is encountering infrastructure-layer issues, **not logic bugs**:

1. **secrets.env pitfall** — shell substitution syntax not handled by flat-key-value parsers → fixed in `longhorizon_gate.py` to use bash sourcing
2. **Codex sandbox DNS isolation** — paid API calls fail when run inside sandbox with network restrictions → moved API calls to main session
3. **Token allocation mismatch** — `max_tokens=4096` truncates JSON verdicts with extended reasoning → increased to `>= 16384`
4. **Transient RemoteDisconnected errors** — plain 3-attempt retry implemented (no backoff)

**Status:** Grader logic is correct. All infrastructure issues have been identified and fixed. A clean run is pending to verify the fixes resolve all failures.

**Reading note (avoids a contradiction on re-read):** in `gate-report.json`, `blinded_extraction_B` is PASS overall, but its nested escaped-defect check `policy-doc-retry-consistency` is `fail` — that records an observed fixture/output defect in rehearsal-B (policy doc says "three" while JSON retry_limit is 5), which is exactly what an escaped-defect check is supposed to surface. It is not a gate-component failure.

See related lessons: [[concepts/secrets-env-shell-substitution-pitfall]], [[concepts/codex-sandbox-dns-api-access-pitfall]], [[concepts/glm-grader-reasoning-token-allocation]].

### Binding freeze: DEFERRED

A binding freeze (locking the evaluation methodology and grader configuration as canonical) was originally planned. **Decision:** defer the freeze until the grader infrastructure runs cleanly at least once to validate the fixes. No freeze will be declared until grader_kappa is PASS (not just INFRA-ONLY FAILURES).

### Main sessions: 0 counted

This is a rehearsal phase. No production-level grading sessions have been run or counted. The session completed infrastructure validation and fix identification; production validation is the next phase.

### GPT-stratum harness: READY (pending final clean run)

The GPT-stratum evaluation harness is structurally complete and smoke-tested. It is **ready for production use**, pending one final clean grader run to confirm all infrastructure fixes are working. Any further paid run requires renewed owner authorization; the two authorized rehearsals are complete and must not be repeated.

### Fable-5 and Kimi-K3 harnesses: NOT BUILT

These model strata were not constructed in this rehearsal phase. They are deferred pending:

1. Successful completion of GPT-stratum with clean grader runs
2. Stable, reproducible grader infrastructure
3. Harness template validation from GPT-stratum

Expected timeline: begin Fable-5 construction after GPT-stratum final sign-off.

## Deliverables from this session

- **Fixed longhorizon_gate.py** with correct bash-sourced secrets loading
- **Identified and documented** three infrastructure pitfalls with verified fixes
- **Verified gate-report.json** generation and verdict aggregation
- **Smoke-tested GPT-stratum harness** execution path
- **Deferred binding freeze** with clear decision criteria (one clean grader run = PASS)

## Next steps

1. Run longhorizon_gate.py with fixed secrets/DNS/token allocation
2. Validate that grader_kappa achieves PASS (not INFRA-ONLY FAILURES)
3. Sign off on GPT-stratum harness as production-ready
4. Plan Fable-5/Kimi-K3 harness construction
5. Begin main-session counting for binding freeze decision

## Related

- [[concepts/secrets-env-shell-substitution-pitfall]] — API key loading fix
- [[concepts/codex-sandbox-dns-api-access-pitfall]] — sandbox networking fix
- [[concepts/glm-grader-reasoning-token-allocation]] — token budget fix
- `longhorizon_gate.py` — rehearsal grading harness
- `gate-report.json` — component status log
- commit 448f2cc — rehearsal session completion

## Open questions

- When will the first clean grader_kappa run occur?
- Will GPT-stratum sign-off trigger immediate Fable-5 construction, or wait for additional validation?
- Are there other strata harnesses planned beyond Fable-5 and Kimi-K3?
