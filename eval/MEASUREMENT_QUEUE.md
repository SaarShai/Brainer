# Measurement queue — pay down the eval debt

Catalog policy: only measured-win or cheap load-bearing skills stay on the
default path. 10 of 24 skills are unmeasured/pending. This queue orders them by
**resident-cost × uncertainty** (a default-installed skill with no number is the
most expensive ignorance). Method per skill lives in its EVAL.md; this file is
the order + the standing baselines.

## Queue (top = next)

| # | Skill / question | Why this rank | Method pointer |
|---|---|---|---|
| 1 | requirements-ledger drop-rate | default-on + hook cost every turn; the no-drop guarantee has no number | EVAL.md (multi-conjunct corpus, with/without) |
| 2 | loop-engineering N≥50 | default-on, largest body in catalog | EVAL.md (cross-family, pending since v1.8) |
| 3 | eval-gate rubric-gate A/B | default-on; 79% judge-human agreement needs N≥50 | EVAL.md |
| 4 | usage-vs-mention instrumentation | per-repo skill profiles are BLOCKED on it (2026-07-01 mining showed sessions-touched ≈ catalog residency, not usage) | extend measure.py to aggregate canary state (probes fired per skill per session) across repos |
| 5 | wiki-refresh A/B savings | default, pending live run | EVAL.md |
| 6 | write-gate project-local A/B | default, pending | EVAL.md |
| 7 | context-keeper preservation metrics | default, extraction measured but preservation-through-compaction not | EVAL.md |
| 8 | index-first static cost | pending measurement note in EVAL | EVAL.md |
| 9 | prompt-triage research-lite leg | one routing leg unmeasured | EVAL.md |
| 10 | think 2026-07 edits (doc-bloat governor, smallest-verifiable-steps) | slash-only so cheap, but repo culture A/Bs think edits (premortem precedent) | premortem-style eval (wiki: premortem-and-think-edits-measured) |
| 11 | impact-of-change / security-oversight | opt-in → lowest urgency | new EVAL.md stubs (2026-07-01) |

## Standing baselines (2026-07-01)

**Drift-probe fire rates** (measure.py over 10 recent Brainer sessions, 10,611
events; 27 probes deployed):
- `verify-before-completion:edit-without-read` — **60% of sessions** (top real drift; the read-before-edit reflex is the weakest in practice)
- `learn-skill:nominate` — 50% · `completion-without-closure` — 30% · `claim-without-evidence` — 30% · `caveman-ultra:word-creep` — 20%
- 22/27 probes never fired offline (most are prompt_intent / context-gated — expected offline; not evidence of deadness)
- Mean 1.9 fires/session; 1 of 10 sessions clean.

**propagate prompt_intent probe P/R** (2026-07-01, fire-test corpus): 6/6
positives, 0/4 negatives.

**ORCHESTRATION.md comprehension** (naive local subject, qwen3.6:35b, blind):
5/5 scenarios resolved per doctrine.

**wiki retrieval miss rate** (transcript mining 2026-07-01, 20 transcripts /
31 searches / 7 sessions): **0 confirmed misses**; 12 confirmed hits; 18
inconclusive — because searches run inside compound bash pipelines
(`… && wiki.py search … | head -8`), their results are invisible to transcript
mining. True miss rate ∈ [0%, 58%], N small. **Decision: no semantic-search
investment on this evidence.** The actionable finding is instrumentation, not
retrieval: run wiki searches as standalone commands (results then land in
tool_results and become minable) — folded into queue item 4.

**Per-repo usage mining caveat** (2026-07-01): grep sessions-touched conflates
catalog mention with use (resident CLAUDE.md catalogs make every skill appear in
~15/15 sessions). Only true zero-signals: impact-of-change, security-oversight
(both opt-in). **Decision: no per-repo trims on this evidence** — queue item 4
first, then revisit `.brainer-sync-optout` profiles with real firing data.
