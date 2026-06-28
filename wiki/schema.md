# Brainer Wiki — Schema

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

> Where knowledge actually lives: in practice durable facts are filed under the
> topical folders (`concepts/`, `queries/`) and reusable playbooks under
> `patterns/` (and `L3_sops/` for runbook-style SOPs). `L2_facts/`/`L3_sops/` are
> available L-tier buckets, often empty — they are not the primary store. Choose
> the folder by *kind of knowledge*, not by L-tier number; `L1_index` catalogs
> `concepts/`+`patterns/`+`projects/`+`queries/` so they are discoverable.

## Frontmatter v2 (new pages)
```
---
schema_version: 2
title: Example
type: entity|summary|decision|source-summary|procedure|concept|pattern|project|query|fact|sop|raw|person|handoff|error|lesson
domain: framework|tools|patterns|experiments|project
tier: working|episodic|semantic|procedural
confidence: 0.0
created: YYYY-MM-DD
updated: YYYY-MM-DD
verified: YYYY-MM-DD
sources: []
resource:            # optional, single-valued: the one live artifact this page documents
supersedes: []
superseded-by:
tags: []
---
```

`resource:` (optional, OKF-aligned) is the canonical URI/path of the single live artifact a page documents — existence-checkable, unlike the overloaded `sources:` list. Strict lint emits `broken_resource`; `python3 skills/wiki-memory/tools/wiki.py audit-refs` resolves it alongside body refs. A `[[?stub]]` wikilink (leading `?`) is a sanctioned forward-ref to not-yet-written knowledge and is exempt from the broken-link error.

Legacy v1 pages remain readable. `python3 skills/wiki-memory/tools/wiki.py lint --strict` emits migration warnings for v1 pages and enforces v2 fields on v2/template-generated pages.

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
- Recreate all useful source-wiki information in repo-local Brainer pages.
- Track every source-wiki item in `raw/YYYY-MM-DD-import-manifest.md` with status `adapted`, `archived`, or `discarded`.
- `index.md` and `L1_index.md` must point to local wiki pages and local commands only.
- Agents must not use home-directory rules, external wikis, or source-wiki paths for project facts after import.
- Validate imports with `python3 skills/wiki-memory/tools/wiki.py lint --strict --fail-on-error` and `python3 skills/wiki-memory/tools/wiki.py import-audit --manifest raw/YYYY-MM-DD-import-manifest.md`.

## Retrieval Discipline

> Invocation: commands below call the tool directly with
> `python3 skills/wiki-memory/tools/wiki.py …`. (`./te` in older notes was a
> planned unified wrapper that was never shipped — there is no `./te` binary.)

Default command sequence:

```bash
python3 skills/wiki-memory/tools/wiki.py search "<task/topic>"
python3 skills/wiki-memory/tools/wiki.py timeline "<id>"
python3 skills/wiki-memory/tools/wiki.py fetch "<id>"
```

Use `python3 skills/wiki-memory/tools/wiki.py context "<task/topic>"` when an agent needs one audited packet listing loaded, uncertain, and rejected wiki citations.
Use `python3 skills/wiki-memory/tools/code_map.py "<symbol/path/topic>"` before loading broad source files for code tasks.

Rules:
- Load `L1_index.md` first, never the whole wiki.
- Search before full fetch.
- **Navigate the link graph, don't re-search blindly.** `timeline "<id>"` returns
  `backlinks` (what cites this → go broader), `outbound` (what this points to → go
  deeper), and `neighbors` (same-dir siblings → fallback). Both backlinks and
  outbound stem-resolve `[[bare]]` links, so the graph is symmetric. Follow the
  edge most relevant to the task as your next `fetch` before broadening to a fresh
  keyword search — the link graph is your primary navigation index.
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
- refresh `L1_index.md` with `python3 skills/wiki-memory/tools/wiki.py index` when page pointers change

## Confidence rungs
- low: 1 source, unverified
- med: 2+ sources OR 1 source + sanity check
- high: 3+ sources + independent verification + measured numbers
