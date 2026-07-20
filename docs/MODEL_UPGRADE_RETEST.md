# Model-upgrade re-test ritual

## Why

The 2026-07-16 skill-effectiveness campaign found a **FRONTIER-vs-OFF null**:
the focused v2 pilot (76 valid outcomes, 19 frozen task families x 2 arms x 2
hosts) showed zero pass-rate lift from the compact static doctrine bodies on
that era's frontier models (`eval/FINDINGS.md`, "2026-07-16 skill-effectiveness
verification campaign"). The 2026-07-18 long-horizon counted probe
independently returned a binding **DEMOTE** verdict under the preregistered
`no_improvement_n2_zero_better` rule (`eval/FINDINGS.md`, "2026-07-18
long-horizon counted probe: SCORED"). Both results back the shelf-life
doctrine (Every.to "The Case Against Skills", 2026-07-16 harmful-skills
campaign) and the 2026 harness literature: a scaffold that compensates for one
model's weaknesses is a **capability-dated artifact** — its measured lift can
evaporate, or flip to pure overhead, the moment the underlying model improves.
A past pass/fail verdict does not carry over to a new model tier; it must be
re-measured.

## Trigger

Run this ritual whenever a host adopts a new frontier model tier for
main-loop work in a Brainer-consuming project (e.g. the model behind "Fable 5"
moving to its successor, GPT-5.6 moving to GPT-5.7). This is a
manually-executed ritual carried out by an agent when triggered — no cron, no
new automation.

## Steps

### a. Re-run the FRONTIER-vs-OFF pilot

Re-run the same 19-frozen-task-family focused pilot
(`eval/skills_effectiveness/focused_pilot.py`) on the new model tier and
record pass rates and token overhead against the prior null:

```bash
python3 eval/skills_effectiveness/focused_pilot.py --plan
python3 eval/skills_effectiveness/focused_pilot.py --execute \
  --campaign-dir eval/results/skills-effectiveness/focused-pilot-v2-<model-tag>-<YYYY-MM-DD> \
  --max-runs 10   # smoke cap first; drop --max-runs for the full 76-run campaign
python3 eval/skills_effectiveness/focused_pilot.py --analyze \
  --campaign-dir eval/results/skills-effectiveness/focused-pilot-v2-<model-tag>-<YYYY-MM-DD> \
  --out eval/results/skills-effectiveness/focused-pilot-v2-<model-tag>-analysis.json
```

`--execute` makes live paid model calls; smoke-cap with `--max-runs` before a
full campaign, per the existing `ab_harness.py` convention documented in
`eval/skills_effectiveness/README.md` ("Focused native pilot").

### b. Canary probe-precision spot check on live sessions

The frozen trigger corpus (`run_trigger_cases.py` / `trigger_gate.py`) drives
the deterministic hook mechanically and does not itself exercise the new
model's writing style, so it cannot detect model-specific false-fire drift by
itself. Spot-check by piping a sample of the new model's actual recent
prompts/turns through the live hook exactly as production does:

```bash
echo '{"prompt": "<verbatim prompt/turn text from a recent live session on the new model>"}' \
  | COMPLIANCE_CANARY_PROFILE=frontier python3 skills/compliance-canary/tools/hook.py
```

Any reminder output on a legitimate summarize/report-shaped turn (the shapes
the frozen corpus already tracks as hard negatives — quoted-article,
fenced-code, bare-`again`, casual `vs`, simple-draft; see
`eval/skills_effectiveness/README.md`, "Frozen trigger gate") is a false fire.
As due diligence, also re-run the mechanical gate to confirm no regression
from the code side:

```bash
python3 eval/skills_effectiveness/run_trigger_cases.py \
  --profile frontier --out /tmp/frontier-trigger-results.jsonl
python3 eval/skills_effectiveness/trigger_gate.py \
  /tmp/frontier-trigger-results.jsonl --profile frontier --json
```

If new live false fires are found, the existing remediation pattern is to
extract them and add them as new hard negatives to the corpus (see
`eval/skills_effectiveness/CODEX_FOLLOWUP_PACKET.md`, "Lane 1" — the 2026-07-18
false-interruption fix followed exactly this extract-classify-fix-regate
sequence) — that is corpus/hook maintenance work in `skills/`, routed
separately per step (d), not performed inline by this ritual.

### c. Review the auto-on skill list against the results

List the currently auto-on skills (`auto-install` missing or not `false`):

```bash
grep -L "auto-install: false" skills/*/SKILL.md
```

Cross-reference each against (a)'s pass-rate/overhead results and (b)'s
precision spot check:

- No measured lift on the new model → demotion candidate (role brief / manual,
  per the "Demote to role brief" gate below).
- Compensates for a specific fixed weakness of the *old* model that the new
  model no longer has → retirement candidate.

### d. Record verdicts

Append a dated `eval/FINDINGS.md` entry recording the new model tier, the
re-run pass rates/overhead, the probe-precision spot-check result, and any
demotion/retirement candidates from (c). Route any actual retire/demote
change through the normal branch + adversarial-review flow (as the 2026-07-18
DEMOTE and the 2026-07-19 catalog contraction both did) — never land a
retirement or demotion directly to main from this ritual.

## Decision thresholds

Reuse the campaign's preregistered gates rather than inventing new ones — all
from `docs/SKILLS_EFFECTIVENESS_VERIFICATION.md`, "Preserved full-matrix
verdict gates":

- **Keep default-on:** pass-rate lift of at least 5 percentage points, 95% CI
  above zero, no material-scope regression, no more than 15% median token
  overhead.
- **Demote to role brief:** no frontier lift but at least 5 points of mid-tier
  lift with CI above zero.
- **Retire:** no quality lift with at least 10% overhead, or a non-positive
  upper confidence bound.
- **Disable as harmful:** at least 5 points of task-success regression, or any
  attributable material scope or safety violation.

For a probe/hook verdict specifically, reuse the DEMOTE rule already applied
in production: `no_improvement_n2_zero_better` — treatment (FRONTIER) improves
neither primary metric versus control (OFF) at the tested n (`eval/FINDINGS.md`,
"2026-07-18 long-horizon counted probe: SCORED").

## Anti-scope

This document is the ritual itself. It defines no new scripts, no automation,
and no cron trigger — every command above already exists in the repository
and is invoked by hand when the trigger in this doc fires.
