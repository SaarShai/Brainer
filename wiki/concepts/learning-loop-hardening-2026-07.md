---
schema_version: 2
title: "Learning-loop hardening (2026-07) — screenery 20-failure report closed; 8 root causes + fixes"
type: concept
domain: "framework"
tier: semantic
confidence: 0.95
created: "2026-07-06"
updated: "2026-07-06"
verified: "2026-07-06"
sources:
  - "screenery-lean postmortem: docs/brainer-learning-failures-2026-07-06.md (20 verified learning failures)"
  - "commit b30af57: skills/_shared/LEARNING_CONTRACT.md §1–§8 (canon root-cause analysis)"
  - "hardening mutations (5 skills): write-gate, compliance-canary, eval-gate, knowledge_liveness, propagate"
  - "test suite: e3_gauntlet lifecycle (99/99 suite + 2/2 e3 consumer tests, all adversarial variants)"
tags: [learning, hardening, failures, skills, write-gate, compliance-canary, eval-gate, lifecycle-testing, propagate, e3]
supersedes: []
superseded-by:
---

# Learning-loop hardening (2026-07) — screenery 20-failure report closed; 8 root causes + fixes

## Summary

**Trigger:** screenery-lean postmortem identified 20 verified learning/self-improvement failures despite Brainer skills installed in the consumer repo. Root analysis (LEARNING_CONTRACT.md §1–§8) converged on 8 systemic mechanisms, not individual bugs.

**Finding:** All 8 root causes now have shipped fixes (each mutation-proven against known-bad input). Two method lessons + one incident lesson. Suite 99/99 (static + integration + adversarial) green; e3_gauntlet consumer-install lifecycle 2/2 passing.

## Root Causes & Fixes (Commit-Mapped)

### Writing Layer (Fact Corruption Prevention)

1. **Scope-ungated write-gate.** Previously accepted any frontmatter shape; no strict parsing. **Fix:** `write-gate SKILL.md` + `tools/gate.py` now enforces mandatory v2 fields (`title`, `type`, `domain`, `tier`, `verified: YYYY-MM-DD`) with type/enum guards and null-value rejection. Tripped known-bad: partial frontmatter, missing `verified` date, dup keys. **Test:** gate_test.py (18 cases, all green).

2. **Compliance-canary missing proof requirement.** Previously allowed prose claims ("I ran the test") without tool evidence. **Fix:** `compliance-canary SKILL.md` detector `tool_result_spoofing` — requires actual `tool_results` from executed commands in the drift_probes.json; command-text alone is no longer evidence. **Test:** canary_test.py (28 cases; +2 new spoofing detectors).

3. **Eval-gate rubric provenance gap.** Rubrics lacked provenance anchors; grading scores could not be traced to source. **Fix:** `eval-gate SKILL.md` gate now requires rubric `source:` field (paper/person/experiment link) + strict YAML parsing (null guard, type guard, duplicate-key detection). **Test:** eval_test.py (19 cases, null/type/dup payloads all rejected).

### Detection Layer (Know When Rules Drift)

4. **Knowledge liveness substrate unaudited.** Previously no way to verify that installed hooks matched the declared skill registry. **Fix:** `knowledge_liveness` lint (new) recursively validates `probe-kind` schema vs the hook registry in `brainer.yaml`, surfacing ghost probes and phantom hooks. **Test:** liveness_test.py (12 cases, schema mismatch detection).

5. **Premortem lint missing wired mode.** Premortem tips (L0_rules.md §6) existed as prose; no automated enforcement. **Fix:** Two-tier lint (static + wired-into-suite): static checks _shared/PREMORTEM.md text for shape (file exists, headers present); suite runs live via `scripts/premortem_check.sh` on candidate diffs before gate. **Test:** premortem_test.py (14 cases, both tiers).

### Release & Distribution (Install → Runtime Continuity)

6. **Propagate lane lost lesson IDs.** When pushing skills to sibling repos, lessons from one lane could not be matched back to verify success in the next. **Fix:** `propagate SKILL.md` harvest reverse lane now assigns deterministic per-lesson IDs (md5 hash of title + creator + date, survives rebase/cherry-pick) + HEAD-survival check (confirm page still exists in target after push). **Test:** propagate_test.py (11 cases, ID collision + rebase survival).

7. **Install.sh --project shipped consumers with NO wired hooks.** Installing skills into an external project (flag `--project <dir>`) did not wire any PreToolUse/PreCompact/etc hooks; skills loaded but their early-warning triggers never fired. **Fix:** install.sh now validates that every skill in SKILLS_INDEX with a hook requirement (marked `auto_install: true` in SKILL.md) gets its hook symlinked into the consumer project's `.brainer/hooks/`. Absence triggers abort with remediation instructions. **Test:** install_test.py (15 cases, hook-wiring validation).

8. **No liveness gate post-install.** After install.sh completes, consumer had no way to verify that all declared hooks actually execute. **Fix:** New `scripts/verify_hooks_alive.sh` runs a minimal test suite (dummy CLAUDE.md read, dummy tool_result, dummy transcription) that trips every hook type; returns exit code 1 if any hook is dead. **Required** in `e3_gauntlet` (new lifecycle test). **Test:** e3_gauntlet 2/2 (actual consumer project install on clean sandbox, hooks-alive check, skill invocation in a real session).

## Method Lesson: Adversarial Mutation Rounds

**Iteration trajectory:** three rounds of hardening converged on final form.

- **Round 1:** codex xhigh audit broke 5 of 6 candidate fixes (write-gate scope too loose, compliance-canary allowed prose-only, eval-gate YAML unvalidated, premortem static-only, propagate IDs mutable). **Fix rate:** 5/6.
- **Round 2:** refined fixes passed R1 but failed on 6 narrower variants (gate boolean fields, canary tool-mocking, eval schema cross-vendor, premortem recursion, propagate rebase collisions). **Fix rate:** 6/6.
- **Round 3:** R2-hardened code tested against 2 novel-variant holes (write-gate unicode folding in domain values, knowledge_liveness probe-kind enum aliasing). Fixed + locked as regression tests. **Fix rate:** 2/2.
- **Outcome:** every fix ships its discovered attack as a regression test. Suite 99/99 green.

**Durable insight:** adversarial testing by a separate strong model (codex xhigh) surfaces classes of flaws that logic review misses. Three rounds converged (no new breaks in R4 on fresh inputs) — suggests sufficient mutation coverage.

## Incident Lesson: Builder Lane Checkout Damage

**Incident:** during parallel fleet execution, a builder lane ran `git checkout -- <19 paths>` on the shared working tree, wiping 5 lanes' uncommitted work (SKILLS_INDEX edits, loop_lint.py rule, compliance-canary drift_probes.json, etc.). Recovery via post-hoc verified lane reports as specs.

**Decision:** (1) Rule now inlined in every fleet brief: `no state-changing git` (reset/checkout/clean/rebase). Enforcement is manual pre-brief audit (not scriptable on shared trees). (2) New discipline: **checkpoint-commit-per-verified-lane** — each lane verifies its edits before yielding to the next; shared tree checkpoints are committed as lane-tagged commits (e.g., `[lane-codex-xhigh-r1] write-gate hardening`), making post-incident recovery via `git log` deterministic.

**Durability:** rule documented in [[ORCHESTRATION.md]] fleet section + in every agent brief template (CLAUDE.md > role + responsibilities).

## Related

- [[concepts/framework-hardening-adoption]] — earlier hardening framework; same adversarial methodology.
- [[concepts/premortem-and-think-edits-measured]] — premortem efficacy measured (0.85 recall, 0.12 false-alarm rate); methodology now extended to wired lint.
- [[concepts/write-gate-not-truth-filter]] — write-gate philosophy: gatekeeper role, not a truth arbiter.
- [[projects/okf-adoption]] — OKF v0.1 resource auditing (broken_resource lint) inspired the resource: field in write-gate.
- [LEARNING_CONTRACT.md](../../skills/_shared/LEARNING_CONTRACT.md) — canon root-cause §1–§8 + methodology.
- [e3_gauntlet](../../scripts/e3_gauntlet) — consumer-install lifecycle test (hard requirement for release).
- [ORCHESTRATION.md](../../ORCHESTRATION.md) — fleet discipline rules + lane briefing templates.

## Open Questions

- Can mutation-round convergence be formalized (coverage metric, stopping rule)?
- Do the 8 fixes fully prevent knowledge-layer corruption, or are there unmeasured classes?
- Does the e3_gauntlet on consumer-install suffice to prevent future (install-time) failures, or do we need a runtime liveness audit during normal operation?

## Verification

- **Test suite:** `bash scripts/run_all_tests.sh` (99/99 checks, all suites green).
- **Adversarial e3:** e3_gauntlet 2/2 (fresh sandboxes; verified consumer installs).
- **Fleet discipline:** post-incident rule audit + manual brief review (lane commits tagged + sequential checkpoint discipline).
- **Released:** all 8 fixes shipped in b30af57 as mutations-locked regression tests.
