---
type: raw
source: deepseek-r1:32b
date: 2026-04-19
tags: [m5-generated, round11-partial]
---

```bash
#!/bin/bash

# Read JSON input from stdin
json_input=$(cat)

# Check if jq is installed
if ! command -v jq &> /dev/null; then
    echo "jq is required but not installed" >&2
    exit 1
fi

# Extract tool, path, and operation from JSON
tool=$(echo "$json_input" | jq -r '.tool')
path=$(echo "$json_input" | jq -r '.path')
operation=$(echo "$json_input" | jq -r '.operation')

# Check if required fields are present
if [ "$tool" == "null" ] || [ "$path" == "null" ] || [ "$operation" == "null" ]; then
    echo "Missing required fields in input JSON" >&2
    exit 1
fi

# Only validate Write/Edit operations
if [[ "$tool" != "Write" && "$tool" != "Edit" ]]; then
    exit 0
fi

# Check if path starts with 'raw/'
if [[ "$path" == raw/* ]]; then
    echo "Cannot write to paths starting with 'raw/'" >&2
    exit 2
fi

# Check for protected patterns using case statement
case "$path" in
    .git/* | .env | *.pem)
        echo "Cannot write to protected path: $path" >&2
        exit 2
        ;;
esac

# If none of the conditions match, allow the operation
exit 0

# Trap for any errors during execution
trap 'echo "An unexpected error occurred" >&2; exit 1' ERR
```
