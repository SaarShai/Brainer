# Fixture — unattended loop, irreversible action, no human gate

Used by H2c (`eval/harness_acceptance/run.py`) to assert that `loop_lint.py`
FAILs (not merely WARNs) an unattended spec whose generator names an
irreversible action with no human approval gate. Every OTHER lint rule
(budget, memory contract, on_error policy, output allowlist) is deliberately
satisfied so the spec isolates R7 (IRREVERSIBLE-NO-HUMAN) as the only
finding — don't add a human-approval gate here, that would defeat the check.

```loop
name: nightly-release-loop
topology: scheduled
generator: nightly job that builds the release artifact and deploys it to
  production with no review step
verifier: automated smoke test that checks the health endpoint
gate: verifier exit code
stop: 3 consecutive clean runs
budget: max_iterations=10
on_error: transient -> retry with backoff (max 2); else halt and surface
anchor_files: [release-state.json]
state_store: release-state.json
recall: read release-state.json before each pass
writeback: append run result to release-state.json
output_actions: [deploy max 1]
```
