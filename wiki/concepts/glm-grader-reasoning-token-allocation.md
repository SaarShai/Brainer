---
schema_version: 2
title: "glm-5.2 grader reasoning_content token allocation pitfall — max_tokens 4096 truncates JSON verdicts"
type: lesson
domain: "framework"
tier: semantic
confidence: 0.95
created: "2026-07-18"
updated: "2026-07-18"
verified: "2026-07-18"
sources:
  - "2026-07-18 long-horizon rehearsal session observation: grader token truncation"
  - "glm-5.2 API behavior: reasoning_content consumes large variable token share"
  - "commit 448f2cc: rehearsal gate-report.json"
tags: [grader, glm-5.2, token-allocation, reasoning-content, json-verdict, truncation, infra]
supersedes: []
superseded-by:
---

# glm-5.2 grader reasoning_content token allocation pitfall — max_tokens 4096 truncates JSON verdicts

## The failure

During the 2026-07-18 long-horizon rehearsal session, grading calls using the glm-5.2 model with `max_tokens=4096` were returning truncated or incomplete JSON verdict objects. The structured output was being cut off mid-field or mid-array, leading to parse failures and invalid verdicts.

## Root cause

The glm-5.2 model's `reasoning_content` (extended thinking) consumes a large and **variable** share of the allocated token budget:

1. **reasoning_content is not pre-budgeted.** Extended-thinking reasoning can expand or shrink based on the problem complexity and the model's reasoning depth.
2. **max_tokens allocates the total output budget.** With `max_tokens=4096`, the model's reasoning phase may consume 2000–3500 tokens, leaving only 500–2000 tokens for the final JSON verdict.
3. **JSON output is structured and cannot be interrupted.** Unlike prose, JSON verdicts with nested fields and arrays cannot be gracefully truncated; a cut-off mid-field produces invalid JSON.
4. **Truncation is silent.** The grader returns partial JSON without an error flag; downstream verdict parsers break on the malformed data.

## The fix

Increase `max_tokens` to give sufficient room for both reasoning AND structured output:

```python
# Before (truncates verdicts):
response = client.messages.create(
    model="glm-5.2",
    max_tokens=4096,
    thinking={
        "type": "enabled",
        "budget_tokens": 8000  # or default auto-allocation
    },
    ...
)

# After (safe for reasoning + JSON output):
response = client.messages.create(
    model="glm-5.2",
    max_tokens=16384,  # ≥16384 recommended
    thinking={
        "type": "enabled",
        "budget_tokens": 8000  # or default auto-allocation
    },
    ...
)
```

**Recommended**: use `max_tokens >= 16384` for grading verdicts that include extended thinking. Monitor actual token usage in responses and adjust based on observed reasoning depth.

## Transient failures

Grader calls may also fail with `RemoteDisconnected` errors (network-level disconnects during extended reasoning phases). These are **transient**; implement exponential backoff + retry logic:

```python
max_retries = 3
for attempt in range(max_retries):
    try:
        response = client.messages.create(...)
        break
    except RemoteDisconnected as e:
        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)  # exponential backoff
        else:
            raise
```

## Lesson

- **Extended-thinking models require larger output budgets.** The `reasoning_content` token cost is variable; allocate conservatively.
- **Set max_tokens based on worst-case reasoning depth + structured output size.** For JSON verdicts, this is often 2-3x larger than prose-only output.
- **Test graders with complex examples.** Truncation is most likely on harder reasoning tasks; smoke-test with a representative difficult case before shipping.
- **Validate structured output parsing.** JSON parse errors should trigger a retry or escalation, not silent data loss.
- **Expect transient network failures during extended thinking.** Implement retry logic for RemoteDisconnected and other transient errors.

## Related

- [[concepts/codex-sandbox-dns-api-access-pitfall]] — API access constraints
- [[concepts/secrets-env-shell-substitution-pitfall]] — API authentication
- `longhorizon_gate.py` — grading harness implementation

## Open questions

- Should the grader auto-scale `max_tokens` based on verdict schema complexity?
- What is the observed max reasoning_content usage for typical grading tasks?
- Should failed verdicts trigger re-runs with increased max_tokens, or escalate to manual review?
