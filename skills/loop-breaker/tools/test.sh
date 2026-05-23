#!/usr/bin/env bash
# loop-breaker self-test. Exercises hook.py against the unit-gap matrix.
# Exits 0 only if every assertion passes.
set -uo pipefail

TOOLS_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK="bash $TOOLS_DIR/hook.sh"
STATE_ROOT="$(mktemp -d -t lb-test-XXXX)"
trap 'rm -rf "$STATE_ROOT"' EXIT

PASS=0
FAIL=0
declare -a FAIL_NAMES

ok() { echo "  [PASS] $1"; PASS=$((PASS+1)); }
no() { echo "  [FAIL] $1${2:+  | $2}"; FAIL=$((FAIL+1)); FAIL_NAMES+=("$1"); }

# Helpers
call() {
  # call <state-subdir> <env-overrides...> -- <payload-json>
  local subdir="$1"; shift
  local env_overrides=()
  while [ "$1" != "--" ]; do env_overrides+=("$1"); shift; done
  shift  # drop "--"
  local payload="$1"
  if [ ${#env_overrides[@]} -gt 0 ]; then
    printf '%s' "$payload" | env LOOP_BREAKER_STATE_DIR="$STATE_ROOT/$subdir" "${env_overrides[@]}" $HOOK
  else
    printf '%s' "$payload" | env LOOP_BREAKER_STATE_DIR="$STATE_ROOT/$subdir" $HOOK
  fi
}

bash_payload() {
  # bash_payload <session_id> <command-string>
  printf '{"session_id":"%s","hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":%s}}' \
    "$1" "$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$2")"
}

payload() {
  # payload <session_id> <tool_name> <tool_input_json>
  printf '{"session_id":"%s","hook_event_name":"PreToolUse","tool_name":"%s","tool_input":%s}' \
    "$1" "$2" "$3"
}

emitted() {
  # emitted "$out" → returns 0 if non-empty AND contains additionalContext
  [ -n "$1" ] && echo "$1" | grep -q '"additionalContext"'
}

denied() {
  echo "$1" | grep -q '"permissionDecision": *"deny"'
}

# -----------------------------------------------------------------------------
echo "[1] Threshold env override (LOOP_BREAKER_THRESHOLD=3)"
SUB=t1
for i in 1 2; do
  out=$(call $SUB LOOP_BREAKER_THRESHOLD=3 -- "$(bash_payload t1 'echo x')")
done
out=$(call $SUB LOOP_BREAKER_THRESHOLD=3 -- "$(bash_payload t1 'echo x')")
if emitted "$out"; then ok "warns on 3rd identical with threshold=3"; else no "warns on 3rd identical with threshold=3"; fi

# -----------------------------------------------------------------------------
echo "[2] Threshold clamps below 2 → behaves as 2"
SUB=t2
out=$(call $SUB LOOP_BREAKER_THRESHOLD=1 -- "$(bash_payload t2 'echo y')")
if [ -z "$out" ]; then ok "1st call silent even with threshold=1 (clamped to 2)"; else no "1st call silent" "got: $(echo "$out" | head -c80)"; fi
out=$(call $SUB LOOP_BREAKER_THRESHOLD=1 -- "$(bash_payload t2 'echo y')")
if emitted "$out"; then ok "2nd call emits (threshold clamped to 2)"; else no "2nd call emits with clamped threshold"; fi

# -----------------------------------------------------------------------------
echo "[3] Same tool, different args → counter resets"
SUB=t3
for c in "echo a" "echo a" "echo a" "echo a" "echo b" "echo a"; do
  out=$(call $SUB -- "$(bash_payload t3 "$c")")
done
if [ -z "$out" ]; then ok "no emit after reset (4 a, 1 b, 1 a)"; else no "no emit after reset" "got: $(echo "$out" | head -c80)"; fi

# -----------------------------------------------------------------------------
echo "[4] Different tool, same args → counter resets"
SUB=t4
P_BASH='{"command":"echo same"}'
P_READ='{"command":"echo same"}'  # same args but Read tool
for _ in 1 2 3 4; do out=$(call $SUB -- "$(payload t4 Bash "$P_BASH")"); done
out=$(call $SUB -- "$(payload t4 Read "$P_READ")")
if [ -z "$out" ]; then ok "no emit when tool name changes mid-streak"; else no "no emit on tool-name change" "got: $(echo "$out" | head -c80)"; fi

# -----------------------------------------------------------------------------
echo "[5] tool_input = null → no crash, signature still computed"
SUB=t5
for _ in 1 2 3 4 5; do
  out=$(call $SUB -- "$(payload t5 SomeTool 'null')")
done
if emitted "$out"; then ok "5x null tool_input still triggers warn"; else no "null tool_input handled and triggers"; fi

# -----------------------------------------------------------------------------
echo "[6] tool_input is a list → no crash"
SUB=t6
for _ in 1 2 3 4 5; do
  out=$(call $SUB -- "$(payload t6 WeirdTool '[1,2,3]')")
done
if emitted "$out"; then ok "list-type tool_input handled"; else no "list-type tool_input handled"; fi

# -----------------------------------------------------------------------------
echo "[7] Non-ASCII tool_input → stable signature"
SUB=t7
for _ in 1 2 3 4 5; do
  out=$(call $SUB -- "$(payload t7 Bash '{"command":"echo 日本語"}')")
done
if emitted "$out" && echo "$out" | grep -q '日本語\|\\u65e5'; then
  ok "non-ASCII preserved in preview (or escaped)"
elif emitted "$out"; then
  ok "non-ASCII at least did not crash (preview may be escaped)"
else
  no "non-ASCII handled"
fi

# -----------------------------------------------------------------------------
echo "[8] Large tool_input (10KB) → still works, preview truncated"
SUB=t8
BIG=$(python3 -c 'print("x"*10000)')
PAYLOAD_BIG=$(payload t8 Bash "$(python3 -c 'import json,sys;print(json.dumps({"command":sys.argv[1]}))' "$BIG")")
for _ in 1 2 3 4 5; do
  out=$(printf '%s' "$PAYLOAD_BIG" | env LOOP_BREAKER_STATE_DIR="$STATE_ROOT/$SUB" $HOOK)
done
if emitted "$out"; then ok "10KB tool_input triggers warn"; else no "10KB tool_input triggers"; fi
# Preview should be capped (≤200 char + ellipsis); check the JSON output doesn't contain the full 10KB
out_size=$(echo -n "$out" | wc -c)
if [ "$out_size" -lt 2000 ]; then ok "warn JSON stayed compact (<2KB) despite 10KB input ($out_size bytes)"; else no "warn JSON stayed compact" "got $out_size bytes"; fi

# -----------------------------------------------------------------------------
echo "[9] Two sessions interleaved → independent counters"
SUB=t9
# 4 calls in A, 4 calls in B, then 1 more in A → A should hit 5, B at 4
for _ in 1 2 3 4; do call $SUB -- "$(bash_payload alpha 'cmd-A')" >/dev/null; done
for _ in 1 2 3 4; do call $SUB -- "$(bash_payload beta  'cmd-B')" >/dev/null; done
out_a=$(call $SUB -- "$(bash_payload alpha 'cmd-A')")
out_b=$(call $SUB -- "$(bash_payload beta  'cmd-B')")
if emitted "$out_a"; then ok "session alpha hits 5 independently"; else no "session alpha hits 5"; fi
if emitted "$out_b"; then ok "session beta hits 5 independently"; else no "session beta hits 5"; fi

# -----------------------------------------------------------------------------
echo "[10] Corrupt state file → recovers, no crash"
SUB=t10
mkdir -p "$STATE_ROOT/$SUB"
echo "this is { not json" > "$STATE_ROOT/$SUB/corrupt.json"
out=$(call $SUB -- "$(bash_payload corrupt 'echo ok')")
exit_code=$?
if [ $exit_code -eq 0 ]; then ok "exit 0 despite corrupt state"; else no "exit 0 despite corrupt state" "got $exit_code"; fi
# Should have rewritten as valid JSON
if python3 -c 'import json,sys;json.load(open(sys.argv[1]))' "$STATE_ROOT/$SUB/corrupt.json" 2>/dev/null; then
  ok "state file recovered to valid JSON"
else
  no "state file recovered to valid JSON"
fi

# -----------------------------------------------------------------------------
echo "[11b] Concurrency: 10 parallel invocations → count=10 (no lost increments)"
SUB=t11b
mkdir -p "$STATE_ROOT/$SUB"
PAYLOAD_C=$(payload concur Bash '{"command":"x"}')
for _ in 1 2 3 4 5 6 7 8 9 10; do
  printf '%s' "$PAYLOAD_C" | env LOOP_BREAKER_STATE_DIR="$STATE_ROOT/$SUB" $HOOK > /dev/null &
done
wait
final_count=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["consecutive_count"])' "$STATE_ROOT/$SUB/concur.json")
if [ "$final_count" = "10" ]; then ok "10 parallel hooks → count=10"; else no "10 parallel hooks → count=10" "got $final_count"; fi

echo "[11] Hard-block exclusivity (no deny at threshold, deny past it)"
SUB=t11
for _ in 1 2 3 4; do
  out=$(call $SUB LOOP_BREAKER_HARD_BLOCK=1 -- "$(bash_payload hard 'cmd-h')")
done
out=$(call $SUB LOOP_BREAKER_HARD_BLOCK=1 -- "$(bash_payload hard 'cmd-h')")
if emitted "$out" && ! denied "$out"; then ok "5th call: warn only, no deny"; else no "5th call: warn only" "got: $(echo "$out" | head -c120)"; fi
out=$(call $SUB LOOP_BREAKER_HARD_BLOCK=1 -- "$(bash_payload hard 'cmd-h')")
if denied "$out"; then ok "6th call: deny present"; else no "6th call: deny present" "got: $(echo "$out" | head -c120)"; fi

# -----------------------------------------------------------------------------
echo
if [ $FAIL -eq 0 ]; then
  echo "loop-breaker test.sh: $PASS/$((PASS+FAIL)) PASS"
  exit 0
else
  echo "loop-breaker test.sh: $PASS/$((PASS+FAIL)) — failures:"
  for n in "${FAIL_NAMES[@]}"; do echo "  - $n"; done
  exit 1
fi
