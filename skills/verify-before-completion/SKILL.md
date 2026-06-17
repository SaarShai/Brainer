---
name: verify-before-completion
description: Use before claiming work is done, fixed, passing, committed, or ready. Evidence before claims. Run the verification fresh; report exact command + output + remaining risk. For high-stakes or hard-to-reverse results, escalate to a separate cross-vendor verifier before shipping.
effort: low
pulse_reminder: before claiming done/fixed/passing, run a fresh verification command and quote its exact output. Evidence beats claims. High-stakes/irreversible result → cross-vendor verify before shipping.
---

# Verify Before Completion

Rule: evidence before claims.

> "If you have a fast, deterministic, agent-runnable pass/fail signal for the bug, you will find the cause. If you don't have one, no amount of staring at code will save you."  — *mattpocock/skills/engineering/diagnose*

The same applies to "done": without a fresh, runnable signal that proves the work is correct, "done" is a guess.

Before any completion/success claim:
1. Identify the command, inspection, or checklist that proves it.
2. Run or perform it fresh.
3. Read the output or result.
4. Re-read the ORIGINAL ask (or the plan's `done means:` block) and check **each criterion** — code-level green is not goal-level done.
5. Report the verification as a **per-criterion verdict** (criterion → pass/fail → the evidence line that proves it), not prose "done" — a claim with no per-criterion evidence is not a verdict. **Two-pass:** score it once from your own claims, then again from the artifact; any criterion that drops on the second pass is a refuted claim → NOT done (the hallucination signature).

Do not claim:
- tests pass without a fresh test run
- lint/build is clean without running it
- bug is fixed without reproducing the original symptom or a regression test
- delegated work is correct without inspecting result/diff
- ship/merge-ready without Live Proof: exercise the changed path on the real built artifact or service — a mock or simulation does not count
- a **visual / rendered** output (chart, diagram, UI, PDF, image) is correct without **looking at it** — screenshot or open the rendered artifact and verify it with vision; text-only checking misses occlusion, flattening, overlap, and scale

When dispatching verification to a subagent: mid-tier model (sonnet-class) with read-only tools is the default — verifying is cheaper than making; escalate only when the artifact demands frontier reasoning.

If verification is impossible, say what was not verified and why.

## Don't stop at the plan, and don't move the line

- **Anti-early-stop:** if your final paragraph is a *plan* or a *promise* ("next I'll…", "let me…"), do that work **now** — a described step is not a done step. Yield only for a genuine blocker: a destructive/irreversible action, a real scope change, or input only the user can give. (Mechanical backstop: the `early_stop` drift probe.)
- **Don't weaken the gate to pass.** A failing check is failing. Never lower a threshold/tolerance or relabel a FAIL→PASS mid-run to ship — that needs explicit human approval. Move the bar by *raising* it, never to wave work through.

## High-stakes: escalate to a cross-vendor verifier (inline, before shipping)

Steps 1–5 prove the work runs. For a **high-stakes or hard-to-reverse** result, "runs" is not "correct" — your own check shares your blind spots. Before shipping such a result, escalate to a **separate, preferably cross-vendor, read-only** verifier — the same mechanism as [`task-retrospective` Part D](../task-retrospective/SKILL.md#part-d--adversarial-cross-check-a-separate-preferably-cross-vendor-verifier-agent), fired **now** instead of at task-end.

**Fire (cost-gated — NOT every claim):** the output is hard to reverse (publish/send/merge/migrate/delete), money- or security-relevant, or a contested/load-bearing conclusion the user will act on. Trivial, internal, or easily-reverted results skip this and just use steps 1–5.

**How:** dispatch the OTHER vendor read-only and synchronous — `codex exec` (Claude→GPT), `claude -p --model opus` (GPT→Claude), or `gemini -p --approval-mode plan`. Hand it the result + evidence; ask it to re-run the key check and **refute if it can** (holds:bool, exit 0). See Part D for the full vendor table, channel caveats, the odd-N (default 3) majority rule, and the `loop`-spec. Agreement → ship. Refutation → do not ship; resolve or escalate to the user.

This is verification, not generation — a different foundation model catching errors, the one ensemble mechanism the evidence backs. It does NOT replace the task-end retro; it's the pre-ship gate for results that can't wait for it.

## Harvest the learning (before you call it done)

Completion is also the moment experience compounds. Before the final claim, decide whether to harvest with this **one-line test**:

> **Harvest IFF the task produced a _durable, project-specific_ lesson you would want a FUTURE session to recall.**

**Fire the harvest** — write the lesson to [`wiki-memory`](../wiki-memory/SKILL.md) via [`write-gate`](../write-gate/SKILL.md) — when ANY of these is true:
- **failure / bug** hit and fixed → the prevention rule;
- **feedback / correction** received (user, review, red test) → the corrected rule + *why*;
- **reusable success** → a non-trivial procedure worth repeating.

**Do NOT harvest** (this is the discipline cross-model testing showed models get wrong — both over- and under-firing): plain acknowledgements/thanks, ephemeral or general-knowledge questions (arithmetic, definitions, one-off lookups), chit-chat, or any task that produced **no new project-specific fact**. When unsure, re-apply the one-line test — if you would not retrieve this next session, skip.

Both directions are failures: an un-harvested genuine lesson doesn't compound, and a spurious harvest pollutes memory (and `write-gate` only filters *low-signal* noise, not *off-topic* writes). The one-line test is the gate. (Harvest logic lives in `wiki-memory`; this is the reflex that fires it — including on quick, unplanned tasks `plan-first-execute` never sees.)
