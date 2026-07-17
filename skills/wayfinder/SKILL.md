---
name: wayfinder
description: Experimental/manual decision-recovery workflow retained for paired evaluation. Invoke explicitly; frontier leads do not auto-load it.
status: experimental
source: "https://github.com/mattpocock/skills/tree/main/skills/engineering/wayfinder"
learned_at: 2026-07-13
trigger_type: model
risk_level: medium
host_support: [claude, codex, gemini, generic]
side_effects: [reads_repo, writes_files, network]
requires_tools: [read, write, edit]
disable-model-invocation: true
auto-install: false
---

# wayfinder

> **Manual during evaluation.** Invoke directly with `/wayfinder`; related
> planning skills may recommend that follow-up but do not auto-load it.

Adapted from Matt Pocock's
[Wayfinder](https://github.com/mattpocock/skills/tree/main/skills/engineering/wayfinder)
and its [companion article](https://www.aihero.dev/skills-wayfinder). It keeps the
source's decision-frontier model but uses Brainer's portable local-first
conventions instead of requiring a particular tracker or companion skill suite.

## When to Use

Use Wayfinder when an effort is too large or uncertain to turn into a
trustworthy spec or plan in one session: the destination can be named, but
important decisions cannot yet be phrased or ordered. This may follow a
recommendation from `plan-first-execute` or `/think`, or a direct request.

**Positive example:** `/wayfinder Map the decisions needed before we can specify
the multi-region migration.`

**Negative example:** `Add the already-specified retry flag and its unit test.`
That is ordinary `plan-first-execute` work, not wayfinding.

Skip it when [`plan-first-execute`](../plan-first-execute/SKILL.md) can already
produce a complete, gradeable `done means:` block. Wayfinder sits *before* a
spec. It clears decisions; it does not implement the destination.

When invoked after a recommendation, the same map-writing rules and user-scope
boundaries apply as for a direct `/wayfinder` request. Do not create, claim, close, or otherwise
mutate a decision map when `plan-first-execute` can already produce a complete,
gradeable plan.

## Procedure

### 1. Name the destination

Write one or two lines describing what a cleared route reaches: normally a
spec, a locked decision, or a changed state. The destination fixes scope; every
ticket and every patch of fog must point toward it.

The destination must quote or link the user's request, or be explicitly
confirmed by a named human. Never infer the scope anchor from plausible context.

Then map breadth-first. If the whole route is already clear and small enough for
one session, stop: use `plan-first-execute` instead of manufacturing a map.

### 2. Choose one canonical map

Prefer the project's existing issue tracker only when it already provides
shared child items, dependencies, and claims. Do not install or invent tracker
infrastructure for this skill.

Otherwise use:

```text
plans/wayfinder/<slug>/
├── MAP.md
└── tickets/
    └── <ticket-name>.md
```

Local markdown is suitable only for serialized sessions. It provides no atomic
claim operation between concurrent writers, whether they share a worktree or use
isolated worktrees. Use an existing shared tracker or a real locking mechanism
whenever sessions must claim work concurrently.

### 3. Keep the map low-resolution

The map is an index, not the decision store:

Every map statement must come from the user's request, verified research, or an
actual human exchange. Do not invent Notes, tickets, fog, dependencies, or scope
boundaries merely to make the map look complete; empty sections are valid. Make
this auditable: every non-empty Notes, Not yet specified, and Out of scope item
ends with `— source: <request | link | named human reply>`.

```markdown
# <map name>

## Destination
<one or two lines> — source: <request | named human confirmation>

## Notes
<domain, governing skills/docs, standing constraints — each with source pointer>

## Active tickets
- [<descriptive ticket title>](tickets/<name>.md) — <type>; <AFK | HITL>; <status>; blocked by: <named links or none>; claimed by: <owner or none>

## Decisions so far
- [<closed ticket title>](tickets/<name>.md) — <one-line gist>

## Not yet specified
<in-scope areas whose decision question cannot yet be stated precisely — each with source pointer>

## Out of scope
<ruled-out work plus why it lies beyond the destination — each with source pointer>
```

Refer to maps and tickets by descriptive names, with the name wrapping the
link. A filename slug such as `target-audience-profile` is not a descriptive
title. Never make a bare issue number or slug the human-facing identity.
Every active-ticket line must show all five fields: type, AFK/HITL mode, status,
`blocked by`, and `claimed by`; write `none` rather than omitting a field.

### 4. Separate tickets from fog

The test is whether the question can be stated precisely *now*, not whether it
can be answered now:

- **Ticket:** one precise decision or investigation question, even when blocked.
- **Not yet specified:** an in-scope area that cannot yet be phrased that
  sharply. Do not pre-slice it into speculative tasks.
- **Out of scope:** work the destination or a human decision actually rules
  beyond this effort. Do not invent exclusions merely to fill the section; an
  empty **Out of scope** section is valid. It never graduates into a ticket
  unless the destination is explicitly redrawn as a new effort.

Each ticket contains:

```markdown
# <ticket title>

- Type: research | prototype | discussion | prerequisite
- Mode: AFK | HITL
- Status: open | claimed | closed | out-of-scope
- Claimed by: <session/person or empty>
- Blocked by: <named ticket links or none>
- Source: <request | research link | named human reply>

## Question
<the one decision or investigation this ticket resolves>

## Resolution
<empty until resolved; then the answer, evidence, and asset links>
```

Ticket types:

- **Research** (agent-driven): establish an external or local fact a decision
  waits on.
- **Prototype** (human-in-the-loop): make a cheap concrete artifact so a human
  can judge how something should look or behave.
- **Discussion** (human-in-the-loop): resolve a judgment through live exchange;
  the agent must not answer for the human.
- **Prerequisite** (agent- or human-driven): perform the minimum manual action
  needed to expose facts for a later decision, not to deliver the destination.

Every ticket also declares its execution mode. Use **AFK** only when an agent can
resolve it without human judgment or action. Use **HITL** when a prototype,
discussion, approval, credentialed action, or other human input is required.
Prototype and discussion tickets are always HITL; research is normally AFK;
prerequisites must choose explicitly rather than inheriting a mode from type.

The **frontier** is exactly the open, unblocked, unclaimed tickets. Create all
currently precise tickets first, then wire dependencies in a second pass so
their identities exist before they are referenced.

### 5. Advance one frontier decision

Charting creates the map but resolves no ticket. In a later `/wayfinder` session:

1. Load `MAP.md`, not every ticket.
2. Use the named ticket, or choose the first frontier ticket.
3. Claim it before work. In local mode, first establish that no other writer is
   operating; write and re-read the claim only as confirmation, never as a lock.
   If concurrent claiming is possible, stop and use a shared tracker or real lock.
4. Resolve at most one non-research ticket in the session. Zoom into related
   tickets only as needed.
5. Put the full resolution in the ticket, close it, and append one named,
   one-line pointer under **Decisions so far**. Never duplicate the resolution
   in the map.
6. Graduate newly precise fog into tickets, then remove that text from **Not yet
   specified**. Update or close tickets invalidated by the resolution.
7. If work lies beyond the destination, close it as `out-of-scope` and record
   the linked reason under **Out of scope**, not **Decisions so far**.

Independent research tickets may be worked by separate sessions, but each must
obey the same claim and single-source-of-truth rules.

### 6. Hand off when the route is clear

The map is cleared only when there are no active tickets and **Not yet
specified** is empty. Then hand the destination plus **Decisions so far** to
`plan-first-execute` for the spec or implementation plan.

Use [`baton`](../baton/SKILL.md) only to transfer an unfinished session's live
state; use [`wiki-memory`](../wiki-memory/SKILL.md) for durable project decisions
after they are verified. Neither replaces the working decision map.

## Pitfalls

- **Implementation tickets:** the pull to build is the handoff signal. Stop when
  the route is clear unless the map's Notes explicitly override planning-only.
- **False precision:** an unknown is not automatically a ticket. Keep it as fog
  until its question is sharp.
- **Two sources of truth:** resolutions live in tickets; the map only links and
  gists them.
- **Synthetic human input:** never close a prototype or discussion ticket by
  inventing the human's reaction.
- **Unsafe local concurrency:** markdown claims are not atomic between any
  concurrent writers, including a shared worktree. Serialize or use an existing
  shared tracker or real lock.
- **Scope laundering:** out-of-scope work does not remain on the frontier or hide
  under **Not yet specified**. Conversely, do not invent exclusions unsupported
  by the destination or a human decision.
- **Map rot:** every close, invalidation, or graduation updates the map in the
  same session.

## Verification

- The destination is one or two lines, cites the request or named human
  confirmation, and every ticket/fog item points toward it.
- Every active ticket asks one precise question and has type, dependencies,
  AFK/HITL mode, status, claim ownership, and a source pointer visible in the
  ticket; operational fields are also visible in the map index.
- Every active-ticket index line visibly includes type, AFK/HITL mode, status,
  `blocked by`, and `claimed by`, using `none` for empty values.
- Frontier tickets are exactly open + unblocked + unclaimed; blocked, claimed,
  closed, and out-of-scope tickets are excluded.
- Every resolved decision appears once in its ticket and only as a named,
  one-line pointer in **Decisions so far**.
- A human-in-the-loop ticket contains actual human input before it closes.
- **Out of scope** contains only destination- or human-supported exclusions;
  empty is acceptable.
- Notes, tickets, fog, dependencies, and boundaries are traceable to the request,
  verified research, or actual human input rather than invented completeness.
- Every non-empty Notes, Not yet specified, and Out of scope item ends with a
  source pointer; an unsupported item is removed rather than rationalized.
- Completion means zero active tickets and an empty **Not yet specified** section.

<!-- Adoption rationale checked by write-gate:
Wayfinder earns a dedicated skill because Brainer's plan-first-execute starts when
a task is already specifiable, requirements-ledger tracks user intent rather
than project decisions, baton transfers session state, and wiki-memory stores
durable resolved decisions. None represents the unresolved-decision frontier or
deliberately unformulated in-scope fog. We adapt the source rather than adopting
it verbatim because its required grilling, domain-modeling, research, and
tracker-setup skills do not exist across Brainer hosts, and because Brainer
previously rejected mandatory GitHub issue machinery as infrastructure beyond a
portable skills framework. The local-first map preserves the distinct
decision-frontier mechanism so that multi-session planning does not invent
premature tasks or lose emerging questions.
-->
