# Brainer Skills

Lean skills for AI coding agents (Claude Code · Codex · Cursor · Gemini · Copilot) across four pillars: **(1)** token-use optimization, **(2)** context-window optimization & management, **(3)** LLM wiki-memory framework, **(4)** self-improvement & learning.

This replaces the old `start.md` boot doc. Each skill is a self-contained folder under `skills/<name>/`. Skill descriptions are the only thing always resident in the agent's context; full bodies load on trigger.

For measured per-skill deltas and the live A/B table see [`eval/FINDINGS.md`](../eval/FINDINGS.md); each skill also ships its own `EVAL.md`.

## Catalog

| Skill | One-line |
|---|---|
| [caveman-ultra](caveman-ultra/SKILL.md) | Terse output style. Drops filler; preserves code/numbers/errors verbatim. |
| [plan-first-execute](plan-first-execute/SKILL.md) | Plan before executing non-trivial tasks. |
| [think](think/SKILL.md) | How an agent should think: first-principles, reduce/simplify, research & borrow, experiment-to-falsify; ideation + 5-whys + pre-mortem/inversion. **Slash-only** (`/think`). |
| [lean-execution](lean-execution/SKILL.md) | Prune plans/scope to the smallest safe path. |
| [verify-before-completion](verify-before-completion/SKILL.md) | Run fresh verification before claiming done. |
| [wiki-memory](wiki-memory/SKILL.md) | Repo-local markdown wiki: progressive retrieval + gated writes. |
| [prompt-triage](prompt-triage/SKILL.md) | Pre-model classifier hook; routes simple tasks to cheap models. |
| [context-keeper](context-keeper/SKILL.md) | PreCompact hook: structured memory before compaction. |
| [semantic-diff](semantic-diff/SKILL.md) | AST-node diff on file re-reads (95%+ savings; opt-in MCP). |
| [index-first](index-first/SKILL.md) | Prefer pre-built indexes / composite verbs over grep+read chains; batch N related lookups into one capped call. |
| [output-filter](output-filter/SKILL.md) | Strip ANSI/progress/dup noise from terminal output. |
| [compliance-canary](compliance-canary/SKILL.md) | UserPromptSubmit hook: the **single always-on drift watcher**. Two mechanisms in one process — (1) symptomatic per-skill `drift_probes.json` scans (filler regex / word-count creep / claim-without-evidence / looping tool errors), and (2) a periodic skill-rule **re-anchor** every N turns (paper-calibrated, arXiv 2510.07777). The re-anchor yields to a fired probe (no double-nag). Absorbed `skill-pulse` (v1.10). Ships an offline `measure.py`. **Default-on since v1.7** (cross-model longrun: +0.44 probes / +0.27 re-anchor, 2 model families). |
| [write-gate](write-gate/SKILL.md) | Content-quality gate before persistent writes. Signal-score (decisions / errors / architecture / code / numbers, minus filler / speculation) + why-clause enforcement for decisions. Lineage: ogham-mcp + codenamev/claude_memory. |
| [wiki-refresh](wiki-refresh/SKILL.md) | Reconcile wiki pages against the current codebase (Keep/Update/Consolidate/Replace/Delete); code-grounded via `audit-refs`, emits typed `contradicts:` edges. Ground-truth reconcile. Lineage: [EveryInc/compound-engineering-plugin](https://github.com/EveryInc/compound-engineering-plugin) (`plugins/compound-engineering/skills/ce-compound-refresh`). |
| [cache-lint](cache-lint/SKILL.md) | Static audit against Anthropic's 6 prompt-cache rules — dynamic content above breakpoint, prefix mutation by Stop-hooks, model switching, breakpoint sizing. Lineage: ussumant/cache-audit. |
| [task-retrospective](task-retrospective/SKILL.md) | Task-end close of the learning loop: agent self-audit (with a rationalization catalog) + show-evidence-first user check (review card, closed verbs) + ≤3 gated lessons routed to the NARROWEST home; a REPEATED failure escalates to a mechanical `compliance-canary` drift probe, not more prose. `tools/audit_lessons.py` Measure phase scans `wiki/log.md` for post-fix recurrence (tag-aware). Generalized from screenery-lean; adopts GenericAgent + EveryInc compound-engineering/compound-knowledge patterns. |
| [loop-engineering](loop-engineering/SKILL.md) | Design the verifier, not the prompt. Chooses the loop SHAPE (open/closed · inner/outer · single/fleet) and wires a generator to a SEPARATE verifier — the net-new layer no other skill provides. Ships `loop_lint.py`: a static gate that refuses a loop spec with no gate / no stop+budget / generator==verifier (self-grading; also catches same-actor-different-verb, and allows an explicit human-approval gate). Delegates the verify reflex→`verify-before-completion`, the learning loop→`task-retrospective`, the closed-loop plan→`plan-first-execute`, restraint→`lean-execution`. **Opt-in** (`auto-install: false`, unmeasured). Lineage: the "design the verifier" generator-verifier framing (ReAct/Reflexion) + pattern sources HarnessCode (yzddp) & autonomy-loop (inferencegod). |
| [eval-gate](eval-gate/SKILL.md) | LLM-as-judge quality gate for AI output: score a draft / post / answer / agent reply against a written rubric before it ships — returns 0–5 + reason, exit code gates, every caught failure becomes a permanent case. The output-side complement to `loop-engineering` (which designs the loop's verifier) and `verify-before-completion` (which runs deterministic checks); eval-gate is the *judgment* check where "good enough" has no test. **Opt-in** (`auto-install: false`; 79% judge–human agreement, N≥50 validation pending). |

18 skills total — 16 **default-installed** since v1.7, plus `loop-engineering` and `eval-gate` shipped **opt-in** (`auto-install: false`, v1.8/v1.9: zero measured A/B deltas at launch, so per the anti-goal "no default-on skill without a measured number" it stays off the measured default-stack; its `loop_lint.py` gate is CI-runnable value at opt-in, promotion to default gated behind N≥50 cross-family — see [`loop-engineering/EVAL.md`](loop-engineering/EVAL.md)). Of the default skills: `compliance-canary` (which **absorbed `skill-pulse` at v1.10** — one hook now runs both the symptomatic probes and the periodic re-anchor) was promoted from opt-in to default-on (`auto-install: true`, commit `bc2ec0d`) once the cross-model longrun replicated both mechanisms' uplift (+0.44 probes / +0.27 re-anchor, two model families — see FINDINGS "Cross-model long-run") and it became load-bearing for output-style drift control. Rationale unchanged: only measured-win or cheap load-bearing skills sit on the default install path (see [`eval/FINDINGS.md`](../eval/FINDINGS.md)). (`think` is a pure-prompt mindset skill, now **slash-only** (`/think`, `disable-model-invocation: true`) — its frontier A/B measured posture-neutral, so it is not carried always-on; see [`think/EVAL.md`](think/EVAL.md).)

Removed after measurement: `personal-assistant` / `memory-api` / `skill-creator` (v1.1.0, redundancy), `delegate` (v1.2.0, zero measured gain — auto-routing via `prompt-triage` already covers the use case), `context-refresh` (v1.3.0, merged into `handoff` — its only unique piece was the auto-launcher which never worked reliably; the rest is now `/handoff --full` and `/handoff --ask`), `handoff-from` + `memory-decay` (v1.6.0, redundant / verified no-op), and `compress-context` + `session-recall` + `loop-breaker` (v1.6.0, the unproven-gain tail: each was both ❌/🟡 on measured benefit and redundant with a kept skill — `caveman`+`context-keeper`, `context-keeper`+`wiki`+`handoff`, and host loop-protection respectively; see `eval/FINDINGS.md` "Catalog cuts"), and `handoff` (v1.6.1 — operational-only, no measured gain; the host's `/compact` + `context-keeper` PreCompact extraction cover session continuity).

External integrations: [`index-first`](index-first/SKILL.md) and [`wiki-memory`](wiki-memory/SKILL.md) recognize [graphify](https://github.com/safishamsi/graphify) (`graphify-out/graph.json`) when present — graphify owns the auto-extracted *what/how/connected* layer; wiki-memory owns the curated *why/decision* layer. See each skill's body for the exact protocol.

## Most-recommended stack

The eight slots below cover the measured-win axes (output × routing × memory × retrieval × re-read × terminal × done-claims). Each skill earns its slot with a measured number; numbers compose across axes, diminish within. Per-axis sources in [`eval/FINDINGS.md`](../eval/FINDINGS.md).

| Slot | Skill | Headline measurement |
|---|---|---|
| Output style | [`caveman-ultra`](caveman-ultra/SKILL.md) + [`lean-execution`](lean-execution/SKILL.md) | **−87.7%** output (combo) |
| Routing | [`prompt-triage`](prompt-triage/SKILL.md) | −20.9% total, 100% accuracy |
| Memory across compaction | [`context-keeper`](context-keeper/SKILL.md) | 97.7% transcript compression |
| Retrieval — what/how/connected | external: [graphify](https://github.com/safishamsi/graphify) | **−93%** vs grep+read at parity evidence (`graphify explain`) |
| Retrieval — why/decision | [`wiki-memory`](wiki-memory/SKILL.md) | 100% evidence on project-history questions; combo with graphify: −87% vs grep at 100% evidence |
| Re-reads | [`semantic-diff`](semantic-diff/SKILL.md) | 95.5% reduction on unchanged re-reads |
| Terminal output | [`output-filter`](output-filter/SKILL.md) | −88.8% bytes, errors preserved |
| Claims of done | [`verify-before-completion`](verify-before-completion/SKILL.md) | −33.5% output, evidence-first |

Bootstrap once per project: `python3 skills/wiki-memory/tools/wiki.py init && graphify extract .` (graphify is auto-installed by `./install.sh`; pass `--no-graphify` to opt out).

## Prime directive

- **Caveman-Ultra by default** for emitted prose. Reasoning budget separate.
- **Plan-first** for non-trivial tasks.
- **Lean execution**: smallest reversible action.
- **Verify before claiming done**.
- **Retrieve before reasoning** about project/wiki facts — prefer `graphify explain` for code questions, `wiki-memory` for decision questions.
- **Use cheapest capable worker**; keep main context clean.

Stacking, anti-patterns, and workload guidance live in [`eval/FINDINGS.md`](../eval/FINDINGS.md) — not always-loaded; read once when installing or tuning the catalog.

## Install

```bash
./install.sh             # symlink to all four host loaders
./install.sh --host claude-code   # just one host
```

## Status

Each skill ships an `EVAL.md` with measured token/context deltas. Skills claiming >20% savings get N≥50 Kaggle-T4 verification before being promoted to default. The opt-in mechanism remains supported: a skill carrying `auto-install: false` in its SKILL.md frontmatter is symlinked and listed by `install.sh` but its `tools/install.sh` is not run, so it never auto-wires a hook or pulls a heavy dependency (no skill currently uses it; `skill-pulse` + `compliance-canary` graduated to default-on at v1.7). To **disable** a hook skill: per-skill installers append to `.claude/settings.json` and never delete, so remove the stale hook entry from `.claude/settings.json` by hand.
