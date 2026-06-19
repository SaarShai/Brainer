# EVAL — `brainer-audit`

## Static cost

Run `python3 eval/static_cost.py --json` after catalog changes.

| field | tokens / size |
|---|---|
| description (always resident) | **67 tokens** (344 chars) |
| body (loaded on trigger) | **1,412 tokens** (6,121 chars) |
| tools/ payload | **69.0 KB** (`audit_session.py` · `antigravity_sidecar.py` · `watch_artifacts.py` · `hook.py` · `install.sh` · `normalize.py` · `ingest_event.py` · `inspect_session.py` · `detectors.py` · `report.py` · tests) |
| model pin | `any` (none) |
| effort pin | `medium` |

## Purpose metric

This skill optimizes Brainer obedience and drift discovery, not token reduction. The MVP metric is detector precision on deterministic offline fixtures.

## Functional checks

- `python3 skills/brainer-audit/tools/test_brainer_audit.py`
- `python3 skills/brainer-audit/tools/test_hooks.py`
- `python3 skills/brainer-audit/tools/test_antigravity_sidecar.py`
- `python3 -m pytest tests/test_audit_modes_hardening.py -q`
- `python3 skills/brainer-audit/tools/inspect_session.py --events <events.jsonl> --format json`
- `python3 skills/brainer-audit/tools/inspect_session.py --events <events.jsonl> --format markdown`

Current fixture coverage:

- normalized event ingestion;
- stable markdown report with no file mutation;
- unverified completion claim detection;
- dropped requirement detection;
- missed output-filter opportunity detection;
- repeated tool-error loop detection;
- task-retrospective boundary violation detection;
- write-gate bypass detection and suppression when gate evidence exists;
- malformed event log fails cleanly;
- cross-collector no-write regression coverage;
- redaction consistency across task-retrospective and Brainer-audit collectors;
- stable report fixtures for clean, compound-finding, boundary-error, and Antigravity lower-fidelity cases.

## Known gaps

- Claude/Codex hooks are opt-in and marker-gated; no hooks are auto-installed by a bare `./install.sh`.
- Antigravity support is lower-fidelity sidecar support only; no native hook adapter is claimed.
- No apply mode. Candidate Brainer improvements are report-only.
- No LLM judge. MVP detectors are deterministic and intentionally conservative.
