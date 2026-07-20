---
schema_version: 2
title: "Handoff artifacts rot at their mutable values"
type: pattern
domain: patterns
tier: procedural
confidence: 0.9
created: 2026-07-20
updated: 2026-07-20
verified: 2026-07-20
sources: [.brainer/baton/2026-07-20-post-audit-remediation.md, skills/baton/SKILL.md, skills/context-keeper/tools/archive.py]
resource: skills/baton/SKILL.md
supersedes: []
superseded-by:
contradicts: []
tags: [baton, handoff, verification, cold-verify, context-keeper, rot, session-lifecycle]
---

# Handoff artifacts rot at their mutable values

A baton/handoff document is durable prose wrapped around **volatile facts**
(hashes, commit heads, byte sizes, test counts, agent ids). The prose stays true;
the volatile facts go stale the moment the repo moves — **because** they were
captured by copying a value at drop time instead of naming where the value lives.

Refreshing the document does not fix this. A refresh updates the occurrences the
author happens to look at, leaving the rest — so a *partially* refreshed handoff
is more dangerous than a stale one, because its freshness elsewhere earns trust
the stale lines don't deserve.

## Evidence (2026-07-20, screenery-design-master)

A baton was dropped, then refreshed after five further commits. The refresh still
left the canon pin wrong in **2 of 4 places**: quoted `1ca4b362…` where both
repos' `canon/canon.sha256` read `81a8edb2…`, plus a stale card size (4625 vs
live 4943 bytes). The stale value predated commit `c15d89e`, which regenerated
the card.

The successor session caught it **only because it was instructed to re-derive
evidence cold rather than trust the handoff.** A successor that accepted the
document — the normal, cooperative behavior — would have carried a wrong canon
hash into its own work and cited it downstream.

## Rule

- **Name the source, don't inline the value.** Write `` `cat canon/canon.sha256` ``
  rather than the digest. Rot-proof, and cheaper in tokens than any re-verify
  sweep.
- Where a literal genuinely helps a reader, **stamp it**: value + the date and
  command it was verified with, so a reader can see its age.
- **Instruct successors to cold-verify.** This is the control that actually
  caught the defect; it is not redundant with a careful drop.

## Related failure: the archive that never fires

Same session exposed a second lifecycle hole. `context-keeper`'s raw-transcript
archive is wired to `SessionEnd`, but the Claude desktop app has **no exit
action** — sessions go idle and never end, so the hook never fires and
`.brainer/sessions/raw/` stays empty. Compounding it, PreCompact checkpoints
only cover up to the last compaction, so a session's final stretch is missed by
both mechanisms (observed gap: 06:03 → 07:19, spanning two audits landing and
five commits).

Recovery, and the workaround until the skill is fixed — synthesize the payload
and fire the workers by hand:

```bash
printf '{"transcript_path":"%s","cwd":"%s","hook_event_name":"SessionEnd"}' "$T" "$PWD" \
  | python3 skills/context-keeper/tools/archive.py
```

Verified: produced a byte-identical 6,197,500-byte copy. The same trick with
`hook_event_name: PreCompact` into `tools/hook.sh` generates a checkpoint over
the final stretch.

**Generalization:** any hook bound to a lifecycle event the host never emits is
silently dead, and its failure mode is indistinguishable from "nothing needed
archiving." Check `docs/HOST_CAPABILITY_MATRIX.md` before trusting a
lifecycle-triggered guarantee.
