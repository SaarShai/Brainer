# EVAL — `think`

`think` is a pure-prompt **mindset** skill (no hook, no tool). It is the hardest
category to measure: unlike `caveman-ultra` (−% output) or `semantic-diff`
(token savings) there is no crisp metric, and the behaviors it targets
(challenge premises, reduce-before-add, first-principles) only surface in a
model capable enough to recognize a flawed framing. **Read the interpretation
section before trusting the A/B delta.**

## Static cost (measured)

| field | tokens / size |
|---|---|
| description (always resident) | **68 tokens** (311 chars) |
| body (loaded on trigger)      | **1,344 tokens** (6,200 chars) |
| tools/ payload                 | 0.0 KB |
| model pin                      | `any` |
| effort pin                     | `medium` |

Source: [`eval/results/static_cost.json`](../../eval/results/static_cost.json).
68 resident tokens is ~0.03% of a 200K window — the cheap, model-agnostic part
of the case for keeping it.

## Trigger accuracy (measured) — the solid result

`eval/exp8_trigger/run_trigger.py`, live 16-skill catalog, qwen2.5:7b router,
one canonical should-fire prompt per skill:

| metric | value |
|---|---|
| top-1 accuracy | **14/14 = 1.0** |
| `think` self-fire | ✅ correct |
| regression on other 15 skills | **none** — adding `think`'s broad description stole no other skill's prompt (incl. `plan-first-execute`, `lean-execution`) |

Raw: [`eval/exp8_trigger/results/with-think.json`](../../eval/exp8_trigger/results/with-think.json).
Caveat: this is the one-prompt-per-skill design; it does **not** probe ambiguous
boundary prompts (think-vs-plan-first). Boundary/negative trigger cases are a
follow-up.

## A/B (smoke — NON-CONFIRMING) — N=3 × 5 trap probes

- Subject model: **qwen2.5:7b-instruct** (local Ollama).
- Judge model: **gemma2:9b** (distinct family → no self-judge; `gemma4:26b`, the
  repo default judge, is a broken local pull — 404s on `/api/generate`).
- Tasks: [`eval/tasks/think.yaml`](../../eval/tasks/think.yaml) — each prompt is a
  TRAP (false premise / unnecessary work / reinvention / cargo-cult / XY-problem);
  pass = catch the trap.

| metric | without skill | with skill | Δ |
|---|---|---|---:|
| input tokens (mean)  | 61 | 1,406 | +2,219% (the 1.3k body when loaded) |
| **output tokens (mean)** | 690 | 854 | **+23.7%** |
| latency (ms)         | 12,222 | 15,435 | +26% |
| **judge score (0–5)**    | **3.4** | **2.8** | **−0.6** |

Raw: [`eval/results/think.json`](../../eval/results/think.json) ·
[`eval/results/think.judged.json`](../../eval/results/think.judged.json).

### Per-probe trap-catch (judge gemma2:9b)

| probe | trap | without | with | Δ |
|---|---|---:|---:|---:|
| 0 | GIL ≠ "threads can't help I/O-bound" | 4 | 4 | 0 |
| 1 | cache a once-at-startup 12-row read | 4 | 4 | 0 |
| 2 | hand-roll RFC-3339 parsing | 1 | 1 | 0 |
| 3 | microservices for ~500 DAU | 3 | **1** | **−2** |
| 4 | regex micro-opt vs per-keystroke | 5 | 4 | −1 |

The whole −0.6 comes from probe 3 (−2) and probe 4 (−1); probes 0–2 are flat.

## Interpretation — why the smoke is non-confirming, not a verdict

1. **`think` is token-positive (+23.7% output).** Ideation, premise-challenging,
   and the named methods add prose. Its justification therefore **cannot** be
   token economy — it is the one discipline skill expected to *increase* output.
   It composes badly on the same axis as `caveman-ultra`/`lean-execution`; if
   stacked, expect the output reducers to claw most of it back. Measure the
   `think + caveman` interaction before relying on it in a terse stack.
2. **The −0.6 is dominated by method-theater, not reasoning harm.** Manual read
   of the raw outputs: with `think`, the 7b model *recites* the skill's
   vocabulary ("Step 2: Brain Blizzard + Scout Tests + Sieve…") as ritual, then
   on probe 3 still lands on a confidently-wrong answer (recommends
   Linkerd + RabbitMQ for 500 users) — which the judge penalized harder than the
   hedged baseline. The skill induced *ceremony* the model couldn't cash into
   *insight*.
3. **Small models are an invalid testbed here — as subject AND as judge.**
   - Subject (7b-instruct) is too literal/compliant: it obeyed "don't use date
     libraries" (probe 2) and "design cache invalidation" (probe 1) instead of
     challenging the premise — the exact behavior `think` exists to override.
   - Judge (9b) is too weak to *detect* trap-catching: it scored probe 1 a 4/4
     when **neither** answer caught the trap, and tied probe 0 where `think`
     clearly corrected the premise harder. A judge that can't see the trap can't
     credit catching it.
   Net: this smoke mostly measured "does a 7b perform the rituals and does a 9b
   like the result," not "does `think` improve frontier reasoning."

**Do not read −0.6 as "think degrades reasoning."** Read it as: *unverified, and
local small models can't verify it.* The two trustworthy results are trigger
(1.0, no regression) and the 68-token resident cost.

## What the skill currently rests on

- ✅ Triggers cleanly, zero regression (measured).
- ✅ Trivially cheap resident (68 tok, no hook/dep).
- ❓ Behavioral value **unverified** — the 7b/9b smoke is non-confirming and
  capability-limited. It is kept as a default pure-prompt skill on cost +
  triggering grounds, not on a measured behavioral win. Honest status:
  **unmeasured-positive**, same bar the catalog applies to opt-in skills, minus
  the hook cost that forces those to opt-in.

## Recommended decisive test (next)

Re-run `eval/tasks/think.yaml` with a **frontier model as both subject and judge**
(`runner.py --backend anthropic --model claude-…`, judge likewise). That is the
only setup that can tell whether `think` converts to real trap-catching or just
adds ceremony. Needs `ANTHROPIC_API_KEY` + spend authorization — not run here.
Add boundary/negative trigger cases in the same pass.

## Failure modes (observed at 7b — watch for them at scale)

- **Method-theater:** named methods ("Brain Blizzard", "5 Whys") recited as
  ritual headers without doing the underlying work. If a frontier run reproduces
  this, the fix is to make the methods *triggers to think*, not *sections to
  fill* — i.e. trim prescriptive method-naming. Not changed now: a 7b artifact is
  too weak to justify editing user-authored, user-approved content.
- **Output inflation** on prompts that didn't need deliberation (the catalog's
  known weakness on terse/clear tasks — `think` should not fire there; trigger
  test suggests it doesn't).

## Methodology

- Sample size: N=3 local smoke (directional only). N≥50 + frontier model for any
  behavioral claim — none is made here.
- Backends: `runner.py` supports `ollama` / `anthropic` / `mimo` / `mlx`.
- Judge: `judge.py --backend ollama --model gemma2:9b` (default `mimo`/`gemma4:26b`
  unavailable — see above). Rubric embedded per-task in the YAML.
