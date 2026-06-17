# EVAL — `semantic-diff`

## Static cost (measured)

| field | tokens / size |
|---|---|
| description (always resident) | **80 tokens** (348 chars) |
| body (loaded on trigger)      | **427 tokens** (1714 chars) |
| tools/ source (shipped, git)   | ~120 KB |
| runtime install — CLI (default) | **~18 MB** (tree-sitter + 4 grammars; fresh venv, measured 2026-06-17) |
| runtime install — +MCP (opt-in) | ~44 MB (adds mcp → cryptography ~24M) |
| model pin                      | `any` |
| effort pin                     | `low` |

> Earlier revisions listed a "150671 KB tools/ payload" — that was mis-measuring
> a local, git-ignored `.venv` (the old 86M `tree-sitter-languages` bundle + the
> `mcp`/`cryptography` chain), not anything shipped. v1.11 split deps into a slim
> CLI core (per-language grammars) and an optional MCP extra; fresh CLI install
> is ~18M, an 88% cut.

agentskills.io budget reference: description ≤ 1,536 chars (1% of a 200K context window).

## A/B savings (measured, N=? × 0 prompts, model=?)

| metric | without skill | with skill | Δ | 95% CI |
|---|---|---|---|---|
| input tokens (mean)  | — | — | — | n/a |
| output tokens (mean) | — | — | — | n/a |
| latency (ms)         | — | — | n/a | n/a |
| judge score (0–5)    | —   |   |   |   |


Raw: [`eval/results/semantic-diff.json`](../../eval/results/semantic-diff.json)


## Methodology

- Sample size: N=3-10 local smoke; N≥50 on Kaggle T4 for any >20% savings claim.
- Tasks: 3–5 representative prompts in `eval/tasks/semantic-diff.yaml`.
- Backends supported: `ollama`, `anthropic`, `mimo`, `mlx` (`--backend` arg).
- Judge: Xiaomi MiMo via `https://api.xiaomimimo.com/v1` (preferred for quality) or local Ollama.
- Rubric: per-task rubric embedded in the YAML.

## Failure modes

To be filled in after analysis of result outputs (see raw JSON for individual trial outputs).

## Moved from SKILL.md (2026-06-12 SkillReducer-criteria audit)

_Provenance/rationale below is maintainer context, not runtime instruction — relocated so the lazy-loaded body stays actionable._

## Lineage

Inspired by cocoindex-code (AST MCP, claims 70% reduction + 80-90% cache hit). Our scope is narrower (file re-read diff, not full codebase index) and our measurements are repeatable on the published dataset.

## Measured gain (2026-06-13, `eval/gains.py`)

**97.3% fewer tokens** re-reading a 446-line file after a 2-function edit (4,672→127 est tokens), **break-even after R*=2 re-reads** vs naive full re-read — confirms the AST-node-diff savings claim deterministically. tree_sitter-guarded.
