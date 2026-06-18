# EVAL — `loop-engineering`

## Static cost (measured — `eval/static_cost.py`)

| field | tokens / size |
|---|---|
| description (frontmatter) | **221 tokens** (973 chars; budget ≤ 1,536) |
| resident catalog line (first sentence only) | **~32 tokens** — what `install.sh` injects into CLAUDE.md/AGENTS.md/GEMINI.md |
| body (loaded on trigger) | **5,270 tokens** (22,084 chars) |
| tools/ payload | **139.9 KB** (`loop_lint.py` · `loop_run_monitor.py` · tests · `schema.md`) |
| model pin | `any` (none) |
| effort pin | `medium` |

Resident cost when a project installs the suite is the ~32-token first-sentence
catalog line (install.sh's `short_desc` truncates to the first sentence). The
221-token full description, the 5,270-token body, and the tools load only on
trigger.

## A/B savings

**Not yet measured as a savings claim.** This skill optimizes *loop topology and
gate discipline*, not token count, so its headline metric is not a token delta.
It is default-installed because `loop_lint.py` and the prompt-intent probes are
cheap load-bearing gates; N≥50 cross-family measurement is still required before
claiming a quantified reduction. Candidate promotion-grade measurements:

- wasted iterations on a generate→verify task with a gate vs. without one;
- runaway-loop tokens spent before halt, budget-capped vs. unbounded;
- self-grading loops (generator==verifier) caught pre-run by `loop_lint.py`;
- benchmark-green-mistaken-for-correct flags raised before a "done" claim;
- runtime traces where `loop_run_monitor.py` catches stuck / costly loops before
  the remaining budget burns.

The falsifiable parts are the gates: a self-grading or gateless spec
`loop_lint.py` passes, a clean spec it FAILs, a stuck trace
`loop_run_monitor.py` passes, or a healthy trace it flags STUCK is a measurable
bug.

## Functional checks (deterministic — in `scripts/run_all_tests.sh`)

- `python3 skills/loop-engineering/tools/test_loop_lint.py` → 61/61 pass (clean
  spec exit 0; gateless R1 exit 2; unbounded/no-stop R2 exit 2; generator==verifier
  R3 exit 2; open-no-ack R4 / fleet-no-quorum R5 / no-topology R6 each WARN exit 1).
- `python3 skills/loop-engineering/tools/test_loop_run_monitor.py` → runtime trace
  gate tests pass (same-command / repeated-error / flat-metric STUCK triggers,
  cost-per-accepted-change WARNs, JSON output, bad-input exits).
- `python3 skills/loop-engineering/tools/loop_lint.py <gateless-fixture>` exits **2**;
  a clean fixture exits **0**.
- `drift_probes.json` is a top-level array using only shipped kinds
  (`claim_without_evidence` / `prompt_intent`), including harness-audit and
  loop-memory intent,
  so compliance-canary auto-discovers it after `./install.sh` and never crashes
  on it.
- `python3 scripts/lint_skill_md.py skills/loop-engineering/SKILL.md` passes
  (name + `Use BEFORE…` trigger + `##` nav headings).

## Methodology

N=3–10 local smoke (`test_loop_lint.py`, `test_loop_run_monitor.py`); N≥50
Kaggle T4 for any promotion-grade claim. Backends/judge per the repo standard
(see `eval/FINDINGS.md`).

## Promotion path

Already default-installed as of v1.11 because the static and prompt-intent gates
are cheap and load-bearing. Do not publish a quantitative savings claim until an
N≥50 cross-family measurement shows the topology/gate discipline reduces wasted
iterations, runaway-loop tokens, or cost per accepted change.

## Why a standalone skill (not folded into an existing one)

A runtime loop-detection skill (`loop-breaker`) was **cut at v1.6.0** as redundant
with the host's built-in loop-protection (see `skills/SKILLS_INDEX.md` removal log).
loop-engineering is **not** that skill and does not reopen the cut: the discriminator
is **harness discipline vs. host loop protection**. `loop-breaker` tried to infer
generic spinning from the live assistant session (the host already does this);
loop-engineering validates a loop's spec before it runs via `loop_lint.py`, and
when a harness emits an explicit iteration trace it can run `loop_run_monitor.py`
as a domain-specific runtime health gate. Cron/interval execution remains host
wiring (`/loop` + schedule). The net-new core is the **topology-choice +
generator↔verifier-wiring** layer, which no existing skill provides:
`plan-first-execute` assumes one closed loop already exists, `lean-execution` only
prunes, `prompt-triage` picks a worker not a topology, and `verify-before-completion`
runs one done-claim check but never bounds an iteration count or rejects a self-grading
loop. Every enforcement *reflex* is delegated by link, not re-implemented.

## Failure modes

- **Over-orchestration** — designing a fleet where a one-shot would do. Mitigated by
  the front-loaded "Do you even need a loop?" gate (defers to `lean-execution`) + the
  `ONE SHOT` override.
- **R1 prose-gate boundary** — the machine-token allowlist is regex-based; tune against
  `test_loop_lint.py` fixtures, not in prod. (Allowlist, not denylist: absence of a
  machine token FAILs, so "the reviewer agrees" is caught.)
- **Redundancy drift** — a future edit restating the verify/plan/learn/restraint reflexes
  instead of linking them. Guarded by `suite-health`'s prose-vs-code reconcile.
