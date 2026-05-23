# loop-breaker — eval status

**Status:** unmeasured for in-the-wild token impact (v1.4.0). Hook correctness is verified by [tools/test.sh](tools/test.sh) — 23/23 unit cases — plus three live e2e runs against a real `claude -p` subprocess.

## Verified — unit (23/23 in test.sh)

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
| Same `command`, varying model-generated `description` → same signature | ✓ (key bug fix) |
| Leading-underscore fields excluded from signature | ✓ |
| Different commands still produce different signatures | ✓ (anti-overgen) |
| State GC at session-start: 8-day-old files purged, fresh kept | ✓ |
| Output JSON shape matches Anthropic docs | ✓ (`hookSpecificOutput.additionalContext` / `permissionDecision`) |
| settings.json merge — 4 scenarios + idempotency | ✓ (14/14 assertions) |
| Latency p99 over 100 invocations | 39 ms (acceptable; Python cold start dominates) |

## Verified — live e2e (`claude -p` subprocess, haiku, n=3 runs)

| Check | Result | Evidence |
|---|---|---|
| Hook fires on each PreToolUse in a real session | ✓ | 8/8 hook_started events for 8 Bash calls |
| Warning JSON emitted at 5th+ identical call | ✓ | 4 hook_response events with `additionalContext` (calls 5–8) |
| Warning text appears in model-facing transcript | ✓ | `attachment.type="hook_additional_context"` entries on calls 5–8 |
| Model reads + acknowledges warning | ✓ | Model wrote "This repetition is intentional ... Continuing" — quoting the loop-breaker message |
| `LOOP_BREAKER_HARD_BLOCK=1` denies excess calls | ✓ | At threshold=3, 4th Bash call's tool_result contained the loop-breaker text, NOT the `pwd` output |
| Hard-block stops the agent from retrying identical calls | ✓ | Model attempted only 4 calls instead of the requested 8 |

**Caveat — model adaptation is task-dependent.** With an explicit user instruction to "run `pwd` 8 times," haiku correctly prioritized the user instruction over the soft warning and completed all 8. The hook is doing its job (the warning is delivered) — *whether* the model heeds it depends on instruction strength. For genuine drift (model retrying without explicit user pressure), the hard-block mode is the deterministic option.

## Bug found + fixed during e2e

The model's tool_input includes a `description` field that varies per call (`"Run pwd - call 1"`, `"Run pwd - call 2"`, …). Hashing the raw tool_input therefore produced different signatures per call → counter never accumulated → hook never triggered in real sessions. Fix: project signature input down by dropping `description` and any leading-underscore fields ([hook.py signature_input()](tools/hook.py)). Regression cases 12–14 in test.sh.

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
