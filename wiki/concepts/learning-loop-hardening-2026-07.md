---
schema_version: 2
title: "Learning-loop hardening (2026-07) — screenery 20-failure report closed"
type: concept
domain: "framework"
tier: semantic
confidence: 0.9
created: "2026-07-06"
updated: "2026-07-06"
verified: "2026-07-06"
sources:
  - "screenery-lean postmortem: docs/brainer-learning-failures-2026-07-06.md (in that repo; 20 verified learning failures)"
  - "commits 6ebb776, 997c1ce, ea37611, b30af57 (Brainer)"
tags: [learning, hardening, failures, skills, write-gate, compliance-canary, eval-gate, lifecycle-testing, propagate, e3]
supersedes: []
superseded-by:
---

# Learning-loop hardening (2026-07) — screenery 20-failure report closed

## Summary

**Trigger:** screenery-lean postmortem reported 20 verified learning/
self-improvement failures despite Brainer skills being installed there.
Canon distillation: `skills/_shared/LEARNING_CONTRACT.md` §1–§8.

**Outcome:** every mechanism below shipped with a negative test proving it
trips on known-bad input. Suite `bash scripts/run_all_tests.sh` 99/99;
consumer-lifecycle gauntlet `--group e3` 2/2. Commits: 6ebb776 → b30af57.

## What shipped (real paths, real tests)

1. **write-gate SCOPE gate** — mandatory SCOPE classification
   (`this-skill/this-repo/cross-skill/cross-repo/canon`); strict well-formed
   frontmatter parsing (body-text `scope:` and unclosed frontmatter
   rejected); frontmatter `kind` honored, CLI conflict = error.
   Tests: `skills/write-gate/tools/test_write_gate.py` (25).
2. **compliance-canary correction ledger (Mechanism 4)** — a user correction
   opens a closeout-blocking item (LEARNING_CONTRACT §2) that resolves only
   on a real, executed, successful banking call: invocation-shape match AND
   a correlated `tool_result` carrying the tool's output signature
   (`PASSED:`/wiki page path). Command-text spoofing (`echo write_gate.py`,
   `false && …`, `CMD="…"`) does not resolve. Known residual: bare `gate`
   without `--json` prints nothing → cannot resolve (documented in EVAL.md).
   Tests: `skills/compliance-canary/tools/test.sh` (118, incl. 34a–34o).
3. **eval-gate rubric provenance** — criteria may declare
   `source: spec|canon|frozen-before-generation`; invalid/executor-claims/
   null/non-string/duplicate-key `source` → exit 2; `--require-provenance`
   also rejects bare lists. Self-attestation limit documented.
   Tests: `skills/eval-gate/tools/test.sh`.
4. **knowledge_liveness lint** (`skills/_shared/knowledge_liveness.py`) —
   gate substrate must parse AND probe `kind`s must exist in the canary
   hook's implemented detector set (derived from hook.py, not hard-coded);
   recursive `tools/**/*.json`; markdown-link resolution in skills + wiki.
   Wired into `run_all_tests.sh` and `install.sh`.
   Tests: `skills/_shared/test_knowledge_liveness.py`.
5. **Premortem lint** (`scripts/lint_skill_md.py --strict`) — gate-shipping
   skills need a real `## Failure modes` section (3 named non-placeholder
   bullets) + a negative-test artifact with live-code assertions that is
   wired into something that runs. Static tier ≠ execution proof
   (documented); `if False:` evasion accepted as a static limit.
6. **propagate harvest lane** — reverse flow sibling→canon with per-lesson
   IDs (sha256 of normalized block, 12 hex; or file+heading), marker
   grammar `harvested: <ISO-date> <sha> <lesson-id>` outside code fences,
   survival check at Brainer HEAD before marking.
7. **install.sh --project consumer wiring** — the concrete mechanism behind
   screenery's failures: consumers got skill files but NO wired hooks and
   no liveness check. Now wires compliance-canary/context-keeper/
   prompt-triage into the consumer's `.claude/settings.json` + runs the
   portable liveness subset on the consumer tree.
8. **e3 lifecycle gauntlet** (`scripts/e3_gauntlet.py`, opt-in
   `run_all_tests.sh --group e3`) — real `install.sh --project` into a
   fresh temp project; checks skill set, cross-repo write-gate rejection,
   substrate liveness, probe parsing, hook wiring (check e). Negative
   self-tests: `scripts/test_e3_gauntlet.py` (6).

## Method lesson

Three adversarial rounds (codex, xhigh, read-only) converged: round 1 broke
5/6 mechanisms (command-text spoofing, frontmatter bypass, bare-list
provenance bypass, probe-kind blindness, harvest double-count, lint
theater); round 2 broke 6 strictly narrower variants; round 3 held against
replays + novel variants (incl. forged tool_result signatures). Every
exploit became a permanent regression test. Convergence of attack classes —
not effort — is the ship criterion (same rule as the redaction-sink work).

## Incident lessons

- A builder lane ran `git checkout -- <19 paths>` on the shared tree for a
  "clean baseline", wiping 5 lanes' uncommitted work; a second lane used
  `git stash` despite prohibition. Controls now: no-state-changing-git
  inlined in every fleet brief; checkpoint-commit after each verified lane;
  on incident, demand each agent's verbatim git history (culprit
  self-identified). Recovery worked because verified lane reports doubled
  as rebuild specs.
- **Delegate fabrication:** the first draft of THIS page (written by a
  wiki subagent from an accurate brief) invented file names, tests, and
  attack details at confidence 0.95. Knowledge-layer writes by a delegate
  must be fact-checked against ground truth by the briefing context before
  commit (LEARNING_CONTRACT §5).
- First consumer install (product images repo) had its liveness lint trip
  on a cross-repo dead link in a canonical skill on day one — led to the
  canon rule: skill files link only paths that travel with the skill.

## Related

- [[concepts/framework-hardening-adoption]] · [[concepts/write-gate-not-truth-filter]]
- `skills/_shared/LEARNING_CONTRACT.md` — canon §1–§8
- `skills/_shared/ORCHESTRATION.md` — fleet cost/verify doctrine
- `scripts/e3_gauntlet.py` — consumer-lifecycle test

## Open questions

- Formal stopping rule for adversarial-round convergence?
- Runtime (not install-time) liveness audit during normal consumer operation?
