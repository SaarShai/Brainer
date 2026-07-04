---
schema_version: 2
title: "4-layer memory architecture article — evaluation vs Brainer, Layer 2 + 3 rejected"
type: concept
domain: "memory-architecture"
tier: semantic
confidence: 0.92
created: "2026-07-03"
updated: "2026-07-03"
verified: "2026-07-03"
sources:
  - "article: '4-layer memory architecture' (identity+index / auto-retention / shared live-context log / searchable wiki)"
  - "github.com/vectorize-io/hindsight (v0.2.0, 17,959 stars, MIT)"
  - "session evaluation 2026-07-03: 4-sandbox A/B test (Layer 3), Hindsight infra audit (Layer 2), prior memory-evaluation precedents"
tags: [memory, article-adoption, multi-agent, concurrency, negative-result, ab-test]
supersedes: []
superseded-by: []
---

# 4-layer memory architecture article — evaluation vs Brainer, Layer 2 + 3 rejected

## Summary

**Trigger / symptom:** evaluated "4-layer memory architecture" article (identity+index / Hindsight auto-retention / shared live-context log / searchable wiki) against Brainer adoption, with particular focus on Layers 2 and 3 as potential new mechanisms.

**Finding:** Layers 1 and 4 already match Brainer's architecture exactly (no action needed). Layer 2 (PostgreSQL+pgvector semantic recall) rejected on infra-stack mismatch + measured prior negative results. Layer 3 (shared live-context log for concurrent diffs) A/B tested on the actual incident condition and rejected: the log prevents pre-existing diffs only, not mid-run-appearing diffs (the real danger window). Adopted instead: smallest verified-relevant delta — "Foreign diffs are not damage" writer-brief rule for loop-engineering.

## Why (decisions)

1. **Layer 1 (identity file + always-loaded index) — no action.** The article describes: a local identity/metadata file + a compact file-per-fact index loaded at boot. Brainer already implements this exactly: `CLAUDE.md` (identity + resident trigger list), `MEMORY.md` (user auto-memory, persists across sessions with index structure), `wiki/L1_index.md` (compact pointers). **Because:** this pattern is the proven minimal-context memory surface; Brainer's bootstrap loads it consistently before any per-project work.

2. **Layer 4 (compiled searchable wiki) — no action.** The article describes: a searchable knowledge base built from accumulated facts. Brainer covers this via `wiki-memory` skill: progressive retrieval (search→timeline→fetch), verified-facts-only writes enforced by `write-gate`. **Because:** the mechanics are already implemented; the wiki is actively maintained and linted per `schema.md`.

3. **Layer 2 (Hindsight auto-retention + semantic ranking) — rejected on infra and precedent.** The article's primary innovation: automatic capture + LLM extraction + semantic-vector indexing (PostgreSQL+pgvector, 1536-dim embeddings, FastAPI, docker deployment, JWT/OAuth, OTel). **Because:** (a) Infra-stack mismatch — Brainer's markdown-first bet rejects heavy external services (no docker, no Postgres, no external API deps). (b) Measured prior negative results: `queries/memory-as-a-tool-validation.md` A/B tested write-gate (Brainer's verified-ingest mechanism) on memory-as-a-tool baseline — gated arm 6.62 vs ungated 8.62; write-gate SUBTRACTED quality. (c) Confidence precedent: three earlier memory features (session-recall, memory-decay, handoff-as-external-service) were all removed from `eval/FINDINGS.md` Catalog after "no measured Δ" evaluations; compounding rejections on the same layer raise the bar for Layer-2-style mechanisms. Kept as reference pointer: Hindsight is a plausible **external semantic-recall backend** for a consuming project that outgrows markdown; its "promoted path" (auto-capture → human review → index) is already Brainer's posture via `write-gate/task-retrospective`.

4. **Layer 3 (shared live-context log to prevent concurrent diffs) — tested and rejected.** The article describes: a log appended by every agent in a shared tree, read at dispatch time to detect concurrent work and avoid re-applying it. **Test condition:** 2026-07-03, 4-sandbox A/B, scratchpad/memtest (generator=codex GPT-5.5 via plugin, verifier=deterministic git script). **Control arm (no protocol):** planted uncommitted `utils.py` diff in a clean tree, then fired two concurrent codex runs; both preserved the planted diff AND passed the task (2/2 + 2/2). **Live-context-log arm:** same setup, both runs read the log at start, appended their own entry, preserved the diff, and followed protocol (2/2 + 2/2). **Result:** null lift — the log adds nothing for PRE-EXISTING diffs. **Incident analysis:** The real 2026-07-03 codex incident that motivated this test had a different condition: tree was clean at executor start, concurrent diffs appeared MID-RUN, strict-scope brief language caused the executor to treat them as self-damage and restore-to-clean. A log read at START OF RUN cannot detect diffs that appear during execution. **Because:** the danger window is DURING a run, not at dispatch; testing pre-existing diffs would have shipped a useless convention file without the distinction. **Durable insight:** the test validated the diagnosis — the mechanism does not address the actual failure mode.

5. **Adopted instead: "Foreign diffs are not damage" writer-brief rule.** The smallest verified-relevant delta. Added to `skills/loop-engineering/SKILL.md` orchestration section: every writer brief into a shared tree carries the directive — "diffs you did not create are concurrent work — never revert/restore/clean; report instead". **Because:** executors respect pre-existing dirty trees unprompted, but mid-run-appearing foreign diffs are misidentified as self-damage. This rule names the condition and blocks the error path without requiring a log or protocol. Measured on the A/B test incident shape; no measured cost.

## Incident learned

**Codex-revert-concurrent-diffs incident:** a codex-rescue agent implementing strict-scope work believed that mid-run-appearing uncommitted edits to `SKILLS_INDEX.md`, `MEASUREMENT_QUEUE.md`, and a GLM agent's loop_lint.py were "out-of-scope diffs since initial git status was clean" and reverted them as damage. Only .gitignored paths survived. This is a failure mode specific to executors with high confidence in their own scope boundaries.

**Decision:** Isolate the danger window. A log read at start-of-run covers pre-existing state; concurrent appearance requires a different mechanism or acceptance of the drift.

## Durable insights

- **Test the incident's actual condition before adopting an article's mechanism.** The A/B test planted pre-existing diffs (article's tested scenario) but the real incident involved mid-run diffs (untested). Testing only the article's scenario would have shipped a useless convention file. This is a special case of the measurement-before-adopting discipline.

- **Executors treat pre-existing dirty trees and mid-run-appearing foreign diffs differently.** Pre-existing: respected, never reverted, unprompted. Mid-run: misidentified as self-damage in high-confidence-scope contexts. The danger window is DURING execution, not at dispatch.

- **18k stars ≠ architectural fit.** Hindsight is a solid external tool (active, MIT, stars indicate reach) but the postgres-vector-fastapi stack is orthogonal to Brainer's markdown-first bet. Architectural fit is a prior to adoption; measured gaps are a secondary gate.

- **Three memory-layer rejections compound.** Layer 2 (auto-extraction), Layer 3 (live-context log), and prior features (session-recall, memory-decay) all show "no measured Δ or measured negative Δ". The pattern suggests incremental memory mechanisms beyond L1+L4 carry a high burden of proof in this system.

## Related

- [[concepts/harness-article-adoption-2026-07]] — parallel article-evaluation session on the same day; same 3-adoption pattern; validates the measurement-before-adopting discipline.
- [[concepts/premortem-and-think-edits-measured]] — article-pitched additions usually confirm/reject, rarely net-new; measured wins and measured rejections on evidence.
- [[queries/memory-as-a-tool-validation]] — write-gate A/B test showed no improvement (6.62 vs 8.62 ungated); precedent for Layer-2-style mechanism rejection.
- [[concepts/lean-execution]] — measure before adding; enrich existing over create new.
- [[skills/loop-engineering/SKILL.md]] — orchestration section now carries the "Foreign diffs are not damage" writer-brief rule.
- [[concepts/systematic-debugging-skill-measured-null]] — sibling precedent: article-pitched skill A/B'd and rejected.

## Open Questions

- Does the "foreign diffs are not damage" brief rule reduce executor errors on shared trees? (Condition: next concurrent-executor incident; metric: reduction in surprise reverts.)
- Is Hindsight's semantic-ranking layer worth evaluating as an external backend for a future memory-plus-retrieval layer? (Deferred: depends on retrieval gaps in current system.)
