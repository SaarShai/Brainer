---
name: task-retrospective
description: Use at the end of any non-trivial task (after the work is verified, before the final report); ALSO fire mid-task the moment the user corrects you — says you were wrong, that you skipped a step or claimed something without actually running it, calls out a mistake you have made before ("again", "second time", "you keep", "I told you", "stop doing that"), or pushes back on your approach; or when the user types /retro. Runs a fixed agent self-audit (incl. 5-whys root-cause), shows the user the evidence, asks at most 3 closed feedback questions, then routes each banked lesson through write-gate to the NARROWEST home — escalating a REPEATED failure to a mechanical gate (a compliance-canary drift probe) instead of more prose. For high-stakes or contested results it dispatches a separate, preferably cross-vendor, verifier agent (Claude ↔ GPT-via-Codex ↔ Gemini) for independent review + root-cause.
effort: medium
tools: [Bash, Read, Write]
pulse_reminder: at task end run task-retrospective — self-audit (5-whys to root cause), show evidence + ask the user, harvest lessons; a REPEATED failure earns a mechanical gate (drift probe), not another paragraph; a high-stakes/contested result earns a separate cross-vendor verifier agent, not self-grading.
---

# task-retrospective — close the learning loop

[`wiki-memory`](../wiki-memory/SKILL.md) records and retrieves lessons; [`write-gate`](../write-gate/SKILL.md)
keeps junk out; [`compliance-canary`](../compliance-canary/SKILL.md) fires drift probes. What was
missing is the **close**: a fast self-audit, a real user check, a gated write, and — the load-bearing
part — a **measure** phase that detects when a lesson keeps recurring and forces it into a mechanical
gate. This skill is that close. Lean by default — **skip Part B for trivial tasks**; never turn it
into ceremony. It does NOT re-implement the write: it *fires* wiki-memory + write-gate at the task
boundary.

## Trigger
End of any non-trivial task (after the work is verified, before the final report), on a corrective
user message mid-task, or on the literal `/retro` token. For a long task, **arm it early**: state at
the start "I'll run a retrospective at the end" — the closing check is the deferred self-instruction,
not a thing you hope to remember once the context is full.

## Part A — agent self-audit (answer honestly, ≤1 line each)

First, counter your own known evasions — read this table before answering:

| Evasion you reach for | Counter |
|---|---|
| "the code looks correct" | Run it. Reading code is not verification. |
| "the tests passed" | The implementer was an LLM, and a green test can cover a stubbed half — check the last 20%. |
| "nothing to fix here" | The bar is too low. Name one stricter check you did NOT run, and run it. (An empty audit is not a free PASS.) |

Then audit:
1. Which skill / wiki SOP / runbook did this task match — and did I load it BEFORE acting? (retrieve-first)
2. Did a FRESH verification (a command + its exact output, not a code-read) back every done-claim? (cf. [`verify-before-completion`](../verify-before-completion/SKILL.md))
3. Where did I waste >2 tool calls — and what one-line rule would have prevented it?
4. What did the user correct, in their exact words?
5. **Root cause, not symptom** — for any failure/correction, run **5-whys** down to a cause you can *gate* (borrow [`think`](../think/SKILL.md)'s 5-whys / pre-mortem). "Fixed the typo" is a symptom; "no test covered the parse path" is closer; "I edit before reading" is a root you can turn into a probe. Stop at the deepest cause a mechanical gate (Part C HARD RULE) could catch.

## Part B — user feedback (≤3 closed questions; SKIP for trivial tasks)

**SHOW THE EVIDENCE FIRST (hard prerequisite — the user sees only the chat window; "you assume that
I can see the result").** Before asking ANY feedback question, surface the artifact the user must
judge in the cheapest *faithful* form:
- the **command + its exact output**, the **diff**, the **EVAL.md number delta**, or the **file at its path** — never a claim *that* it works;
- show the **prior state next to the new state** (old output vs new output, baseline metric vs new metric) — never two indistinguishable views ("the 2 screenshots look exactly the same — what am I judging?"). No prior state exists → say so explicitly: "no delta to judge — feedback is on process only";
- for a **measured claim** (a count, a %, a timing), show the measurement with its source — don't describe a number, show where it came from.

**REVIEW CARD per reviewed item** ("you're not telling me what I'm supposed to be approving") — never
just point at evidence. Each item carries: (1) what changed, (2) exactly where to look (path / command),
(3) what PASS looks like, (4) what FAIL would look like, (5) what your approval DECIDES (which lesson
gets banked / which gate gets built).

Then ask — on Claude Code via **AskUserQuestion buttons**; on other hosts as plain numbered questions.
A feedback question is a **hard yield**: show evidence, ask, then WAIT — do not answer your own
questions. At most three, each a closed candidate set:
- **Result quality:** accepted / minor issues / wrong
- **Process:** efficient / too slow / asked too much / too verbose
- **Lessons:** bank as I suggest / I'll dictate one / **add a lesson you missed** / none

The 4th lesson option is not filler — the user naming a blind spot you didn't see is the
highest-signal input in the whole ritual. Per item, the user's verdict resolves to a closed verb:
`bank-as-lesson` / `fixed` / `not-a-real-issue (cite evidence)` / `declined (cite the harm)` /
`needs-human`. Citing evidence/harm to divert is required — do not manufacture doubt to dodge a
correction.

## Headless mode (no interactive human — subagent / orchestrator / CI / `/retro` in a pipeline)

When there is no human to answer (this is the common subagent path), **degrade, don't block**: skip
the questions and the approval card, auto-extract the ≤3 candidate lessons (Part C), route survivors
through write-gate at the default threshold, bank the passers, and emit ONE machine-parseable result
as a fenced `json` block — a free-text line is not parseable (a page summary with a comma, colon, or
bracket breaks naive splitting). The caller reads the LAST such block:
````
```json
{"retrospective": {
  "banked": [{"id": "<wiki-page-id>", "pattern": "<signature>", "summary": "<one line>"}],
  "dropped": [{"candidate": "<one line>", "reason": "write-gate reject | low-confidence | duplicate"}],
  "recurrence": [{"signature": "<pattern>", "count": <int>}]
}}
```
````
All three arrays may be empty — `{"retrospective": {"banked": [], "dropped": [], "recurrence": []}}` is
the valid "no durable lesson" result.

## Part C — route each accepted lesson

1. **Cap nominations at ≤3 BEFORE the gate.** write-gate scores items one-at-a-time and has no count
   cap, so it stops *reasonless* writes but not *lukewarm-but-individually-passing* bulk. If you're
   nominating 5 things you aren't filtering. Nomination bar — **only the points you got burned on**
   (a quotable failure, something that concretely broke), by confidence:
   - **HIGH** — you can name what concretely broke / a caller or operator will hit it → nominate to bank.
   - **MEDIUM** — "felt suboptimal / I'd have done it differently" (taste, not a failure) → surface in the card, do NOT persist.
   - **LOW** → drop silently.
   Blessed null exit: **"This task produced no durable, project-specific lesson; the work is captured in the diff/log."** Writing nothing is the comfortable default.
2. **Bug-lesson or knowledge-lesson?** A bug-lesson MUST fill *what didn't work* + *prevention* (the
   prevention is exactly what later becomes a mechanical gate); a knowledge-lesson MUST fill *when to
   apply*. Map onto Brainer's existing page types — `error`/`lesson` vs `concept`/`pattern`/`convention`
   — do NOT create a parallel tree.
3. **Gate it:** `python3 skills/write-gate/tools/write_gate.py gate --kind <fact|decision|convention|error|sop> --file <candidate>`. Reject → revise (add the why-clause, cite evidence, drop the filler) or drop. Do not bypass.
4. **Write it to the NARROWEST home** via wiki-memory — write the fact once, where the next task will
   surface it, not preloaded into CLAUDE.md unless it's a broad operating rule:
   `python3 skills/wiki-memory/tools/wiki.py new --template page --title "<title>" --domain "<domain>"`.
   Ladder (narrowest first): `wiki/L2_facts` · `wiki/concepts|patterns|projects` → `wiki/L3_sops` → a
   specific `skills/<name>/SKILL.md` body → `CLAUDE.md` (broad rule only).
   Tag the page **`pattern: <named-signature>`** — the recurring class this lesson belongs to (e.g.
   `pattern: edit-without-read`). The why-clause says *why it's true*; the pattern tag says *when to
   re-fire it*, and it is the key the Measure phase counts against. Tell the user which future work
   will re-trigger it.
5. **Read it back** — `python3 skills/wiki-memory/tools/wiki.py fetch <id>` (or grep the page) to
   confirm it persisted — THEN move on. The disk is the source of truth; conversation context is not
   durable storage, and the retrospective runs exactly when context is most likely to be compacted away.
6. **Append ONE line** to `wiki/log.md`: `## [YYYY-MM-DD] retro | <what happened> + <artifact updated> + pattern:<signature>`. Include the signature so [`audit_lessons.py`](tools/audit_lessons.py) can scan it.

### HARD RULE — a REPEATED failure earns a gate, not prose
If the lesson already appears in [`lesson_patterns.json`](lesson_patterns.json) or recurs in
`wiki/log.md` history, **prose is not an acceptable fix** — the covering rule was already written and
the failure repeated anyway. Ask the compounding question: *would the system catch this automatically
next time?* Escalate:
1. **1st occurrence** → a wiki lesson page (prose, via Part C).
2. **Measure flags a signature ≥ N** → STOP writing prose; build a **mechanical gate** — but only if the
   lesson is *mechanical* (regex / count detectable, no judgment). Pick the closed target:
   - a recurring **user-correction** → a `user_correction` or `forbidden_regex` probe in the owning skill's `drift_probes.json`;
   - a recurring **tool error** → a `repeated_tool_error` probe (worked precedent: the `edit-without-read` probe declared in `skills/verify-before-completion/drift_probes.json` and *fired* by compliance-canary, itself transcript-mined from "File has not been read yet" — see `wiki/log.md [2026-06-12]`);
   - a recurring **unverified done-claim** → a `claim_without_evidence` probe, or a `verify-before-completion` criterion.
   - a recurring **loop-design violation** (ran-past-budget / no-gate / generator==verifier — the runtime echo of [`loop-engineering`](../loop-engineering/SKILL.md)'s `loop_lint` R1–R3, which is a *design-time* static check) → this is the handoff loop-engineering advertises. loop-engineering already ships a `loop-done-without-gate` probe in its own `drift_probes.json`, so per rule 4 below **tighten/confirm that existing probe**, don't duplicate it; only the pure budget-overrun slice that never surfaces as a done-claim needs a *new* probe — and it goes in `skills/loop-engineering/drift_probes.json` (loop-engineering owns the failure). The recurrence COUNT stays here in [`lesson_patterns.json`](lesson_patterns.json) (`loop-ran-past-budget`); the PROBE lives with the failure-owner.
   Probes are *declared* in a skill's own `drift_probes.json` and *fired* by compliance-canary, which auto-discovers every skill's probe file on the next run after `./install.sh` — no canary code change. Put the probe in the skill that owns the failure.
3. If the recurring lesson is **real but judgment-heavy** (not regex-detectable), it stays a page AND
   gets escalated to a `pulse_reminder:` frontmatter line on the owning skill — re-anchored every N turns by [`compliance-canary`](../compliance-canary/SKILL.md)'s periodic re-anchor (formerly skill-pulse), not another page.
4. **The gate already exists but the failure recurred anyway** → do NOT add a duplicate probe. A recurrence past an existing gate is a **threshold or wiring defect**: tighten the probe (e.g. `min_count` 2→1), or confirm the canary is actually wired on this host (`.claude/settings.json`) — a probe that never fires is a paper gate.

Precondition before generating any probe: re-check that the evidence still matches at the cited
`file:line` — don't mechanize a lesson that the code already moved past.

## Part D — adversarial cross-check (a SEPARATE, preferably cross-vendor, verifier agent)
A self-audit shares the generator's blind spots; a different foundation model usually doesn't. Per
[`loop-engineering`](../loop-engineering/SKILL.md) the verifier must be a *separate* agent (never
self-grade) — and the strongest separation is a **different foundation company**.

**When (cost-gated — NOT every retro):** the result is high-stakes / hard to reverse, the user
flagged it `minor issues` / `wrong`, or a repeated failure needs an independent root-cause. Trivial or
cleanly-accepted tasks skip Part D.

**Who — pick by descending separation (different company > different model > just a fresh context).**
Identify your own vendor (you know which host/model you are) and dispatch the OTHER, **read-only**:

| You (orchestrator) | Preferred verifier | Invocation (read-only, sync) |
|---|---|---|
| Claude / Opus | **GPT** via Codex | `codex exec "<judge prompt>"` — or Gemini: `gemini -p --approval-mode plan "<…>"` |
| GPT / Codex | **Claude / Opus** | `claude -p --model opus "<judge prompt>"` — or Gemini |
| Gemini (Antigravity) | **Claude or GPT** | `claude -p --model opus "<…>"` / `codex exec "<…>"` |

Fallback ladder if no cross-vendor CLI / auth on this host: a same-vendor separate subagent (Task/Agent,
fresh context) → an in-context adversarial pass driven by the Part A rationalization catalog. Never let
the generator grade itself unchallenged on a result that matters. Channel caveats (measured on this box):
`codex exec` and `gemini -p` return cleanly; **`claude -p` needs `ANTHROPIC_API_KEY` / `apiKeyHelper`** in
headless mode (it 401s on inherited OAuth) — so the →Claude channel only works where that auth is wired,
else fall back. (Codex gotcha — memory `codex-rescue-sync-dispatch`: demand a SYNCHRONOUS `codex exec`
with the verdict in the final message, else it fire-and-forgets.)

**Hand the verifier the result + evidence + the candidate lesson(s), and ask (it judges, never edits):**
1. Does the result actually HOLD? Re-run the key check; cite command + output; refute if you can.
2. Independent ROOT-CAUSE of any failure — your own 5-whys, do NOT anchor on mine.
3. Is each banked lesson correct, and is the proposed gate the right mechanism?

**Reconcile, don't rubber-stamp:** agreement → proceed. Disagreement → do NOT auto-accept either side;
for a high-stakes/repeated result gather up to an **odd N (default 3)** cross-vendor opinions and take
the majority — if still split at N, force the conflict to the user. A cross-vendor refutation of a
lesson **blocks its write** until resolved. This works in Headless mode too — it is agent-to-agent and
needs no human.

**Part D is itself a generator→verifier loop, so it carries [`loop-engineering`](../loop-engineering/SKILL.md)'s
4-field spec** — the cross-check cannot spin (the budget caps the dissent path above), and `loop_lint.py`
passes it clean:
```loop
name: task-retrospective-part-D-cross-check
topology: closed · inner · single
generator: this orchestrator (produced the result + candidate lessons)
verifier: a SEPARATE, preferably cross-vendor, read-only agent (codex exec / claude -p / gemini -p)
gate: verifier re-runs the key check and returns a JSON verdict — holds:bool with exit_code == 0
stop: verifier verdict agrees with mine, OR an odd-N majority (default N=3) is reached
budget: max_iterations=3 (≤3 cross-vendor verifier calls), then escalate the conflict to the user
```

## Measure (the loop's missing phase)
```
python3 skills/task-retrospective/tools/audit_lessons.py            # scan wiki/log.md
python3 skills/task-retrospective/tools/audit_lessons.py --log <path> --since YYYY-MM-DD
```
Reads `lesson_patterns.json` (`{id, description, regex, promoted, fix}`) and scans `wiki/log.md` for
each pattern recurring in a dated entry **AFTER** its `promoted` date. A post-promotion hit = the
documented fix did NOT hold = **exit 1** = escalate that pattern to a mechanical gate per the HARD
RULE. Every recurrence row carries the grep-locatable log date + the verbatim snippet — the output is
a queryable record, not prose. A pattern with zero post-promotion hits is reported as *holding*. Run
at the retrospective or periodically.

## Never
- Run Part B for a one-file trivial edit — a `wiki/log.md` line is enough.
- Bank a lesson that fails write-gate (no reason, just a recap).
- Answer a repeated failure with another paragraph — that's the failure repeating.
- Claim "logged it" without the fetch read-back — that's the failure end-of-task compaction causes.
- Emit an empty self-audit as a free PASS — no-op forbidden (raise the bar instead).
- Self-grade a high-stakes or contested result — use a separate (ideally cross-vendor) verifier (Part D); the generator sharing the grader's blind spots is the whole failure mode.
- Stop at the symptom — 5-whys to a cause you can *gate* (Part A.5), or the same failure returns.

## Files
- [`SKILL.md`](SKILL.md) — this ritual.
- [`tools/audit_lessons.py`](tools/audit_lessons.py) — the Measure phase: recurrence scan over `wiki/log.md`.
- [`lesson_patterns.json`](lesson_patterns.json) — promoted-lesson registry the scan counts against.
- [`drift_probes.json`](drift_probes.json) — this skill's own discipline probe (auto-discovered by compliance-canary).
- [`EVAL.md`](EVAL.md) — static cost + A/B (deltas not yet measured).

## Lineage
Generalized from screenery-lean's `task-retrospective` (the four user corrections that shaped its
show-evidence-first / review-card doctrine came from the "Fable 5" build session). Patterns adopted:
**GenericAgent** (lsdefine) — deferred task-end self-instruction, the rationalization catalog,
no-op-forbidden self-audit, recurrence-mining as a separate pass with grep-locatable findings;
**EveryInc compound-engineering** ([guide](https://every.to/guides/compound-engineering)) —
"would the system catch this automatically next time?" (gates over docs), the bug/knowledge two-track,
the cite-evidence-to-divert verdict set; **EveryInc compound-knowledge-plugin** — headless/Pipeline
mode, ≤3-learnings cap with a scripted null exit, the pattern-tag-for-retrieval. The
repeated-failure⇒mechanical-gate doctrine and the `wiki/log.md` recurrence scan are the screenery
original; Brainer's `compliance-canary` drift probe is the native gate home. **Part D** (separate
verifier agent) takes the generator≠verifier rule from [`loop-engineering`](../loop-engineering/SKILL.md)
and compound-engineering's parallel-reviewer / judge-panel pattern, and adds cross-vendor diversity
(Claude ↔ GPT-via-Codex ↔ Gemini) so the verifier doesn't inherit the generator's foundation-model
blind spots.
