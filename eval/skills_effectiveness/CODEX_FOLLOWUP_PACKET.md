# Codex follow-up packet — post-DEMOTE work (4 lanes, all offline/free)

Prepared 2026-07-18, after the long-horizon probe verdict (commit `0a5c927`:
**DEMOTE to shadow**, rule `no_improvement_n2_zero_better`). Reader: a
`codex exec` agent (recommended `gpt-5.6-sol`, effort `xhigh`) in
`/Users/za/Documents/Brainer`, acting as orchestrator. Same discipline as the
previous packet (`CODEX_HANDOFF_PACKET.md`): verify every fact fresh; this
document decays.

**Lane split (2026-07-18): lanes 2 and 4 are reassigned to a separate,
possibly concurrent Kimi-K3 run (`CODEX_KIMI_PACKET.md`). You own lanes 1
and 3 only. Do not edit `longhorizon_score_counted.py`,
`test_longhorizon_score_counted.py`, or run the suite-health/cache-lint
sweeps — and expect those files to change under you; `git pull --ff-only`
before each commit. Lane 3 still sequences after lanes 1 AND 2 (check
that lane 2's commit has landed on `main` before regenerating the
bundle; if it hasn't, finish lane 1 and report rather than waiting
indefinitely).**

**None of these lanes involves paid counted sessions.** All four are
offline/deterministic (lane 1 may use cheap grading only if its own eval
requires it — check before spending). The frozen experiment is scored and
closed; the freeze lock no longer blocks commits, but keep commits
per-lane and surgical.

## 0. Context you must load first

1. `eval/results/skills-effectiveness/longhorizon-main/verdict-report.json` —
   the DEMOTE verdict and per-scenario table.
2. `eval/results/skills-effectiveness/longhorizon-main/mechanism-M-*.json` —
   unblinded mechanism metrics; the FRONTIER sessions (check
   `scenario-end-snapshot-M-*.json` / manifests for arm mapping) recorded
   **3 and 4 false interruptions** respectively. These 7 events are lane 1's
   raw material.
3. `eval/skills_effectiveness/longhorizon_preregistration_draft.md` — §
   decision rules; DEMOTE means FRONTIER runs in shadow until a fix is
   validated and a new authorized run passes.
4. `skills/compliance-canary/SKILL.md` + `REFERENCE.md` +
   `tools/hook.py` / `drift_probes.json` — the probe machinery under repair.

Verify baseline before anything:

```bash
cd /Users/za/Documents/Brainer
git rev-parse HEAD          # expect 0a5c927 or later on main
git status --porcelain      # expect empty; if not, STOP and report
```

## Lane 1 — FRONTIER false-interruption fix + re-gate (highest value)

Goal: find why FRONTIER fired 3–4 wrong interruptions per 44-turn session
while catching nothing OFF missed, fix the trigger conditions, and prove the
fix with the existing deterministic gates — precision recovered, recall not
lost.

1. **Extract the 7 false-fire events.** They live in the raw session
   transcripts under
   `eval/results/skills-effectiveness/longhorizon-main/scenario-0{2,6}-frontier/`
   (per-turn `turn-NN.jsonl`) and are counted in `mechanism-M-*.json`
   (see the extractor `longhorizon_extract_mechanism.py` for how an
   "interruption" is identified — replicate its logic to locate the exact
   turns/probe texts). For each: which probe fired, what drift signal it
   claimed, why it was wrong (quote the turn evidence).
2. **Classify failure modes.** Expect patterns like: probe firing on
   documentation/quoted text rather than actual agent claims; firing on
   already-verified claims; firing repeatedly on the same stale signal.
3. **Fix narrowly** in `skills/compliance-canary/` (likely
   `tools/hook.py` / `drift_probes.json` / probe prompts). Smallest change
   per failure mode. Do NOT weaken recall to buy precision blindly.
4. **Re-run the deterministic trigger gate** — the frozen E1-style corpus
   machinery lives at `eval/skills_effectiveness/trigger_gate.py` /
   `run_trigger_cases.py` / `cases.py` and `eval/behavior/e1_probe_pr.py`
   (verify which is current before running; the 2026-07-16 FINDINGS entry
   records the frozen corpus SHA
   `a6ad89582077faf83722be5ec2e9c9e1323ae058bb9db5116c57e89ee860c276` and
   the bar: frontier 50/50 TP, 0 FP on 400 hard negatives). The fixed
   profile must still pass that gate AND demonstrably not fire on the 7
   extracted false-fire contexts (add them as new hard negatives to the
   corpus — that changes the corpus hash; record the new hash in
   `eval/FINDINGS.md`).
5. Also run `skills/compliance-canary/tools/test.sh` and the
   `test_profiles.py` / `test_hook_safety.py` suites.
6. Deliverable: one commit — fix + new hard negatives + gate results +
   FINDINGS entry. Note plainly that this does NOT un-DEMOTE anything; a new
   owner-authorized counted run is required for that.

## Lane 2 — scoring wiring for scenarios 01/03/04/05

Goal: make `longhorizon_score_counted.py` able to score all six scenarios, so
a future authorized full run is possible.

1. For each scenario `eval/skills_effectiveness/scenarios/scenario-0{1,3,4,5}.md`,
   transcribe its answer-key table (search `S0N-R0`) into a
   `snapshot_scenario_0N` builder + `SESSION_CONFIGS` entry, mirroring the
   existing scenario-02/06 pattern exactly (post-`0a5c927` version — it
   includes mandatory archive verification; new entries must follow it).
   Predicates come from the answer key, never invented. Beware the lesson
   from scenario-02 R06: a requirement satisfied in CLI-flag syntax must not
   be failed by a literal-JSON grep — write predicates against semantics the
   scenario key actually demands.
2. Synthetic-fixture tests per scenario in
   `test_longhorizon_score_counted.py`, same style as the existing ones
   (pass + targeted-failure cases per predicate).
3. Run the full suite from inside `eval/skills_effectiveness/` (module
   imports require that cwd; running from repo root fails on
   `ab_harness` — known, not your bug).
4. Deliverable: one commit. No sessions run — wiring only.

## Lane 3 — freeze-bundle regeneration

The driver fix (`_archive_final_artifacts`, commit `286cd98`/`8e6e28d`)
changed `longhorizon_run_session.py`, so the frozen `run_driver` hash in
`eval/results/skills-effectiveness/longhorizon-freeze-bundle.json` no longer
matches the current file. Any future counted run needs a fresh bundle.

1. Find how the bundle was generated (search for the script that wrote it;
   check `longhorizon_preregistration_draft.md` and git history around
   `f1479f4`). Regenerate against current `main` HEAD, but write it to a NEW
   file (e.g. `longhorizon-freeze-bundle-v2.json`) — never overwrite the v1
   bundle; it is the audit record of the scored probe.
2. If lanes 1–2 land first, regenerate AFTER them so the v2 bundle captures
   the fixed canary + full scoring wiring. Sequence lane 3 last.
3. Deliverable: one commit — v2 bundle + a FINDINGS note that v2 is
   pre-authorization only (a new counted run still needs its own rehearsal
   gate + owner sign-off).

## Lane 4 — repo hygiene sweeps (lowest priority, fully independent)

1. `suite-health`: reconcile every `skills/*/SKILL.md` against its `tools/`
   behavior; report mismatches; fix only doc-side drift, flag code-side
   drift for the owner.
2. `cache-lint`: run the cache-hygiene audit
   (`skills/cache-lint/` — see its SKILL.md for invocation) over the repo;
   report pass/warn/fail; fix only mechanical warns.
3. Deliverable: one commit per sweep, or a report with zero commits if
   nothing is safely fixable.

## Hard constraints

- **No paid counted long-horizon sessions. None.** Nothing in this packet
  authorizes one. If a lane seems to require it, stop and report instead.
- **Never touch** `eval/results/skills-effectiveness/longhorizon-main/`
  scored artifacts, `artifact-archives/`, the v1 freeze bundle, or the
  rehearsal results — they are audit records.
- **Never re-run** the two SPENT rehearsal sessions.
- One surgical commit per lane; no opportunistic edits outside a lane's
  scope. If lanes conflict, sequence 1 → 2 → 3 (4 anywhere).
- Grader/eval spend: glm-5.2 only, and only if a lane's own frozen eval
  demands it — the deterministic gates in lane 1 are offline; prefer them.
- Kimi K3 (not K2.7) via `pi_agents` if you delegate; cheap GPT tiers for
  mechanical transcription in lane 2.
- Trust what you observe over this document; flag discrepancies to the human.
