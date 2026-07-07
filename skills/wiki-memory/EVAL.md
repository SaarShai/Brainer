# EVAL — `wiki-memory`

## Static cost (measured)

| field | tokens / size |
|---|---|
| description (always resident) | **90 tokens** (378 chars) |
| body (loaded on trigger)      | **3623 tokens** (14388 chars) — re-measured 2026-07-06 after the core+deep-dive split (REFERENCE.md carries compile-ingest, loop-mode, consolidate/decay, schema-evolution, aging/reconcile, graphify boundary, and OKF interop; loaded only when consulted, not on every trigger) |
| tools/ payload                 | 400.7 KB |
| model pin                      | `any` |
| effort pin                     | `low` |

agentskills.io budget reference: description ≤ 1,536 chars (1% of a 200K context window).

## Measured (retrieval + gated write)

wiki-memory is a retrieval + gated-memory skill, not a router — the block previously here was a
mis-pasted prompt-triage routing template (it described classification/tier-routing this skill
never does). Its real results live in the experiment suite:

- **Retrieval** — `eval/exp2_retrieval`, `eval/exp6_retrieval_scale`: progressive search → timeline → fetch; evidence-rate on project-history questions.
- **Poison defense / gated write** — `eval/exp5_adversarial` + `tools/provenance.py` trust tiers: write-gate scores signal, not truth (8/8 adversarial lessons passed at mean 4.88), so trust-gated `resolve` recovers the truth+poison case (dependent accuracy 0.5 → 1.0).
- **Consolidate / decay** — `tools/test_consolidate.py`, `tools/test_decay.py`: reuse-driven promotion + time-based aging (deterministic unit suites in `scripts/run_all_tests.sh`).

See [`eval/FINDINGS.md`](../../eval/FINDINGS.md) for consolidated numbers. `eval/results/wiki-memory.json` holds the cold-vs-retrieved token A/B from `eval/runner_wiki.py` (its summary `delta_*_pct`, mirrored in `eval/FINDINGS.md`); the broader value is retrieval quality + memory hygiene, measured by the suites above.


## Methodology

- Sample size: N=3-10 local smoke; N≥50 on Kaggle T4 for any >20% savings claim.
- Tasks: 3–5 representative prompts in `eval/tasks/wiki-memory.yaml`.
- Backends supported: `ollama`, `anthropic`, `mimo`, `mlx` (`--backend` arg).
- Judge: Xiaomi MiMo via `https://api.xiaomimimo.com/v1` (preferred for quality) or local Ollama.
- Rubric: per-task rubric embedded in the YAML.

## Failure modes

Premortem ([`LEARNING_CONTRACT`](../_shared/LEARNING_CONTRACT.md) §8):

- **Silent-failure path** — `new_page()` calls `gate_candidate()` in-code (write-gate is
  structurally wired, not conventional), but the *retrieval* half has no such gate: an agent
  that skips `search`/`timeline`/`fetch` and answers from conversation memory instead
  produces a plausible-looking answer with no visible error — there is nothing that detects
  "the wiki was never consulted" the way write-gate detects "the candidate was never scored."
- **Rot-when-unwatched** — pages accumulate without re-validation against the codebase they
  describe; a fact that was true when written (a file path, a config default, a decision that
  got reversed) silently goes stale and is served at full confidence by `fetch` — the wiki has
  no self-decay for factual accuracy, only reuse-driven promotion/aging (`test_consolidate.py`,
  `test_decay.py`) which tracks *staleness of attention*, not *staleness of truth*.
  `wiki-refresh`'s reconcile cycle (Keep/Update/Consolidate/Replace/Delete) is the owning
  mechanism, and it only runs when invoked.
- **No-hooks host** — wiki-memory is a plain CLI (`wiki.py`), so retrieval and gated writes
  work identically on Codex/Gemini per `docs/HOST_CAPABILITY_MATRIX.md` ("tools are plain
  python3/bash"); the actual host-shaped gap is the **loop-mode memory contract** (recall
  before each pass / write after each pass), which depends on a harness that inlines skill
  directives into subagent briefs — on a host or subagent context that skips that inlining,
  the recall/write rhythm silently doesn't happen, and no probe fires to say so.
