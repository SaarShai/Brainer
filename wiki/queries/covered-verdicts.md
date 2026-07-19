---
trust: verified
schema_version: 2
title: "Covered-verdicts index — every head-to-head adopt/reject/covered ruling"
type: query
domain: "framework"
tier: episodic
confidence: 0.8
created: "2026-07-06"
updated: "2026-07-18"
verified: "2026-07-18"
sources: ["wiki/concepts/*-adoption-*.md", "wiki/concepts/*-measured*.md", "wiki/queries/*-adoption*.md", "wiki/queries/external-validation.md"]
supersedes: []
superseded-by:
tags: [covered-verdicts, adoption, index, decision, external-review]
---

# Covered-verdicts index — every head-to-head adopt/reject/covered ruling

## Purpose

**Consult this page BEFORE re-deriving whether X is already covered, already
adopted, or already rejected.** A recurring failure mode: a session asserts an
external tool/idea is "already covered" from a one-line catalog description,
skipping the real head-to-head comparison
([[concepts/adoption-covered-needs-merits-citation]] names the rule this page
enforces mechanically) — and when the comparison was finally run, 1 in 5 such
claims flipped to a real adopt. This page exists to be the **memory that stops
that re-derivation loop**: one row per source/idea already reviewed, each
citing the detailed page where the real comparison happened. If a source you
are about to review already has a row here, fetch the cited page instead of
re-deriving the verdict from scratch. If it has no row, do the real
head-to-head, then add a row here (and file/extend the detailed page it
points to) so the next session doesn't repeat the work.

This page is the **compact ledger**; [[queries/external-validation]] is the
denser **per-source corroboration table** for external loop/memory-doctrine
articles specifically (its rows are folded in below, one line each). Where a
page's own wording is ambiguous about the precise verdict, this table quotes
it rather than paraphrasing into a false-precision label.

## Verdicts

| source reviewed | verdict | one-line why | detailed page |
|---|---|---|---|
| warpdotdev-demos/replatformer (generator→verifier loop, machine gate, fan-out) | ALREADY-COVERED | Brainer's `loop_lint.py` statically enforces the same pattern (R1/R2/R3); article asserts it in prose, Brainer already gates it — no change | [[queries/external-validation]] |
| Anthropic enterprise PDF (harness pre-flight + human gate before irreversible actions) | ALREADY-COVERED | pre-flight is already a SKILL.md section; R7/R10 flag irreversible/unbounded side effects statically — no change | [[queries/external-validation]] |
| Loop Engineering playbook ("chain of self-persuasion" — verifier reading generator's own justification inherits its bias) | ADOPTED 1/1 | drove the R3 blind-verifier wording tightening — verifier must be blind to generator's reasoning, not merely a different actor | [[queries/external-validation]] |
| CoEvoSkills (arXiv:2604.01687 — info-isolation proposer/evaluator, two-tier verify) | ADOPTED 2/2 | first source to earn changes: two-tier verify folded into outer-loop build; R3 tightening (verifier sees only task+outputs) | [[queries/external-validation]] |
| MyWestLord "$200/hour brain" product-factory thread (cheap-default constitution, escalate-on-2-fails, write-fixes-back, nightly orchestrator) | ADOPTED 2/N (mostly covered) | cheap-default/two-strike/write-back/nightly-loop already mapped onto existing skills; 2 real deltas: learn-skill weakest-executor acceptance test + ORCHESTRATION §6 "author down the ladder" | [[queries/external-validation]] |
| Thariq "A Field Guide to Fable: Finding Your Unknowns" (unknowns taxonomy, blindspot pass, interview-me, deviations log) | ADOPTED 2/N (mostly covered) | interview/deviations/references/prototypes already mapped to existing skills; 2 deltas: plan-first-execute blindspot pass + plan-ordering (data models first); comprehension-quiz-before-merge explicitly NOT adopted (no measured need) | [[queries/external-validation]] |
| vectorize-io/hindsight repo (35 memory concepts: TEMPR retrieval, freshness, memory-defense, proof counts) | ADOPTED 1/35 (mostly covered/reject) | retrieval/consolidation infra (RRF, embeddings, vector DB) categorically rejected under markdown-first axiom; 1 delta: `redact_secrets()` memory-defense ported into context-keeper's persistence path | [[queries/external-validation]] |
| "How I Prompt Fable" (goal-not-steps, house-rules, pre-push checker, builder-never-grades, loop-until-bar) | ADOPTED 2/10 (9/10 covered) | 9/10 already covered by plan-first-execute/eval-gate/R3/R13/lean-execution/ORCHESTRATION §6; post-progress-to-third-party advice explicitly rejected (R12 egress anti-pattern); 2 deltas: delegated metric-invention rule + brief-altitude rule (goal-shaped vs spec-shaped briefs) | [[queries/external-validation]] |
| 0xCodez "Build self-improving agent system w/ Fable 5 in 14 steps" (verifier-sub-agent, worktree isolation, 4-tier routing, 5-stage memory ladder) | ADOPTED 2/14 (11/14 covered) | 11/14 already core doctrine (R3/R9/R8, context-keeper, learn-skill, ORCHESTRATION §1+§6); 2 deltas: vision-verify rule in verify-before-completion + policy/classifier-block failure class in R14's on_error taxonomy | [[queries/external-validation]] |
| DanMcInerney/architect-loop (timed-ruling protocol, phase-0 disagreement, recovery ladder, 400-line diff cap, liveness doctrine) | ADOPTED 9/15, REJECTED 6/15 | full breakdown in [[concepts/architect-loop-adoption-2026-07]]: 9 adopted into loop-engineering/team-lead/ORCHESTRATION §6; 6 rejected (GitHub infra out-of-scope, scripts repo-specific, watchdog/guard/fan-out already handled, codex billing not doctrine) | [[concepts/architect-loop-adoption-2026-07]] |
| Matt Pocock Wayfinder (destination map, decision tickets, fog, frontier, HITL/AFK) | ADOPTED, adapted as proposed `/wayfinder` | genuine pre-spec gap: plans/ledgers/batons/wiki did not represent unresolved decision frontiers; kept destination/index/fog/frontier/single-decision mechanics, added provenance, rejected mandatory GitHub machinery and auto research fan-out | [[concepts/wayfinder-adoption-2026-07]] |
| OriginTrail DKG V10 (memory layers, Knowledge Assets, trust ladder, lifecycle provenance) | ADOPTED 1 narrow delta; weaker local analogues SUFFICIENT; distributed guarantees REJECTED | Brainer's evidence tiers, gated durable writes, source metadata, path IDs, and Git history meet its current repo-local need but are not DKG-equivalent identity/attestation/cryptographic guarantees; adopted a bounded random per-panel `correlation_id`; rejected RDF/blockchain/gossip/identity/economics and a new skill as category mismatches | [[concepts/origintrail-dkg-adoption-2026-07]] |
| DannyMac180/fable-advisor (architect pattern: 4-lane routing table, 5-part spec contract, no-silent-fallback) | ADOPTED 3 deltas (mostly EXCEEDS) | Brainer already exceeds on routing table, two-strike gates, fail-closed reachability, cross-vendor panels; 3 deltas: token-volume-inversion principle, pre-decision commitment-boundary consult, verify-the-pin (silent model substitution); "don't manufacture objections" prompt-craft noted but NOT adopted (measured negative) | [[queries/external-validation]] |
| EXM7777 "The Fable Loop Library: 25 Workflows" (5-part loop anatomy, autonomy colors, pasted-proof done contract) | ADOPTED 3/25 (mostly EXCEEDS) | colors < R7/R10 mechanical gates; "pasted proof" (self-reported) < verify-before-completion's fresh recompute; premortem PREVENTED/CARRIED ledger explicitly SKIPPED (prior measured negative, see premortem-and-think-edits-measured row below); 3 deltas: typed stop states, freeze-the-check + one-change-per-round, evidence floor on noisy gates | [[queries/external-validation]] |
| openforage "How To Use Loops In Agentic Engineering" (fresh-context blind verifier, rubric-guided verification, threshold/plateau stops) | ADOPTED 3/9 (6/9 corroboration) | Brainer exceeds on verifier isolation and rubric machinery; 3 deltas: spec-tied `required` rubric criterion, first-gate-check-early-in-budget rule, `compromises` extraction category in context-keeper | [[queries/external-validation]] |
| E2 A/B: eval-gate `required` criterion + loop-engineering typed stop states (2026-07-05 measurement of two rules adopted above) | MEASURED-NULL (mostly), one robust declaration effect | quoting the page directly: "Keep both rules... but do not cite them as measured behavioral lift. The one real effect is declaration-level"; drop-at-cap follow-up also null (lift 0.0); PHASE-0/LANE-REPORT follow-up did show a real behavioral gain (0/3→2/3 escalated a planted flaw) | [[concepts/e2-prose-rules-measured-2026-07]] |
| "Anatomy of an Agent Harness" article (12 harness components + 7 design decisions) | ADOPTED 3/7, REJECTED 3/7 (framing: category error) | ~85% of article confirmed existing Brainer bets (skill layer ≠ harness layer); 3 adopted: cache-lint rule 7 unused-tool-surface, loop_lint R14 unclassified-failure-policy, MEASUREMENT_QUEUE scaffold-shrink rule; 3 rejected: global ~/.claude.json extension (false-positive by construction), observation-masking skill (not scoped), harness-design-checklist skill (unmeasurable prose, premortem precedent) | [[concepts/harness-article-adoption-2026-07]] |
| "4-layer memory architecture" article (identity+index / Hindsight auto-retention / shared live-context log / searchable wiki) | ALREADY-COVERED (Layers 1+4), REJECTED (Layers 2+3, tested) | Layers 1+4 match Brainer exactly (CLAUDE.md+MEMORY.md+L1_index; wiki-memory) — no action; Layer 2 (pgvector semantic recall) rejected on infra-stack mismatch + prior measured negative ([[queries/memory-as-a-tool-validation]]: write-gate 6.62 vs ungated 8.62); Layer 3 (shared live-context log) A/B tested on the real incident condition and rejected — log only catches pre-existing diffs, not mid-run-appearing ones (the actual danger window); adopted instead: smallest verified delta, "foreign diffs are not damage" writer-brief rule | [[concepts/memory-article-4layer-evaluated-2026-07]] |
| `systematic-debugging` skill pitch (reproduce-first → isolate → fix-at-root → verify, from "top 1%" article) | MEASURED-NULL, reverted | built it, A/B'd against no-skill across 2 regimes (sonnet toy bugs + opus hard multi-file/stateful/decoy bugs), zero lift on every axis, byte-identical diffs in the hard run — reverted (deleted), not adopted; reflexes already owned by verify-before-completion + lean-execution + impact-of-change | [[concepts/systematic-debugging-skill-measured-null]] |
| Standalone `premortem` skill + `/think` premortem/anti-flattery edits (Klein/Kahneman framing article) | MEASURED, mostly REJECTED (1 small win) | article's premise ("Claude defaults to agreeable") false for opus (0/4 flawed plans endorsed, 10/12 flaws caught bare); one win shipped: early-warning-sign clause to `/think` (lifted leading-indicators 1→21 at zero detection cost); rejected: standalone skill, calibration/anti-over-warning clause (cuts real external flaws too), false-premise line sharpening (not load-bearing), 6-months-horizon framing | [[concepts/premortem-and-think-edits-measured]] |
| Egonex-AI/Understand-Anything (5 ideas: fingerprint change-classifier, wiki-refresh staleness nudge, fleet doctrine, index-first, tiered verifier) | ADOPTED 3/5, REJECTED 1/5, SKIPPED 1/5 | adopted #2 (staleness nudge), #3 (fleet doctrine: payloads-to-disk), #4 (index-first); #1 dropped — adversarial review found 13 dangerous false-negatives in the classifier (token-saving premise was false); #5 skipped — Brainer already ships both verifier tiers (lint scripts + eval-gate) | [[queries/understand-anything-adoption-kept-2-3-4-dropped-1-5]] |
| Karpathy LLM-Wiki "compile-not-retrieve" | ADOPTED (gated), partial | quoting the page: "Brainer's wiki-memory is already a Karpathy 3-layer implementation and a superset of the paper" on retrieval/lint/poison-defense; two real gaps closed — belief-update propagation (`stale-citers`) + quorum gate (`quorum_decision`) — both gated for autonomy since the paper assumes a human reviews compiled output and Brainer has none; L1_index boot-budget guard and 14-day TTL auto-purge explicitly rejected (premature / conflicts with supersede-don't-delete law) | [[queries/llm-wiki-compile-on-ingest-adoptions]] |
| DeusData/codebase-memory-mcp (pure-C code-graph MCP, "covered by graphify" catalog-line claim) | ADOPTED (narrow), patterns only | verdict was "adopt", not "already covered" — Brainer ported **patterns, not the engine**: grep-augment PreToolUse hook, degraded-write + loud unsupported-query + ADR, hook-safety validator+CI-gate, artifact merge=ours+integrity, new impact-of-change skill, eval ground-truth gate; row 10 of the adoption matrix | [[concepts/framework-hardening-adoption]] |
| topoteretes/cognee (heavyweight AI-memory platform; re-audit of the codebase-memory-mcp "covered by graphify" call) | ADOPTED (narrow, 1 real gap found on re-audit) | mostly already covered, but the re-audit is the **exact 1-in-5-flip precedent this index exists to prevent**: graphify emitted `inherits` edges but `impact.py:37` only consumed `calls` — a "covered" verdict from a catalog-line name-match had silently dropped a real, cheap capability; found only when re-audited head-to-head per [[concepts/adoption-covered-needs-merits-citation]]; bi-temporal intervals + hybrid-LSP resolution rejected as categorical infra-axiom rejects | [[concepts/framework-hardening-adoption]] |
| "You're competing against people who treat Claude like an operating system" article (32 skills across 9 hubs: Anthropic/Rezvani/Composio/BehiSecc/Jezweb) | ADOPTED 1/32 | net one capability adopted — pre-install `skill_audit.py` folded into security-oversight (prompt-injection detection in SKILL.md prose + exfil-combo/symlink-escape/typosquat checks); rest already-covered (skill-authoring→learn-skill, self-improving-agent bundle→existing skills, research/rag→wiki-memory) or out-of-scope-by-design (domain verticals); a 34-agent review workflow initially mis-reported the whole Rezvani cluster as "vaporware/404" from bare-URL WebFetch false-negatives — a single gh-api spot-check overturned that and surfaced the one real candidate | [[concepts/claude-skills-ecosystem-scan-2026-07]] |
| snarktank/ralph fresh-pass story queue + Brainer recipe-pilot harness | MEASURED-NULL, reverted | a three-arm PROMPTER pilot produced correct results in every arm, so no reliability gain was demonstrated; the 77.6% input-token reduction for queue-fresh came under synthetic 200 KB context pressure and does not establish billing savings or a real dropped-request fix. Harness/results/fixtures removed; reopen only after an observed natural multi-session failure. Recipe-index idea remains deferred, not implemented | [[queries/external-validation]] |

## Related

- [[concepts/adoption-covered-needs-merits-citation]] — the RULE this index enforces mechanically: a "covered" verdict needs a consumer `file:line` citation, not a catalog-line name-match; the 1-in-5-flips incident this page's Purpose section refers to
- [[queries/external-validation]] — denser per-source table for external loop/memory-doctrine articles specifically; most rows above are folded from it
- [[concepts/framework-hardening-adoption]] — earlier article-review session with the same 3-adoption pattern
- [[index]]
- [[schema]]
