---
type: raw
source: deepseek-r1:32b
date: 2026-04-19
tags: [m5-generated, round9]
---

```python
patterns = [
    # Intent: ask
    (r'\b(ask|how|what|why|can you)\b', 'ask', 0.8),
    
    # Intent: plan
    (r'\b(plan|strategy|organize|schedule|outline)\b', 'plan', 0.8),
    
    # Intent: debug
    (r'\b(debug|error|bug|fix|troubleshoot)\b', 'debug', 0.8),
    
    # Intent: decision
    (r'\b(decide|evaluate|option|choice|consider)\b', 'decision', 0.8),
    
    # Intent: refactor
    (r'\b(refactor|simplify|restructure|optimize|clean up)\b', 'refactor', 0.8),
    
    # Intent: scaffold
    (r'\b(scaffold|template|framework|outline|base)\b', 'scaffold', 0.8),
    
    # Intent: review
    (r'\b(review|assess|evaluate|critique|analyze)\b', 'review', 0.8),
    
    # Intent: doc-request
    (r'\b(documentation|guide|explain|describe|tutorial)\b', 'doc-request', 0.8),
    
    # Intent: bug-report
    (r'\b(bug|issue|error|problem|fault)\b', 'bug-report', 0.8),
    
    # Intent: test-request
    (r'\b(test|verify|check|validate|debug)\b', 'test-request', 0.8),
    
    # Intent: comparison
    (r'\b(compare|difference|vs|analyze|evaluate)\b', 'comparison', 0.8),
    
    # Intent: summarization
    (r'\b(summarize|overview|brief|concise|highlight)\b', 'summarization', 0.8),
    
    # Intent: explanation
    (r'\b(explain|understand|concept|meaning|clarify)\b', 'explanation', 0.8),
    
    # Intent: code-gen
    (r'\b(generate|write|create|snippet|function)\b', 'code-gen', 0.8),
    
    # Intent: code-modify
    (r'\b(modify|update|change|revise|alter)\b', 'code-modify', 0.8)
]
```
