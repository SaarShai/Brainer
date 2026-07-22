<!-- demoted-from-skill: verify-before-completion (long checklist portion) — 2026-07-17 (D31 consolidation) -->
<!-- The compact claim-layer invariant and verifier tooling (tools/verify_artifact.py,
     the cross-vendor escalation dispatch) stayed in skills/verify-before-completion/SKILL.md.
     This brief is the demoted prose checklist for delegated/cheap-model execution. -->

# Verify before completion — full checklist (delegate brief)

Rule: evidence before claims. Without a fresh, runnable signal that proves
the work is correct, "done" is a guess.

## Before any completion/success claim
1. Identify the command, inspection, or checklist that proves it.
2. Run or perform it fresh.
3. Read the output or result.
4. Re-read the ORIGINAL ask and check each criterion — code-level green is
   not goal-level done. Goal-level includes deliverable shape (right file
   count/format, stale prior-version artifacts removed) and every instance
   of a repeated element — N files/entries/cases need N checks, never a
   spot-check of one. Where a source ground truth exists (git, a file, a
   config key), a computed comparison against it is the non-skippable
   check — a render or spot-read only corroborates, it doesn't substitute.
5. Report the verification as a per-criterion verdict (criterion → pass/fail
   → the evidence line that proves it), not prose "done". Two-pass: score it
   once from your own claims, then again from the artifact; any criterion
   that drops on the second pass is a refuted claim → NOT done.
6. Visual deliverables get a vision check. If the artifact is visual — UI,
   chart, rendered doc, slide, image — render it and verify with vision
   against the goal; a text-only check structurally cannot see layout,
   overlap, or wrong-shape failures. On a vision-less host, don't silently
   skip it — route to a vision-capable lane or report the criterion as
   NOT-RUN with the artifact path.

## Do not claim
- tests pass without a fresh test run
- lint/build is clean without running it
- bug is fixed without reproducing the original symptom or a regression
  test — write the test that FAILS before your change and passes after
- delegated work is correct without inspecting result/diff
- ship/merge-ready without exercising the changed path on the real built
  artifact or service — a mock or simulation does not count
- a visual/rendered output is correct without looking at it
- a security-sensitive change is safe without triaging the diff first

## When fixing a bug
Investigate before editing: reproduce it, read the whole error and stack
trace, change one thing at a time. Don't add a guard for a failure whose
root cause you haven't located — a null-check over an unexplained null just
moves the bug somewhere quieter.

## Fix-class work requires a diagnostic receipt (owner-ratified 2026-07-20)
A "fix" is never dispatched from a guess. Before editing to repair
something, produce a measured diff of actual-vs-ground-truth-at-the-target-state
(a diagnostic receipt) and cite the ground-truth artifact as the repair
target — "restore how it was" is not a repair spec.

**Exemplar (Birds Nest, 2026-07-20):** two same-day repairs (a shear fix,
then a v6-restoration fix) shipped defects because they ran ahead of ground
truth — patched a misdiagnosed door flip through three compounding rounds.
The third fix, sequenced behind a diff table plus a gate-verified CAD
export, was surgical and correct on first dispatch. The wait was cheaper
than the escape.

**Gate pattern (fail-closed, stable reason code):** a change-review contract
declaring `change_class: "fix"` is rejected unless it also carries a
`diagnostic_receipt` object with `path`, `artifact_sha256`, and
`produced_at` all present — reason code `FIX_WITHOUT_DIAGNOSTIC_RECEIPT`.
Missing or incomplete receipt is a lint violation, not a warning; the
contract fails closed. Reference implementation:
`tools/release/contract.py` (`lint_contract`, the `change_class == "fix"`
branch) in the screenery-lean sibling repo.

**How to apply generically:** any repair-shaped task (bug fix, geometry
correction, restore-to-known-good) needs, before the edit: (1) a measured
comparison against the actual ground-truth target state, produced first;
(2) the ground-truth artifact identified by path/hash, not by memory or
narrative ("it used to look like..."). A repair brief lacking either is
malformed — treat it the same as any other missing-spec gap: stop and ask,
don't guess-and-patch.

## Don't stop at the plan, and don't move the line
- Anti-early-stop: if your final paragraph is a plan or a promise ("next
  I'll…"), do that work now — a described step is not a done step. Yield
  only for a genuine blocker: a destructive/irreversible action, a real
  scope change, or input only the user can give.
- Don't weaken the gate to pass. A failing check is failing. Never lower a
  threshold/tolerance or relabel a FAIL→PASS mid-run to ship — that needs
  explicit human approval.

## Learning handoff
Completion is a good moment to decide whether anything durable was learned,
but this skill does **not** auto-launch task-retrospective or write memory.

- If task-retrospective is armed, hand it the verification evidence and any
  corrections before closing the task.
- If the user explicitly asked to remember/log/save a lesson, route the
  candidate through wiki-memory and write-gate.
- If neither is true, do not persist by default.

Write IFF the task produced a durable, project-specific lesson a future
session would want recalled. Do not write plain acknowledgements,
ephemeral/general-knowledge questions, chit-chat, or anything with no new
project-specific fact.
