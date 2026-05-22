---
type: raw
source: deepseek-r1:32b
date: 2026-04-19
tags: [m5-generated, round8]
---

To design a tool-level token budget system, we'll create a dictionary mapping each tool to its maximum allowed tokens per call. When a tool exceeds this limit, a warning is sent to stderr.

**Dictionary Structure:**
```python
tool_token_budget = {
    "text-davinci-003": 2048,
    "gpt-4": 128000,
    # Add more tools as needed
}
```

**Warning System Implementation:**
When a tool's token usage exceeds its limit, trigger a warning:
```python
import sys

def check_token_usage(tool_name, tokens_used):
    max_tokens = tool_token_budget.get(tool_name, 0)
    if tokens_used > max_tokens:
        warning_msg = f"Token budget exceeded for {tool_name}: {tokens_used} > {max_tokens}"
        print(warning_msg, file=sys.stderr)
```

**Proposed Defaults:**
- `text-davinci-003`: 2048 tokens (suitable for older models with smaller context windows).
- `gpt-4`: 128,000 tokens (accommodates larger models' capacities).

This system ensures efficient resource management by monitoring and alerting on token usage per tool.
