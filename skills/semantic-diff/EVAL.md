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
- Tasks: `eval/tasks/semantic-diff.yaml` — **source artifact removed, date unrecorded;
  the A/B table above is honestly blank (N=? × 0 prompts) because this task file
  never existed in git history to run it from.** The real, current measurements for
  this skill are the `eval/results/semantic-diff.json` numbers below (produced by
  `runner_semdiff.py`, not the generic `eval/runner.py` + task-YAML harness) and the
  "Measured gain" section at the bottom — both live and reproducible.
- Backends supported: `ollama`, `anthropic`, `mimo`, `mlx` (`--backend` arg) — applies
  to the generic harness only, not `runner_semdiff.py`.
- Judge: Xiaomi MiMo via `https://api.xiaomimimo.com/v1` (preferred for quality) or local Ollama.
- Rubric: per-task rubric embedded in the YAML (n/a — see task-file note above).

## Failure modes

Premortem ([`LEARNING_CONTRACT`](../_shared/LEARNING_CONTRACT.md) §8):

- **Silent-failure path** — the per-session AST snapshot lives in memory/session
  state; if the snapshot is ever lost or invalidated (session restart, snapshot
  corruption) without semantic-diff detecting the mismatch, a "re-read" silently
  falls back to treating the file as first-seen, and the caller gets a full read
  with no signal that the diff-mode savings didn't apply this time.
- **Rot-when-unwatched** — tree-sitter grammars are pinned per supported language
  (Python, JavaScript, TypeScript, Rust); a language server/grammar update upstream
  that changes node shapes could desync the AST-node diff from what the file
  actually contains, and nothing here re-validates the grammars against new
  tree-sitter releases on a cadence.
- **No-hooks host** — semantic-diff is a Bash CLI that works on every host by
  design, but nothing forces a caller to invoke it before a re-read; on any host, an
  agent that just uses the plain `Read` tool out of habit gets the full-file cost
  every time, with no interception mechanism recovering the AST-diff savings.

## Moved from SKILL.md (2026-06-12 SkillReducer-criteria audit)

_Provenance/rationale below is maintainer context, not runtime instruction — relocated so the lazy-loaded body stays actionable._

## Lineage

Inspired by cocoindex-code (AST MCP, claims 70% reduction + 80-90% cache hit). Our scope is narrower (file re-read diff, not full codebase index) and our measurements are repeatable on the published dataset.

## Measured gain (2026-06-13, `eval/gains.py`)

**97.3% fewer tokens** re-reading a 446-line file after a 2-function edit (4,672→127 est tokens), **break-even after R*=2 re-reads** vs naive full re-read — confirms the AST-node-diff savings claim deterministically. tree_sitter-guarded.
