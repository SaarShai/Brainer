# Loop-engineering hardening — the final 6

WHAT/WHY: the robustness audit (this session) surfaced 6 concrete defects in the
loop-engineering skill. Fix each, adversarially + independently verified.

## The 6 items

| # | Item | Type | File(s) |
|---|---|---|---|
| 1 | R3 false **negative** — bare-role-noun self-grades slip (`the writer drafts`/`the writer reviews`, `our model produces`/`our model checks`) | recall bug | `loop_lint.py` |
| 2 | R3 false **positive** — shared Capitalized infra/vendor token mis-flags distinct models (`claude on Bedrock`/`gpt on Bedrock` → self-grading) | precision bug | `loop_lint.py` |
| 3 | R13 — verifier-blindness has no declarable spec field, though egress/concurrency/memory all do (declare-to-audit asymmetry) | missing field | `loop_lint.py`, `schema.md` |
| 4 | EVAL doc drift — says `75/75`, actual `94/94`; body/tools token figures stale | doc | `EVAL.md` |
| 5 | model_roster R11/R12 coupling — `_MODEL_SLUGS`/`_EGRESS` in loop_lint vs roster's LANE/slug truth; silent break if out of sync | audit | `loop_lint.py`, `model_roster.py` |
| 6 | Firing/enforcement gap — skill fires unreliably; subagents don't auto-invoke; hooks don't fire in subagents (fleet = least enforced) | systemic | design / probe |

## Testable requirements (each verifiable, no guessing)

- **R1.1** the 4 false-negative pairs FAIL R3; **R1.2** all 94 existing tests still pass.
- **R2.1** `claude on Bedrock`/`gpt on Bedrock` and `opus via Acme`/`sonnet via Acme` do NOT fire R3; **R2.2** genuine same-name self-grades (`Alfred drafts`/`Alfred reviews`) still FAIL.
- **R3.1** a spec that names a separate verifier but declares it sees generator reasoning warns (R13); a blind/declared one is clean. **R3.2** opt-in (silent until the field or a separate verifier is present) — no nag on plain inner loops.
- **R4.1** `test_loop_lint.py` count line + EVAL `75/75` reconcile to the real number; token figures re-measured via `eval/static_cost.py`.
- **R5.1** a written verdict: is loop_lint's slug/egress vocabulary consistent with `model_roster.py`'s lanes; concrete drift cases or "consistent".
- **R6.1** a concrete, mechanical proposal (not prose exhortation) for the firing gap, or an honest "out of scope for a linter, here's where it belongs".

## done means (≤5, re-read at close)

1. Items 1–4 are code/doc changes; full `test_loop_lint.py` suite green AND new adversarial fixtures pass.
2. Items 1–2 cause **zero** regression in the existing 94 tests.
3. Items 5–6 produce a written, evidence-backed verdict (fix applied OR "no change needed, because…").
4. Each item independently refuted by a cross-vendor/blind verifier (GLM-5.2 + a second agent) with no surviving counterexample.
5. The loop spec below lints clean (skill dogfoods itself).

## Loop spec (lint this)

```loop
name: loop-eng-hardening
topology: closed · inner · single
generator: opus orchestrator patches loop_lint.py / schema.md / EVAL.md and writes adversarial fixtures
verifier: python3 skills/loop-engineering/tools/test_loop_lint.py (94 existing + new fixtures) as the machine gate, cross-checked by a second blind agent that reads only the patched code and tests
gate: python3 skills/loop-engineering/tools/test_loop_lint.py exit 0 and the new adversarial fixtures assert as specified
stop: all 6 items resolved, full suite green, the blind refuter finds no surviving counterexample
budget: max_iterations=4
stuck: same fixture fails 2 iterations with no movement
advisor: GLM-5.2 via glm-executor proposes a structurally different regex/approach, read-only, blind to the patch rationale
redaction: scrub secrets/.env/keys via audit_redact before any cross-vendor dispatch (patch text is non-secret repo code)
egress: cross-vendor review via GLM-5.2 (glm-executor)
```
