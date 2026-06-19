# EVAL — `brainer-audit`

## Static cost

Run `python3 eval/static_cost.py --json` after catalog changes.

| field | tokens / size |
|---|---|
| description (always resident) | **67 tokens** (344 chars) |
| body (loaded on trigger) | **927 tokens** (4,128 chars) |
| tools/ payload | **30.9 KB** (`ingest_event.py` · `inspect_session.py` · `detectors.py` · `report.py` · `test_brainer_audit.py`) |
| model pin | `any` (none) |
| effort pin | `medium` |

## Purpose metric

This skill optimizes Brainer obedience and drift discovery, not token reduction. The MVP metric is detector precision on deterministic offline fixtures.

## Functional checks

- `python3 skills/brainer-audit/tools/test_brainer_audit.py`
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
- malformed event log fails cleanly.

## Known gaps

- No live Claude/Codex hooks yet. PR 4 owns host adapters.
- No Antigravity sidecar yet. PR 5 owns lower-fidelity watcher support.
- No apply mode. Candidate Brainer improvements are report-only.
- No LLM judge. MVP detectors are deterministic and intentionally conservative.
