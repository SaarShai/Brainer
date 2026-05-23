---
name: index-first
description: Prefer pre-built indexes and composite retrieval verbs over chains of grep/read/scan. Use when about to look up symbols, callers, references, routes, or "where is X used / what depends on Y" — query the index (codegraph, repomap, ctags, wiki search, ticket-tracker API, semantic-diff snapshot) before scanning raw text. Batch N related lookups into one capped call instead of N sequential reads. Applies to code AND to any indexed corpus (wiki, tickets, docs, threads).
effort: low
---

# Index-First Retrieval

## Principle

If a structured index already answers the question, scanning raw text repeats work the index did. Default agent behavior is grep → read → grep → read; most "find references / trace flow / show related" tasks have a one-shot answer if the right index is in scope.

## Triggers

- Question shape: "where is X used?", "what calls Y?", "what depends on Z?", "show me the route handlers for /api/...", "what changed about this symbol?", "find all docs that reference this decision."
- About to grep + read multiple files (or threads, or tickets) to trace something.
- About to read N related items sequentially.
- An index is in scope: `codegraph`, `repomap`, `ctags`, `semantic-diff` snapshot, a wiki search endpoint, Linear/Jira/GitHub Issues APIs, an email/thread search tool.

## Protocol

1. Before any grep/read loop, ask: is there an index for this corpus?
2. If yes, call the composite verb (e.g., `context`, `explore`, `impact`) — not chained primitives. One call beats `search` → `read` → `search` → `read`.
3. If the index returns ranked candidates with confidence scores, surface ambiguity to the user instead of picking one and guessing.
4. When you must read N related items, batch: one capped composite call, or parallel reads in a single message — never sequential loops.
5. Pass natural-language queries through. Indexes that extract symbols (CamelCase, snake_case, dot.path, SCREAMING_SNAKE) will pull them out; you don't need to pre-parse.
6. Use structured filters (`kind:function path:src/api`, `state:open label:bug`) to narrow before content search; full-text scoring runs within the narrowed set.
7. If no index exists for a corpus you query often, build one once — the upfront cost amortizes over future queries.

## Anti-patterns

- `search` → `read` → `search` → `read` chains when a `context` verb does it in one.
- Looping `Read` over N files when a batched / parallel / composite alternative exists.
- Spawning a sub-agent for exploration that the index could answer directly — codegraph's own findings: this guidance confuses non-Claude models and repeats work the index already did.
- Grepping for a symbol that an AST/symbol index can resolve precisely.
- Picking the top-ranked candidate silently when the index returned multiple low-confidence matches.
- Hand-extracting symbols from a user prompt before passing to an index that already does this.

## Caveats

- Initial-index cost amortizes over many queries. On tiny corpora (<200 files / <50 docs) grep is already cheap — skip this skill.
- Indexes go stale. If the corpus changed since last build and there is no watcher, rebuild or trust grep instead.
- Confidence matters: a top-result confidence of ~0.4 means "I don't know" — treat as ambiguous, do not silently pick.
- Don't push agents toward an index that isn't installed. Check first, fall back to grep+read if absent.

## Lineage

Distilled from `colbymchenry/codegraph` — the generalizable parts of its agent-instruction template: one-call composition, batched exploration, confidence-scored name resolution, structured-filter + FTS composition. Their measured savings on real codebases (VS Code, Django, Tokio, …): ~59% fewer tokens, ~70% fewer tool calls, scaling with corpus size. Pattern applies to any indexed corpus, not just code.

Related skills: [`semantic-diff`](../semantic-diff/SKILL.md) (file-re-read diff — a per-file index), [`wiki-memory`](../wiki-memory/SKILL.md) (the manually-curated prose analog), [`lean-execution`](../lean-execution/SKILL.md) (general scope pruning).
