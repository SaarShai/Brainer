# Focused FRONTIER versus OFF pilot

Date: 2026-07-16
Verdict: **feasible null; do not expand the paid matrix**

## Result

The compact frontier-protection body produced no task-success or scope-safety
lift over the native `OFF` control on this frozen set. Both arms passed every
case in both host lanes. The preregistered expansion gate required at least a
10-point pass-rate lift in each lane, no scope regression, and no more than 15%
median token overhead. The observed pass-rate delta was zero, so the gate did
not clear.

| lane | valid pairs | OFF pass | FRONTIER pass | pass delta | scope violations OFF / FRONTIER | paired median token overhead | median wall seconds OFF / FRONTIER |
|---|---:|---:|---:|---:|---:|---:|---:|
| Codex default | 19 | 19 | 19 | 0 points | 0 / 0 | +1.20% | 42.07 / 45.64 |
| Claude opus alias | 19 | 19 | 19 | 0 points | 0 / 0 | +1.74% | 25.99 / 30.46 |

For each lane, McNemar had zero discordant pairs and two-sided `p=1.0`. The
paired bootstrap over the observed frozen sample returned a zero delta with a
degenerate `[0, 0]` interval because every arm passed every case. That interval
must not be generalized beyond this ceilinged sample.

## Integrity checks

- 76/76 v2 outcomes completed: 19 cases × 2 arms × 2 hosts.
- The four earlier v1 transport probes were **completed** outcomes, not
  invalidated runs: all four passed the deterministic task check, but each
  recorded a harness-induced material-scope violation (unrequested
  `__pycache__/` writes from the pre-fix harness; see
  `focused-pilot-2026-07-16/campaign-summary.json` and outcome records). They
  are excluded from outcome analysis for those scope violations. They are
  balanced one per lane×arm cell (Codex/Claude × OFF/FRONTIER), so the
  exclusion is symmetric and unlikely to bias the paired conclusion. Together
  with v2, they exhaust the approved 80-call cap.
- Every pair used the same user-task hash and a fresh, single-use git fixture.
- Native arm-body delivery was observed in 76/76 outcomes. The marker proves
  delivery, not compliance with every rule in the body.
- There were zero blockers, tripwire leaks, permission denials, unsafe tool
  attempts, unrequested-write records, reused fixtures, or material scope
  violations.
- Median observed tool calls were identical by arm: 12 for Codex and 5 for
  Claude. Codex ran the in-fixture check in 38/38 outcomes; Claude had no Bash
  capability, so the harness ran deterministic acceptance externally.
- Median total token telemetry was 111,986 OFF versus 112,765 FRONTIER for
  Codex and 69,156 versus 70,035 for Claude. The preregistered overhead metric
  is the median of paired ratios, not the ratio of these arm medians.

The Claude trace reported `claude-opus-4-7` plus
`claude-haiku-4-5-20251001` in host model-usage telemetry. Codex CLI 0.144.1 did
not report served model identity in its JSON trace, so the Codex lane is
accurately labelled only as the host's current default. Claude Code was
2.1.146. The same Claude model-usage pair appeared in 19/19 OFF and 19/19
FRONTIER records; no arm imbalance was observed. All strata were also ceilinged
in both lanes and arms: trivial 4/4, normal 10/10, and compound 5/5.

Claude had no Bash capability, so adherence to FRONTIER's evidence-gathering
rule was not directly observable in that lane; the external acceptance check
measured the resulting artifact. Codex ran the requested check in both arms,
which means this corpus had no remaining headroom to measure an incremental
verification-behavior effect.

## Interpretation and action

This is evidence against paying for the preserved 8,300-run broad matrix and
against claiming that the compact static body improved outcomes on these 19
frozen coding cases. It is not a retirement verdict for longitudinal canary hooks,
compaction handoff, wiki trust gates, task-specific acceptance criteria, or the
mechanical verifier: those are different estimands and were not exercised here.

The sample also has a ceiling effect. A harder follow-up would only be justified
by a specific residual risk that deterministic trigger tests or shadow
telemetry expose. The default action is therefore to keep the Wave 1 quiet
defaults and minimum protection mechanisms, continue the hash-pinned
quarantine/role-brief decisions, and spend no more model calls on this compact
body without a new preregistered failure hypothesis.

Machine-readable analysis:
`eval/results/skills-effectiveness/focused-pilot-v2-analysis.json`.
Preregistration SHA-256:
`3d233acba3287b017bc6ed7df70dd0cd30a4a7daca9531727791df84364f678c`.
