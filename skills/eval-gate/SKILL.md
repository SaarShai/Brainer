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
   only works if you never wave a 0.6 through because you liked it — and never
   lower the threshold mid-run to turn a FAIL into a PASS. A threshold change
   needs explicit sign-off; the ratchet only ever *raises* the floor.

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

# per-criterion rubric: judge each criterion PASS/FAIL -> a FAIL names WHICH one
$EG score --criteria-file skills/eval-gate/tools/criteria.example.json --file draft.md
```

**Per-criterion mode** (`--criteria-file` / `--criteria-json`) turns one holistic
`0-5` into a list of `{id, description, weight, required}` criteria judged
independently. Output carries a per-criterion `pass`/`reason` breakdown,
a weighted `score_norm`, and `blocking_criteria` — a failed `required` criterion
fails the gate **even if the weighted mean clears the threshold**, so a FAIL gives
*failure coordinates* ("complete: missed ask #3"), not just "below the line". Without
`--criteria*` the gate is unchanged (single holistic score). `--stub-criteria` mirrors
`--stub-score` for offline CI. (Granularity adopted from cognee's `rubric.py`; the
weighting + required-blocking + fail-safe parse are Brainer's.)

**Judge strength is load-bearing for grounding-sensitive rubrics.** Live-judge testing
on real briefings: a **≥32B** judge (`qwen3.6:35b`, `deepseek-r1:32b`) passed a
well-grounded draft and failed a fabricated one with the *exact* blocking criteria;
an **8B** judge (`llama3.1:8b`) both **false-failed** the good draft and **false-passed**
weak criteria — discrimination collapsed. For rubrics that turn on facts/grounding, pin a
≥32B judge with `--model`; don't let it default to a small fast model. (The per-criterion
machinery is correct regardless; it's the *judge's* verdicts that degrade on a weak model.)

Backends (from `eval/judge.py`): local **Ollama** by default (no key), **MiMo**
when `MIMO_API_KEY` is set (`--backend mimo`). `--stub-score N` scores without a
model — for wiring / CI. Exit `2` = judge unreachable or unparseable (the gate
fails *safe* — it never reports a pass it couldn't compute).

## Protocol

0. **Author the case targets first — ground truth never comes from the system
   under test.** Before writing a rubric or committing a case, lay out the
   *facts the question asks about* (its targets) and validate them statically
   with [`tools/validate_case.py`](tools/validate_case.py):

   ```bash
   python3 skills/eval-gate/tools/validate_case.py \
     --mode preflight --questions questions.jsonl --repo-root .
   ```

   `questions.jsonl` is one JSON object per line —
   `{id, skill, text, targets:[{fact, source, source_path}], sillito_dim}`.
   Each target's `source ∈ {file, git, lsp_symbol, config, api_contract}` and
   `source_path` must be **independently verifiable** (the file exists, the git
   SHA resolves, the symbol is defined, the config key is present) — never a
   model-generated answer key. `sillito_dim ∈ {D1..D5, cross-cutting}` anchors
   the question to the Sillito/Murphy/De Volder taxonomy (IEEE TSE 2008) instead
   of being authored ad-hoc. The validator **runs no skill and no model** — it
   only reads static facts. Exit 0 → ready for rubric authoring; exit 1 → it
   cites which targets failed (missing file, unresolved SHA, undefined symbol,
   absent dim). This step is the circularity break: the author of the question
   cannot also invent its answer key. *(Exempt: rubric-only gates with no
   verifiable target — see [Status](#status); eval-gate itself is one.)*
1. Write the rubric once, **as a file at task start** (`tools/rubric.example.md`
   is a starting point) — checkable criteria committed up front, not reverse-
   engineered after the work to fit what you produced. Encode your actual taste —
   the criteria a reader would bookmark you for. The grader trusts this rubric
   blindly: a **missing or wrong-target** criterion passes bad output as surely
   as a vague one, so make it complete (covers the degenerate/edge cases that
   matter), not just specific.
2. `score` at the point of shipping. Exit 1 → rework or kill; do not ship.
   **Two-pass when a maker hands you a result:** score it once from the maker's
   claims, then again from the artifact alone — any criterion that drops on the
   second pass is a refuted claim → below the line (the cold-context catch a
   self-grade structurally misses).
3. On any prompt / model / pipeline change, run `suite` against the baseline.
   A regression blocks until you've looked at which case dropped and why.
4. Every time you (or a reviewer) catch a bad output, `add-case` it. The reason
   is required and must say *why* it's bad — that's what makes the new case
   teach instead of just accumulate. For a case promoting to the **N≥50 gate**,
   the reason cites the **Sillito dimension** and the **ground-truth source**
   (e.g. *"Tests D3 — targeted retrieval — of a function defined in git commit
   abc1234"*), and the case's targets must clear Step 0's `validate_case.py`.

## Case-design SOP (for N≥50 case-sets)

When a case-set graduates from one-off `add-case` ratcheting to a measured
N≥50 evaluation, design each case ground-truth-first:

1. **Read the ground truth first.** Identify the fact (a function name in code, a
   git SHA, a config key in a file) *before* drafting the question — never the
   reverse.
2. **Map to Sillito.** Is the question "where is X defined?" (D1), "what calls
   X?" (D2), "what does X do?" (D3), "how are X/Y related?" (D4), "where is
   similar code?" (D5), or cross-cutting? Record it as `sillito_dim`.
3. **Run `validate_case.py --mode preflight`** to confirm every target is
   independently verifiable before the question text is committed.
4. **Benchmark cross-check (opportunistic).** If the skill touches retrieval and
   a published set (SWE-QA, CoReQA) happens to ask a similar question on the same
   repo, note that provenance in the reason. Opportunistic, not systematic —
   Brainer keeps its own full case-set; the benchmark is a cross-check.
5. **Aggregate by dimension.** `eval/FINDINGS.md` rolls results up by Sillito
   dimension so a systematically weak *category* of question surfaces across the
   catalog, not just one skill.

## The ratchet gate

`add-case` refuses a case whose `--reason` is thin or reasonless (mirrors
[`write-gate`](../write-gate/SKILL.md)'s why-clause rule) so the case-set teaches
instead of bloating. For heavier signal-scoring of the reason, pipe it through
`write-gate` first. `--force` overrides.

## Where this sits

- [`verify-before-completion`](../verify-before-completion/SKILL.md) checks *did
  it run* (binary, deterministic). eval-gate checks *is the output good*
  (graded, rubric). Use both: no signal, no "done"; below the line, no ship.
- [`compliance-canary`](../compliance-canary/SKILL.md) is the **runtime** drift
  watcher; eval-gate is the on-demand / pre-ship form of the same measurement.
  eval-gate ships its own `drift_probes.json` (fires when content ships unscored,
  when the user asks "is this good enough / would this pass", or when a gate is
  being weakened to pass).
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

**Opt-in / unmeasured.** Plumbing self-tested offline (`tools/test.sh` +
`tools/test_validate_case.py`, no network). Per catalog policy it earns N≥50
before any default promotion — target: gating output on a rubric cuts downstream
rework / re-reads / "done"-reversals without rejecting good runs. See
[EVAL.md](EVAL.md).

**eval-gate is itself exempt from the N≥50 ground-truth regime** — it is a
**design-by-intent** gate, not an empirically-measured skill. Its rubrics encode
human taste ("the answer must include a copy-pasteable step"), which is authored
intent, not a fact recoverable from git/file/LSP. So Step 0's `validate_case.py`
has no verifiable target to check on eval-gate's *own* output, and N≥50 is not a
meaningful bar for it. The Step-0 gate applies to the **case-sets eval-gate
evaluates** (retrieval/comprehension skills with verifiable ground truth), not to
the rubric-grading gate itself. To empirically validate a rubric, write a
separate validator that judges against human-labeled gold outputs.
