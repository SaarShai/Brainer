---
schema_version: 2
title: "New-skill landing integration-gate regress (2026-07) — blast radius beyond skill-local tests"
type: lesson
domain: "framework"
tier: semantic
confidence: 0.95
created: "2026-07-12"
updated: "2026-07-12"
verified: "2026-07-12"
sources:
  - "commit bb5d773 (standing-orders build session, 2026-07-12)"
  - "measured: baseline 108/108 core tests → 3 undisclosed FAILs post-landing"
supersedes: []
superseded-by:
tags: [skills, testing, integration, regression, new-skill-landing, gate-first, builders, integration-test]
---

# New-skill landing integration-gate regress (2026-07)

## Summary

**Trigger:** A builder lane gates a new skill only on skill-local tests (the skill's own `.../test_*.py`, `check_skill_contracts`, e1 suite) and reports green. Skill ships. Hidden regressions appear only in a cold full-suite run.

**Root cause:** A new skill's hidden blast radius extends far beyond the skill directory. Landing touches **six integration points** that local gates do not check:

1. **carrier-sync** — CLAUDE.md / AGENTS.md / GEMINI.md catalogs must be updated; re-run `./install.sh` needed
2. **marketplace-sync** — `.claude-plugin/marketplace.json` entry must be added; prose entry count must match the file count
3. **README skill count** — the skill count line in project README must be updated
4. **eval/exp8 fixture coverage** — hardcoded live-skill counts and TARGET_CASES must match new count
5. **harness_acceptance H1a** — resident catalog block byte budget (7668B) is consumed by skill descriptions; overflow breaks it
6. **harness_acceptance H1b–H1c** — SKILL.md >15360B needs a linked REFERENCE.md companion; cross-file count consistency

## Measured outcome

**Standing-orders build session, commit bb5d773:**

- Baseline: `bash scripts/run_all_tests.sh --group core` → 108 PASS / 0 FAIL
- Post-landing (single-skill lane gate reported green): 3 undisclosed FAILs in integration suite
- Root-cause: cold verifier ran full core suite that local lane did not

## Rule

**Any new-skill lane's DONE-MEANS must include:**
- `bash scripts/run_all_tests.sh --group core` at 0 FAIL (not just local skill tests)
- Brief must name integration-check files as in-scope: carrier-sync, marketplace-sync, README, eval/exp8, harness/H1a/H1b/H1c

## Why it matters

- **Local gates are honest about their domain** but silent about what they don't cover
- **Integration tests are the real verifier** — they discover coupling that skill-local tests cannot see
- **Builder confidence must match actual coverage** — a lane reporting "green" on tests that don't touch integration files ships false confidence
- **Cold verifier catch-rate was 100%** — if task-local tests missed it, full suite found it (3/3 in this session)

## Related

- [[learning-loop-hardening-2026-07]] — lifecycle testing and negative tests
- [[gate-first-rebuild-methodology]] — gate before code, honest baselines
- [[lean-execution]] — scope discipline
- `skills/_shared/LEARNING_CONTRACT.md` — builder doctrine §3 (verification gates)
- `scripts/run_all_tests.sh --group core` — the integration suite

## Open questions

- Should `./install.sh` or builder brief auto-check for missing integration-file updates?
- What's the minimum set of integration checks a builder lane can run locally (shorter than full core suite)?
