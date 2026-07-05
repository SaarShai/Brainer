# E2 A/B: spec-tied criterion + typed stop states — once-through eval pipeline

topology: closed · inner · single
generator: glm-5.2 naive subjects — fresh context per call, no Brainer boot context, subjects not told they are in an eval
verifier: python3 eval/e2-rules-202607/run_e2.py --grade (deterministic regex checks) + a BLIND cross-family binary judge on local Ollama qwen3.6:35b for the spec-tie question only; verifier_blind: true; verifier_inputs: task, outputs (judge never sees arm label or subject reasoning)
gate: python3 eval/e2-rules-202607/run_e2.py --grade exits 0 and writes results.json with per-cell PASS/FAIL + lift per eval; unparseable subject output = FAIL fail-closed
stop: all planned cells graded exactly once — done; any arm with <75% parseable outputs = BLOCKED, report instead of verdict
budget: max_iterations=1 (once-through), max 100 GLM calls, max 30 min wall-clock
redaction: prompts are synthetic eval text only (no repo content); all egress strings pass audit_redact.redact_secrets before send
on_error: transient (network/rate-limit) → 1 retry with backoff; auth/key missing → interrupt, human-fixable; policy/classifier block → skip cell, log, never retry same lane; unexpected → halt and surface
state_store: eval/e2-rules-202607/results.json (written once at end)
output_actions: write files under eval/e2-rules-202607/ only
