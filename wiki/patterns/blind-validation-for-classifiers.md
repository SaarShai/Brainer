---
schema_version: 2
title: "Blind-validation for deterministic classifiers"
type: pattern
domain: patterns
tier: procedural
confidence: 0.9
created: 2026-06-14
updated: 2026-06-14
verified: 2026-06-14
sources: [skills/wiki-memory/tools/claim_grade.py, skills/wiki-memory/tools/test_claim_grade.py]
resource: skills/wiki-memory/tools/claim_grade.py
supersedes: []
superseded-by:
contradicts: []
tags: [validation, eval, classifier, claim-grade, methodology, falsification]
---

# Blind-validation for deterministic classifiers

When building a heuristic classifier (claim-typing, contradiction detection, any
marker-based labeler), validate it against an **independent blind-labeled
corpus**, not only a self-authored gold set — **because** a self-gold overfits to
the author's own intuitions and gives a falsely high score.

## Evidence (the falsification that motivated this)

`claim_grade` scored **93.6% on its self-authored gold** but **28% against
independent blind labels** on real PROMPTER claims. The gap was real
generalization failure: the default-to-`observation` prior misgraded
directive-heavy SOP prose. The blind round caught what the self-gold could not.

## Procedure

1. Extract real claims from an actual corpus (e.g. `PROMPTER`), normalized and
   readable (don't blank wikilinks/code spans — it mangles the text and labels).
2. Have **N independent agents blind-label** them (no access to the classifier's
   output) — a dynamic workflow with one labeler agent per pass.
3. Reconcile by majority; **report inter-annotator agreement**. Low agreement
   (~40% unanimous on messy SOP prose, measured) is itself a signal: the task is
   ambiguous for humans too, **so** the classifier should ABSTAIN there, not
   force a label.
4. Measure precision-when-confident + coverage vs the human-majority gold; mine
   the disagreements (some "errors" are the classifier being right vs noisy 2/3
   human votes).

## Lessons (transferable)

- **Abstain-on-no-marker beats a forced default** — emitting `unknown` keeps a
  noisy label out of downstream logic, **so that** unknowns can't trigger false
  contradictions or false promotions. High precision + abstention > high recall.
- **Ship noisy heuristics as report-only lenses, never gates** — `claim-audit` /
  `synth-candidates` / `maturity` advise an agent; they do not auto-edit, **to
  avoid** a wrong label silently corrupting memory.
- **Bound marker regexes** — an unbounded `.+`/`.*` between word anchors
  backtracks catastrophically (a 73KB page hung a scan ~42s). Bound the gap.
- See [[schema]] and [[concepts/wiki-governance]] for where typed claims fit.
