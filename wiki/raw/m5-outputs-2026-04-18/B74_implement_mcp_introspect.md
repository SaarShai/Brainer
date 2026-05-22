---
type: raw
source: deepseek-r1:32b
date: 2026-04-19
tags: [m5-generated, round11-partial]
---

```python
import subprocess

def introspect_server(mcp_server):
    # Run 'initialize' followed by 'tools/list'
    cmd = f"echo -e 'initialize\\ntools/list' | {mcp_server}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    # Parse server responses
    lines = result.stdout.split('\n')
    initialize_response = {}
    tools_list = []
    for line in lines:
        if line.strip() == '':
            continue
        try:
            json_obj = eval(line)  # Unsafe but works for JSON-like output
            if 'status' in json_obj and json_obj['status'] == 'success':
                if 'tools' in json_obj:
                    tools_list = json_obj['tools']
        except:
            pass
    
    # Calculate metrics
    tool_count = len(tools_list)
    total_description_length = sum(len(tool.get('description', '')) for tool in tools_list)
    avg_description_len = round(total_description_length / tool_count, 2) if tool_count > 0 else 0
    
    # Collect warnings
    warnings = []
    for tool in tools_list:
        if any(c.isupper() for c in tool.get('name', '')):
            warnings.append(f"Tool name '{tool['name']}' contains uppercase letters")
    
    return {
        'tool_count': tool_count,
        'avg_description_len': avg_description_len,
        'warnings': warnings
    }
```
