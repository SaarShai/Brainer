---
type: raw
source: deepseek-r1:32b
date: 2026-04-19
tags: [m5-generated, round11-partial]
---

```bash
#!/bin/bash

# Configuration
SCRIPT_NAME=$(basename "$0")
LOG_DIR="kaggle_results/nightly"
TODAY=$(date +%Y-%m-%d)
RESULT_FILE="$LOG_DIR/$TODAY.log"

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Run adversarial sweep and capture output
echo "[$(date +"%T")] Running adversarial sweep..." >> "$RESULT_FILE"
OUTPUT=$(./adversarial_sweep.sh 2>&1)
EXIT_CODE=$?

# Append results to log file
echo "$OUTPUT" | tee -a "$RESULT_FILE"

# Check for regressions
if [ $EXIT_CODE -ne 0 ]; then
    echo "[$(date +"%T")] Regression detected!" >> "$RESULT_FILE"
    
    # Format issue message
    ISSUES_URL=$(git remote get-url origin | sed 's/git@github.com:/https:\/\/github.com\//; s/\.git$/'/issues'/')
    BODY="### Nightly Adversarial Sweep Results\n\n**Date:** $(date)\n**Exit Code:** $EXIT_CODE\n\n```\n$OUTPUT\n```"
    
    # Post to GitHub Issues
    gh issue create \
        --title "Nightly Adversarial Sweep Regression Detected" \
        --body "$BODY" \
        --label regression,nightly \
        --repo "$ISSUES_URL"
fi

# Log completion
echo "[$(date +"%T")] Nightly sweep completed with exit code $EXIT_CODE." >> "$RESULT_FILE"

exit $EXIT_CODE
```
