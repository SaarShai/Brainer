---
type: raw
source: deepseek-r1:32b
date: 2026-04-19
tags: [m5-generated, round11-partial]
---

```python
class TokenBudget:
    def __init__(self):
        self.tool_limits = {}  # Dictionary to store max tokens per tool
        self.usage = {}        # Dictionary to track current token usage
        
    def check(self, tool: str, tokens_in: int, tokens_out: int) -> dict:
        if tool not in self.tool_limits:
            self.tool_limits[tool] = 0  # Default limit is 0 if not set
        total_tokens = tokens_in + tokens_out
        if tool not in self.usage:
            self.usage[tool] = 0
        self.usage[tool] += total_tokens
        
        limit = self.tool_limits[tool]
        status = {
            'status': 'ok',
            'current_usage': self.usage[tool],
            'limit': limit
        }
        
        if self.usage[tool] > limit:
            status['status'] = 'exceeded'
        elif self.usage[tool] >= (0.8 * limit):
            status['status'] = 'warning'
            
        return status
    
    def set_limit(self, tool: str, limit: int) -> None:
        self.tool_limits[tool] = limit
```
