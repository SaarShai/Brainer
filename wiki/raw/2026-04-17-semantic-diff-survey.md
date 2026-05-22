---
type: raw
date: 2026-04-17
source: sonnet-4.6 subagent
tags: [semantic-diff, prior-art]
---

# Semantic Diff for LLM Code Editing — Prior Art (Apr 2026)

## Tools
1. Difftastic — tree-sitter AST diff, 30+ langs. github.com/Wilfred/difftastic
2. Diffsitter — tree-sitter AST difftool. github.com/afnanenayet/diffsitter
3. GumTree — language-agnostic AST diff. TOSEM 2024 basis.
4. ast-grep — structural search/rewrite + MCP. ast-grep.github.io
5. grep-ast — Aider's tree-sitter context. github.com/Aider-AI/grep-ast
6. LeanCTX — MCP+Rust hook, AST-strip, session cache, 60-90% claim. leanctx.com
7. Codebase-Memory — tree-sitter knowledge graph MCP. arxiv 2603.27277
8. Morph Fast Apply — semantic merge model for edits. morphllm.com
9. Diff-XYZ benchmark — LLM diff comprehension eval. arxiv 2510.12487
10. Aider unified-diff — 3× cut on large files (output format). aider.chat/docs/unified-diffs.html

## Agent file-read behavior (all full-file, all lack diff-on-read)
- Aider: full file; repomap PageRank symbol map (1-13k tokens).
- Cursor: 250-500 lines; Jan 2026 dynamic-context-discovery (46.9% token cut on MCP-heavy).
- Claude Code: full; Snip/Microcompact/Collapse/Autocompact.
- Cline: full reads on demand.
- OpenHands: fresh reads, event log history.
- GitHub Copilot: full `<attached-files>`, 2-stage rerank.

## Gap
Nobody caches per-file AST snapshot and serves only changed nodes on re-read within session. LeanCTX: strip-and-compress (not diff). Codebase-Memory: graph query (not diff). Morph: output-side. Aider udiff: output-side.

## Novelty: 4/5
- Combo unaddressed: (a) session AST snapshot (b) node-granularity diff on re-read (c) MCP-pluggable.
- LeanCTX partially covers (a), (c).
- Engineering gap, not algorithmic novelty. Someone will build it.

## MVP (~1 day)
MCP `read_file_smart(path, session_id)`. First call: tree-sitter parse, hash nodes, return full. Next: reparse, diff hashes, return changed + parent wrapper, stub rest (`// [unchanged: foo, bar, +4 more]`). Python/TS/Rust grammars. Target: 1000-line file, 2 changed fns → ~80 tok vs ~750.

## All sources
- github.com/Wilfred/difftastic
- github.com/afnanenayet/diffsitter
- users.encs.concordia.ca/~nikolaos/publications/TOSEM_2024.pdf
- ast-grep.github.io, github.com/ast-grep/ast-grep-mcp
- github.com/Aider-AI/grep-ast
- leanctx.com, github.com/yvgude/lean-ctx
- morphllm.com, morphllm.com/fast-apply-model
- arxiv.org/abs/2603.27277 (Codebase-Memory)
- arxiv.org/html/2510.12487v1 (Diff-XYZ)
- aider.chat/docs/unified-diffs.html
- aider.chat/docs/repomap.html
- cursor.com/blog/dynamic-context-discovery
- arxiv.org/pdf/2511.03690 (OpenHands SDK)
