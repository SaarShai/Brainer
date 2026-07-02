# drift-watch — loop spec

Weekly, unattended, **report-only** outer loop: detect sibling skill drift
before it silently accumulates (the 2026-06 drift sat unnoticed for weeks).
Each scheduled run is a single budget=1 pass; a human consumes the report and
decides whether to run the propagate skill. Linted by
`skills/loop-engineering/tools/loop_lint.py` (exit 0 required before the cron
is installed).

```loop
name: drift-watch
topology: outer
open_or_closed: closed
schedule: weekly (cron, Mon 09:17)
generator: scripts/drift_watch.sh (runs sibling_sync_audit.py --classify, writes .brainer/drift-reports/<date>.md)
verifier: human reads the report; the propagate skill's own verify/post-check gates any subsequent apply
gate: exit code 0 from `bash scripts/drift_watch.sh` AND `test -f .brainer/drift-reports/$(date +%F).md` exits 0
stop: one pass per scheduled run (report written)
budget: max_iterations=1 per run; wall-clock < 2 min
verifier_blind: true
verifier_inputs: task, outputs
output_actions: write_report max 1
anchor_files: wiki/concepts/brainer-multi-repo-topology.md, skills/propagate/SKILL.md
state_store: .brainer/drift-reports/ (last 12 kept)
recall: read the newest prior report before interpreting a new one (trend, not snapshot)
writeback: the dated report file
redaction: none needed — no cross-vendor egress; local filesystem only
consent: n/a (no egress)
human_gate: any APPLY action (fast-forward/adopt) happens only via the propagate skill, human-invoked — this loop never writes to siblings
```
