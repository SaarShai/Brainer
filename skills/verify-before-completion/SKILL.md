---
name: verify-before-completion
description: Use before claiming work is done, fixed, passing, committed, or ready. Evidence before claims. Run the verification fresh; report exact command + output + remaining risk.
model: any
effort: low
---

# Verify Before Completion

Rule: evidence before claims.

Before any completion/success claim:
1. Identify the command, inspection, or checklist that proves it.
2. Run or perform it fresh.
3. Read the output or result.
4. Report the exact verification and any remaining risk.

Do not claim:
- tests pass without a fresh test run
- lint/build is clean without running it
- bug is fixed without reproducing the original symptom or a regression test
- delegated work is correct without inspecting result/diff

If verification is impossible, say what was not verified and why.
