# Memory model

Brainer separates durable memory from derived indexes and scratch outputs. The goal is useful continuity without turning every local artifact into truth.

## Canonical durable memory

`wiki/*.md` is the canonical durable memory layer. These files hold reviewed decisions, procedures, lessons, project facts, and source summaries. Future agents should retrieve from markdown first, using `wiki/L1_index.md` as the compact pointer map for high-value pages and folders. `L1_index.md` is not an exhaustive manifest of every nested page.

## Derived memory indexes

`.brainer/wiki.sqlite3` is derived index data. It can be rebuilt from `wiki/*.md` by wiki tooling and must not be treated as the source of truth.

## Scratch and audit outputs

The following are runtime or audit outputs unless explicitly promoted:

- `scratch/`
- `.brainer/audit_results.json`
- `.brainer/verify_results.json`
- `.brainer/ledger/`
- `.brainer/sessions/`
- `.deepeval/`
- transient eval run logs

Promote durable findings into `wiki/*.md` or docs, not by relying on scratch output remaining on disk.

## Write policy

Durable memory should be:

- verified against a command, file, test, source, or user-confirmed decision
- stable enough to help a future session
- specific enough to prevent repeated work or repeated mistakes
- safe to preserve

Use `write-gate` before persistent writes. It is a signal-quality gate, not a truth oracle, so factual claims still need evidence.

## Refresh policy

Use `wiki-refresh` when code, paths, hook behavior, or documented procedures may have drifted. Use the narrowest affected page, tag, or directory rather than refreshing the entire wiki by habit.

## Hygiene check

Run:

```bash
make check
```

The memory-specific part is:

```bash
python3 scripts/check_wiki_hygiene.py
```

This check verifies the core wiki files and this model doc exist, and that `.brainer/wiki.sqlite3` is documented as derived rather than canonical.
