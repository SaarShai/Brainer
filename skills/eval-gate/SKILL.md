---
name: eval-gate
description: Score AI output against a written rubric before it ships — an LLM-as-judge quality gate for content output (drafts, posts, answers) and product output (an agent's reply, an extraction, a generated payload). Use when asked "is this good enough", "score/grade this", "would this pass", to gate output on quality, to regression-check a prompt/model/pipeline change, or to turn a flagged bad output into a permanent test case. Returns 0-5 + reason; exit code gates. Opt-in until N≥50 verified.
effort: low
tools: [Bash, Read, Write]
auto-install: true
pulse_reminder: before shipping AI-generated output (or a prompt/model change), gate it — score against the rubric; nothing below the line ships, and every caught failure becomes a new case.
---

# eval-gate — quality gate for AI output

Slop is an output-side problem. You can sharpen the generator forever (better
prompt, bigger model, more memory, a context file the size of a novel) and
still ship a bad run, because there is no layer **measuring the output before it
leaves the building**. This skill is that layer.

It promotes the internal `eval/judge.py` harness — the LLM-as-judge this repo
uses to A/B its *own* skills — into a gate you point at *your own* output.

## The loop (three verbs, three places)

| Verb | Eval-loop role | Exit `1` means |
|---|---|---|
| `score` | runtime / pre-ship check on ONE output | below the line |
| `suite` | pre-ship **regression** gate over a saved case-set vs a baseline | a case failed or the mean regressed |
| `add-case` | the **ratchet** — a flagged failure becomes a permanent case | reason too thin |

The ratchet is the part that compounds: every output you catch becomes a test
that can't silently come back. The floor rises on its own.

## A benchmark is three things

1. **Cases** — real inputs + what good looks like. For content: your 20-50 best
   pieces (extract the standard you already hit on your best days). For product:
   pull real inputs from your logs, not the happy-path demos.
2. **Metric** — `score`/5 → a 0-1 number. A *specific* rubric ("contains a
   copy-pasteable step") yields a score you can trust; a vague one ("is this
   good") doesn't. The judge inherits your taste only if you write it down.
3. **Threshold** — the line below which nothing ships. Default `0.7`. The gate
   only works if you never wave a 0.6 through because you liked it.

## CLI

```bash
EG="python3 skills/eval-gate/tools/eval_gate.py"

# score one output (stdin / --file / --text) against a rubric
$EG score --rubric skills/eval-gate/tools/rubric.example.md --file draft.md
echo "$AGENT_REPLY" | $EG score --task "$USER_MSG" --threshold 0.7

# regression-gate a change: re-run the case-set, compare to baseline, block on drop
$EG suite --cases cases.jsonl --save-baseline base.json   # set the line once
$EG suite --cases cases.jsonl --baseline base.json        # gate every change after

# ratchet: a bad output becomes a permanent case (reason must say WHY)
echo "$BAD_OUTPUT" | $EG add-case --cases cases.jsonl \
    --task "$INPUT" --reason "wrong total because it hallucinated a line item"
```

Backends (from `eval/judge.py`): local **Ollama** by default (no key), **MiMo**
when `MIMO_API_KEY` is set (`--backend mimo`). `--stub-score N` scores without a
model — for wiring / CI. Exit `2` = judge unreachable or unparseable (the gate
fails *safe* — it never reports a pass it couldn't compute).

## Protocol

1. Write the rubric once (`tools/rubric.example.md` is a starting point). Encode
   your actual taste — the criteria a reader would bookmark you for.
2. `score` at the point of shipping. Exit 1 → rework or kill; do not ship.
3. On any prompt / model / pipeline change, run `suite` against the baseline.
   A regression blocks until you've looked at which case dropped and why.
4. Every time you (or a reviewer) catch a bad output, `add-case` it. The reason
   is required and must say *why* it's bad — that's what makes the new case
   teach instead of just accumulate.

## The ratchet gate

`add-case` refuses a case whose `--reason` is thin or reasonless (mirrors
[`write-gate`](../write-gate/SKILL.md)'s why-clause rule) so the case-set teaches
instead of bloating. For heavier signal-scoring of the reason, pipe it through
`write-gate` first. `--force` overrides.

## Where this sits

- [`verify-before-completion`](../verify-before-completion/SKILL.md) checks *did
  it run* (binary, deterministic). eval-gate checks *is the output good*
  (graded, rubric). Use both: no signal, no "done"; below the line, no ship.
- [`compliance-canary`](../compliance-canary/SKILL.md) runs the same judge as a
  **runtime** drift probe (`llm_judge` kind). eval-gate is the on-demand /
  pre-ship form of the same measurement.
- [`write-gate`](../write-gate/SKILL.md) gates *facts into memory*; eval-gate
  gates *output to an audience*. Same shape, different door.

## Anti-patterns

- A vague rubric. "Is this good and engaging" → a vague score. Be specific.
- Threshold theatre — logging a score but shipping the fail anyway.
- Judging with the same model that generated, at temperature > 0, expecting a
  stable critic. The judge runs at temp 0; a sharp rubric is the consistency.
- Gating non-shipping scratch output. The gate is for what reaches an audience.

## Lineage

- `eval/judge.py` (this repo) — the judge backends and 0-5 rubric scoring this
  skill exposes; previously inward-only (skill A/B), now user-facing.
- Pattern: LLM-as-judge + regression suite + failure→case ratchet — the eval
  loop standard to ML engineering, ported to agent / content output.

## Status

**Opt-in / unmeasured.** Plumbing self-tested offline (`tools/test.sh`, no
network). Per catalog policy it earns N≥50 before any default promotion —
target: gating output on a rubric cuts downstream rework / re-reads /
"done"-reversals without rejecting good runs. See [EVAL.md](EVAL.md).
