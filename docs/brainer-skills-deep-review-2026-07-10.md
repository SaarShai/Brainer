# Brainer skills deep review — 2026-07-10

## Outcome

The filesystem-derived catalog contains 27 skills. Three independent lanes reviewed all 27 using the `/think` contract: frame the real constraint, separate evidence from inference, seek the smallest falsifying probe, prefer removal/clarification over new machinery, and retain explicit unknowns. The initial dispositions were 20 defect-bearing, four gap-only, and three held.

## Baseline evidence

- `bash scripts/run_all_tests.sh --group all`: 105/105 PASS.
- Four deterministic suites passed directly but were absent from the central runner.
- Strict contract lint failed 19/27 skills, chiefly missing explicit failure-mode, negative-test, or wiring sections; default lint suppressed those warnings.
- The legacy trigger set covered 14/27 skills. Local `gemma4:26b-mlx` scored 13/14; the miss (`wiki-memory` versus required companion `write-gate`) showed the top-1 oracle could mislabel honest composition.
- Security dogfood: 26 PASS and `security-oversight` WARN on its own adversarial fixtures. The catalog's historical 23/24 claim had drifted.
- No `graphify-out/graph.json` was present, so blast-radius checks degraded to labelled lexical analysis.

## Complete 27-skill matrix

| Skill | Disposition | Observed issue or evidence | Intervention / remaining gap |
|---|---|---|---|
| baton | Defect | Advisory reads and slash-only mutation authority contradicted each other. | Clarified read-only inspection versus `/baton`-authorized writes. |
| brainer-audit | Defect | Codex results lost `call_id`; statusless or contradictory verification could satisfy done-claim evidence. | Normalize paired calls/results and require explicit successful verification. |
| cache-lint | Gap | Existing fixtures exercise rule checks, but not a full read-only audit nor current claim drift. | Deferred behavioral/full-audit expansion. |
| caveman-ultra | Held | Compact prose contract and tests agreed; no falsifying defect reproduced. | No change. |
| compliance-canary | Defect | Ledger metadata/conjunct coverage and Bash dependency-manifest mutations had false negatives. | Match ledger identity, count broader action conjuncts, detect redirection and package-manager mutation. |
| context-keeper | Defect | Non-object payloads plus non-string or malformed path/metadata fields could crash PreCompact/SessionEnd workers despite their always-exit-0 contract. | Normalize typed fields, guard path probes, fail open with logs, and test valid fallback/copy/extraction behavior. |
| eval-gate | Defect | Panel refutation could leave final JSON inconsistent with the failing verdict. | Make machine verdict agree with panel result; add negative panel fixture. |
| fable-mode | Held | Layered-task discipline and existing probes agreed. | No change. |
| impact-of-change | Defect | Body-only hunks could be misattributed or disappear as false LOW; graph gaps were understated. | Parse hunk context, emit loud UNKNOWN sentinels, add E7-E10 adversarial cases. |
| index-first | Defect | Opt-in status was not encoded; malformed hook deadlines did not fail open. | Add `auto-install: false`; validate deadline and emit nothing on malformed values. |
| lean-execution | Defect | Bash dependency mutations were absent from the drift surface. | Add Bash probe coverage and mutation/read-only controls. |
| learn-skill | Defect | A missing `Pitfalls` section passed lint; fenced examples could impersonate the heading. | Require a real non-fenced section and add negative fixtures. |
| loop-engineering | Defect | Multi-document YAML, string booleans, and stale accepted iterations produced parsing/monitor false-greens. | Parse only real document separators; normalize booleans; judge the latest stuck suffix. |
| output-filter | Defect | Custom keep rules were dropped by search/log and diff compression paths. | Thread keep patterns through every compression mode and test preserved signals. |
| plan-first-execute | Gap | Static contract is coherent; no controlled behavioral A/B establishes execution uplift. | Deferred model-dependent behavioral evaluation. |
| prompt-triage | Defect | Sensitive extraction could cross vendors; escalation bypassed the veto; noun `plan` overrode review intent. | Make veto absolute, cover plain secret requests, preserve verifier precedence for existing-plan review. |
| propagate | Defect | Indentation-only customization and the required four-flag probe were misclassified or incompletely reported. | Compare indentation and emit all four flags; add controls. |
| requirements-ledger | Defect | Maintenance cross-check could accept mismatched ledger metadata or undercount common multi-action conjuncts. | Bind metadata and broaden conjunct verbs in the canary integration tests. |
| security-oversight | Gap | Historical self-dogfood count was stale and self-fixture WARN was undocumented; broader installed-scanner proof is absent. | Refresh contract/tests and add self-dogfood assertion; scanner-backed evaluation remains deferred. |
| semantic-diff | Defect | Syntax errors, module-only edits, legacy cache shape, or unsupported non-code extensions could yield an empty delta or crash before the documented fallback. | Return loud full-source fallbacks, migrate/validate cache records, and bypass parser/cache loading for exact non-code full reads. |
| task-retrospective | Defect | `R1|R2|R3` pattern matched longer tokens such as `R10`. | Add a word boundary and regression. |
| team-lead | Defect | Negative, non-finite, fractional, boolean, or partially corrupt token telemetry could be priced. | Treat the whole record as unpriced unless every present token field is a nonnegative integer. |
| think | Held | Manual-only `/think` contract and portable contract test agree; behavioral uplift remains a declared unknown. | No review-task change; retain manual trigger boundary. |
| verify-before-completion | Defect | Prefixed or embedded negative text such as failed tests/missing screenshots could be mistaken for positive artifact evidence. | Reject contradictory negative evidence while retaining explicit `no failures` positives. |
| wiki-memory | Defect | Decision templates did not always enter decision gating; `--force` authority was unaudited. | Gate decision kind and record caller-asserted override metadata; human authority remains mechanically unverifiable. |
| wiki-refresh | Gap | Core staleness checks pass, but behavioral A/B is thin and `artifact_guard.py` ownership overlaps wiki-memory. | Defer ownership/deletion decision pending architecture evidence. |
| write-gate | Defect | Examples were not directly executable and scope values were underspecified. | Repair executable examples and enumerate scope; add negative tests. |

Catalog assertion: the table names the exact sorted set returned by `skills/*/SKILL.md` (27/27).

## System findings

1. A green aggregator was incomplete: deterministic suites can exist without central registration. The fix wires the four baseline orphans, surfaced and registered `test_brief_header.py`, and replaces shell-text inference with one marked declarative registry consumed by both the runner and roster audit. Fake, echoed, quoted, heredoc, before-start, and after-end registrations all fail.
2. Top-1 trigger accuracy is not sufficient for stacked skills. The expanded suite has one exact target per live skill plus explicit multi-skill accepted sets; it remains a routing probe, not proof that both companions execute.
3. Many failures were evidence-integrity defects rather than missing prose: statusless verification, stale acceptances, dropped keep rules, and false LOW/positive outcomes. Tests now target those false-greens.
4. Auto-install, manual-trigger, and host-hook semantics are distinct. Catalog prose had conflated them in several places; generated host verification must inspect both symlinks and actual hook wiring.
5. Strict lint exposes useful debt but mechanically adding 19 sections would inflate the prompt surface. It is reported, not mass-fixed.

## Architecture decisions

- Keep `wiki-refresh/artifact_guard.py` until ownership is decided from caller and lifecycle evidence; deletion during this review would be speculative.
- Keep `wiki.py --force` API compatibility. Audit metadata records the caller's assertion, but software cannot prove that a human actually authorized it.
- Do not redesign `cache-lint` or add new dependencies without an observed failure that the current rule engine cannot represent.
- Keep prompts that name both a credential and a concrete credential file local, even when phrased as maintenance. This is an intentional conservative routing false-positive; benign rotation guidance without a concrete source remains delegable.
- Do not invent browser checks: Brainer's user-facing path is installer-generated host files, symlinks, CLI tools, and hooks.

## Prioritized remaining work

1. **Host retargeting (high):** `install.sh --project` fully retargets the known Claude hook subset, but Codex hook JSON, MCP registration, and agent-definition copying still follow each source skill installer's own checkout path. Gemini hook migration is explicitly manual. Keep the warning loud; redesign installers around an explicit target root in a separate compatibility change.
2. **Strict contract debt (medium):** final strict lint passes 10/27 and flags 17/27, improved from the 8/27 baseline. Decide which warnings predict an observed failure before adding prose; promote only falsified invariants into failure-mode/negative-test/wiring sections.
3. **Behavioral evidence (medium):** run controlled model A/Bs for `cache-lint`, `plan-first-execute`, `security-oversight`, and `wiki-refresh`; their deterministic plumbing does not establish task-level uplift.
4. **Graph precision (medium):** build a current graphify index before treating final blast-radius estimates as precise. This review's impact gates are explicitly degraded lexical evidence.
5. **Wiki ownership (low until a caller conflicts):** resolve `wiki-refresh/artifact_guard.py` ownership only after a real lifecycle/caller conflict is observed.

## Final verification

- `bash scripts/run_all_tests.sh --group all` → `112/112 PASS`.
- `bash scripts/run_all_tests.sh --group e3` → `2/2 PASS` against fresh consumer projects.
- `python3 eval/harness_acceptance/run.py --gate` → `16/16 PASS`.
- Live local routing, `gemma4:26b-mlx` → `30/30` across 27 exact targets plus three honest composition cases; the deterministic stub remains plumbing-only.
- Isolated real install/readback → 27/27 resolving symlinks and 27/27 catalog entries for Claude, Codex, and Gemini; four installed Claude hook commands executed with exit 0. Codex consumer hook JSON is not retargeted, and Gemini hooks still require the documented manual migration.
- Strict contract lint → `10/27 PASS`, `17/27` warnings retained as explicit debt rather than filled with boilerplate.
- Skill-audit dogfood → 26 PASS, `security-oversight` WARN on its deliberate fixtures. Final diff triage → REVIEW only, no HIGH/MEDIUM; all nine REVIEW surfaces are defensive hook/test/accounting terminology and received human cold review.
- Impact analysis → graphless/degraded HIGH (191 changed symbols, 4,012 lexically affected callers, inflated by generic `main`/`run` names, plus explicit UNKNOWN attribution sentinels). The broad suite, targeted regressions, E3, and host checks are the compensating evidence; this is not a precise graph claim.
- Browser/click testing → not applicable: no Brainer skill or installer path exposes a browser UI. The actual user-facing interface is CLI installation, generated host files, symlinks, and hook execution, all exercised above.
