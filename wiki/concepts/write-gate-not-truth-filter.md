---
schema_version: 2
title: "write-gate-not-truth-filter"
type: concept
domain: "eval-methodology"
tier: semantic
confidence: 0.5
created: "2026-06-06"
updated: "2026-06-06"
verified: "2026-06-06"
sources: []
supersedes: []
superseded-by:
tags: []
---

# write-gate-not-truth-filter

## Summary

One compact statement.

## Evidence

- Source or command path.

## Related

- [[index]]
- [[schema]]

## Open Questions

- None yet.

## Lesson

DECISION: the write-gate scores signal/form, not truth — `eval/exp5_adversarial` showed 8/8 confident-WRONG lessons PASSED it (mean score 4.88), identical to their correct twins. Memory-poisoning defense must come from provenance/trust (`skills/wiki-memory/tools/provenance.py`), not the gate, because the gate cannot adjudicate truth it cannot verify. The defense recovers the truth+poison coexistence case (dependent accuracy 0.5→1.0) given a verifier; the verifier-less poison-only case can only be flagged unverified.
