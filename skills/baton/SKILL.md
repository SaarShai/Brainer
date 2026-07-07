---
name: baton
description: Drop/grab a verified session-handoff file — pass in-progress work to the next agent (future session, another window, codex) via .brainer/baton/
status: proposed
source: "https://github.com/blader/baton"
learned_at: 2026-07-01
requires_tools: 
disable-model-invocation: true
auto-install: false
---

# baton

> **Proposed skill** — born from `/learn`. Slash-only until trusted: it will NOT
> auto-fire. Promote with the telemetry-gated gate once usage proves it out:
> `python3 skills/learn-skill/tools/learn.py promote --name baton` (needs N
> consecutive recorded hits, no trailing abort — see `learn-skill/SKILL.md` → Trust).

Vendored from [blader/baton](https://github.com/blader/baton) (MIT), adapted to
Brainer conventions. A relay only works if the baton is passed cleanly: when you
hand work to another agent — a fresh window, a future session, a different
model — that runner starts with **zero of your context**. A baton is a single
markdown file capturing what the next runner can't reconstruct from the code or
git history — your *intent*, the *dead ends you already ruled out*, and the
*exact next step* — grounded in verified repo state, not your chat narrative.

Relation to [`context-keeper`](../context-keeper/SKILL.md): context-keeper is
*mechanical* extraction at PreCompact/SessionEnd; a baton is the *curated*
handoff document, and covers cross-agent handoffs (Claude→codex, pre-dispatch)
that no hook fires for. Complementary, not duplicates.

## When to Use

**Drop a baton when:**
- A session ends with work unfinished and someone/something will continue it.
- The user says "hand this off", "pick up later", "pass this to another agent".
- You're running low on context and want to checkpoint before it's summarized away.
- You're about to dispatch the rest of the work to a separate agent/session (e.g. `codex exec`).

**Grab a baton when:**
- Starting work in a repo where a prior session may have left one (check first:
  `ls -t .brainer/baton/ 2>/dev/null`).

**Don't use for:** a finished task (no handoff needed), or durable architecture
rationale (that belongs in the wiki via write-gate, not a baton).

## Procedure

### Where the baton lives

**`.brainer/baton/`** at the repo root (Brainer adaptation of upstream's
`.baton/` — keeps local scratch under the same git-ignored roof as
`.brainer/sessions/`). Created on first drop; ensure `.gitignore` covers it.
Filename: `<YYYY-MM-DD>-<short-slug>.md`
(e.g. `.brainer/baton/2026-07-01-formula-eval-rounding.md`).
The next agent finds the latest with `ls -t .brainer/baton/`.

### The Iron Rule: verify before you write

A baton built from the chat story instead of repo reality is worse than none —
it sends the next runner the wrong way with false confidence. Before writing,
run `git status` and `git branch --show-current` and confirm what is *actually*
committed vs. uncommitted. The "State of Play" section must reflect runtime
truth. If reality contradicts the narrative, **the baton documents reality**
and flags the gap.

### Drop — the baton format

Fill every section. If one is genuinely empty, write "none" — don't delete it
(the next runner relies on the shape being consistent).

```markdown
# Baton: <one-line title of the work>

**TL;DR:** <1–3 sentences: what this is, where it stands, the single next action.>

## Intent & Goal
Why this work exists and the desired end state. Include the acceptance
criteria — ideally the exact command/test that must go green.

## State of Play (verified against git)
- Branch: <branch> — confirmed via `git branch --show-current`
- Committed: <what's landed>
- Uncommitted / in flight: <what's in the working tree, from `git status`>
- Verified working: <what you've actually run and confirmed>
- Assumed / unverified: <what you believe but haven't proven>

## Learnings & Landmines
The highest-value section — what the next runner can't get from the code:
- Non-obvious discoveries.
- **Dead ends already ruled out** (so they don't repeat them) and *why*.
- **Do NOT touch** zones and the reason.

## Pointers
- Key anchors: `path/to/file.ts:123` — what's there.
- Relevant docs / prior batons / PRs.
- Commands to get oriented or reproduce: `<cmd>`.

## Next Steps
Ordered, concrete, immediate action first. Not "finish the feature" — the
literal next move.

## Open Questions
Unresolved decisions + your current lean (so they can proceed if no one answers).
```

After dropping, state the exact path written and a one-line summary of what's
in it.

### Grab — resuming

1. **Find it:** `ls -t .brainer/baton/` — read the newest.
2. **Trust but verify:** re-check "State of Play" against real `git status`
   before acting; the repo may have moved since the baton was dropped.
3. **Continue** from Next Steps.
4. **Retire it** when the work lands: delete it if it was only scratch, or
   promote durable learnings through [`write-gate`](../write-gate/SKILL.md)
   into [`wiki-memory`](../wiki-memory/SKILL.md), then delete. Don't let stale
   batons pile up.

## Pitfalls

| Mistake | Fix |
|---------|-----|
| Baton restates the diff | The diff is already in git. Capture intent, dead ends, next step. |
| Built from chat, not `git status` | Verify first — a confidently-wrong baton is worse than none. |
| Vague next step ("continue the work") | Write the literal next action. |
| Dead ends omitted | Naming what *didn't* work is the highest-value content — it saves a full re-derivation. |
| Scattered handoff location | Always `.brainer/baton/` at repo root — never elsewhere, or the next agent can't find it. |
| Stale batons pile up | Retire on land: delete, or promote learnings via write-gate → wiki, then delete. |

## Verification

- Drop side: the written baton's "State of Play" matches a fresh `git status` /
  `git branch --show-current` run (Iron Rule), every template section is
  present (or "none"), and the reply states the exact file path.
- Grab side: before acting, re-run `git status` and confirm or flag drift from
  the baton's State of Play.

## Failure modes

Premortem ([`LEARNING_CONTRACT`](../_shared/LEARNING_CONTRACT.md) §8):

- **Silent-failure path** — dropping a baton is a manual, model-invoked write with
  `disable-model-invocation: true` (slash-only); a session that runs out of context
  before anyone types `/baton` ends with zero handoff and nothing anywhere flags
  that the next agent is about to start from scratch on in-progress work.
- **Rot-when-unwatched** — batons are meant to be retired on land (deleted or
  promoted via write-gate), but nothing enforces that; an agent that grabs a stale
  baton without checking its date against current `git log` can act on dead-ends or
  a State of Play that no longer matches the repo, because the retirement step is a
  convention in this file, not a check any tool runs.
- **No-hooks host** — this skill is pure markdown-file convention with no hook and
  `auto-install: false`; on any host, a baton only gets written or read if a human
  or agent remembers the slash trigger, so the entire mechanism depends on
  attention rather than automatic enforcement.

<!-- Rationale (why this earns a skill) — scored by write-gate before commit:
Baton earns a skill because Brainer has no forward-handoff procedure: context-keeper is mechanical PreCompact/SessionEnd extraction, but nothing captures curated intent + dead-ends + literal-next-step when passing unfinished work to a fresh session, another window, or codex — so that the next agent doesn't re-derive ruled-out approaches (memory notes record codex fire-and-forget and subagent-handoff failures as recurring pain). Decision: vendor blader/baton (MIT, prompt-only, reviewed 2026-07-01, dedup verdict CREATE) rather than author from scratch, because its Iron Rule (verify State of Play against `git status`, never chat narrative) and its dead-ends-with-why section are field-tested phrasing we'd otherwise reinvent. Adapted to `.brainer/baton/` and retirement-via-write-gate→wiki so scratch never pollutes the durable store. Error avoided: a confidently-wrong handoff built from chat narrative sends the next runner the wrong way with false confidence — worse than no handoff.
-->
