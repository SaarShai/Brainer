---
name: wiki-memory
description: Repo-local markdown wiki with progressive retrieval (search → timeline → fetch) and gated writes (verified facts only). Use when the task references past work, decisions, memory, "have we done X", project facts, or when you need to record a durable finding. Tiered: L0 rules · L1 pointer index · L2 facts · L3 SOPs · L4 archive. Replaces note-app sprawl; no global agent config.
model: any
effort: low
tools: [Bash, Read, Write, Glob, Grep]
---

# wiki-memory

Long-term repo-local memory. One skill, two modes: **retrieve** (read) and **write** (gated).

## Retrieve

Use when the task references past work, decisions, docs, memory, project facts, or "have we done X".

1. Read `wiki/L1_index.md` first.
2. Run `python skills/wiki-memory/tools/wiki.py search "<query>"`.
3. For relevant hits, `python ... timeline "<id>"`.
4. Fetch ≤3 pages first with `python ... fetch "<id>"`.
5. If insufficient, fetch ≤2 more pages.
6. Cite page paths/IDs in your response.

Never:
- load the whole wiki
- speculatively fetch raw/ archives
- cite a superseded page without noting the newer one

## Write

Trigger:
- verified finding
- user-confirmed decision
- source ingested
- reusable procedure discovered
- non-trivial failure lesson worth preventing later

Protocol:
1. Search existing pages first.
2. Prefer updating an existing page over creating a new one; fewer rich pages beat many thin one-off pages.
3. If no page, run `python skills/wiki-memory/tools/wiki.py new --template page --title "<title>" --domain "<domain>"`.
4. Name new pages at domain/category level, not task-specific bug names.
5. Fill v2 frontmatter completely.
6. For procedures/failures, include when it applies and the exact prevention rule.
7. Add ≥2 useful wikilinks when possible.
8. Append `wiki/log.md`.
9. Run `python ... index`; for new v2 pages run `python ... lint --strict`.

Write-gate (enforced in `tools/wiki.py`):
- No durable memory from unexecuted plans.
- No trivial lookups inflated into fake procedures.
- `wiki/raw/` is immutable after creation.
- No duplicate page without supersession.

## Tier layout

```
wiki/
├── L0_rules.md        # stable behavior rules
├── L1_index.md        # compact pointer catalog
├── L2_facts/          # durable facts
├── L3_sops/           # solved-task playbooks
├── L4_archive/        # cold session archives
├── concepts/          # atomic technique pages
├── patterns/          # reusable workflows
├── projects/          # target-project pages
├── people/            # referenced humans
├── queries/           # durable Q&A
├── raw/               # immutable sources
├── index.md           # rich catalog
├── log.md             # append-only timeline
└── schema.md          # contract for page types
```

## Optional MCP

`tools/wiki_mcp/` exposes `wiki_search`, `wiki_fetch`, `wiki_timeline`, `wiki_new` for MCP-aware hosts.

## Files

```
tools/
├── wiki.py            # search/fetch/timeline/new/index/lint
├── code_map.py        # symbol-level navigation aid
├── write_gate.py      # gate library (no execution, no memory)
├── wiki_mcp/          # optional MCP server
└── INSTALL.md
```
