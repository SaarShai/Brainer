# Kimi-K3 packet — post-DEMOTE lanes 2 & 4 (mechanical/structured work)

Prepared 2026-07-18. Reader: a `codex exec` agent powered by **Kimi K3**
(not K2.7 — if you are not K3, stop and report), running in
`/Users/za/Documents/Brainer`. You own **lanes 2 and 4 only** of the
post-DEMOTE follow-up plan. Lanes 1 and 3 belong to a separate
gpt-5.6-sol run via `CODEX_FOLLOWUP_PACKET.md` — do not touch their scope
(`skills/compliance-canary/`, the freeze bundle, trigger-gate corpus). The
two runs may execute concurrently; strict file separation is what keeps
that safe.

Verify every fact fresh; this document decays.

## 0. Baseline checks (run before anything)

```bash
cd /Users/za/Documents/Brainer
git rev-parse HEAD          # expect f0eb7b7 or later on main
git status --porcelain      # if it shows changes in YOUR lanes' files, STOP and report
git pull --ff-only          # pick up anything the sol run already landed
```

Context to read first:
- `eval/results/skills-effectiveness/longhorizon-main/verdict-report.json`
  — the probe verdict (DEMOTE); background only, you don't act on it.
- `eval/skills_effectiveness/longhorizon_score_counted.py` (current `main`
  version — includes mandatory sha256 archive verification) — the pattern
  you extend in lane 2.
- `eval/skills_effectiveness/scenarios/README.md` (if present) and the six
  `scenario-0N.md` scripts.

## Lane 2 — scoring wiring for scenarios 01, 03, 04, 05

Goal: extend `longhorizon_score_counted.py` so all six scenarios are
scoreable. Pure code + tests; no sessions run, no grading, no network.

Per scenario (`eval/skills_effectiveness/scenarios/scenario-0{1,3,4,5}.md`):

1. Find the answer-key table (search `S0N-R0`). Transcribe every
   requirement into a `snapshot_scenario_0N(root: Path) -> dict` builder
   mirroring `snapshot_scenario_02` / `snapshot_scenario_06` exactly —
   same return shape, same predicate style, registered in
   `SNAPSHOT_BUILDERS` and `SESSION_CONFIGS`.
2. **Predicates encode semantics, not literal strings.** Hard lesson from
   scenario-02 R06: a requirement satisfied in CLI-flag syntax
   (`--queue new --queue recovery`) was falsely failed by a grep for the
   literal JSON list. For each predicate, ask: what evidence does the
   answer key actually demand, and what surface forms could legitimately
   express it? Prefer parsing the artifact (JSON load, structured field
   check) over substring matching wherever the artifact is structured.
3. Tests in `test_longhorizon_score_counted.py`: per scenario, one
   synthetic fixture that passes all predicates, plus one targeted-failure
   fixture per requirement (flip exactly that requirement, assert exactly
   that predicate fails). Follow the existing scenario-02/06 test style.
4. Run the suite from inside the directory (repo-root invocation fails on
   `ab_harness` imports — known, not yours to fix):
   ```bash
   cd eval/skills_effectiveness && python3 -m pytest test_longhorizon_score_counted.py -q
   ```
   Then the full local suite: `python3 -m pytest . -q` (same cwd) — must be
   green before you claim the lane done.
5. Deliverable: ONE commit touching only
   `longhorizon_score_counted.py` + `test_longhorizon_score_counted.py`
   (+ a short `eval/FINDINGS.md` note that scoring now covers 6/6
   scenarios, wiring only, no sessions run). Push after commit.

## Lane 4 — repo hygiene sweeps

Independent of lane 2; do after it (or interleave if blocked).

1. **suite-health**: for every `skills/<name>/SKILL.md`, reconcile the
   prose (triggers, tool names, flags, file paths) against the actual
   contents of `skills/<name>/tools/`. Fix ONLY doc-side drift (stale
   path, renamed flag, removed tool still documented). Anything where the
   CODE looks wrong relative to the doc: do not edit code — list it in
   your final report for the human. Skip `skills/compliance-canary/`
   entirely (sol's lane 1 is editing it concurrently).
2. **cache-lint**: read `skills/cache-lint/SKILL.md` for the invocation,
   run its audit over this repo, capture the typed report. Fix only
   mechanical WARN-level items that don't touch hooks' logic; report the
   rest.
3. Deliverable: ONE commit per sweep (or zero commits + a report if
   nothing is safely fixable). Doc-only diffs must stay doc-only.

## Hard constraints

- **Scope wall**: never edit `skills/compliance-canary/**`, any
  `eval/results/**` file, `longhorizon-freeze-bundle*.json`,
  `longhorizon_run_session*.py`, or the trigger-gate corpus/files
  (`trigger_gate.py`, `cases.py`, `run_trigger_cases.py`,
  `eval/behavior/e1_probe_pr.py`). Those belong to the sol run or are
  audit records.
- **No paid runs of any kind** — no counted sessions, no grader calls, no
  network APIs. Everything here is deterministic/offline.
- **No state-changing git beyond your own commits**: no checkout/reset/
  restore/clean on paths you didn't author this run. Pull ff-only before
  each commit; if a pull conflicts with your work, stop and report.
- One surgical commit per deliverable; nothing opportunistic. Match local
  code style; don't reformat untouched code.
- Every "done" claim needs fresh evidence in your final message: the
  pytest tail, the diff stat, the commit hash.
- Trust what you observe over this document; report discrepancies instead
  of improvising around them.

## Final report format

End with: lane status table (done/blocked + evidence), commit hashes,
list of code-side drift items flagged for the human, anything skipped and
why.
