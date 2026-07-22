# Brainer Skills

Lean skills for AI coding agents (Claude Code · Codex · Gemini) across four pillars: **(1)** token-use optimization, **(2)** context-window optimization & management, **(3)** LLM wiki-memory framework, **(4)** self-improvement & learning.

This replaces the old `start.md` boot doc. Each skill is a self-contained folder under `skills/<name>/`. Skill descriptions are the only thing always resident in the agent's context; full bodies load on trigger. The adopted design standard for the suite is [`docs/TARGET_ARCHITECTURE.md`](../docs/TARGET_ARCHITECTURE.md).

For measured per-skill deltas and the live A/B table see [`eval/FINDINGS.md`](../eval/FINDINGS.md). Sixteen skills ship an `EVAL.md`; `baton` and `propagate` currently do not.

## Catalog

| Skill | One-line |
|---|---|
| [caveman-ultra](caveman-ultra/SKILL.md) | **Experimental/manual.** FULL terse-output style retained without SessionStart injection. |
| [think](think/SKILL.md) | **Experimental/manual.** FULL thinking protocol retained for explicit `/think` evaluation arms. |
| [prompt-triage](prompt-triage/SKILL.md) | **Experimental/opt-in.** Pre-model classifier retained for paired evaluation; root reinstall removes its old per-prompt hook. |
| [wiki-memory](wiki-memory/SKILL.md) | Repo-local markdown wiki: progressive retrieval + gated writes. |
| [context-keeper](context-keeper/SKILL.md) | PreCompact hook: structured memory before compaction. |
| [index-first](index-first/SKILL.md) | Prefer pre-built indexes / composite verbs over grep+read chains; batch N related lookups into one capped call. |
| [compliance-canary](compliance-canary/SKILL.md) | UserPromptSubmit hook: the **single always-on drift watcher**. Three mechanisms in one process — symptomatic per-skill probes, a request ledger, and an armed-only correction ledger (`legacy`/`shadow`'s periodic re-anchor was retired 2026-07-19, not rehomed). Closeout ledgers remain visible until completed or user-closed. Absorbed `skill-pulse` (v1.10). Ships an offline `measure.py`. **Default-on since v1.7** (the cross-model longrun measured the original probe/re-anchor pair: +0.44 / +0.27, 2 model families — historical, pre-retirement). Its own `claim-without-evidence` / `completion-without-closure` probes are the canary-owned, canonical home for evidence-before-claims / closure enforcement (2026-07-19 rehome; no duplicate probe survives under any other skill's name). |
| [write-gate](write-gate/SKILL.md) | Content-quality gate before persistent writes. Signal-score (decisions / errors / architecture / code / numbers, minus filler / speculation) + why-clause enforcement for decisions. Lineage: ogham-mcp + codenamev/claude_memory. |
| [task-retrospective](task-retrospective/SKILL.md) | **Experimental/manual.** User-triggered task-audit workflow retained for explicit `/retro` evaluation arms. |
| [brainer-audit](brainer-audit/SKILL.md) | Report-only Brainer skill-use audit mode: inspect normalized events for missed skill triggers, unverified completion claims, write-gate bypasses, task-retrospective boundary violations, dropped requirements, and output-filter opportunities. Claude/Codex hooks are opt-in and marker-gated; Antigravity uses lower-fidelity sidecar snapshots. Proposes Brainer improvements but does not apply them. |
| [loop-engineering](loop-engineering/SKILL.md) | **Experimental/manual.** FULL loop-design prose retained for paired evaluation; deterministic `loop_lint.py` remains callable (the unwired `loop_run_monitor.py` monitoring tools were deleted — zero production callers). |
| [eval-gate](eval-gate/SKILL.md) | LLM-as-judge quality gate for AI output: score a draft / post / answer / agent reply against a written rubric before it ships — returns 0–5 + reason, exit code gates, every caught failure becomes a permanent case. Eval-gate is the *judgment* check where "good enough" has no test. **Default-installed** (v1.11; previously opt-in, 79% judge–human agreement with N≥50 validation pending — promoted on user request). |
| [baton](baton/SKILL.md) | Session handoff: drop/grab a single verified handoff file in `.brainer/baton/` — intent, git-verified State of Play, dead-ends-with-why, literal next step. Iron Rule: state built from `git status`, never chat narrative. Vendored from [blader/baton](https://github.com/blader/baton) (MIT) via `/learn`; **proposed, slash-only** (`/baton`) until telemetry promotes. Ships a `prompt_intent` canary probe on handoff/resume phrases. |
| [brainer](brainer/SKILL.md) | **Proposed/manual.** `/brainer` selects the smallest relevant set of optional Brainer skills or exported methods from an on-demand reference; whole contracts remain indivisible and umbrella permission grants no new authority. |
| [learn-skill](learn-skill/SKILL.md) | **Experimental/manual.** `/learn` workflow and tools retained for paired evaluation; no default hooks. |
| [impact-of-change](impact-of-change/SKILL.md) | Map a code edit to its blast radius before committing — parses `git diff` for changed symbols, reverse-traverses graphify's `calls` + `inherits` edges (callers + subclasses, depth≤3) for inbound dependents, emits a LOW/MEDIUM/HIGH risk score; degrades to a labelled lexical grep when graphify is absent. **Opt-in** (`auto-install: false`). |
| [propagate](propagate/SKILL.md) | Push canonical skill changes to the sibling/consumer repos: per-sibling classify → `--apply-stale`/`--apply-absent` → sibling `install.sh` → verify → `--post-check`, sequentially. STALE (byte-matches canonical history) fast-forwards; CUSTOMIZED (sibling-local work) is never overwritten — flagged for manual merge. Canonical must be committed first. Trigger-loaded on "propagate/sync to siblings" via its `prompt_intent` probe (not part of frontier's compact mechanical emit set — `legacy`, the profile that once carried it, was retired 2026-07-19; the model is expected to recognize the trigger unassisted here). |
| [team-lead](team-lead/SKILL.md) | **Experimental/manual.** FULL orchestration protocol retained for explicit team requests and paired evaluation; compact builder/verifier role briefs remain available. |

18 skills total — all **listed and symlinked by the current installer**. Opt-in status controls hook/dependency wiring, while `disable-model-invocation` keeps suspect bodies manual. `compliance-canary` remains the default frontier service with silent intent state and compact verification; executable tools remain callable without auto-loading their manuals. Promotion history and measured deltas live in [`eval/FINDINGS.md`](../eval/FINDINGS.md).

Removed after measurement: `personal-assistant` / `memory-api` / `skill-creator` (v1.1.0, redundancy), `delegate` (v1.2.0, zero measured gain — auto-routing via `prompt-triage` already covers the use case), `context-refresh` (v1.3.0, merged into `handoff` — its only unique piece was the auto-launcher which never worked reliably; the rest is now `/handoff --full` and `/handoff --ask`), `handoff-from` + `memory-decay` (v1.6.0, redundant / verified no-op), and `compress-context` + `session-recall` + `loop-breaker` (v1.6.0, the unproven-gain tail: each was both ❌/🟡 on measured benefit and redundant with a kept skill — `caveman`+`context-keeper`, `context-keeper`+`wiki`+`handoff`, and host loop-protection respectively; see `eval/FINDINGS.md` "Catalog cuts"), and `handoff` (v1.6.1 — operational-only, no measured gain; the host's `/compact` + `context-keeper` PreCompact extraction cover session continuity), and `standing-orders` + `self-improvement-loops` + `requirements-ledger` + `wayfinder` + `fable-mode` + `plan-first-execute` + `lean-execution` (v1.12, 2026-07-19 catalog contraction: unproven doctrine bodies per the null FRONTIER-vs-OFF pilot, the 2026-07-17 adversarial-review taxonomy, and `docs/TARGET_ARCHITECTURE.md`'s migration map; their still-valuable mechanical probes — repeated-failure stall, dependency-manifest, whitespace-only-edit, ledger-not-materialized, assumption-self-close — were rehomed to `compliance-canary/drift_probes.json`, and canary's unconditional intent capture already replaces the ledger workflow), and `cache-lint` + `output-filter` + `semantic-diff` (Great Pruning A2, 2026-07-22: zero clean-signal usage across the full curated-session + telemetry window per `screenery-design-master/.brainer/pruning-audit/usage-evidence.md`), and `verify-before-completion` + `wiki-refresh` + `security-oversight` (Great Pruning A2, 2026-07-22, D31 method: demoted to compressed delegate briefs in [`_shared/briefs/`](_shared/briefs/) — rare/low-signal usage but not zero, so the method/procedure prose survives as a manually-invoked brief rather than a full skill; `security-oversight`'s callable tools moved to [`_shared/tools/security-oversight/`](_shared/tools/security-oversight/); `verify-before-completion`'s mechanical probes stay canary-owned per the 2026-07-19 rehome, see `compliance-canary`'s catalog line — `loop-engineering` / `learn-skill` / `prompt-triage` were reconsidered post-audit: fired within the evidence window, so they stay full skills, not briefs).

External integrations: [`index-first`](index-first/SKILL.md) and [`wiki-memory`](wiki-memory/SKILL.md) recognize [graphify](https://github.com/safishamsi/graphify) (`graphify-out/graph.json`) when present — graphify owns the auto-extracted *what/how/connected* layer; wiki-memory owns the curated *why/decision* layer. See each skill's body for the exact protocol.

## Most-recommended stack

The eight slots below cover the measured-win axes (output × routing × memory × retrieval × re-read × terminal × done-claims). Each skill earns its slot with a measured number; numbers compose across axes, diminish within. Per-axis sources in [`eval/FINDINGS.md`](../eval/FINDINGS.md).

| Slot | Skill | Headline measurement |
|---|---|---|
| Output style | [`caveman-ultra`](caveman-ultra/SKILL.md) | **−87.7%** output (combo, measured with the since-retired lean-execution prose; surgical-diff rules now resident + probe-enforced) |
| Routing | [`prompt-triage`](prompt-triage/SKILL.md) | −20.9% total, 100% accuracy |
| Memory across compaction | [`context-keeper`](context-keeper/SKILL.md) | 97.7% transcript compression |
| Retrieval — what/how/connected | external: [graphify](https://github.com/safishamsi/graphify) | **−93%** vs grep+read at parity evidence (`graphify explain`) |
| Retrieval — why/decision | [`wiki-memory`](wiki-memory/SKILL.md) | 100% evidence on project-history questions; combo with graphify: −87% vs grep at 100% evidence |
| Re-reads | *(retired, Great Pruning A2 — `semantic-diff` had zero clean-signal usage)* | 95.5% reduction on unchanged re-reads (historical measurement) |
| Terminal output | *(retired, Great Pruning A2 — `output-filter` had zero clean-signal usage)* | −88.8% bytes, errors preserved (historical measurement) |
| Claims of done | `compliance-canary`'s `claim-without-evidence` probe + `_shared/briefs/verify-before-completion.md` (Great Pruning A2: demoted, invoke manually for the full checklist) | −33.5% output, evidence-first (historical measurement) |

Bootstrap once per project: `python3 skills/wiki-memory/tools/wiki.py init && graphify extract .` (graphify is auto-installed by `./install.sh`; pass `--no-graphify` to opt out).

## Prime directive

- **Caveman-Ultra when elected** for emitted prose. Reasoning budget separate.
- **Plan before non-trivial work; smallest reversible diffs** (resident code-craft directives).
- **Verify before claiming done**.
- **Retrieve before reasoning** about project/wiki facts — prefer `graphify explain` for code questions, `wiki-memory` for decision questions.
- **Use cheapest capable worker**; keep main context clean. Dispatch speaks in capability **tiers**, resolved to the newest in-host (or clearly-better reachable) model at dispatch time — doctrine in [`_shared/ORCHESTRATION.md`](_shared/ORCHESTRATION.md).

Stacking, anti-patterns, and workload guidance live in [`eval/FINDINGS.md`](../eval/FINDINGS.md) — not always-loaded; read once when installing or tuning the catalog.

## Install

```bash
./install.sh             # symlink to all four host loaders
./install.sh --host claude-code   # just one host
```

## Status

Sixteen skills ship an `EVAL.md`; `baton` and `propagate` currently do not. Skills claiming >20% savings get N≥50 verification before promotion. A skill carrying `auto-install: false` remains symlinked and listed, but its installer does not run. Root reinstall removes stale managed hooks for opt-in skills; explicit per-skill installation can re-enable one for a controlled arm.
