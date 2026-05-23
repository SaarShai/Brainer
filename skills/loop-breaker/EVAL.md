# loop-breaker — eval status

**Status:** unmeasured for in-the-wild token impact (v1.4.0). Hook correctness is verified by [tools/test.sh](tools/test.sh) — 17/17 cases passing including concurrency.

## Verified (synthetic)

| Check | Result |
|---|---|
| 5-call threshold + reset on different signature | ✓ |
| `LOOP_BREAKER_THRESHOLD` env override | ✓ (3 confirmed) |
| Threshold clamps below 2 to floor=2 | ✓ |
| `LOOP_BREAKER_HARD_BLOCK=1` deny past threshold | ✓ |
| `LOOP_BREAKER_ALLOWLIST_TOOLS` suppression | ✓ |
| Independent counters per `session_id` | ✓ |
| `tool_input` = null / list / non-ASCII / 10KB | ✓ (no crash; warn JSON capped <2KB) |
| Corrupt state file → recover | ✓ |
| Unwritable state dir → exit 0 + stderr log | ✓ |
| Empty / malformed stdin | ✓ exit 0 |
| **10 parallel invocations → count=10** | ✓ (fcntl.flock) |
| Output JSON shape matches Anthropic docs | ✓ (`hookSpecificOutput.additionalContext` / `permissionDecision`) |
| settings.json merge — 4 scenarios + idempotency | ✓ (14/14 assertions) |
| Latency p99 over 100 invocations | 39 ms (acceptable; Python cold start dominates) |

## What to measure

Mid-task loop drift is a *tail* failure mode — only a fraction of sessions exhibit it, but those sessions burn disproportionate tokens. Standard A/B over a random task batch will under-represent the effect.

Better measurement plan:
1. **Loop-prevalence baseline** — instrument a 2-week window without the hook firing (log only, no `additionalContext` output). Count sessions where the same `(tool, args)` signature occurs ≥5× consecutively. Expect 5–15% of long sessions.
2. **Token delta on loop-positive sessions** — for sessions that trigger, compare estimated tokens-to-completion vs a paired baseline. Lower bound: the cost of the calls that would have run between trigger and self-correction.
3. **False-positive rate** — fraction of triggers where the agent's next message indicates the repetition was intentional (polling, batch retry). Target <10%.

## Self-test

```bash
# Empty payload exits 0:
printf '' | bash skills/loop-breaker/tools/hook.sh; echo exit=$?

# Malformed JSON exits 0:
printf 'not json' | bash skills/loop-breaker/tools/hook.sh; echo exit=$?

# 5× identical Bash call emits additionalContext on the 5th:
for i in 1 2 3 4 5; do
  printf '{"session_id":"selftest","hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"git status"}}' \
    | LOOP_BREAKER_STATE_DIR=/tmp/lb-selftest bash skills/loop-breaker/tools/hook.sh
  echo "--- call $i ---"
done
rm -rf /tmp/lb-selftest
```

The 5th iteration should print a JSON object with `hookSpecificOutput.additionalContext`; the first four should print nothing.

## Out of scope

- Cross-session loop patterns (different session, same recurring failure) — that's `wiki-memory`'s job.
- Loop detection in the model's text output (Gemini-CLI also catches identical sentences ≥10×). Needs transcript scanning, not a PreToolUse hook.
