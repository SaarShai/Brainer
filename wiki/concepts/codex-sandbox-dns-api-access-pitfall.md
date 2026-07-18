---
schema_version: 2
title: "Codex-rescue sandbox DNS isolation pitfall — external API endpoints unreachable (curl exit 6)"
type: lesson
domain: "framework"
tier: semantic
confidence: 0.95
created: "2026-07-18"
updated: "2026-07-18"
verified: "2026-07-18"
sources:
  - "2026-07-18 long-horizon rehearsal session observation: Codex sandbox DNS failure"
  - "curl exit code 6 (CURLE_COULDNT_RESOLVE_HOST)"
  - "commit 448f2cc: rehearsal gate-report.json"
tags: [codex, sandbox, dns, network, api-access, infrastructure, paid-api, pitfall]
supersedes: []
superseded-by:
---

# Codex-rescue sandbox DNS isolation pitfall — external API endpoints unreachable (curl exit 6)

## The failure

During the 2026-07-18 long-horizon rehearsal session, grading calls to paid APIs (e.g., `api.z.ai`) were initiated inside a Codex-rescue sandbox job. The calls failed with network errors:

- `curl exit code 6` (CURLE_COULDNT_RESOLVE_HOST)
- DNS resolution timeouts
- Unreachable external endpoints

The sandbox environment does not have DNS routing to external APIs.

## Root cause

Codex-rescue sandbox jobs run in an isolated network environment with restricted external connectivity:

1. **No DNS to external services.** The sandbox cannot resolve hostnames like `api.z.ai`, `api.openai.com`, etc.
2. **Paid API calls fail immediately.** Any tool or script running inside the sandbox that attempts to call external APIs will fail with network errors, not auth errors or timeouts.
3. **Network access is intentionally restricted.** This is a security/isolation boundary, not a transient failure.

Grading workflows that depend on external API calls cannot complete inside the sandbox.

## The fix

**Move paid-API grading calls to the main session**, not into sandbox jobs:

```
Main session (has external connectivity)
  ├─ Codex sandbox job (isolated, no external API access)
  │   └─ [local-only work: file handling, local models, parsing, etc.]
  │   
  └─ [External API grading calls run here, after sandbox work completes]
```

Do not try to call external paid APIs from within a Codex-rescue sandbox. Run the sandbox job for local work only, then execute grading in the main session where network access is available.

## Lesson

- **Sandbox jobs have restricted network scope.** Codex-rescue sandboxes are isolated from external services by design.
- **Test the network boundary before dispatching work.** If a job needs external API calls, it must run in the main session, not in a sandbox.
- **Document which work is sandbox-safe.** Clearly mark which tasks can run isolated (file I/O, local parsing, local models) vs which require external connectivity (API calls, fetch calls, paid services).
- **Budget network latency and quota in the main session.** External API calls are on the critical path; do not relegate them to secondary execution paths that may time out or be cancelled.

## Related

- [[concepts/secrets-env-shell-substitution-pitfall]] — API authentication pitfalls
- [[concepts/glm-grader-reasoning-token-allocation]] — grading infrastructure constraints
- Codex-rescue documentation: sandbox networking model

## Open questions

- Should the rehearsal harness automatically route paid-API calls to the main session?
- Are there local-only graders that can run in the sandbox without external API calls?
