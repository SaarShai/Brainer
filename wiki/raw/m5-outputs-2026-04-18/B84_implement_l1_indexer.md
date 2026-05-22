---
type: raw
source: deepseek-r1:32b
date: 2026-04-19
tags: [m5-generated, round11-partial]
---

```python
import os
from pathlib import Path

# Directories to scan
dirs = ['L2_facts', 'L3_sops']

# Collect all markdown files
md_files = []
for d in dirs:
    for root, _, files in os.walk(d):
        for file in files:
            if file.endswith('.md'):
                md_files.append(os.path.join(root, file))

# Generate index content
index_content = "# L1 Index\n\n"
for d in dirs:
    index_content += f"## {d}\n\n"
    for file in md_files:
        if str(file).startswith(d):
            relative_path = os.path.relpath(file)
            filename = Path(file).name
            index_content += f"- [{filename}]({relative_path})\n"

# Write to index file
with open('L1_index.md', 'w') as f:
    f.write(index_content)
```
