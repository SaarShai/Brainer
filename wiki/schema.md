# Token Economy Wiki — Schema

Purpose: persistent, contextual, inter-linked long-term memory for AI agents working in the current target project. Karpathy 3-layer (raw/wiki/schema) + git-wiki immutability + progressive retrieval.

This file is the operating contract. Agents must use the wiki before reasoning about stored project facts, and must document durable discoveries after verified execution.

## Folders
- `raw/` immutable sources (papers, repos, gists). Filename: `YYYY-MM-DD-slug.md`.
- `concepts/` atomic ideas (one technique per page).
- `patterns/` reusable workflows, recipes.
- `projects/` active target-project state.
- `people/` humans (authors, collaborators).
- `queries/` durable Q&A.
- `L0_rules.md` stable behavior rules loaded at startup.
- `L1_index.md` compact pointer index loaded at startup.
- `L2_facts/` verified durable facts.
- `L3_sops/` solved-task playbooks.
- `L4_archive/` cold session archives and fresh-start packets.

## Frontmatter v2 (new pages)
```
---
schema_version: 2
title: Example
type: entity|summary|decision|source-summary|procedure|concept|pattern|project|query|fact|sop|raw|person|handoff
domain: framework|tools|patterns|experiments|project
tier: working|episodic|semantic|procedural
confidence: 0.0
created: YYYY-MM-DD
updated: YYYY-MM-DD
verified: YYYY-MM-DD
sources: []
supersedes: []
superseded-by:
tags: []
---
```

Legacy v1 pages remain readable. `./te wiki lint --strict` emits migration warnings for v1 pages and enforces v2 fields on v2/template-generated pages.

## Ops
- **Ingest**: source -> `raw/`, update relevant concepts/projects/patterns, add backlinks, append `log.md`, update `index.md`/`L1_index.md`.
- **Query**: `wiki context` for audited bounded task context, or `wiki search` -> inspect compact hits -> `timeline` -> `fetch` only pages needed -> answer with path citations -> file useful synthesis in `queries/` when reused.
- **New concept**: full frontmatter, link related, add to index.
- **Evidence up**: bump `evidence_count`, recalibrate confidence.
- **Contradiction**: flag both pages, prefer newer/stronger evidence, downgrade confidence, log.
- **Crystallize**: after successful verified work, write an L3 SOP if the workflow is reusable.

## Imported Wiki Completeness

Imported projects must be self-contained in the new working folder.

- Treat any source project wiki as evidence to adapt, not as a dependency to keep using.
- Recreate all useful source-wiki information in repo-local Token Economy pages.
- Track every source-wiki item in `raw/YYYY-MM-DD-import-manifest.md` with status `adapted`, `archived`, or `discarded`.
- `index.md` and `L1_index.md` must point to local wiki pages and local commands only.
- Agents must not use home-directory rules, external wikis, or source-wiki paths for project facts after import.
- Validate imports with `./te wiki lint --strict --fail-on-error` and `./te wiki import-audit --manifest raw/YYYY-MM-DD-import-manifest.md`.

## Retrieval Discipline

Default command sequence:

```bash
./te wiki search "<task/topic>"
./te wiki timeline "<id>"
./te wiki fetch "<id>"
```

Use `./te wiki context "<task/topic>"` when an agent needs one audited packet listing loaded, uncertain, and rejected wiki citations.
Use `./te code map "<symbol/path/topic>"` before loading broad source files for code tasks.

Rules:
- Load `L1_index.md` first, never the whole wiki.
- Search before full fetch.
- Fetch all relevant pages, and only relevant pages.
- Treat `raw/` pages as search-visible but not auto-loaded unless raw/source/archive context is explicitly requested.
- Stop fetching when additional pages would not change the plan or answer.
- Cite page IDs or paths in answers and durable notes.
- If search finds nothing, say so and use `rg`/filesystem search before inventing.

## Documentation Discipline

Document only after verified work:
- successful command, test, build, benchmark, install, source read, or user-confirmed decision.
- no execution -> no durable memory.
- failed attempts can be recorded in session archive or issue notes, but do not promote as facts.
- raw sources are append-only; synthesized pages can be updated with supersession links.

Every material update must:
- include provenance (source path, URL, command, result, or linked note)
- add backlinks where useful
- append `log.md`
- refresh `L1_index.md` with `./te wiki index` when page pointers change

## Confidence rungs
- low: 1 source, unverified
- med: 2+ sources OR 1 source + sanity check
- high: 3+ sources + independent verification + measured numbers
