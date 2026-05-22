#!/usr/bin/env python3
"""MCP server for context-keeper v2 memory retrieval."""
from __future__ import annotations

from memory_api import ck_fetch, ck_query, ck_recent

try:
    from mcp.server.fastmcp import FastMCP
except Exception as exc:  # pragma: no cover - runtime dependency
    raise SystemExit(f"mcp package unavailable: {exc}")


mcp = FastMCP("context-keeper-v2")


@mcp.tool()
def ck_query_tool(keyword: str, k: int = 10) -> list[dict]:
    """Search L0-L3 memory and return compact pointers."""
    return ck_query(keyword, k=k)


@mcp.tool()
def ck_fetch_tool(tier: str, slug: str) -> dict:
    """Fetch one L0/L1/L2/L3/L4 memory item."""
    return ck_fetch(tier, slug)


@mcp.tool()
def ck_recent_tool(days: int = 7) -> list[dict]:
    """List recent L4 archive entries."""
    return ck_recent(days)


if __name__ == "__main__":
    mcp.run()
