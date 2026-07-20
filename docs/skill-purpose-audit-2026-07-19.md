# Per-skill purpose audit — 2026-07-19 (post-contraction, 24 skills)

Method: purpose from SKILL.md; fulfillment from measured evidence
(`eval/FINDINGS.md`), test suites (`scripts/run_all_tests.sh` 105/105 at
`43738eb`, canary `test.sh` 188/188), and prior reviews
(`docs/brainer-skills-deep-review-2026-07-10.md`,
`docs/adversarial-review-harmful-skills-audits-2026-07-17.md`,
`docs/SKILLS_EFFECTIVENESS_VERIFICATION.md`). Interplay from the cross-skill
reference map. Simplification verdicts feed the phase-2 backlog at the end.
Kimi K3 ran an independent adversarial pass over the same catalog; divergences
noted inline where they occurred.

Verdict key — **fulfills**: mechanism exists, is wired, and has evidence ·
**partial**: mechanism exists but task-level effect unproven · **prose-only**:
claims without mechanism.

| Skill | Purpose (one line) | Fulfills? | Works with others | Simplify? |
|---|---|---|---|---|
| baton | manual session-handoff file for no-hook hosts/windows | fulfills (protocol + prompt_intent probe; no EVAL — operational utility) | complements context-keeper (auto) — covers the hookless gap; no overlap conflict | leave — 2 files, small |
| brainer | `/brainer` selects the smallest relevant optional-skill set | fulfills (REFERENCE.md + test_reference.py 11/11) | meta-layer over the catalog; selection recently separated from routing (49b91c3) | keep now; phase-2: value shrinks as the optional set shrinks — fold into the catalog when the experimental set stabilizes |
| brainer-audit | report-only offline audit of Brainer skill use (L3 telemetry) | fulfills (detectors + tests; opt-in hooks) | consumes events all skills produce; distinct from canary (offline vs live) | leave — it is the measurement moat; keep report-only |
| cache-lint | static prompt-cache hygiene audit | fulfills (Exp10: detection F1 1.0, 18-case corpus) | standalone L1 analyzer | leave |
| caveman-ultra | terse-output style (user-elected) | fulfills (−87.7% output combo measurement; in live daily use) | canary forbidden_regex/word-count probes enforce its drift | leave — 38 lines, already minimal |
| compliance-canary | single always-on drift watcher + unconditional intent capture (no-drop) | fulfills (188/188 tests; frontier gate TP50/FP0/FN0; one proven live catch) | hub: hosts every skill's probes; notification evidence boundary; feeds wrap-up ledger | phase-2: SKILL.md deep trim (462 lines; move war-stories to REFERENCE.md) + retire `legacy` profile once rollback confidence is established |
| context-keeper | PreCompact extraction + SessionEnd raw archive | fulfills (97.7% compression, 100% URL recall) | L0 layer with wiki/baton; no overlap | leave |
| eval-gate | LLM-as-judge rubric gate for untestable "good enough" | partial (79% judge–human agreement; N≥50 validation pending) | judgment complement to verify-before-completion (deterministic) and loop-engineering (loop verifier design) | trim SKILL.md prose (236 lines) in phase-2; complete N≥50 validation before further promotion |
| impact-of-change | pre-commit blast-radius map | partial (mechanism + fallback tested; task-level A/B unproven) | feeds verify-before-completion WHAT to verify; sibling of security-oversight | leave (opt-in, cheap); do not grow until A/B evidence |
| index-first | prefer pre-built indexes over grep/read chains | fulfills (−93% retrieval at parity evidence) | graphify + wiki integration | leave |
| learn-skill | `/learn` — capture a finished workflow as a reusable skill | fulfills mechanically (tools + tests; hooks opt-in); adoption-level effect unproven | ships the workflow_nomination wrap-up probe; routes through write-gate/wiki | phase-2 consolidation candidate with task-retrospective (both are learning lanes; LEARNING_CONTRACT is the shared canon) |
| loop-engineering | loop design doctrine + deterministic loop_lint | tools fulfill (loop_lint FAIL-severity verified in suite H2c); doctrine unproven | eval-gate designs the judge; briefs carry the doctrine | phase-2 per migration map: doctrine → task-local brief; keep loop_lint/monitor as L1 tools |
| output-filter | strip ANSI/progress/dup noise, preserve errors | fulfills (−88.8% bytes, errors preserved) | standalone L1 | leave |
| prompt-triage | pre-model routing classifier + escalation modes | partial (historical N=13 100%; current native host path unmeasured) | escalate-up modes referenced by agent roster; overlaps host-native routing | keep opt-in; phase-2: cede routing to host per migration map, keep only measured deterministic savings |
| propagate | classify-then-apply sibling sync + reverse harvest | fulfills (sibling_sync_audit.py; exercised across 5 siblings 2026-07-18) | carries agent-defs; harvest feeds learning lanes | trim harvest-lane prose phase-2; NOTE: retired skills linger in siblings as "sibling-only" — next propagation pass per sibling should remove them deliberately |
| security-oversight | introduced-risk triage of diffs + untrusted-skill pre-install audit | partial (dogfood 26 PASS; task-level A/B unproven) | routes HIGH/MEDIUM to verify-before-completion; sibling of impact-of-change | trim prose (242 lines) phase-2; keep report-only |
| semantic-diff | AST-node diff for re-reads | fulfills (95.5% measured savings) | standalone L1 | leave |
| task-retrospective | `/retro` — after-task audit that banks lessons | fulfills mechanically (task_audit.py + tests); usage-level effect unproven | overlaps learn-skill at the "bank the lesson" step; canary correction items point here | phase-2: merge with learn-skill into one learning lane (longest surviving prose at 333 lines) |
| team-lead | explicit orchestration protocol + builder/verifier briefs | fulfills (brief tooling + routing hardening 2b9115e..71d95ad; H6b/H7 pass) | ORCHESTRATION.md §6 is canonical; prompt-triage roster; canary delegated_diagnosis probe | keep until routing telemetry stabilizes; phase-2 per migration map: reduce body to role briefs |
| think | thinking guidelines, slash-only, weak-model tiers | fulfills its scoped role (in live use; think_contract.py) | referenced by borrow-first directive | leave — scope already narrowed to weak-model tiers |
| verify-before-completion | FULL manual verification workflow (canary compact probe is the default) | fulfills (−33.5% output evidence-first; compact probe default-on) | canary emits the probe; eval-gate covers judgment claims; impact-of-change picks targets | leave — the split the adversarial review asked for already exists (compact default vs manual FULL) |
| wiki-memory | durable curated memory with progressive retrieval | fulfills (100% evidence rate on project-history questions) | trio with write-gate (input gate) + wiki-refresh (reconcile); graphify split | phase-2: merge trio into one provenance-graded subsystem (blocked on sibling CUSTOMIZED blast radius) |
| wiki-refresh | reconcile wiki pages against current code | fulfills (audit-refs tooling; typed contradicts edges) | trio member | phase-2 trio merge |
| write-gate | quality gate before persistent writes | fulfills (H2b behavioral check: low-signal write REFUSED live) | trio member; canary correction-ledger bank path | phase-2 trio merge |

## Phase-2 backlog (ranked by benefit/risk)

1. **Wiki trio merge** (wiki-memory + write-gate + wiki-refresh → one subsystem)
   — 3 catalog lines → 1, one SKILL.md instead of 427 lines across three;
   blocked on sibling CUSTOMIZED handling; needs its own propagation lane.
2. **Learning-lane merge** (learn-skill + task-retrospective → one lane over
   LEARNING_CONTRACT) — 581 lines of overlapping workflow prose today.
3. **compliance-canary SKILL.md deep trim** + `legacy` profile retirement.
4. **team-lead → role briefs**, after routing telemetry stabilizes.
5. **prompt-triage cede-to-host**, keep measured deterministic savings only.
6. **Prose trims**: task-retrospective 333, security-oversight 242, eval-gate
   236, propagate 212 lines.
7. **Sibling cleanup**: next `/propagate` pass per sibling should deliberately
   remove the 7 retired skill dirs (classifier treats them as sibling-only and
   will not touch them otherwise).
