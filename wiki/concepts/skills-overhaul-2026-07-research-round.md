---
schema_version: 2
title: "Skills-overhaul research round (2026-07) — 5 reports, 2 reviewer verdicts, borrow list"
type: concept
domain: "skill-authoring"
tier: semantic
confidence: 0.85
created: "2026-07-20"
updated: "2026-07-20"
verified: "2026-07-20"
sources:
  - ".brainer/research/2026-07-skills-overhaul/research-ecosystem-terra.md"
  - ".brainer/research/2026-07-skills-overhaul/research-memory-luna.md"
  - ".brainer/research/2026-07-skills-overhaul/research-verification-terra.md"
  - ".brainer/research/2026-07-skills-overhaul/research-recency-luna.md"
  - ".brainer/research/2026-07-skills-overhaul/research-skills-hurt-frontier.md"
  - ".brainer/reviews/phase2-2026-07/sol-opinion-round.md"
  - ".brainer/reviews/phase2-2026-07/kimi-opinion-round.md"
tags: [research-round, skills-overhaul, ecosystem, memory, verification, recency, frontier-harm, sol-review, kimi-review, borrow-list]
supersedes: []
superseded-by:
---

# Skills-overhaul research round (2026-07) — 5 reports, 2 reviewer verdicts, borrow list

## Summary

During the phase-2 skills-overhaul, five external-research reports (ecosystem,
memory, verification, recency, "skills hurt frontier models") were commissioned
in parallel to test whether Brainer's catalog and mechanisms still match
2025-2026 best practice, and whether resident scaffolding costs frontier models
more than it helps. Two reviewers (Sol, Kimi) then critiqued both the phase-2
diff and the research itself for quality, priority, and blind spots. This page
compiles the durable findings so future work reads curated synthesis instead of
five ephemeral report files.

## Per-report findings

### Ecosystem (research-ecosystem-terra.md)
- Public catalogs cluster on artifact production, dev workflow, integrations, and vertical domain packs; memory/verification/token-hygiene are niche, so Brainer is differentiated, not incomplete.
- Superpowers' `writing-skills` doctrine: description should be trigger-only ("Use when...") not a workflow summary, because an agent may act on the summary instead of loading the body.
- Recommends adding false-positive/false-negative trigger fixtures per auto-invokable `EVAL.md`.
- Notes Brainer has no `scripts/`/`references/`/`assets/` layout (uses `tools/` in 21 skill folders) — a portability delta, not a compliance defect.
- Recommends annotating helpers "execute vs read" since Anthropic warns code may be either deterministic machinery or reference material.

### Memory (research-memory-luna.md)
- Brainer is unusually strong on provenance, progressive retrieval, and truth-conflict visibility (trust tiers, `contradicts`/`supersedes`).
- Clearest gaps: temporal validity/decay (cf. Graphiti bitemporal facts), a formal memory-quality eval suite (cf. LongMemEval), and retention/redaction policy for `context-keeper`'s raw-transcript archive.
- RecMem: consolidate only on recurrence rather than every turn (87% lower construction cost in its own report) — Brainer's `write-gate` selective-promotion already does something similar.
- "Experience-following behavior" paper: selective addition + deletion beat naive memory growth by ~10pp — supports write filtering over unconditional capture.

### Verification (research-verification-terra.md)
- No strong external analogue exists for Brainer's "claim without fresh, class-matched evidence" probe — it is differentiated but needs strong fixture/false-positive testing.
- `Stop` is a different, stronger control point than `UserPromptSubmit` for catching false completion claims (Ralph Wiggum plugin, cwc-long-running-agents).
- PaperBench/RULERS: validate the judge itself against human gold labels; freeze/version rubrics before candidate generation; require evidence pointers or `CANNOT_ASSESS`, not persuasive prose.
- Route each criterion deterministic/judge/human before evaluating; judges are flexible but non-deterministic and need calibration.

### Recency (research-recency-luna.md, window 2026-01-01 to 2026-07-20)
- Harness assumptions go stale fast: Anthropic's Sonnet 4.5→Opus 4.5 finding turned a context-reset workaround into "dead weight" on the stronger model.
- Claude Code 2.1.215 (2026-07-19) stopped auto-running `/verify`/`/code-review` — advisory verification is becoming explicit/opt-in industry-wide.
- SkillsBench: curated skills +16.2pp average pass rate, but 16/84 tasks regressed, and focused 2-3-module skills beat comprehensive documentation.
- Recommends a "scaffolding lifecycle ledger": mechanism, failure addressed, model/host assumptions, last observed benefit, removal/revalidation date.

### Skills-hurt-frontier (research-skills-hurt-frontier.md)
- Chroma's context-rot study (18 frontier models): resident text has a measured, universal per-token distraction cost that frontier models do not escape.
- Anthropic's own Claude 4 migration guidance: strip scaffolding calibrated for weaker models (MUST/ALWAYS, forced progress summaries) because newer, more literal models over-trigger on it.
- Minimal harnesses (mini-swe-agent) matched/beat feature-rich native harnesses on frontier models in several benchmarks; first-party harness advantage shrinks or vanishes at the top capability tier (Han Lee's cited Opus 4.5 data).
- Net reading: NOT "all scaffolding hurts" — resident catalogs/reminders and coercive MUST-language backfire on strong models, but lazy-loaded facts the model cannot know (project state, verified memory, indexes) are the exempted category.

## Reviewer verdicts

**Sol** ranks the verification report highest (judge-calibration packet, verifier-independence criteria) and calls the memory report broadest but weakest-prioritized (raw-transcript retention is its most urgent item; bitemporal graphs/LongMemEval-scale eval are overrated for this repo's size). Sol's collective-miss: no report built a **consequence-weighted actuation model** (`detect silently < advise once < persist state < interrupt repeatedly < block closeout`) or a cross-surface **policy/actuation authority matrix**. Sol's plan: raw-transcript policy, skill/no-skill ablation, trigger-selection tests, and a scaffolding lifecycle+policy matrix as P0 after merge; closure-time evidence gating and temporal validity deferred to P2/prototype-only.

**Kimi** ranks the five reports **recency > verification > skills-hurt > memory > ecosystem** by decision-relevance density. Kimi's explicit cut: **drop the LongMemEval-style memory-eval clone** — "a formal benchmark for a wiki this size fails the repo's own scope test"; drift/contradiction/unsupported-write failure modes are already gated by `wiki-refresh`/`write-gate`/`contradicts:` edges. Kimi also downgrades bitemporal/typed-lifetime memory and the `tools/`→`scripts/` rename as overrated churn, and flags RecMem-style consolidation as duplicating `write-gate`. Kimi's four **collective misses** (named explicitly, none of the five reports covered them): (1) **the distribution problem** — no lane studied deletion/tombstone semantics across Brainer's multi-repo sibling propagation, which is where the phase's worst non-blocker bug actually lived; (2) **re-measurement debt** — the recency lane's own top finding (scaffolding is model-specific/capability-dated) indicts Brainer's own stored FINDINGS.md deltas, measured on older models and never re-baselined; (3) **the resident boot surface** — no lane proposed measuring Brainer's own always-loaded AGENTS.md catalog + resident directives against the frontier corpus, only individual skills; (4) **the armed arm** — the compliance-canary correction-ledger's armed mode was untested by the frozen 862-case gate at review time, so the acceptance bar proved the default path quiet without measuring armed-path precision.

**Disagreement:** Sol frames the correction-ledger fix as a detector-bug question ("make detection context-safe"); Kimi separates the **policy question** (should default frontier carry a closeout-blocking ledger at all — answer: no, armed-only) from the **detector question** (the pattern still needs quoted-span/code-fence stripping once armed) and credits the owner's armed-only call while flagging the detector fix as still incomplete at review time (it subsequently landed as phase 2l, 2026-07-20: quoted-span/code-fence stripping, bare-`again` removal, armed FP 0/15).

## Borrow list

| Item | What it is | Serves goal | Priority tier |
|---|---|---|---|
| Trigger-only descriptions + selection fixtures | Rewrite auto-invoke descriptions to state symptom/scope only; add should-fire/must-not-fire/ambiguous fixtures per skill | #2 reliability | Ecosystem: recommended. Kimi: P0, but sequence tests *before* the rewrite (else unmeasured discovery-layer change) |
| Judge-calibration packet for `eval-gate` | Frozen rubric ID, gold-set version, judgment scale, abstention policy, confusion matrix, Cohen's kappa | #2 reliability | Verification: P0 for shipping gates. Sol: conditional P1 (not urgent for deterministic gates). Kimi: "P0 with teeth" — the marketplace's unqualified "79% judge-human agreement" claim needs this before it can be trusted |
| Raw-transcript retention/redaction/access/deletion policy | Governance for `context-keeper`'s byte-for-byte archive | #4 memory/wiki | Memory: most urgent finding. Sol: P0 after merge. Kimi: "cheapest real security fix in the plan" |
| Skill/no-skill ablation + negative-delta tracking | Measure each skill's marginal effect, including regressions (SkillsBench: 16/84 tasks regressed) | #1 token efficiency, #2 reliability | Sol: P0 after merge, promoted from P1. Kimi: "run this before borrowing new scaffolding" |
| Scaffolding lifecycle ledger | Manifest: mechanism, failure addressed, model/host assumptions, last benefit, removal/revalidation date | #2 reliability, #6 mindset | Recency: proposed. Kimi: best idea across all 5 reports, but only if wired into the model-upgrade ritual as enforcement, not left as an unread doc |
| Consequence-weighted actuation model / policy-authority matrix | Evidence threshold scales with allowed side effect (`detect < advise < persist < interrupt < block`); one table per default-on mechanism naming owner/source/activation/evidence/retirement | #2 reliability, #5 loops | Sol: names this as the repo-specific miss across all 5 reports; P0 |
| Deterministic/judge/human criterion routing | Route each eval criterion to the cheapest sufficient check before any judge | #1 token efficiency, #2 reliability | Verification report + Sol: P1, precedes judge calibration |
| Execute/read annotations on skill helpers | Mark whether a bundled script is meant to be run or read | #1 token efficiency | Ecosystem: recommended. Sol: add on touch, not a catalog-wide pass |

**Explicitly rejected:**
- **LongMemEval-style memory-eval clone** — Kimi: cut. Fails Brainer's own AGENTS.md scope test (adds machinery without serving a goal); the failure modes it targets (drift, unsupported writes, contradiction loss) are already gated by `wiki-refresh`/`write-gate`/`contradicts:` edges.
- **Bitemporal/Graphiti-style temporal-validity memory + typed memory lifetimes** — Kimi: real ideas, wrong scale; fold into one small P2 wiki-metadata experiment (`valid_as_of`/`superseded_at` fields) instead of adopting graph-memory infrastructure.
- **`tools/` → `scripts/`/`references/`/`assets/` rename** — Sol and Kimi both reject: pure churn with zero measured benefit; a portability delta only, not a reliability one.
- **RecMem-style recurrence-triggered consolidation pipeline** — Kimi: duplicates `write-gate`'s existing selective-promotion under a new name.
- **Default-on unconditional correction-ledger banking** — Sol and Kimi both side with the owner's armed-only decision over the earlier "fix the text, keep the machinery" reading; the frozen-corpus measurement (FP=175, precision 65.2%) is treated as the deciding evidence, not a text/code inconsistency to patch around.

## Pointers

- Raw reports: `.brainer/research/2026-07-skills-overhaul/research-{ecosystem-terra,memory-luna,verification-terra,recency-luna,skills-hurt-frontier}.md`
- Reviews: `.brainer/reviews/phase2-2026-07/{sol-opinion-round,kimi-opinion-round}.md`
- Follow-up queue: `.brainer/research/2026-07-skills-overhaul/PROPOSED_TASKS.md`

## Related

- [[concepts/harness-article-adoption-2026-07]] — prior article-adoption pattern (confirm/reject, rarely net-new)
- [[concepts/claude-skills-ecosystem-scan-2026-07]] — prior ecosystem-scan adoption precedent
- [[concepts/write-gate-not-truth-filter]] — write-gate scores signal not truth, relevant to the correction-ledger disagreement
