---
trust: corroborated
schema_version: 2
title: "Memory-as-a-Tool validates the paper's method; Brainer's write-gate did NOT add value on top"
type: decision
domain: "concepts"
tier: episodic
confidence: 0.6
created: "2026-06-25"
updated: "2026-06-25"
verified: "2026-06-25"
sources: ["arXiv:2601.05960", "GLM matrix run results/glm_matrix.json"]
supersedes: []
superseded-by:
tags: [decision, eval, memory, negative-result]
---

# Memory-as-a-Tool: paper method validated; Brainer write-gate did NOT add value here

## What was tested

4-arm matrix, agent=glm-4.6, judge=glm-5.2 (via z.ai), n=4 samples/cell:
- **baseline** — no memory, no feedback
- **memory_only** — accumulate prior outputs, no method
- **paper_mem** — Memory-as-a-Tool (arXiv:2601.05960), the paper's method as-is
- **brainer_mem** — paper_mem + `write_gate.py` prune between samples (Brainer's signal-gate)

Question: does Brainer's write-gate add value ON TOP of the paper's method?

## Result

| arm | visual_writing | claude-like | chaotic_writing |
|-----|---------------|-------------|-----------------|
| baseline | 6.88 (±3.40) | 2.75 (±1.09) | 1.00 (±0.71) |
| memory_only | 6.19 (±3.37) | 2.75 (±1.09) | 1.00 (±0.71) |
| **paper_mem** | **8.62 (±0.41)** | 2.25 (±1.30) | 1.00 (±1.00) |
| brainer_mem | 6.62 (±3.54) | 3.25 (±0.43) | 0.75 (±0.43) |

## Decision

1. **Paper method validated** on the one task with real signal (visual_writing): paper_mem
   8.62 vs ~6.x for every other arm, and variance collapsed ±3.40 → ±0.41. Memory-as-a-Tool
   works. Confirms the file-based-memory bet.

2. **Brainer's write-gate did NOT add value — it subtracted** (brainer_mem 6.62 < paper_mem
   8.62, and back up to baseline variance ±3.54). Prune-between-samples removed context the
   paper's method was using. **Negative result, recorded honestly: gating helps findability,
   not generation quality, on this domain.** Do not assume Brainer's memory-gating improves
   downstream quality without a per-domain test.

## Caveats (cap how far this generalizes — do not over-read)

- **n=4 per cell.** Tiny. Treat all deltas as directional, not significant.
- **chaotic_writing is degenerate** — GLM-4.6 refuses the anti-rubric task; all arms ~1.0.
  Model-capability limit, not a memory signal. Excluded from conclusions.
- **claude-like brainer lift (3.25 vs 2.75) is within noise** at n=4. Low confidence.
- **mixed arm incomplete** — only baseline (0.49) ran; 3 of 4 arms missing. No cross-category
  headline number exists. Recorded as-is per decision; not re-run (GLM budget).

## Consequence for the hygiene plan

- Phase 4 (retrieval `trigger:`/`symptom:` cue) keeps the paper's "semantic filename =
  retrieval key" justification ONLY. The "Brainer memory mechanisms help" crutch is struck —
  this matrix is the first empirical test of a Brainer memory mechanism and it lost.

## Related

- [[queries/external-validation]] — companion external-review corroboration record
- [[index]]
- [[schema]]
