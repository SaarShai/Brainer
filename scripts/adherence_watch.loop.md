# adherence-watch — loop spec

Weekly, unattended, **report-only** outer loop: regression-check the skill
trigger probes against their adversarial corpora and trend real-session drift
probe fires. Companion to drift-watch (files in sync ≠ skills obeyed).

```loop
name: adherence-watch
topology: outer
open_or_closed: closed
schedule: weekly (cron, Mon 09:23)
generator: scripts/adherence_watch.sh (runs trigger_suite --mode probe + measure.py over the week's transcripts, writes .brainer/adherence-reports/<date>.md)
verifier: human reads the report; any probe fix goes through check_drift_probes.py + the canary test suite before shipping
gate: exit code 0 from `bash scripts/adherence_watch.sh` AND `test -f .brainer/adherence-reports/$(date +%F).md` exits 0; ACTION NEEDED line iff any corpus FAIL
stop: one pass per scheduled run (report written)
budget: max_iterations=1 per run; wall-clock < 3 min; zero model calls
verifier_blind: true
verifier_inputs: task, outputs
output_actions: write_report max 1
anchor_files: eval/MEASUREMENT_QUEUE.md, eval/adherence/corpora/
state_store: .brainer/adherence-reports/ (last 12 kept)
recall: read the newest prior report before interpreting a new one (trend, not snapshot)
writeback: the dated report file
redaction: none needed — local filesystem only, no egress
consent: n/a (no egress)
human_gate: probe/corpus edits are human-reviewed commits; this loop never edits skills
```
