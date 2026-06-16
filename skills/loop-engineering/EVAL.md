# EVAL — `loop-engineering`

## Static cost (measured — `eval/static_cost.py`)

| field | tokens / size |
|---|---|
| description (frontmatter) | **96 tokens** (390 chars; budget ≤ 1,536) |
| resident catalog line (first sentence only) | **~32 tokens** — what `install.sh` injects into CLAUDE.md/AGENTS.md/GEMINI.md |
| body (loaded on trigger) | **2,666 tokens** (10,854 chars) |
| tools/ payload | **~33 KB** (`loop_lint.py` · `test_loop_lint.py` · `schema.md`) |
| model pin | `any` (none) |
| effort pin | `medium` |

Resident cost when a project installs the suite is the ~32-token first-sentence
catalog line (install.sh's `short_desc` truncates to the first sentence). The
96-token full description, the 2,011-token body, and the tools load only on
trigger. `auto-install: false` ⇒ no hook is wired and no `tools/install.sh` runs;
the skill is symlinked + listed like any other, so its catalog line is resident
but it is **not** on the measured default-stack.

## A/B savings

**Not yet measured.** This skill optimizes *loop topology and gate discipline*,
not token count, so its headline metric is not a token delta. Per `GOAL.md`'s
anti-goal "no default-on skill without a measured number," it ships **opt-in**
until a number exists. Candidate promotion-grade measurements (Kaggle T4, N≥50
cross-family):

- wasted iterations on a generate→verify task with a gate vs. without one;
- runaway-loop tokens spent before halt, budget-capped vs. unbounded;
- self-grading loops (generator==verifier) caught pre-run by `loop_lint.py`;
- benchmark-green-mistaken-for-correct flags raised before a "done" claim.

The `loop_lint.py` gate is the immediate value at opt-in: a CI-runnable verdict
(exit 2 on a gateless / self-grading / unbounded spec) that pays off with no
default slot. It is also the **falsifiable** part — a self-grading or gateless
spec it passes, or a clean spec it FAILs, is a measurable bug.

## Functional checks (deterministic — in `scripts/run_all_tests.sh`)

- `python3 skills/loop-engineering/tools/test_loop_lint.py` → 25/25 pass (clean
  spec exit 0; gateless R1 exit 2; unbounded/no-stop R2 exit 2; generator==verifier
  R3 exit 2; open-no-ack R4 / fleet-no-quorum R5 / no-topology R6 each WARN exit 1).
- `python3 skills/loop-engineering/tools/loop_lint.py <gateless-fixture>` exits **2**;
  a clean fixture exits **0**.
- `drift_probes.json` is a top-level array using only a shipped kind
  (`claim_without_evidence`), so compliance-canary auto-discovers it after
  `./install.sh` and never crashes on it.
- `python3 scripts/lint_skill_md.py skills/loop-engineering/SKILL.md` passes
  (name + `Use BEFORE…` trigger + `##` nav headings).

## Methodology

N=3–10 local smoke (`test_loop_lint.py`); N≥50 Kaggle T4 for any promotion-grade
claim. Backends/judge per the repo standard (see `eval/FINDINGS.md`).

## Promotion path

Opt-in (`auto-install: false`) at launch — zero measured deltas, and the resident
catalog tax is unjustified on the measured default-stack without a number. Flip to
`auto-install: true` and add to the marketplace default `skills[]` **only** after an
N≥50 cross-family measurement shows the topology/gate discipline reduces wasted
iterations or runaway-loop tokens. Never before a number exists.

## Why a standalone skill (not folded into an existing one)

A runtime loop-detection skill (`loop-breaker`) was **cut at v1.6.0** as redundant
with the host's built-in loop-protection (see `skills/SKILLS_INDEX.md` removal log).
loop-engineering is **not** that skill and does not reopen the cut: the discriminator
is **design-time vs. runtime**. `loop-breaker` tried to *detect a spinning loop while
it runs* (the host already does this); loop-engineering *validates a loop's spec before
it runs* — it chooses the topology and refuses a gateless/self-grading/unbounded design
up front, statically, via `loop_lint.py`. It is silent on cron/interval execution
(that is the host's `/loop` + `schedule`). The net-new core is the **topology-choice +
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
