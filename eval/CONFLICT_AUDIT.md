# Cross-skill conflict audit (#3)

**Question:** when two skills are in context at once, do their directives fight —
e.g. one suppressing behavior another requires?

## Realistic co-occurrence model

Only SKILL.md **bodies** that share the model's context can textually collide.

- **Always-on body:** `caveman-ultra` (`output_style: true`, resident from turn 1).
- **Process-level hooks** (`skill-pulse`, `compliance-canary`, `prompt-triage`,
  `context-keeper`): inject reminders / run subprocesses — they do **not** put a
  competing prose body in context, so they can't textually conflict. (But their
  *probe configs* can encode a policy that fights a skill — see the one real
  collision below.)
- **Trigger-loaded bodies:** every other skill loads its body only when its
  trigger fires. So the live pairings are `caveman + <one triggered skill>`, or
  two skills co-triggered by one prompt.

## Method

1. **Deterministic lint** — `eval/skill_audit.py --conflicts` tags each body's
   directive lines on policy axes (verbosity, planning, delegation, evidence)
   with tight, no-`.*` lexicons + a cross-reference filter, and reports
   opposing-polarity pairs. **Mutation-validated** (a planted "be thorough" vs
   "keep replies short" pair IS caught), so a clean verdict is non-vacuous.
2. **Curated reading** of every axis that looked risky, to rule out textual
   clashes that have an explicit carve-out (the prior false-positive lesson: a
   clash with a carve-out is not a runtime collision).

## Result

`skill_audit.py` reports **0 SKILL.md-vs-SKILL.md directive conflicts** and **0
near-duplicate directives** across the 16 bodies.

Curated verification of the axes that *looked* contentious:

| Axis | Apparent clash | Verdict | Why |
|---|---|---|---|
| verbosity | `caveman` terse vs tasks needing length | **carve-out covers it** | caveman: "Keep replies short **unless the user asks for detail**" + "Full prose when … ambiguity". Self-qualified. |
| evidence | `caveman` terse vs `verify-before-completion` / `compliance-canary` "quote output / show evidence" | **no starvation** | caveman: "Preserve code blocks, paths, numbers, math, **exact errors verbatim**" — verification output IS numbers/exact errors, explicitly preserved. |
| planning | `plan-first-execute` "plan before" vs `lean-execution` "prune steps" | **compose by design** | plan-first body literally says "Simplify (see `lean-execution`)". Plan, then prune the plan — sequential, not opposed. |
| reasoning | `think` (reason deeply) vs `caveman` (terse) | **orthogonal** | caveman: "Changes emitted **prose** only. Reasoning budget separate." think shapes reasoning, caveman shapes output. |
| delegation | `think` "launch subagents to research" vs `lean`/`index-first`/`prompt-triage` "delegate only when it pays" | **conditional, not contradictory** | think gates on *value* (research would pay), lean gates on *cost* (saved > overhead). Both are "delegate iff worth it". |

## The one real collision (found + fixed)

It was **not** between two SKILL.md bodies — it lived in a **drift-probe config**,
which is why the body-scoped lint above doesn't flag it (scope note):

- `compliance-canary`'s `word_count_per_message` probe (and caveman's own
  `word-creep` probe) fired on verbose replies **regardless of whether the user
  asked for detail** — nagging against caveman's own "short *unless detail is
  requested*" carve-out. Observed live: it fired this session on two consecutive
  detail-request turns.
- **Fix (2026-06-14, shipped):** opt-in `warrant_pattern` on the probe. The
  warning governs the *next* reply, so it warrants on the incoming prompt; a
  detail/depth/enumeration request suppresses it. 6/6 detail prompts suppress,
  5/5 trivial still fire. Tests canary `[39]`/`[40]`.

## Conclusion

The suite is conflict-free at the SKILL.md level — by design, via explicit
carve-outs and cross-references, not by luck. The single operational collision
was a probe-config policy that didn't honor a skill's own carve-out, now fixed.
`skill_audit.py` is retained as a standing regression guard (fails on any newly
introduced directive conflict or near-duplicate).
