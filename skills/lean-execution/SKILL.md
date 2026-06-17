---
name: lean-execution
description: Prune plans, process, context, and delegation to the smallest safe path. Trigger when the user asks to simplify, be lean, reduce process, remove steps, or cut rot; or when a plan has more steps than the task seems to need.
effort: low
---

# Lean Execution

## Principle

Maximize work not done. Keep only steps that reduce risk, gather needed facts, implement, verify, or preserve durable learning.

## Protocol
1. Name the desired outcome in one sentence.
2. Inspect only facts needed to choose the next safe action.
3. Prune planned steps that are duplicate, speculative, ceremonial, stale, or reversible without planning.
4. Understand before deleting: if the reason for a step or codepath is unclear, preserve or inspect narrowly.
5. Prefer the smallest reversible action that produces value or evidence.
6. Scope simplification to the active task; avoid drive-by refactors.
7. Delegate only when saved main-context/tool cost exceeds orchestration overhead.
8. Stop and simplify when a workflow starts creating more artifacts than outcome.
9. Verify with the cheapest sufficient check.

## Keep

- safety checks, tests, direct verification
- durable decisions and exact failure evidence
- docs that prevent repeated future work
- project conventions and intentional abstractions

## Delete

- broad research before relevance is clear
- speculative abstractions/features
- duplicate validation
- stale plans/backlogs
- raw logs/transcripts when a compact cited packet is enough
- memory/docs for trivial one-off facts with no reuse value

## Risk

Do not use "lean" to skip necessary context, tests, user approval for risky choices, or docs that prevent recurrence.

## Autonomy — keep going unless you truly need me

Pause for the user ONLY when the work genuinely requires it: a **destructive or irreversible** action (delete / overwrite / publish / send / merge / migrate / charge), a **real scope change**, or **input only the user can provide**. Otherwise proceed through routine, reversible, in-scope steps and report back when done — don't stop to ask permission for work you can safely do and undo. Over-pausing wastes a turn; so does bundling a genuine risk into "just proceeding". (The `early_stop` probe backstops the opposite failure — narrating the next step instead of doing it.)

## Keep instructions short

A brief outcome instruction beats enumerating every case — over-prescription degrades frontier models, which already infer the cases you'd have listed. When a skill or prompt underperforms, suspect it's too LONG before too short: instructions written for weaker models usually need **trimming, not extending**. Cut to the smallest wording that still pins the outcome.
