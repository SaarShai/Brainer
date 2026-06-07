---
schema_version: 2
title: "measure-triggers-by-decision-marker"
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

# measure-triggers-by-decision-marker

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

DECISION: measure skill-trigger behavior with an explicit decision marker (`HARVEST: yes|no`), not by keyword presence, because a vocabulary detector counts `wiki`/`write-gate` as a fire even when the model DECLINES (it names the loaded skills while reasoning). exp7's apparent over-fire (false-fire 0.5) was this artifact; with the explicit marker the true false-fire is 0.0. Fix lives in `eval/exp7_wiring/run_wiring.py` (parse the last HARVEST line).
