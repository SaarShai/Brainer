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
- bug is fixed without reproducing the original symptom or a regression test — write the test that FAILS before your change and passes after; test observable behavior that can break, not internal wiring (a field a constructor sets)
- delegated work is correct without inspecting result/diff
- ship/merge-ready without Live Proof: exercise the changed path on the real built artifact or service — a mock or simulation does not count
- a **visual / rendered** output (chart, diagram, UI, PDF, image) is correct without **looking at it** — screenshot or open the rendered artifact and verify it with vision; text-only checking misses occlusion, flattening, overlap, and scale
- a **security-sensitive** change (auth / secret / dependency / dangerous sink) is safe without triaging the diff — run [`security-oversight`](../security-oversight/SKILL.md) for the HIGH/REVIEW list, then verify those zones; a leaked secret or injected sink that ships is not "done"

When fixing a bug, investigate before editing: reproduce it, read the whole error and stack trace, change one thing at a time. Don't add a guard for a failure whose root cause you haven't located — a null-check over an unexplained null just moves the bug somewhere quieter.

When dispatching verification to a subagent: mid-tier model (sonnet-class) with read-only tools is the default — verifying is cheaper than making; escalate only when the artifact demands frontier reasoning.

If verification is impossible, say what was not verified and why.

### Make the verdict mechanical: `tools/verify_artifact.py`

Steps 1–5 above are prose; this tool enforces them so the verdict can't be hand-waved.
Write the rubric **at task start** (one checkable criterion per line, each naming the
evidence token that proves it); at done-time pipe in the actual tool-result lines:

```
python3 tools/verify_artifact.py --rubric rubric.md --evidence evidence.txt
# rubric line forms:
#   [evidence: 7 passed]  all unit tests pass
#   [vision]              chart renders without overlap   # needs a screenshot/render ref
#   [judge]               summary reads coherently        # defers to eval-gate, not reimplemented
```

It builds the per-criterion verdict table by matching each criterion against the evidence:
a criterion with **no backing evidence line is DONE? = NO** (the two-pass / hallucination
rule — a claim with no evidence is refuted, never assumed). `[vision]` criteria (or any
criterion under `--vision`) additionally require a screenshot/render reference or they fail —
text-only checking of a visual artifact does not count. **Any NOT-DONE row exits non-zero**, so
it gates the done-claim. It does NOT re-score 0–5 quality — that holistic judge already lives in
[`eval-gate`](../eval-gate/SKILL.md); `[judge]` criteria defer to it (imported read-only).

## Don't stop at the plan, and don't move the line

- **Anti-early-stop:** if your final paragraph is a *plan* or a *promise* ("next I'll…", "let me…"), do that work **now** — a described step is not a done step. Yield only for a genuine blocker: a destructive/irreversible action, a real scope change, or input only the user can give. (Mechanical backstop: the `early_stop` drift probe.)
- **Don't weaken the gate to pass.** A failing check is failing. Never lower a threshold/tolerance or relabel a FAIL→PASS mid-run to ship — that needs explicit human approval. Move the bar by *raising* it, never to wave work through.

## High-stakes: escalate to a cross-vendor verifier (inline, before shipping)

Steps 1–5 prove the work runs. For a **high-stakes or hard-to-reverse** result, "runs" is not "correct" — your own check shares your blind spots. Before shipping such a result, escalate to a **separate, preferably cross-vendor, read-only** verifier — the same mechanism as [`task-retrospective` Part D](../task-retrospective/SKILL.md#part-d--adversarial-cross-check-a-separate-preferably-cross-vendor-verifier-agent), fired **now** instead of at task-end.

**Fire (cost-gated — NOT every claim):** the output is hard to reverse (publish/send/merge/migrate/delete), money- or security-relevant, or a contested/load-bearing conclusion the user will act on. Trivial, internal, or easily-reverted results skip this and just use steps 1–5.

**How:** dispatch the OTHER vendor read-only and synchronous — `codex exec` (Claude→GPT), `claude -p --model opus` (GPT→Claude), or `gemini -p --approval-mode plan`. Don't guess which are installed: `python3 skills/_shared/model_roster.py --panel 3 --role verifier --exclude-lane <self> --task "<claim>" --brief "<evidence>"` detects the reachable cross-vendor backends and renders the read-only, refute-if-you-can dispatch for each (odd-N so the majority is clean; it excludes your own lane). Hand each the result + evidence; ask it to re-run the key check and **refute if it can** (holds:bool, exit 0). See Part D for the full vendor table, channel caveats, the odd-N (default 3) majority rule, and the `loop`-spec. Agreement → ship. Refutation → do not ship; resolve or escalate to the user.

This is verification, not generation — a different foundation model catching errors, the one ensemble mechanism the evidence backs. It does not replace an armed task-retrospective; it is the pre-ship gate for results that cannot wait for the project-learning report.

## Learning handoff

Completion is a good moment to decide whether anything durable was learned, but this skill does **not** auto-launch task-retrospective or write memory.

- If [`task-retrospective`](../task-retrospective/SKILL.md) is armed, hand it the verification evidence and any corrections before closing the task.
- If the user explicitly asked to remember/log/save a lesson, route the candidate through [`wiki-memory`](../wiki-memory/SKILL.md) and [`write-gate`](../write-gate/SKILL.md).
- If neither is true, do not persist by default. Optionally mention that task audit mode would be useful when the same task will recur and the nudge is low-noise.

One-line test for any durable write:

> **Write IFF the task produced a _durable, project-specific_ lesson you would want a FUTURE session to recall.**

Do **not** write plain acknowledgements/thanks, ephemeral or general-knowledge questions (arithmetic, definitions, one-off lookups), chit-chat, or any task that produced no new project-specific fact. `write-gate` filters low-signal prose, not off-topic persistence; the invoking protocol must decide relevance and target.
