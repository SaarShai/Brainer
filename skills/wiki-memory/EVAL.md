# EVAL — `wiki-memory`

## Static cost (measured)

| field | tokens / size |
|---|---|
| description (always resident) | **90 tokens** (378 chars) |
| body (loaded on trigger)      | **3004 tokens** (11819 chars) |
| tools/ payload                 | 359.1 KB |
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

To be filled in after analysis of result outputs (see raw JSON for individual trial outputs).
