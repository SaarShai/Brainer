# EVAL — `task-retrospective`

## Static cost (measured)

| field | tokens / size |
|---|---|
| description (always resident) | **105 tokens** (527 chars; budget ≤1536) |
| body (loaded on trigger) | **2,866 tokens** (12,640 chars) — user-triggered project-learning mode incl. optional cross-check and evidence recorder docs |
| tools/ payload | **30.3 KB** (`task_audit.py` · `test_task_audit.py` · `audit_lessons.py` · `lesson_patterns.json` · `drift_probes.json`) |
| model pin | `any` (none) |
| effort pin | `medium` |

agentskills.io budget reference: description ≤ 1,536 chars (1% of a 200K context window). 527 chars — well under.

This is a heavier body than the prose-only skills because it carries arm/observe/review/persist/close doctrine, write-target rules, report format, the evidence-recorder commands, and the optional cross-check. It loads only on explicit task audit / task-retrospective / `/retro` triggers or after-the-fact reconstruction, so ordinary task ends and unarmed corrections pay only the resident description cost.

## A/B savings

**Not yet measured.** This skill optimizes *learning-loop closure and drift-resistance*, not token
count, so the headline metric is not a token delta. Candidate measurements (to run on Kaggle T4,
N≥50 per the repo's promotion bar):

| metric | without skill | with skill | Δ |
|---|---|---|---|
| useful lessons banked per armed repeatable task that survive to next session | — | — | not yet measured |
| repeated-failure recurrences caught (audit_lessons exit 1) before re-shipping | — | — | not yet measured |
| user "I can't see what I'm judging" corrections per review | — | — | not yet measured |
| false done-claims at task end (paired with verify-before-completion) | — | — | not yet measured |

## Functional checks (deterministic — run in CI)

Verified by the `test-task-retrospective` workflow (15 agents; audit edge-cases 14/14 after the bug fix,
drift-probe 11/11, PROMPTER cross-repo 12/12, 5/5 scenario sims PASS, adversarial skeptic confirmed no
theater):

- `python3 tools/audit_lessons.py` exits **0** on a clean `wiki/log.md` (the seeded `edit-without-read`
  pattern is *holding* — promoted 2026-06-12, no post-promotion recurrence) and **1** with a verbatim
  log snippet if a promoted lesson recurs.
- **strictly-after** is the core correctness property: a pattern hit dated ON or BEFORE its `promoted`
  date is NOT a recurrence (operator `<=` at the floor). Confirmed by boundary fixtures (06-11/06-12 →
  exit 0; 06-13 → exit 1) and independently re-derived by the skeptic.
- **Robustness:** missing log → exit 2; not-an-array / bad-regex / bad-date registry entries → skip with
  stderr, never crash; `--since` only *raises* the floor; suffix-letter dates (`[2026-06-13b]`) parse;
  header-only matches detected.
- **Regression (bug fixed):** a calendar-invalid log header (`## [2026-13-40]`, `## [2026-02-30]`) is
  skipped with an stderr warning — it no longer raises an uncaught `ValueError`/traceback (which exited 1
  and collided with the recurrence exit code). Keep a fixture for this.
- `drift_probes.json` is a top-level JSON array using only a shipped probe kind (`claim_without_evidence`),
  auto-discovered by compliance-canary after `./install.sh`. Drift-probe true-positive fires; false
  positives (claim **with** a wiki.py/write_gate/log.md tool use in the last 5; unrelated prose;
  "harvesting crops") do **not** fire.
- **Cross-repo:** copied into PROMPTER (a different vendored repo, no `wiki/log.md`), `audit_lessons.py`
  is path-portable (`REPO_ROOT = parents[3]`) → clean exit 2 on the absent log, exit 1 on a fixture;
  PROMPTER's own compliance-canary discovers the probe; PROMPTER left git-byte-identical.
- `scripts/lint_skill_md.py skills/task-retrospective/SKILL.md` passes; `tests/test_task_retrospective_doctrine.py` guards the user-triggered boundary; `tools/test_task_audit.py` covers recorder start/note/status/finish, redaction, no-write behavior, malformed state, and after-the-fact reports.
- **Part D cross-vendor verifier (channels smoke-tested — mixed):** `codex`, `claude`, `gemini` CLIs are
  all on PATH. One-shot smoke test (`<cli> "Reply with exactly: READY"`): **`codex exec` → READY (exit 0)**,
  **`gemini -p --approval-mode plan` → READY (exit 0)**, **`claude -p` → 401 Invalid authentication** in
  this sandbox (headless Claude needs `ANTHROPIC_API_KEY` / `apiKeyHelper`; the interactive OAuth/keychain
  is not inherited by the `-p` subprocess). So from the **Claude host** (this session) the cross-vendor
  dispatch to GPT/Gemini is live; the reciprocal **→Claude** channel (used from Codex/Gemini hosts) needs
  host auth wired or it 401s — the Part D fallback ladder (same-vendor subagent → in-context adversarial)
  covers a dead channel. **Cost-gated** — fires only on high-stakes / contested / repeated results, never
  on a clean low-risk task audit. **Not yet measured:** disagreement-reconciliation quality and cross-vendor
  catch-rate vs same-vendor (candidate A/B).
- **Headless block:** emitted as a fenced `json` `{"retrospective": {...}}` object (pinned grammar) so a
  parent orchestrator can tokenize it — the earlier free-text `RETROSPECTIVE: banked=[…]` line was
  unparseable on `:`/`,`/`]` and was replaced.

## Methodology

- Sample size: N=3–10 local smoke; N≥50 on Kaggle T4 for any promotion-grade claim.
- The drift probe and the Measure tool are the falsifiable parts: a recurrence the tool misses, or a
  probe false-positive, is a measurable bug.

## Failure modes

- **Ceremony creep** — activating task audit mode for one-off work or persisting too many lessons. Mitigated by explicit user activation, the ≤3 candidate cap, and the blessed null exit. Not mechanically gated once the user deliberately asks for the mode.
- **Probe false positives** — `harvest-claimed-not-written` fires on phrasing without a real write.
  Kept sober (narrow `claim_pattern`, broad `verify_keywords`); tested clean on "harvesting crops" and
  claims-with-a-write. Tune via compliance-canary's `measure.py` evidence if noisy.
- **Pattern-tag rot (known false-negative)** — a recurring failure whose log entry carries no `pattern:`
  signature (or no registry-matching text) is invisible to the Measure scan, which then reports
  *HOLDING* — a confidence-vs-evidence inversion (asserts the fix held when it just couldn't see the
  recurrence). Instructed in Part C step 6 but **not mechanically gated**; the real fix is a write-time
  `wiki.py lint` check that every banked lesson page carries a `pattern:` tag. **Open follow-up.**

## Known gaps (surfaced by the test workflow's completeness critic — not yet covered)

- **Probe double-fire with verify-before-completion** — both ship `claim_without_evidence` probes; a
  message like "retrospective done, build is green" can match both. Overlap is narrow (this probe
  requires retrospective/harvest/wiki context) and the two correctives describe distinct symptoms, but a
  co-fire test over one transcript is not yet written.
- **Persistence chain** — the write-gate-reject→revise loop and the `wiki.py fetch` read-back are
  instructed but not integration-tested here (the components are tested in their own suites).
- **Scale** — `audit_lessons.py` reads the whole log into memory; not benchmarked against a multi-
  thousand-entry log (expected sub-second; read-only, so no concurrency hazard beyond a torn append,
  which the malformed-header guard now tolerates).
