---
name: wiki-memory
description: "Repo-local markdown wiki with progressive retrieval (search → timeline → fetch) and gated writes (verified facts only). Use when the task references past work, decisions, memory, \"have we done X\", project facts, or when you need to record a durable finding. Tiered: L0 rules · L1 pointer index · L2 facts · L3 SOPs · L4 archive. Replaces note-app sprawl; no global agent config."
effort: low
tools: [Bash, Read, Write, Glob, Grep]
---

<!-- split-justified -->

# wiki-memory

Long-term repo-local memory. One skill, two modes: **retrieve** (read) and **write** (gated).

Deep-dive reference: [REFERENCE.md](REFERENCE.md) — compile-ingest of external sources, loop-mode memory contract, consolidate/decay, schema-evolution, aging & reconcile, the graphify boundary, and OKF interop.

## First-time bootstrap (per project)

If `wiki/` doesn't exist in the project root, run once:

```bash
python3 skills/wiki-memory/tools/wiki.py init
```

Creates the `wiki/` tree (`L0_rules.md`, `L1_index.md`, `schema.md`, `L2_facts/`, `L3_sops/`, `L4_archive/`, `raw/`, `concepts/`, `patterns/`, `projects/`, `people/`, `queries/`, `templates/`) seeded from the skill's bundled defaults. Idempotent — re-running after content lands is safe and writes nothing. Default target is `./wiki` in cwd; override with `--root <path>` or `WIKI_ROOT=<path>`.

**Degraded-write detection (cbm `dump_verify.h` lineage):** after `index` (and any write that re-indexes), the result carries `status` + `persisted`. The index re-counts rows actually written to the `docs` table vs the expected page count; if `persisted < ratio × expected` it reports `status: "degraded"` instead of a silent ok — surfacing a write that only half-landed. Pages-only; a floor skips tiny stores (default 5 — below it `status` stays `ok`). Tunable: `WIKI_DEGRADED_RATIO` (default `0.5`), `WIKI_DEGRADED_FLOOR` (default `5`). On `status: "degraded"`, re-run `index` and investigate before trusting retrieval.

**Ingest decisions / ADRs (cbm `manage_adr` lineage):**

```bash
python3 skills/wiki-memory/tools/wiki.py ingest-decisions [--repo-root <path>]
```

Scans the repo (`--repo-root`, default the wiki root's parent) for `DECISIONS.md`, `DECISIONS/*.md`, and `docs/adr/*.md`, and creates one `type: decision` page per source via the normal `new`/decision-template path. The source's H1 is the page title and the dedup key, so a re-run skips already-ingested decisions rather than duplicating them. The full ADR body (Status / Context / Decision / Consequences) is preserved with a source-provenance line.

## Retrieve

Use when the task references past work, decisions, docs, memory, project facts, or "have we done X".

**Wiki-first:** when in doubt about any fact, rule, or decision, prefer reading the wiki over scrolling back through conversation history. The wiki is persistent and indexed; the context window is ephemeral and lossy (compaction silently drops detail). Retrieve before re-deriving.

1. Read `wiki/L1_index.md` first — it catalogs `concepts/` + `patterns/` +
   `projects/` + `queries/`, so it shows the knowledge that exists, not just
   project pages.
2. Run `python skills/wiki-memory/tools/wiki.py search "<query>"`.
3. For relevant hits, `python ... timeline "<id>"`. Timeline returns the page's
   **link graph**: `backlinks` (pages that cite this one), `outbound` (pages this
   one points to), and `neighbors` (same-dir). This graph *is* the retrieval
   index — read it, don't ignore it.
4. Fetch ≤3 pages first with `python ... fetch "<id>"`.
5. If insufficient, **follow the link graph before re-searching**: pick the next
   ≤2 pages from the prior page's edges (a typed edge to a related page beats a
   fresh keyword guess). Which edge: **`outbound`** = what this page depends on /
   points to (follow to go *deeper*); **`backlinks`** = what builds on or cites
   this (follow to go *broader*); **`neighbors`** = same-folder siblings (fallback
   when the typed edges miss). Judge by topical relevance to the task. Broaden to a
   new `search` only when the graph runs dry.
6. Cite page paths/IDs in your response.

**Compounding queries (file substantive answers back).** A query that produced a
*substantive synthesis* — a comparison, analysis, or decision spanning ≥2 pages, not a
trivial lookup — is itself new knowledge. File it back as a `queries/` page through the
normal gated write path (`overlap` → [`write-gate`](../write-gate/SKILL.md) → `new
--template decision` lands in `queries/`), citing the pages it synthesized, stamped
`trust: asserted` (promote on reuse via `consolidate`). This is the paper's "exploration
compounds" — the answer becomes durable so the next session recalls it instead of
re-deriving. Skip one-off / ephemeral lookups (the write **Fire condition** below still
governs).

**Loud query errors (cbm cypher.c lineage):** `search` distinguishes an *unsupported/malformed* query (empty · whitespace · punctuation-only · all-stopwords — nothing searchable) from a *valid* query that simply matched nothing. The former returns `{"error": "unsupported query: <reason>"}` and exits non-zero (`2`); the latter returns a normal empty `[]` (exit 0). Don't read an `error` payload as "no matches" — reword the query.

Never:
- load the whole wiki
- speculatively fetch raw/ archives
- cite a superseded page without noting the newer one

## Write

**Triggers:** write only when there is an explicit persistence request, an armed [`task-retrospective`](../task-retrospective/SKILL.md) run has selected a durable project lesson, a loop contract calls for durable lesson promotion, or the user-confirmed task outcome genuinely requires a repo-local memory update.

Potential sources:
- **failure / bug / issue** — a non-trivial failure, wrong approach, or bug. Record what went wrong + the exact prevention rule (error/lesson page; decay-protected).
- **feedback / correction** — when persistence is explicitly requested or task-retrospective is armed, record the corrected rule and *why* the original was wrong.
- **successful execution** — a non-trivial task solved with a reusable procedure. Distill the playbook only when it will recur and belongs in this project.
- also: verified finding · user-confirmed decision · source ingested.

**No automatic task-boundary harvest:** do not run the write protocol merely because an ordinary task ended, a correction arrived, or work succeeded. If task-retrospective was armed, let it decide relevance and target. If it was not armed, fix the issue and optionally suggest task audit mode when the lesson is clearly repeatable; do not launch a full retrospective or memory write by default.

**Fire condition (one-line test):** write **iff** the candidate is a *durable, project-specific* fact, decision, procedure, or lesson you'd want a FUTURE session to recall. **Do NOT write** plain acknowledgements, ephemeral / general-knowledge questions (arithmetic, definitions, one-off lookups), or anything with no new project-specific fact — `write-gate` filters *low-signal* noise but not *off-topic* writes, so the should-fire judgement remains with the invoking protocol.

Protocol:
1. Search existing pages first.
2. Prefer updating an existing page over creating a new one; fewer rich pages beat many thin one-off pages. **Dedup-at-write:** `python skills/wiki-memory/tools/wiki.py overlap --title "<title>" --tags "a,b" [--body-file <draft>]`. `high` → update the reported `best_match` instead of creating (two pages on one subject inevitably drift apart). `moderate` → create, but it's a Consolidate candidate for [`wiki-refresh`](../wiki-refresh/SKILL.md). `low` → create.
3. **Pre-check the candidate with [`write-gate`](../write-gate/SKILL.md)** — `python skills/write-gate/tools/write_gate.py gate --kind <kind> --file <candidate>`. If it rejects, revise or drop; do not bypass.
4. If no page, run `python skills/wiki-memory/tools/wiki.py new --template page --title "<title>" --domain "<domain>"`.
5. Name new pages at domain/category level, not task-specific bug names.
6. Fill v2 frontmatter completely.
7. **Why-clause requirement (decisions / conventions):** the page body must embed a causal why-clause — see [`write-gate`](../write-gate/SKILL.md) for the accepted phrases (note: `since` is *not* accepted — it reads as temporal and bypasses the gate; write a causal `because`/`in order to`). Reasonless decisions are rejected by write-gate.
8. For procedures/failures, include when it applies and the exact prevention rule.
8b. **Retrieval cue (the observable symptom).** For `error` / `lesson` / `sop` pages, add a body line naming the *observable signal* a future agent would pattern-match on — the symptom, not the topic:
    ```
    **Trigger / symptom:** off-by-hours in date tests (failing by exactly the local UTC offset)
    ```
    Put it **in the page body**, not in a bespoke `trigger:` frontmatter key. `wiki.py search` ranks over title/type/tags/path/preview/**body** — it does **not** index arbitrary frontmatter keys, so a frontmatter-only `trigger:` is a silent search no-op (verified: a phrase living only in frontmatter returns zero hits). A body cue makes the lesson findable by its symptom phrase via the normal search→timeline→fetch path (no load-all-up-front). Phrase it as the symptom itself (a noun phrase / the left side of the "→"), not as ordered fix-steps. Optionally also echo the key symptom word in `tags:` (tags are indexed and weighted), but the body line is the canonical, always-searchable form.
9. Add ≥2 useful wikilinks when possible.
10. Append `wiki/log.md`.
11. Run `python ... index`; for new v2 pages run `python ... lint --strict`.
12. **Selective refresh on write (compounding loop):** if this write *contradicts* or *supersedes* an existing page, or a refactor/rename invalidated refs a related page cites, invoke [`wiki-refresh`](../wiki-refresh/SKILL.md) with the **narrowest** scope hint (the affected page id / tag / dir) — don't wait for the periodic sweep. A new fact that invalidates an old one is exactly when reconcile pays off. Fire only on contradiction/supersession/refactor signals, not on every write. (Port of EveryInc ce-compound Phase 2.5 selective-refresh-check.)

**Conflict & trust — the poison defense (`write-gate` is NOT a truth filter).** The gate scores *signal/quality*, not *truth*: a confident, well-formed but WRONG lesson passes it (measured — 8/8 adversarial lessons passed at mean score 4.88; `eval/exp5_adversarial/`). So before writing a fact that may **contradict** an existing same-subject page, run the trust-gated check:
```bash
python3 skills/wiki-memory/tools/wiki.py resolve --title "<t>" --body-file <draft> --tags "a,b" --trust <tier>
```
Tiers: `asserted` (default) < `corroborated` (independently re-seen) < `verified` (checked against code/test/fs, cf. `audit-refs`) < `user_confirmed`. Stamp each page's tier at creation with `new --trust <tier>`. `resolve` returns an action: **create** (no same-subject page) · **replace** (your higher-trust correction supersedes — wire `supersedes`/`superseded-by`) · **reject** (a higher-trust page exists; do NOT overwrite — raise trust by verifying, or record `contradicts:[[…]]`) · **dispute** (equal trust — mark `contradicts:` both ways so retrieval surfaces the conflict instead of serving one as truth). This recovers the truth+poison coexistence case (measured — dependent accuracy 0.5→1.0). **Honest limit:** with no competing truth and no verifier, a lie can only be *flagged unverified*, not corrected — that hand-off is [`verify-before-completion`](../verify-before-completion/SKILL.md) + code-grounded checks. (Pure logic in [`provenance.py`](tools/provenance.py).)

## Lint

```
python3 skills/wiki-memory/tools/wiki.py lint [--strict] [--stale-days N] [--hub-threshold N] [--scope PATH ...]
```

Always-on findings: broken `[[wikilinks]]`, orphans (0 inbound), duplicate titles, stale `verified:` (>`--stale-days`, default 180, with `age_days`), gravity-well hubs (inbound > `--hub-threshold`, default 20). `--scope` adds extra roots so trees outside the wiki (concepts/, runbooks/, designs/foo/ledger.md) participate in the link graph and get hygiene-scanned. `--strict` adds v2-frontmatter enforcement, missing-provenance / missing-backlinks warnings, and supersession-reverse-link checks.

Write-gate (two layers). Both are **procedure gates** — agent steps in the write protocol above, not code auto-invoked by `wiki.py`. `wiki.py` enforces only the structural guard (a duplicate filename raises `FileExistsError`); the rest is agent discipline plus `lint`/`lint --strict` flagging violations after the fact.

**Execution gate** (agent discipline — see [`verify-before-completion`](../verify-before-completion/SKILL.md)):
- No durable memory from unexecuted plans.
- No trivial lookups inflated into fake procedures.
- `wiki/raw/` is immutable after creation (convention; not enforced by the write path).
- No duplicate page without supersession.

**Content gate** — run [`write-gate`](../write-gate/SKILL.md) before the write (protocol step 3): the candidate must clear write-gate's signal threshold and, if it is a decision/convention, embed a why-clause. (Scoring table + accepted why-phrases live there.)

## Tier layout

```
wiki/
├── L0_rules.md        # stable behavior rules
├── L1_index.md        # compact pointer catalog (lists concepts/patterns/projects/queries)
├── concepts/          # atomic technique pages  ← durable facts land here in practice
├── patterns/          # reusable workflows/runbooks  ← SOPs land here in practice
├── projects/          # target-project pages
├── people/            # referenced humans
├── queries/           # durable Q&A
├── raw/               # immutable sources
├── L2_facts/          # available fact tier (often empty — see note)
├── L3_sops/           # available SOP tier (often empty — see note)
├── L4_archive/        # cold session archives
├── index.md           # rich catalog
├── log.md             # append-only timeline
└── schema.md          # contract for page types
```

**Pick the folder by *kind of knowledge*, not by L-tier number.** In practice
durable facts are filed under `concepts/`/`queries/` and reusable playbooks under
`patterns/`; `L2_facts/`/`L3_sops/` are available L-tier buckets that are usually
empty and are **not** the primary store. Don't send an agent to look in an empty
`L2_facts/` for a fact that lives in `concepts/`. `L1_index` catalogs the topical
folders so the knowledge is discoverable at startup.

## Files

```
tools/
├── wiki.py            # search/fetch/timeline/new/index/lint
├── code_map.py        # symbol-level navigation aid
├── config.py          # path + threshold defaults
├── tokens.py          # shared token estimator
├── wiki_mcp/          # optional MCP server
└── test_lint_hygiene.py
```
