# LEARNING_CONTRACT — canonical rules for how lessons become mechanisms

Canon for the Brainer learning loop. Skills POINT here; they never restate
these rules (restating forks the canon — that fork is how the socket rule
died in screenery-lean). Evidence base: 20 verified failures,
screenery-lean washington postmortem, 2026-07-06
(`docs/brainer-learning-failures-2026-07-06.md` in that repo).

Consumers: [`write-gate`](../write-gate/SKILL.md) (enforces §1–§3 at banking
time) · [`task-retrospective`](../task-retrospective/SKILL.md) +
[`compliance-canary`](../compliance-canary/SKILL.md) (enforce §2) ·
[`eval-gate`](../eval-gate/SKILL.md) +
[`verify-before-completion`](../verify-before-completion/SKILL.md) (enforce
§5) · [`propagate`](../propagate/SKILL.md) (enforces §1 cross-repo lane) ·
`skills/_shared/knowledge_liveness.py` (enforces §4 mechanically).

## §1 SCOPE classification is mandatory at banking time

Every candidate lesson is classified before it is written anywhere:

| SCOPE | Where it lands |
|---|---|
| `this-skill` | the skill's own SKILL.md / tools |
| `this-repo` | repo-scoped fact/lesson, not tied to one skill — wiki-memory (L2 fact, L3 SOP) |
| `cross-skill` | THIS canon doc (or ORCHESTRATION.md if orchestration-shaped); skills get a pointer |
| `cross-repo` | repo canon here + `propagate` queue entry for siblings |
| `canon` | this doc; all consuming skills get pointers |

Banking a cross-skill lesson into a single skill's notes is a **gate
failure**, not a style choice — the next skill that needed it will not read
it (failures #1, #3). Unclassified = unbanked.

## §2 A user correction is closeout-blocking

A user correction (relabel, "no — do X", repeated re-teach) MUST become a
durable artifact — **rule + gate + exemplar** — before the task closes.
Not opt-in, not "if a retrospective is armed" (failure #2: the same
correction re-taught across sessions). Minimum durable artifact: a
SCOPE-classified rule (§1) plus, when the lesson is PASS/FAIL-expressible,
the executable guard of §3. Chat-turn compliance is not capture.

## §3 Mechanism over prose

A lesson expressible as PASS/FAIL MUST land as an executable check (test,
probe, lint rule, gate) — never only as runbook prose (failure #6: every
prose-only gotcha recurred). Two subrules:

- **Negative test first.** A gate that has never tripped is unproven
  (failure #11: the first body-gate blessed the known-bad part). Every new
  gate ships with a known-bad input it demonstrably rejects.
- **Invariant over heuristic.** The lesson template asks: *what is the
  design-independent invariant?* A fix tuned to one instance misfires on
  the next (failure #7). If no invariant exists, say so explicitly and
  bank the heuristic WITH its known scope of validity.

## §4 Gates must be alive

Enforcement machinery silently dead is worse than absent — it converts
vigilance into false confidence (failure #5: specs.yaml unparseable 3 days,
every gate inert). Therefore:

- All machine-readable gate substrate (drift_probes.json, lesson_patterns,
  hooks maps, wiki links, tool paths referenced by SKILL.md) is covered by
  a standing liveness lint (`knowledge_liveness.py`) wired into install and
  the test suite.
- A rule must live ON the read path of the decision it governs (router
  output, gate, tool `--help`) — not at line 388 of a skill nobody re-reads
  (failure #8). Dangling references and orphan rules are lint findings.

## §5 Verifier independence is structural, not situational

- Judge criteria derive from the FULL spec + canon gates, NEVER from the
  executor's claims or a rubric co-authored with the work (failure #9:
  independent context + dependent criteria = false DONE).
- Sampling never verifies a repeated element: N artifacts → N checks, plus
  at least one COMPUTED comparison against source ground truth where one
  exists (failure #10: three sampling layers passed the same wrong part).
- Done-claim pressure is prevented in briefs (executor contract: READY FOR
  JUDGING, never "done"), because hooks do not fire inside subagents
  (failure #12).

## §6 Improvement work IS production work

Self-improvement changes get the same treatment as shipped code: verifier +
judge, checkpoint commits, and a **live gauntlet** against a real case
before the round is declared done (failures #13, #14: 71 dirty files and
zero falsifying runs). Meta-layer additions (canaries, ledgers, rules)
require an object-level justification; the default remedy is **fix or
delete**, not "add a rule" (failure #15).

## §7 Repo canon over private memory

Anything an executor on ANY host (Claude, Codex, Gemini) needs to act
correctly lives in the repo. Private memory dirs and host-specific stores
hold pointers and personal context, never the sole copy of a canonical
rule (failure #4).

## §8 Anticipate at ship time — premortem, lifecycle, gauntlet

Why the 20 failures were not predicted: Brainer's own testing method (probe
fire P/R + in-session A/B lift) validates a skill **within one session**.
Every failure class that hit screenery-lean was a **lifecycle** failure —
across sessions, repos, and hosts — a dimension the shipping process never
tested. The meta-rules that close that hole:

- **Premortem is part of shipping.** Every new or changed skill answers, in
  its EVAL/design notes: *how does this fail silently? what rots when nobody
  looks? what happens on a host without hooks?* A skill whose failure modes
  are undeclared is unshipped design, and "the machine gate is dead" (§4)
  must always be on the list.
- **Lifecycle test (E3).** Beyond E1 (trigger P/R) and E2 (A/B lift), a
  learning-surface skill needs E3: a lesson banked in session A is visible
  AND enforced in a fresh session B, in a consuming repo, on a second host
  where applicable. In-session pass ≠ lifecycle pass.
- **Consumer-repo gauntlet as release gate.** Skill changes meet a real
  task in a real consuming repo (PROMPTER is the standing live target)
  before `propagate` rolls them out — the live-executor battery, §6's
  gauntlet applied to Brainer itself.
- **Detection is not prevention.** A canary that flags drift after the fact
  is layer 2; the shipping gate that refuses the defect is layer 1. Every
  detection-only control names its missing prevention twin or documents why
  none can exist.
