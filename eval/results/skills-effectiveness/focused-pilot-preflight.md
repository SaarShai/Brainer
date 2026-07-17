# Focused pilot transport preflight

The first four calls under `focused_pilot_preregistration.json` were a balanced
one-case transport preflight: `OFF` and `FRONTIER` on Codex and Claude. All four
activated the intended native skill body and passed the external deterministic
task check. They are excluded from outcome analysis because the preflight found
three harness defects before scaling:

- external and model-run Python created unignored `__pycache__/`, contaminating
  scope metrics;
- generic recursive token parsing double-counted cumulative stream usage;
- Claude's broad Bash surface recorded an additional tool attempt beyond the
  intended check command.

The raw redacted records remain under
`focused-pilot-2026-07-16/`. The replacement v2 preregistration removes
`coding-00`, freezes 19 remaining case pairs per host (76 calls), disables
Claude Bash entirely, runs acceptance externally, ignores Python bytecode, and
uses each host's terminal usage record. Four preflight plus 76 outcome calls
preserves the approved 80-call cap.
