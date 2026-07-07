# Learning / self-improvement / documentation failures — evidence report for Brainer
2026-07-06 · compiled by Fable 5 from the washington postmortem session (screenery-lean). Every item
was observed live this session with concrete evidence; each names the failure class, the incident,
and the fix pattern applied here (adopt/port these into Brainer skills).

## A. Lesson capture & propagation
1. **No propagation step at banking time.** Lessons bank where they're learned (one skill's notes, one
   memory file); nothing asks "which OTHER skills does this rule govern?" — Saar's socket rule (taught
   ≥2×, "TRACE tabs/notches, never bridge") stayed in the SVG-version skill; his ship-an-exemplar
   directive stayed in a memory file; create-instructions read neither → production defect.
   *Fix:* canon-first (cross-skill rules live in ONE concepts/ doc; skills carry pointers, never
   restate) + mandatory SCOPE classification (this-skill vs cross-skill) at banking time in
   write-gate/closeout; banking a cross-skill lesson into a single skill = gate failure.
2. **User corrections not forced into durable artifacts.** Corrections became chat-turn fixes;
   task-retrospective only runs when explicitly armed. The SAME correction was re-taught across
   sessions. *Fix:* user-correction → rule+gate+exemplar is a closeout REQUIREMENT, not opt-in.
3. **Exemplar directive itself never propagated** (self-referential failure): "give agents a worked
   exemplar image, not just text" existed as memory since June; no geometry skill shipped one.
   *Fix:* geometry skills must ship reference/ images; check it in skill audits.
4. **Knowledge stored outside the repo.** Canonical rules lived in the private Claude memory dir
   ([[wiki-links]] resolving only for one host/user) — invisible to Codex/Gemini/other sessions.
   *Fix:* repo canon for anything an executor needs; memory holds pointers, not sole copies.

## B. Lessons as prose instead of mechanisms
5. **Gate substrate silently dead.** tools/verify/specs.yaml — the machine-readable "ratchet" file all
   skills bank PASS/FAIL lessons into — had been YAML-unparseable for 3 days. Every specs-based gate
   was inert; nothing tested that the gate file loads. *Fix:* gate-liveness self-test (parse specs,
   json-load probes, resolve referenced tool paths) run in CI/install.
6. **Recurring bugs stored as runbook gotchas, not regression tests.** dedup ReferenceError hit twice,
   render /tmp collision, arguments-shadowing — all documented in prose, all recurred. *Fix:* a lesson
   expressible as PASS/FAIL must land as an executable test; mutation-test the guard (prove it trips).
7. **Heuristic fixes instead of invariants.** Each incident patched with a design-specific heuristic
   (JW "narrow strip = cutter") that misfired on the next design (washington's socket column). *Fix:*
   lesson template must ask "what is the design-independent invariant?" (here: outline fragments abut —
   max join jump ≤2mm, refuse otherwise; body must match source bbox+area).
8. **Rules buried off the read path.** require_trace at line 388/482 of a skill; shared-Illustrator
   concurrency rule with zero backlinks; escalate-up flag documented only in code comments. Routers
   (task-preflight) didn't emit them. *Fix:* rules live where the DECISION happens (router output,
   tool --help, gate), verified by a read-path audit.

## C. Verification & self-assessment
9. **Self-judging / co-authored rubrics.** The cold judge that passed washington v16 "DONE" used a
   rubric authored in the same session as the work — independence of context without independence of
   criteria. *Fix:* judge derives criteria from the FULL spec + canon gates, never from the executor's
   claims; completeness gates (expected-vs-present) mandatory.
10. **Verification by sampling, no ground-truth invariant.** Executor LOOK table, leader spot-review,
    and judge all passed a mis-assembled part; small crops hid it; no layer computed built-vs-source.
    *Fix:* computed comparison against source ground truth is the non-skippable gate; renders corroborate.
11. **A gate that has never tripped is unproven.** The first body-gate implementation passed the
    known-bad part (circular area reference). *Fix:* negative/mutation test required for every new gate.
12. **Done-claim pressure.** 23 Stop-hook firings in one session (11 closeouts with no verdict).
    Detection existed; prevention (executor contract: READY FOR JUDGING, never "done") must be in
    every delegated brief because hooks don't fire inside subagents.

## D. Self-improvement process itself
13. **Improvement work shipped unverified.** The "self-improving" session left 71 uncommitted files:
    a half-finished host removal (live misclassification bug), dead env-var plumbing copy-pasted 6×,
    the unparseable specs.yaml. Same failure one level up: declared improved without evidence.
    *Fix:* improvement lanes get the same verifier/judge treatment as production work.
14. **Improvements never met a falsifying test.** Days of skill/doc editing, zero runs against a hard
    real case until washington v14 broke everything at once. *Fix:* every improvement round ends with
    a live gauntlet on a real file (the live-executor battery pattern).
15. **Meta-layer over-investment.** Canaries/ledgers/traces grew while object-level tools stayed
    fragile and untested across designs. *Fix:* tool regression coverage is a first-class improvement
    target; "add a rule" is not the default remedy — "fix or delete" is.
16. **EVAL bookkeeping drift.** Token counts contradicting the change's stated purpose; stale
    sub-figures; 14 EVAL.md files pointing at a deleted eval/ tree. *Fix:* measurements re-derived at
    edit time; link-liveness lint over knowledge docs.

## E. Traceability & collaboration substrate
17. **Untraced artifacts.** washington v18 saved with zero ledger/baton/verdict/log trace; log.md
    missing days of closeouts. *Fix:* require_trace gate (exists now) + closeout enforcement.
18. **Destructive ops on shared working trees.** `git add -A` swept another agent's WIP (earlier);
    `git checkout --` on a shared dirty file wiped ~700 lines of sibling-lane fixes (today). *Fix:*
    stand-down protocol = remove ONLY your own hunks; tests-as-spec in the same lane as the feature
    (that's what made recovery possible); checkpoint-commit multi-lane work early.
19. **Index/registry rot.** Skill index counts, dangling links, 10 runbooks pointing at moved code
    paths — no liveness lint on the knowledge base. *Fix:* dangling-reference sweep as a standing
    audit (it found ~40 rot items in one pass here).
20. **Duplicate agent spawn storms.** The same audit brief executed 5× in parallel (harness retries),
    burning ~5× tokens for one answer. *Fix (harness-level):* dedupe by brief hash / spawn idempotency.
