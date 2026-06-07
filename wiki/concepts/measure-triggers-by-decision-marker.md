---
schema_version: 2
title: "measure-triggers-by-decision-marker"
type: concept
domain: "eval-methodology"
tier: semantic
confidence: 0.5
created: "2026-06-06"
updated: "2026-06-07"
verified: "2026-06-06"
sources: [eval/exp7_wiring/run_wiring.py]
supersedes: []
superseded-by:
tags: [eval-methodology, triggers, measurement]
---

# measure-triggers-by-decision-marker

## Summary

Measure skill-trigger firing by an explicit decision marker (`HARVEST: yes|no`), not by keyword presence — a vocabulary detector counts loaded-skill names as fires even when the model declines.

## Evidence

- `eval/exp7_wiring/run_wiring.py` — parse the last `HARVEST` line.
- exp7's apparent over-fire (false-fire 0.5) was the vocabulary-detector artifact; the marker gives true false-fire 0.0.

## Related

- [[concepts/optimization-axes]]
- [[concepts/framework-hardening-adoption]]
- [[index]]
- [[schema]]

## Open Questions

- None yet.

## Lesson

DECISION: measure skill-trigger behavior with an explicit decision marker (`HARVEST: yes|no`), not by keyword presence, because a vocabulary detector counts `wiki`/`write-gate` as a fire even when the model DECLINES (it names the loaded skills while reasoning). exp7's apparent over-fire (false-fire 0.5) was this artifact; with the explicit marker the true false-fire is 0.0. Fix lives in `eval/exp7_wiring/run_wiring.py` (parse the last HARVEST line).
