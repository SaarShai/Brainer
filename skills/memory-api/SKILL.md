---
name: memory-api
description: Optional MCP server exposing tier-aware queries over the wiki-memory store (L0 rules, L1 pointer index, L2 facts, L3 SOPs, L4 archive). Use when the host is MCP-aware and the task needs progressive retrieval with strict latency (≤200ms target). Eager-indexed at startup. Opt-in install.
model: any
effort: low
tools: [Bash, Read]
---

# memory-api

MCP server wrapping `wiki-memory`. Adds tier-aware retrieval with strict latency for MCP-aware hosts.

## When to install

- Host is MCP-aware (Claude Code, Cursor, OpenHands, Codex with MCP shim).
- Latency budget for memory queries is ≤200ms.
- Multiple agents in the same session benefit from a shared in-process index.

If you only need wiki search/fetch and latency isn't critical, use the `wiki-memory` skill's CLI tools directly.

## Tools exposed

- `ck_query(query, tier=L1)` — search the tier-specific index.
- `ck_fetch(page_id)` — fetch a page.
- `ck_timeline(page_id)` — fetch the page's update timeline.
- `ck_promote(page_id, target_tier)` — manual promotion (no auto-promotion).

## Performance

L1 index rebuilds at server startup; incremental rebuilds on wiki writes. Verified ≤200ms on a 50-page wiki in local tests. Re-verify on installation:

```bash
python skills/memory-api/tools/bench.py latency --pages 50
```

## Install

```bash
bash skills/memory-api/tools/install.sh
# Then add to your host's MCP config; the install script prints the exact line.
```

For Claude Code:

```bash
claude mcp add memory-api -- python skills/memory-api/tools/mcp_server.py
```

## Files

```
tools/
├── mcp_server.py
├── tier_manager.py
├── l1_indexer.py
├── memory_api.py        # core
├── bench.py             # latency check
└── INSTALL.md
```

## Status

N=8 measured latency on a small wiki. Not yet measured on a 500-page wiki. If your wiki is large, eager index rebuild may exceed 200ms; benchmark before relying on the latency claim.
