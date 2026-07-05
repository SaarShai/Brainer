---
trust: verified
schema_version: 2
title: "team-lead upstreamed from screenery-lean (builder/verifier agents + protocol)"
type: concept
domain: "framework"
tier: episodic
confidence: 0.9
created: "2026-07-05"
updated: "2026-07-05"
verified: "2026-07-05"
sources: ["screenery-lean session f40db6e3 (Self-improving (FABLE))", "screenery-lean skills/team-lead/SKILL.md", "screenery-lean .brainer/sessions/*.md"]
supersedes: []
superseded-by:
tags: [orchestration, team-lead, builder, verifier, upstream, sibling-sync, adoption]
---

# team-lead upstreamed from screenery-lean

**Trigger:** user directive — the "Self-improving (FABLE)" session in
screenery-lean built a frontier-as-leader skill + builder agents; find how, what
was learned, adopt for Brainer.

## What was upstreamed (2026-07-05)

- `skills/team-lead/SKILL.md` — generalized from the screenery original:
  `.ai`/bracket routing removed (left as "domain tables extend this one"
  pointer), roster rewritten to Brainer's actual agents, cost discipline
  DEDUPED to a reference to `ORCHESTRATION.md §6` (which Brainer adopted from
  fable-advisor days earlier — the two converged independently on the same
  pattern).
- `.claude/agents/builder.md` + `.claude/agents/verifier.md` — ported
  near-verbatim minus domain references. Brainer previously had NO
  labor-tier lane worker and NO cold verifier agent.
- `verify-before-completion` rule 4 extended with two session lessons:
  **never sample a repeated element** (N things → N checks; space v29: judge
  crop-checked 1 reg mark of 20, false DONE) and **deliverable-shape
  invariants** (right file count/format, stale prior-version artifacts
  removed; anomaly ⇒ ask WHY, never a pass).

## The load-bearing evidence (why cold-verify is non-negotiable)

screenery forensic pass 2026-06-09: **24 of 25 false done-claims were
self-certified** — the editing context picks easy criteria, proxy evidence, or
claims done mid-closeout. This is the strongest empirical backing yet for
R3/R13 + the verifier agent; cited in team-lead §0.

## Deliberately NOT ported

- `judge` agent + skill (render-based `.ai` done-gate) — domain-specific;
  stays in screenery-lean.
- DPI / anchor / topology lessons — domain instantiations of "metric is
  necessary-not-sufficient; derive your own instrument" (the general form
  already shipped as verify-before-completion rule 6, vision-verify).
- T1/T2/T3 executor tiers — screenery's domain routing table; Brainer's
  general form is the ORCHESTRATION tier ladder.

## Propagation caveat

screenery-lean's `team-lead` is now the CUSTOMIZED sibling copy of a canonical
Brainer skill (reverse of the usual flow). On next `propagate`: classify it
CUSTOMIZED — do NOT fast-forward over its bracket/.ai routing; merge by hand if
canonical changes.

## Related

- [[queries/external-validation]] — fable-advisor row (ORCHESTRATION §6, the
  doctrine team-lead references)
- `skills/_shared/brief_header.py` — renders the §3 brief block
