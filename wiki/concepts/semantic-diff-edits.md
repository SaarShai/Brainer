---
type: concept
tags: [semantic-diff, ast, context-compression, code-editing]
confidence: med
evidence_count: 4
related: [[ROADMAP]], [[raw/2026-04-17-semantic-diff-survey]]
---

# Semantic Diff for LLM Code Editing

## Problem
When an LLM agent edits code, it re-reads full files each turn. Most tokens sent are unchanged since last read. Waste scales with file size × edit count.

## Idea
Cache AST snapshot per `(session, file)`. On re-read: parse, diff node hashes against snapshot, return only changed nodes + minimal structural wrapper (class header if method changed, `// [unchanged: foo, bar, +4 more]` stubs for rest).

Token cost for re-read of 1000-line file with 2 changed fns: ~80 tok vs ~750.

## What exists (prior art)

**AST-diff tools (not wired to agents):**
- Difftastic — tree-sitter, 30+ langs.
- Diffsitter — similar, terminal-first.
- GumTree — language-agnostic AST diff, academic basis.
- ast-grep — structural search/rewrite, has MCP server.
- grep-ast — Aider's tree-sitter context tool.

**LLM-specific compression (adjacent):**
- **LeanCTX** — closest competitor. MCP+Rust hook intercepts reads, AST-strips comments/boilerplate, session cache, incremental deltas. Claims 60-90%. Strip-and-compress, not diff-since-last-read.
- **Codebase-Memory** (arxiv 2603.27277) — tree-sitter knowledge graph, query-based not diff-based. 10× fewer tokens, 83/92% quality.
- **Morph Fast Apply** — output-side: applies edits via semantic merge. Not read-side.

**Academic:**
- Diff-XYZ (arxiv 2510.12487) — benchmark, LLM diff comprehension varies.
- Aider udiff benchmark — 3× token cut on large-file edits (output).

## Current agent behavior

| agent | read strategy | diff on input? |
|---|---|---|
| Aider | full file every call; repomap tree-sitter symbols | no (output only) |
| Cursor | 250-500 lines; dynamic-discovery pulls slices | no |
| Claude Code | full files; Snip/Microcompact pipeline | no |
| Cline | full reads on demand | no |
| OpenHands | fresh reads, event log history | no |
| Copilot | full `<attached-files>`, rerank retrieval | no |

**Unanimous:** all read files fresh and whole. None serve "changed since last read."

## Gap / novelty (4/5)

**Unaddressed combo:**
1. Per-session AST snapshot cache.
2. Re-read diff at **function/class node granularity**.
3. Pluggable MCP tool for any agent.

LeanCTX covers (1) partially, (3). Nobody does (2) with AST granularity. Morph covers output, not input. Academic demonstrates value, doesn't wire to read path.

Novelty subtracted 1 for: LeanCTX overlaps on cache; engineering gap not deep algorithmic novelty; someone will build this.

## Minimum viable prototype (~1 day)

MCP tool `read_file_smart(path, session_id)`:
- First call: tree-sitter parse, store `{node_name → body_hash}`, return full file.
- Next call: reparse, diff hashes, return changed nodes + 1-level parent, stub unchanged.
- Languages v1: Python, TS/JS, Rust (tree-sitter grammars).
- Measure: token ratio vs full re-read on real edit session logs.

## Decisions
- Build **after** compound compression pipeline eval (keeps scope tight).
- Target: Claude Code MCP, Aider integration optional.
- Differentiator vs LeanCTX: true AST-diff on read, not strip-and-compress.

## Sources
- https://github.com/Wilfred/difftastic
- https://github.com/ast-grep/ast-grep-mcp
- https://leanctx.com
- https://arxiv.org/abs/2603.27277
- https://arxiv.org/html/2510.12487v1
- https://aider.chat/docs/unified-diffs.html
- https://cursor.com/blog/dynamic-context-discovery
