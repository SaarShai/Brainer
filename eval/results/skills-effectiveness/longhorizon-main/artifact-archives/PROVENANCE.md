# Artifact-archive provenance (2026-07-18)

The session driver resets (rm -rf) the shared fixture dir at session start and
does not archive final artifacts, so each scenario's first-arm (OFF) final
files were destroyed when the FRONTIER arm started. Recovered as follows —
every file verified against sha256 hashes recorded mechanically inside the
session's own transcript (command_execution aggregated_output, not model
prose):

| archive | source | verification |
|---|---|---|
| scenario-02-frontier/, scenario-06-frontier/ | disk (each ran last) | disk sha256 == CURRENT_HASHES in frontier turn-40/41 transcripts |
| scenario-02-off/ | verbatim FILE dump, turn-42 | sha256 == LEAD-HASH values in turn-41 (config e6e07cdc…, docs 500fbc83…) |
| scenario-06-off/ | verbatim semdiff full dump, turn-42 | exact sha256 == plan_sha256/docs_sha256 in turn-40/41 (8bf594bc…, 814c929b…) |

Counted-run scoring is PAUSED (owner decision 2026-07-18): probe data complete
(4/4 sessions, 44/44 turns each, exit 0), verdict deferred. When resumed, score
each session against ITS archive here, not the shared venue fixture dir.
