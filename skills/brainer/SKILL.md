---
name: brainer
description: "Use when the user explicitly says `/brainer` or asks to use any relevant Brainer skill: inspect the optional-method reference, select the smallest task-relevant set, and apply only exported methods or complete skill contracts as declared. Never auto-fires."
status: proposed
disable-model-invocation: true
auto-install: false
trigger_type: slash
risk_level: low
host_support: [claude, codex, gemini, generic]
side_effects: [reads_repo]
requires_tools: [read]
effort: low
pulse_reminder: select the smallest sufficient optional set from REFERENCE.md; method exports may be partial, whole skills may not; no selection is valid and /brainer grants no new authority.
---

# brainer — task-local optional-skill selection

`/brainer` lets the user delegate optional Brainer-method selection instead of
remembering skill names. It is a manual meta-skill, not a default router.

## When to Use

Invoke when the user's message starts with `/brainer`, or when the user
explicitly says to use any relevant/helpful Brainer skill for the current task.
Treat the rest of that message as the task. The umbrella request authorizes
otherwise-manual Brainer *methods*, subject to the boundaries below.

Do not activate from a merely difficult task, a mention of Brainer, or a request
to list skills. Do not keep it armed for later unrelated tasks.

## Procedure

1. Read [`REFERENCE.md`](REFERENCE.md) completely. It is the on-demand selection
   index; the short resident skill descriptions are not enough for
   instruction-level selection.
2. Identify observable task needs—not keywords—including uncertainty,
   unresolved decisions, scope risk, iterative verification, evaluation,
   handoff, learning, or cross-repo coordination. Reassess only when the task
   materially changes phase.
3. Shortlist the smallest sufficient set. Every candidate must address a
   distinct need or failure mode. An empty shortlist is valid and preferred
   over ceremony.
4. Read every shortlisted source skill completely before final selection, then
   respect the reference's mode. **Do not announce or finalize a selection
   before these source reads finish**; a shortlist is provisional, not a
   selection:
   - **method** — use only the named exported method. Read its source skill
     completely, report the exact stable method name, and do not treat unrelated
     sections as activated.
   - **whole** — load and follow the entire source skill; never cherry-pick its
     safeguards.
   - **authority-gated** — check whether the task already supplies the named
     authority. If yes, load and follow the complete source skill. If not,
     recommend the route without executing it.
5. A selected skill's own mandatory routes, prerequisites, and conflict rules
   remain authoritative. User instructions and project rules outrank this
   selector.
6. Before any task-specific investigation or task tool call, state the final
   selection compactly in the first useful progress update: skill or exact
   exported method, the task signal it addresses, and whether an authority gate
   was satisfied or deferred. Reads needed to obey higher-priority instructions
   or to complete steps 1–5 are selection bootstrap, not task investigation.
   Then perform the behavior; do not recite the index. A selection reported only
   after the work is explanatory bookkeeping, not valid `/brainer` routing.
7. At a real phase transition—such as diagnosis to implementation or
   implementation to closeout—reassess once. Drop methods whose trigger no
   longer applies; do not accumulate a permanent stack.

## Authority boundary

`/brainer` grants permission to choose optional reasoning and workflow methods.
It does **not** independently authorize destructive actions, external writes,
subagents, propagation to sibling repositories, persistent-memory writes,
creation of a new skill, or an after-the-fact audit. Those actions still require
the task itself or the selected skill's normal trigger to place them in scope.
The task text following `/brainer` is still user authority: do not discard an
explicit "sync", "delegate", or "write" request merely because it appears in
the same message as the meta-skill trigger.

Default/mechanical Brainer facilities continue under their normal triggers and
are not part of the discretionary selection result.

Selection identifiers are exact: `<skill>:<export-id>` for a method,
`<skill>:whole` for a whole contract (including an authority-gated skill whose
gate is satisfied), and `none` for an empty selection. A bare skill name is not
a valid final selection because it hides whether the agent used a method or the
complete contract.

## Pitfalls

- **Skill soup:** selecting several overlapping disciplines because they sound
  useful. Keep the one that addresses the actual constraint.
- **Name matching:** routing from words such as "plan" or "learn" without the
  skill's observable condition. Judge the task, not its vocabulary.
- **Late selection:** investigating the task first and naming methods afterward.
  The selection must shape the work, not rationalize it after the fact.
- **Unsafe excerpts:** borrowing one convenient step from a `whole` skill while
  omitting its verifier, rollback, or authority boundary.
- **Hidden scope expansion:** treating umbrella skill permission as permission
  to create artifacts, dispatch agents, or touch sibling repositories.
- **Stale index confidence:** trusting a dangling section pointer. The reference
  liveness test must pass; otherwise load the source catalog and report degraded
  selection.

## Verification

```bash
python3 skills/brainer/eval/test_reference.py
```

That vendored test is the portable check in every consumer. In the canonical
Brainer checkout, run the additional repository checks only when present:

```bash
for check in scripts/check_skill_contracts.py scripts/check_carrier_sync.py; do
  if test -f "$check"; then python3 "$check"; else echo "NOT AVAILABLE: $check"; fi
done
```

`NOT AVAILABLE` is not a pass. Report it as unavailable; never claim a missing
check succeeded.

A selection is behaviorally sound only when it names a real task signal, uses
an exported `method` or complete `whole` contract, respects authority, and
allows a no-skill outcome. Static tests prove index integrity, not model
judgment.

## Failure modes

- **Silent failure:** the agent acknowledges `/brainer` but never reads the
  reference or reports a grounded selection; the user receives ordinary agent
  behavior disguised as routing.
- **Rot when unwatched:** skill headings or activation contracts change while
  the reference still points at the old surface. The registered reference test
  checks every source and heading and includes a broken-anchor negative case.
- **No-hooks host:** no hook is required. Claude, Codex, Gemini, or a generic
  agent follows the literal slash trigger from its resident catalog and reads
  the vendored reference. If that file is absent, report degraded mode and do
  not guess from skill names.

## Related skills

- [`think`](../think/SKILL.md) — first skill exporting independently selectable
  methods.
- [`plan-first-execute`](../plan-first-execute/SKILL.md) — complete planning
  workflow when the task meets its threshold.
- [`wayfinder`](../wayfinder/SKILL.md) — complete decision-recovery workflow for
  a known destination with a foggy route.
- [`learn-skill`](../learn-skill/SKILL.md) — authors skills only when separately
  authorized; it is not the selector.
