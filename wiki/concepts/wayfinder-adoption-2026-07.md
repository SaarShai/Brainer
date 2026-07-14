---
schema_version: 2
title: "Wayfinder adoption review — proposed local-first decision map"
type: concept
domain: "skill-authoring"
tier: semantic
confidence: 0.9
created: "2026-07-13"
updated: "2026-07-13"
verified: "2026-07-13"
sources:
  - "https://github.com/mattpocock/skills/tree/main/skills/engineering/wayfinder"
  - "https://www.aihero.dev/skills-wayfinder"
  - "local verification: make check and make check-tail"
  - "local verification: skills/learn-skill/tools/learn.py lint --file skills/wayfinder/SKILL.md"
  - "local verification: skills/security-oversight/tools/skill_audit.py skills/wayfinder --strict"
tags: [skills, wayfinder, adoption, planning, multi-session, decision-map]
supersedes: []
superseded-by:
---

# Wayfinder adoption review — proposed local-first decision map

## Summary

**Trigger / symptom:** an effort has a nameable destination but is too large or foggy to produce a trustworthy spec in one session.

**Verdict:** ADOPTED, adapted rather than vendored verbatim. A new proposed, slash-only `wayfinder` skill now owns the pre-spec decision map, and `plan-first-execute` routes nameable-but-unspecifiable work to it. This earns a separate skill because existing Brainer skills cover plans, user-intent ledgers, handoffs, and resolved memory, but none represents the unresolved-decision frontier or deliberately unformulated in-scope fog.

## Adopted

1. **Destination first.** Every map is scoped against a one- or two-line destination because the destination separates in-scope fog from work beyond the effort.
2. **Map as index, tickets as stores.** A resolution lives in exactly one ticket; the map keeps only named one-line pointers so that decisions do not drift across duplicate summaries.
3. **Fog versus ticket.** A precise question becomes a ticket even when blocked; an area whose question cannot yet be phrased remains Not yet specified rather than becoming a speculative task.
4. **Frontier and claims.** Open + unblocked + unclaimed tickets form the frontier; one non-research decision is resolved per session, and human-in-the-loop tickets require actual human input.
5. **Source pointers.** Brainer adds provenance to the destination, every ticket,
   and every non-empty Notes/fog/scope entry. Exploratory cold-Gemma runs informed
   this safeguard, but their raw output was not retained and is not counted as
   durable verification evidence.
6. **Plan handoff.** Zero active tickets plus empty fog hands the cleared route to `plan-first-execute`; Wayfinder plans decisions rather than implementing the destination.

## Rejected or adapted

1. **Mandatory GitHub issue machinery rejected.** Use an existing shared tracker only when it already supplies child items, dependencies, and claims; otherwise use serialized local markdown. Concurrent claims require a shared tracker or real lock. This preserves Brainer portability and the prior architect-loop decision rejecting factory infrastructure.
2. **Automatic research fan-out rejected.** Wayfinding has no automated correctness oracle, so it is an attended planning workflow rather than an autonomous generator-verifier loop. Research remains a claimed ticket handled by another session when useful.
3. **Upstream companion-skill dependencies adapted away.** Brainer does not require `/grilling`, `/domain-modeling`, `/prototype`, `/research`, or tracker setup skills across every host.
4. **Automatic invocation rejected for v1.** The learned skill is `status: proposed` and slash-only until usage telemetry earns promotion.

## Verification

- `make check PYTHON=/usr/bin/python3`: PASS.
- `make check-tail PYTHON=/usr/bin/python3`: PASS.
- Resident-context rebaseline followed the documented procedure: pre-change 7661B = 5308B descriptions + 2353B structure; post-change 7733B = 5380B descriptions + 2353B structure. Growth is exactly one 72B skill line; structure is byte-identical.
- `python3 skills/learn-skill/tools/learn.py lint --file skills/wayfinder/SKILL.md`: PASS.
- `python3 skills/security-oversight/tools/skill_audit.py skills/wayfinder --strict`: PASS.

## Related

- [[queries/covered-verdicts]]
- [[concepts/adoption-covered-needs-merits-citation]]
- [[concepts/architect-loop-adoption-2026-07]]
- [[concepts/honest-rebaseline-byte-budget-procedure]]
