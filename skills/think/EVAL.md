# EVAL — `think`

`think` is a pure-prompt **mindset** skill at runtime (no hook or runtime tool;
the shipped Python is an offline contract check). It is the hardest category to
measure: unlike `caveman-ultra` (−% output) or `semantic-diff`
(token savings) there is no crisp metric, and the behaviors it targets
(challenge premises, reduce-before-add, first-principles) only surface in a
model capable enough to recognize a flawed framing. **Read the interpretation
section before trusting the A/B delta.**

## Static cost (measured)

| field | tokens / size |
|---|---|
| description (always resident) | **81 tokens** (378 chars) |
| body (loaded on trigger)      | **1,422 tokens** |
| tools/ payload                 | 7.7 KB (offline contract + test; not loaded into the prompt) |
| model pin                      | none |

## Research-backed pruning (2026-07-10)

The body fell from 2,199 to 1,422 tokens (**−35.3%**) while retaining manual
activation, the behavior-first role, four unconditional posture rules, a compact
mandatory route index, conditional methods, and objective self-checks.

The previous body copied detailed wiki and coding procedures into `/think`.
Current [Agent Skills guidance](https://agentskills.io/skill-creation/best-practices)
warns that every loaded token competes for attention and overly comprehensive
skills can trigger irrelevant work. Current
[Anthropic model guidance](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5)
also recommends removing older over-prescriptive scaffolding when stronger
models perform better without it. A 2026 study found that even self-evident
constraints can interfere with task solving across math, multi-hop QA, and code
([Qi et al.](https://arxiv.org/abs/2601.22047)). These sources justify an
ablation, not an automatic claim that shorter is better.

The detailed procedures now remain in their owning companion skills. `/think`
keeps route activation and small fallback invariants. Unsupported absolutes were
removed: source-at-a-time forever, exactly ten pilot sources, compile-versus-
retrieve as a dichotomy, a fixed five whys, a fixed ideation quota, and blanket
permission to create resources outside the task's normal authorization.

## Operational routing contract

The knowledge and coding disciplines remain mandatory trigger-first handoffs,
but their companion skills are authoritative. The fallback minimum now covers
source provenance, source-versus-derived boundaries, fresh fit-for-purpose
indexes with raw-evidence fallback, reading the actual project target, a
self-contained reversible change, and fresh claim-layer verification.

Deterministic gate:

```bash
python3 skills/think/tools/test_think_contract.py
# 7 PASS — real contract; missing-route, restored-ingest-absolute, mutable-raw,
# prestige-role, and broken-regex negative fixtures; sycophancy boundaries
```

Behavioral task: [`eval/tasks/think-operational.yaml`](../../eval/tasks/think-operational.yaml)
contains four adversarial shortcuts (edit raw history; dump 400 PDFs without a
compile/integrity gate; add an avoidable dependency; guard an unexplained null).
The ingest rubric now expects a small heterogeneous pilot followed by bounded,
resumable batches with per-source provenance—not a universal batch size of one
or exactly ten sources.

The historical directional N=1 run used `gemma4:26b-mlx` as subject and
`qwen3.6:35b-a3b-q4km` as separate judge. It materially improved source
immutability and then-current batch-ingest behavior and held dependency
restraint. The unexplained-null case still failed: the subject requested the
real code but continued to recommend an early return, even with
`verify-before-completion` loaded. Because the body and
rubric have now changed, those results are historical and do not validate the
pruned version.

**Historical verdict:** activation language was regression-locked; behavioral
compliance was **3/4 on one tested model, not proven universal**. Do not claim
that prose can force every model to follow the debugging route. The result files
from iterative prompt tuning were deleted because they mixed skill revisions and
were not a valid publishable A/B.

[`eval/tasks/think-methods.yaml`](../../eval/tasks/think-methods.yaml) now adds
matching and non-matching probes for bottleneck focus, uncertainty ranges,
divergence, causal analysis, pre-mortems, falsification, structural analogy,
research delegation, and packaging. The non-matching pairs penalize method-
theater. The fixture exists; behavioral results must be recorded separately.

### Current pruned-body one-shot smoke (2026-07-10) — FAILED

A frozen N=1 smoke used `gemma4:26b-mlx` as subject and
`qwen3.6:35b-a3b-q4km` as separate judge across five prompts: durable ingest,
causal branching, structural analogy, direct arithmetic, and a one-off
extraction. The gate required every with-skill score to be at least 4, a
with-skill mean no more than 0.25 below baseline, and no regression over one
point. Maximum iterations was one.

| metric | without | with | result |
|---|---:|---:|---|
| output tokens | 1,275 | 1,217 | −4.5% |
| latency | 25,553 ms | 23,519 ms | −8.0% |
| original machine-parsed judge mean | 4 | 3 | gate failed |
| same raw grades with fixed parser | 4.2 | 3.8 | gate failed |

The substantive failure was prompt 1: both arms scored 1 and enabled an
untracked 400-PDF dump. Raw-judge inspection also found two harness defects:
valid prompt-4 and prompt-5 grades of 5 were stored as `None` when the judge
prefixed `Reply:` (the parser now accepts this form), and the with-skill causal
answer was scored 3 only because the judge applied unrelated prompts' criteria
after stating that it satisfied the causal rubric (the harness now injects the
current prompt number and tells
the judge to ignore other cases). Those defects explain the reported `4 → 3`;
they do not erase the durable-ingest failure.

That failure prompted one narrow fallback correction: `/think` now explicitly
locks immutable raw sources and layer ownership, a small heterogeneous pilot,
bounded resumable batches behind compile/integrity gates, and compact coding
fallback invariants. The frozen one-iteration budget prohibited tuning and a
confirmatory rerun. Therefore the final wording is statically covered but **not
behaviorally validated** by this smoke.

## Role wording revision (2026-07-10)

The former role sentence asserted world-class intellectual status. Current
[OpenAI](https://developers.openai.com/api/docs/guides/prompt-engineering) and
[Anthropic](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)
guidance treats role as a task-relevant behavior and tone control, while
empirical persona-prompt results are
[mixed](https://aclanthology.org/2024.findings-emnlp.888/) and
[task-dependent](https://aclanthology.org/2025.emnlp-main.1364/). The role now
states `/think`'s posture: rigorous, resourceful collaboration grounded in
evidence, the actual goal, and real constraints. It also anchors the shortest
decision sequence the role needs to change behavior on weaker models: generate
materially distinct approaches, then choose the smallest testable path instead
of speculative machinery. Detailed ideation and anti-overbuilding procedures
remain in `Always` and `When-relevant` rather than being restated here.

The static contract requires those behavioral markers and rejects restoration
of the prestige wording. A sixth probe in [`eval/tasks/think.yaml`](../../eval/tasks/think.yaml)
tests whether the whole skill rejects an underspecified “objectively best”
maximal architecture and instead frames constraints, compares approaches, and
starts small. This is regression coverage, **not evidence that the role sentence
alone improves performance**; no role-only A/B has been run.

Directional one-case smoke on the new probe, N=1: subject
`gemma4:26b-mlx`; separate judge `qwen3.6:35b-a3b-q4km`; frozen pass line
`with >= 4` and no >1-point regression against without-skill. A minimal
one-sentence role scored `1 → 3` and failed the line because the subject still
recommended one speculative stack. Adding only the two missed behavior cues —
materially distinct approaches and the smallest testable path — scored
`1 → 4` (`+3`) and passed. Treat this as directional weakest-model evidence,
not an effect size or isolated role attribution.

agentskills.io budget reference: description ≤ 1,536 chars (1% of a 200K context window).

## Historical catalog-routing accuracy

`eval/exp8_trigger/run_trigger.py`, live 16-skill catalog, qwen2.5:7b router,
one canonical should-fire prompt per skill:

| metric | value |
|---|---|
| top-1 accuracy | **14/14 = 1.0** |
| canonical `think` description match | ✅ correct |
| regression on other skills | **none** — adding `think`'s broad description stole no other skill's prompt |

Raw: [`eval/exp8_trigger/results/with-think.json`](../../eval/exp8_trigger/results/with-think.json).
Caveat: this measured description classification, not current activation.
`disable-model-invocation: true` keeps direct `/think` activation explicit, while
the loaded skill remains explicit. The historical
one-prompt-per-skill design did **not** test that boundary.

## Historical A/B (smoke — NON-CONFIRMING) — N=3 × 5 then-current trap probes

- Subject model: **qwen2.5:7b-instruct** (local Ollama).
- Judge model: **gemma2:9b** (distinct family → no self-judge; `gemma4:26b`, the
  repo default judge, is a broken local pull — 404s on `/api/generate`).
- Tasks: the five-probe version of [`eval/tasks/think.yaml`](../../eval/tasks/think.yaml)
  used for this run — each prompt was a TRAP (false premise / unnecessary work /
  reinvention / cargo-cult / XY-problem); pass = catch the trap. The current
  file adds a sixth role-behavior probe that is not part of these historical numbers.

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
   It composes badly on the same axis as `caveman-ultra`; if
   stacked, expect the output reducers to claw most of it back. Measure the
   `think + caveman` interaction before relying on it in a terse stack.
2. **The −0.6 coincides with method-theater; causation is unresolved.** Manual read
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

**Do not read −0.6 as "think degrades reasoning," or as evidence that it helps
weaker models.** The subject and judge were both too weak for attribution. The
trustworthy results are the historical catalog classifier and static cost.

## Frontier directional A/B (Opus subject / Sonnet judge)

Ran the same 5 probes with a **frontier subject and a cross-model judge** via a
subagent workflow (no API key — uses session models): subject =
**claude-opus-4-8** (with vs without the skill; the `with` arm *reads the real
`skills/think/SKILL.md`*); judge = **claude-sonnet**, *told the trap* so it scores
reliably (fixing the 9b judge's blindness). N=3 × 5 × 2 = 30 subject runs.

| probe | without | with | Δ | caught w/o→with |
|---|---:|---:|---:|---|
| gil   | 5.00 | 5.00 | 0 | 3/3 → 3/3 |
| redis | 5.00 | 5.00 | 0 | 3/3 → 3/3 |
| dates | 1.33 | 1.33 | 0 | 0/3 → 0/3 |
| micro | 5.00 | 5.00 | 0 | 3/3 → 3/3 |
| regex | 4.67 | 5.00 | +0.33 | 3/3 → 3/3 |
| **overall** | **4.20** | **4.27** | **+0.07** | **80% → 80%** |

**Verdict: neutral on this subject and probe set.** Opus catches the traps
equally well with or without the skill—the baseline already scores 4.20 / 80%
caught, and the skill adds +0.07 (noise). This does not settle other model
families, explain the historical 7b result, or prove the posture is load-bearing
for weaker models.

`dates` (1.33/1.33, neither arm caught) is a **flawed probe**: the old prompt
ordered "do not use any date libraries" — a legitimate user constraint, so
complying isn't a trap-fail. Revised in `think.yaml` (the trap is now the
reinvention *impulse*, not disobeying an order); re-measure next run.

**Mode implication:** on this Opus run, deliberate loading bought approximately
zero posture benefit at +23.7% historical output cost. Manual `/think` is a
control choice, not a proven uplift claim. The pruned body keeps unconditional
posture separate from task-gated methods and ships slash-only via
`disable-model-invocation: true`.

Raw: workflow run `wf_bd0b9813` (subject/judge transcripts under the session's
`subagents/workflows/`).

## What the skill currently rests on

- ✅ Historical catalog classification was clean; literal manual activation still needs a boundary fixture.
- ✅ Trivially cheap resident (manual `/think`, with no hook/dep).
- ✅ Manual activation, compact routes, role posture, removed absolutes, and the drift-probe regex are statically regression-locked with negative fixtures.
- ✅ Role wording is behavior-first and statically rejects restoration of the prestige claim.
- ➖ The role-behavior probe exists, but no isolated role-only A/B has been run.
- ➖ The pruned-body one-shot smoke found a real ingest-fallback failure; the corrected final wording has static coverage but no confirmatory behavioral run.
- ➖ Historical operational behavior was 3/4 on a different directional 26B smoke; the body and ingest rubric have since changed.
- ➖ Posture value was neutral for one Opus subject (+0.07) and negative in a confounded 7b/9b run; no cross-family benefit is established.
- ❓ The situational-method fixture now exists, but no behavioral run is yet recorded.

## Open follow-ups

- Run the corrected posture probes on the pruned body across at least two subject families.
- Run a fresh holdout for the corrected fallback and case-scoped judge; do not reuse the tuning smoke as confirmation.
- Run `think-methods.yaml` with matching and non-matching cases; repeat only discriminating cases at N≥3.
- Re-run `think-operational.yaml` as a clean N≥3 A/B on the final skill body and verify actual companion loading, not just compliant prose.
- Run a role-only ablation and a current-body versus pruned-body ablation with blind pairwise grading.
- Add literal `/think` activation and non-literal boundary cases.
- `think + caveman` interaction (does the +23.7% output survive a terse style).

## Failure modes

- **Silent failure:** an agent can mention a companion skill without loading or
  executing it. The contract locks route presence, but only behavioral runs or
  host traces can prove the handoff occurred.
- **Rot when unwatched:** companion contracts can change while `/think`'s route
  stays static. The route remains short so procedures have one owner; re-run
  operational probes after companion contracts change.
- **No-hooks host:** the sycophancy drift probe cannot fire where
  `compliance-canary` hooks are unavailable. `/think` therefore keeps the
  no-flattery rule inline; the offline test still verifies the regex itself.
- **Method-theater (observed at 7b):** named methods were recited as ritual
  headers without doing the work. Mitigation: behavior-first triggers plus paired
  non-matching probes that penalize unnecessary methods. Effect remains unmeasured.
- **Output inflation:** prompts that didn't need deliberation can grow (the catalog's
  known weakness on terse/clear tasks — `think` should not fire there; trigger
  test suggests it doesn't).

## Methodology

- Sample size: N=3 local smoke (directional only). N≥50 + frontier model for any
  behavioral claim — none is made here.
- Backends: `runner.py` supports `ollama` / `anthropic` / `mimo` / `mlx`.
- Judge: `judge.py --backend ollama --model gemma2:9b` (default `mimo`/`gemma4:26b`
  unavailable — see above). Rubric embedded per-task in the YAML.
- Frontier A/B: subagent workflow (`think-frontier-ab`), Opus subject / Sonnet
  judge, N=3, judge *told the trap*. **Gotcha:** subjects have file tools — the
  `dates` probe made some write a parser to the repo root (`rfc3339.py` etc.),
  which had to be deleted before commit. A re-run must add "answer in text only;
  do not create files" to the subject prompt.
