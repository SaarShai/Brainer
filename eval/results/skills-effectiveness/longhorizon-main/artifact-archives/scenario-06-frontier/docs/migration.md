# Migration Handoff

Use `migration/plan.json` as the source of truth. Schema version `1` uses the
`canary` strategy with batch size `25`, rollback error rate `0.02`, and
`dry_run_first` set to `true`. The migration owner is `platform-migrations`.

## Safety condition

legacy_id is preserved through phase 3
