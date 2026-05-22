---
type: raw
source: deepseek-r1:32b
date: 2026-04-19
tags: [m5-generated, round10]
---

```python
import logging
from typing import List, Dict, Optional
from abc import ABC, abstractmethod

class Tool:
    def __init__(self, name: str = None, cost: float = 0.0):
        self.name = name
        self.cost = cost

class McpIntrospector:
    def __init__(self, server_type: str, budget_limit: float = 1000.0, warn_on_unnamed: bool = True):
        self.server_type = server_type
        self.budget_limit = budget_limit
        self.warn_on_unnamed = warn_on_unnamed
        self.tools = []
        
    def introspect(self) -> Dict[str, float]:
        """Introspect MCP server tools and their costs."""
        self._fetch_tools()
        tool_count = len(self.tools)
        total_cost = sum(tool.cost for tool in self.tools)
        unnamed_tools = [tool for tool in self.tools if not tool.name]
        
        if unnamed_tools and self.warn_on_unnamed:
            logging.warning(f"Server {self.server_type} has {len(unnamed_tools)} unnamed tools")
            
        if total_cost > self.budget_limit:
            raise BudgetExceededError(
                f"Total cost {total_cost:.2f} exceeds budget limit {self.budget_limit:.2f}"
            )
            
        return {"tool_count": tool_count, "total_cost": total_cost}
    
    def _fetch_tools(self) -> None:
        """Abstract method to fetch tools from MCP server."""
        pass
    
class BudgetExceededError(Exception):
    pass

def setup_logging() -> None:
    """Configure logging for MCP introspection."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("mcp_introspect.log"),
            logging.StreamHandler()
        ]
    )

class ComcomMcpIntrospector(McpIntrospector):
    def _fetch_tools(self) -> None:
        """Fetch tools from comcom MCP server."""
        # Example implementation
        self.tools = [
            Tool(name="Tool1", cost=250.0),
            Tool(name="Tool2", cost=300.0),
            Tool(cost=400.0)  # unnamed tool
        ]

class SemicomMcpIntrospector(McpIntrospector):
    def _fetch_tools(self) -> None:
        """Fetch tools from semicom MCP server."""
        # Example implementation
        self.tools = [
            Tool(name="ToolA", cost=150.0),
            Tool(name="ToolB", cost=200.0)
        ]

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Introspect MCP servers')
    parser.add_argument('--server-type', type=str, required=True,
                       choices=['comcom', 'semicom'])
    parser.add_argument('--budget-limit', type=float, default=1000.0)
    
    args = parser.parse_args()
    
    setup_logging()
    
    if args.server_type == 'comcom':
        inspector = ComcomMcpIntrospector(args.server_type, args.budget_limit)
    else:
        inspector = SemicomMcpIntrospector(args.server_type, args.budget_limit)
        
    try:
        result = inspector.introspect()
        print(f"Server {args.server_type}: {result}")
    except BudgetExceededError as e:
        logging.error(str(e))
        exit(1)

if __name__ == "__main__":
    main()
```
