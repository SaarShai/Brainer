# E2 follow-up: drop-at-cap — once-through eval pipeline

topology: closed · inner · single
generator: glm-5.2 naive subjects — fresh context per call, thinking disabled, subjects not told it's an eval
verifier: python3 eval/e2-rules-202607/run_e2b.py --grade — deterministic ID-based leftover checks, separate actor; every FAIL and every strongest-claim cell eyeballed from raw_b.json before certifying
gate: python3 eval/e2-rules-202607/run_e2b.py --grade exits 0 and writes results_b.json with per-cell PASS/FAIL + lift; unparseable = FAIL fail-closed
stop: all 12 cells graded exactly once — done; any arm <75% parseable = BLOCKED (exit 3), report not verdict
budget: max_iterations=1, max 30 GLM calls, max 20 min wall-clock
redaction: prompts are synthetic eval text only; egress strings pass audit_redact.redact_secrets
on_error: transient → 1 retry with backoff; auth/key missing → interrupt, human-fixable; policy/classifier block → skip cell, log, never retry same lane; unexpected → halt and surface
state_store: eval/e2-rules-202607/results_b.json (written once at end)
output_actions: write files under eval/e2-rules-202607/ only
