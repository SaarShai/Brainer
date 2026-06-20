# EVAL — `loop-engineering`

## Static cost (measured — `eval/static_cost.py`)

| field | tokens / size |
|---|---|
| description (frontmatter) | **288 tokens** (1,224 chars; budget ≤ 1,536) |
| resident catalog line (first sentence only) | **~32 tokens** — what `install.sh` injects into CLAUDE.md/AGENTS.md/GEMINI.md (unchanged by the pipeline clause, which lands later in the description) |
| body (loaded on trigger) | **4,825 tokens** (20,381 chars) |
| tools/ payload | **145.1 KB** (`loop_lint.py` · `loop_run_monitor.py` · tests · `schema.md`) |
| model pin | `any` (none) |
| effort pin | `medium` |

Resident cost when a project installs the suite is the ~32-token first-sentence
catalog line (install.sh's `short_desc` truncates to the first sentence). The
288-token full description, the 4,825-token body, and the tools load only on
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

## Non-iterating pipelines (budget=1) — doc-only

A fixed once-through pipeline (A→B→C, each stage runs once, nothing retries) is the
degenerate **budget=1 case** of a loop, not a separate artifact: `max_iterations=1`
+ a machine gate + a verifier separate from each stage's producer lints clean with
**no new schema and no new tool**. Settled by falsification, not assertion — three
real pipeline specs (import→validate→transform→write, intake→classify→route→file,
parse→render→publish) lint clean as budget=1 loops, while their naive forms correctly
FAIL R1/R2/R3. Two regression tests (`test_noniterating_pipeline_budget1_passes`,
`test_naive_pipeline_without_budget1_still_fails`) guard the claim: if `loop_lint`
ever FAILs a budget=1 pipeline, the doctrine is broken. A graph linter (`stages:`/
`edges:` keys + reachability rules) was scoped and **cut** — no multi-node workflow
in the repo has hit a reachability failure that budget=1 cannot express, so it fails
the promotion bar above (ship a gate only for a failure that actually occurs).

## Functional checks (deterministic — in `scripts/run_all_tests.sh`)

- `python3 skills/loop-engineering/tools/test_loop_lint.py` → 75/75 pass (clean
  spec exit 0; gateless R1 exit 2; unbounded/no-stop R2 exit 2; generator==verifier
  R3 exit 2; open-no-ack R4 / fleet-no-quorum R5 / no-topology R6 each WARN exit 1;
  a non-iterating pipeline modeled as a budget=1 loop lints clean exit 0, and a
  naive pipeline written without it FAILs R1/R2/R3).
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

## Lineage

(Relocated out of `SKILL.md` so it does not load every trigger — provenance, not runtime doctrine.)

Doctrine descends from the generator-verifier "design the verifier, not the prompt" framing (ReAct: Yao et al.; Reflexion: Shinn et al.). The five-components-plus-memory, maker/checker, comprehension-debt, and cognitive-surrender framings follow **Addy Osmani**'s loop-engineering essay; the **4-condition economics test** + minimum-viable-loop ordering + cost-per-accepted-change metric follow AlphaSignal / **Lev Deviatkin**'s prompter→loop-designer roadmap; the **Ralph Wiggum loop** failure mode is **Geoffrey Huntley**'s; the durable-project-loop / state-file-as-spine continuity framing is from the repo-as-loop writeups (Jason Liu, steipete). Pattern sources (inspiration, **not** imports — frameworks stay pattern sources per `GOAL.md`):
- **HarnessCode** ([yzddp/harnesscode](https://github.com/yzddp/harnesscode)) — verifier-as-gate with a typed report + failure-type routing; the **anti-false-completion guard** (exit only on independently-recomputed gate state, never a model done-claim); thin deterministic driver + liveness counters.
- **autonomy-loop** ([inferencegod/autonomy-loop](https://github.com/inferencegod/autonomy-loop)) — independent re-verification by a separate actor (Builder/Reviewer in separate worktrees); the **coverage-ratchet** monotonic-floor gate; frozen-invariant + human escalation; cheap-panel + expensive-judge-on-dissent with a bounded-rounds deadlock cap.
- **issue-triage-loop** ([warpdotdev-demos/issue-triage-loop](https://github.com/warpdotdev-demos/issue-triage-loop)) — a worked inner/outer self-improvement loop: inner skill fires on issue-open, outer skill reads recent runs and PRs a SKILL.md diff that **never self-merges** (R7). Source of the **grade-the-feedback-by-source-strength** rule (correction/relabel strong · reaction moderate · silence weak-positive → don't thrash) and the **in-place override delta** as the cheapest feedback channel.
