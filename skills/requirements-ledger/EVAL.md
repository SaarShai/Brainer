# requirements-ledger — EVAL

**Posture: default-installed by explicit user directive, not by measured A/B.**
The no-drop guarantee is unconditional ("never switch off, never opt out") — the
user ranked silently-dropped requests as the top failure. Load-bearing by fiat;
measurement below is for tuning, never for an opt-out.

## What it is
Visible per-session markdown ledger (`.brainer/ledger/<sid>.md`) holding one row
per atomic intent item; native-task mirror on Claude Code; reconcile-and-ask
before any close. Mechanical floor enforced by `compliance-canary`
(`ledger_not_materialized`, `completion_without_closure`, coarse request ledger).

## Deterministic coverage (green)
The enforcement probes are tested in `compliance-canary/tools/test.sh` (ledger
capture, wrap-up surfacing, closure phrases, no-opt-out). This skill itself is
prompt-procedure — no tool of its own to unit-test.

## What to measure (when N is available)
- **Drop rate** — corpus of multi-conjunct prompts ("do X, Y, and Z; also W?");
  count conjuncts silently unaddressed at session end, with vs without the
  ledger. The target metric — should approach 0 with the ledger.
- **Capture noise** — false rows per session (acknowledgements captured as
  asks); bias is deliberately toward over-capture, but track the nag cost.
- **Closure discipline** — fraction of completion claims preceded by a
  reconcile block + explicit "ok to close?" (transcript-mineable).
