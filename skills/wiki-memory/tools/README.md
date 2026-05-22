---
type: project
axis: verification
tags: [write-gate, memory-policy, middleware]
confidence: med
evidence_count: 0
---

# write-gate — "no execution, no memory" middleware

Shared policy library. Called by context-keeper-v2, skill-crystallizer, any tool that writes persistent state.

## Policy

Facts write to memory **only if**:
1. Action was executed (not just planned).
2. Execution succeeded (exit code 0 or tool-specific success signal).
3. Fact hasn't been written already (dedupe).
4. Not from a blacklisted tool pattern (read-only commands, /tmp writes, plans).

## Interface

```python
from write_gate import should_persist

if should_persist(tool, args, result, exit_code):
    # write to L2 / L3
```

## Implementation

See `tier_manager.TierManager.record_action` — it's the reference implementation. Future: extract to standalone lib if adopted by ≥2 tools.

## Rationale

Without this, memory fills with:
- Plans the model made but never executed
- Failed attempts (poisons retrieval)
- Meta-chatter about what to do
- /tmp writes (ephemeral)

Result: noisy memory → wrong context injected → worse answers. Write-gate prevents pollution at source.
