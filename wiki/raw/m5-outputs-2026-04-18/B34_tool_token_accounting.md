---
type: raw
source: deepseek-r1:32b
date: 2026-04-19
tags: [m5-generated, round7]
---

A system for tracking and enforcing token budgets per MCP tool:

1. **Data Structures**:
- `tool_budgets`: Dictionary mapping tool names to their allowed input/output token limits
- `tool_usage`: Dictionary tracking cumulative tokens used by each tool

2. **Core Logic**:
```python
class ToolBudgetTracker:
    def __init__(self, budgets):
        self.tool_budgets = budgets  # Format: {tool_name: {'input': int, 'output': int}}
        self.tool_usage = {
            tool: {'input_used': 0, 'output_used': 0} 
            for tool in budgets.keys()
        }
    
    def track_usage(self, tool_name, input_tokens, output_tokens):
        if tool_name not in self.tool_budgets:
            raise ValueError(f"Tool {tool_name} not registered")
            
        new_input_total = self.tool_usage[tool_name]['input_used'] + input_tokens
        new_output_total = self.tool_usage[tool_name]['output_used'] + output_tokens
        
        # Check against budgets
        if (new_input_total > self.tool_budgets[tool_name]['input'] or 
            new_output_total > self.tool_budgets[tool_name]['output']):
            self._alert_exceeded(tool_name, input_tokens, output_tokens)
            
        else:
            # Update counters
            self.tool_usage[tool_name]['input_used'] = new_input_total
            self.tool_usage[tool_name]['output_used'] = new_output_total
            
    def _alert_exceeded(self, tool_name, input_tokens, output_tokens):
        # Log or raise error
        print(f"Budget exceeded for tool {tool_name}")
        print(f"Input tokens used: {self.tool_usage[tool_name]['input_used']} + {input_tokens} = {self.tool_usage[tool_name]['input_used'] + input_tokens}")
        print(f"Output tokens used: {self.tool_usage[tool_name]['output_used']} + {output_tokens} = {self.tool_usage[tool_name]['output_used'] + output_tokens}")
        
    def add_tool(self, tool_name, input_limit, output_limit):
        self.tool_budgets[tool_name] = {'input': input_limit, 'output': output_limit}
        self.tool_usage[tool_name] = {'input_used': 0, 'output_used': 0}
        
    def reset_tool(self, tool_name):
        if tool_name in self.tool_usage:
            self.tool_usage[tool_name]['input_used'] = 0
            self.tool_usage[tool_name]['output_used'] = 0
```

3. **Features**:
- Tracks both input and output tokens per tool
- Alerts when budget limits are exceeded
- Supports adding new tools dynamically
- Provides method to reset counters
- Efficient dictionary-based lookups

4. **Usage Example**:
```python
# Initialize with budgets
budgets = {
    'text-davinci-3': {'input': 1000, 'output': 2000},
    'gpt-4': {'input': 8000, 'output': 16000}
}

tracker = ToolBudgetTracker(budgets)

# Track tool usage
tracker.track_usage('text-davinci-3', 500, 1000)  # Within budget
tracker.track_usage('gpt-4', 9000, 17000)        # Exceeds output budget

# Add new tool
tracker.add_tool(' Claude-2', input_limit=6000, output_limit=12000)

# Reset usage counters
tracker.reset_tool('text-davinci-3')
```

This implementation provides a flexible and efficient way to enforce token budgets across multiple tools in an MCP system.
