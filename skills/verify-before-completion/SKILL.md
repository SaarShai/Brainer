---
name: verify-before-completion
description: Use before claiming work is done, fixed, passing, committed, or ready. Evidence before claims. Run the verification fresh; report exact command + output + remaining risk.
effort: low
pulse_reminder: before claiming done/fixed/passing, run a fresh verification command and quote its exact output. Evidence beats claims.
---

# Verify Before Completion

Rule: evidence before claims.

> "If you have a fast, deterministic, agent-runnable pass/fail signal for the bug, you will find the cause. If you don't have one, no amount of staring at code will save you."  — *mattpocock/skills/engineering/diagnose*

The same applies to "done": without a fresh, runnable signal that proves the work is correct, "done" is a guess.

Before any completion/success claim:
1. Identify the command, inspection, or checklist that proves it.
2. Run or perform it fresh.
3. Read the output or result.
4. Report the exact verification and any remaining risk.

Do not claim:
- tests pass without a fresh test run
- lint/build is clean without running it
- bug is fixed without reproducing the original symptom or a regression test
- delegated work is correct without inspecting result/diff

If verification is impossible, say what was not verified and why.

## Harvest the learning (before you call it done)

Completion is also the moment experience compounds. Before the final claim, harvest any lesson this task produced into [`wiki-memory`](../wiki-memory/SKILL.md) via [`write-gate`](../write-gate/SKILL.md):
- **failure / bug** hit and fixed → the prevention rule;
- **feedback / correction** received (user, review, red test) → the corrected rule + why;
- **reusable success** → the procedure.

Unharvested experience doesn't compound: a verified-done task whose lesson was never written teaches nothing for next time. Skip only when nothing non-trivial happened. (The harvest logic lives in `wiki-memory`; this is the reflex that fires it — including on quick, unplanned tasks that `plan-first-execute` never sees.)
