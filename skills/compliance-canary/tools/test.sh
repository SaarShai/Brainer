#!/usr/bin/env bash
# compliance-canary self-test.
set -uo pipefail

TOOLS_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK=(bash "$TOOLS_DIR/hook.sh")
STATE_ROOT="$(mktemp -d -t cc-test-XXXX)"
SKILLS_ROOT="$(mktemp -d -t cc-skills-XXXX)"
TRANSCRIPT_DIR="$(mktemp -d -t cc-tx-XXXX)"
trap 'rm -rf "$STATE_ROOT" "$SKILLS_ROOT" "$TRANSCRIPT_DIR"' EXIT

PASS=0; FAIL=0
declare -a FAIL_NAMES
ok() { echo "  [PASS] $1"; PASS=$((PASS+1)); }
no() { echo "  [FAIL] $1${2:+  | $2}"; FAIL=$((FAIL+1)); FAIL_NAMES+=("$1"); }

# Helpers ---------------------------------------------------------------

make_skill_with_probes() {
  # make_skill_with_probes <skills_subdir> <skill_name> <probes_json>
  local sk_root="$SKILLS_ROOT/$1"
  local name="$2"
  local probes="$3"
  mkdir -p "$sk_root/$name"
  cat > "$sk_root/$name/drift_probes.json" <<EOF
$probes
EOF
}

write_transcript() {
  # write_transcript <file> <jsonl-body>
  local file="$1"; shift
  printf '%s\n' "$@" > "$file"
}

assistant_text() {
  # emit one JSONL line for an assistant message with text content
  python3 -c "
import json,sys
text=sys.argv[1]
uuid=sys.argv[2]
print(json.dumps({'type':'assistant','uuid':uuid,
                  'message':{'role':'assistant','content':[{'type':'text','text':text}]}}))
" "$1" "$2"
}

assistant_tool_use() {
  # emit one JSONL line for an assistant tool_use
  python3 -c "
import json,sys
name=sys.argv[1]; inp=json.loads(sys.argv[2])
print(json.dumps({'type':'assistant',
                  'message':{'role':'assistant','content':[{'type':'tool_use','name':name,'input':inp}]}}))
" "$1" "$2"
}

call() {
  # call <state_sub> <skills_sub> <transcript_file> <session_id> [env_overrides...]
  local state_sub="$1" skills_sub="$2" tx="$3" sid="$4"; shift 4
  local payload
  payload=$(python3 -c "
import json,sys
print(json.dumps({'session_id':sys.argv[1],'transcript_path':sys.argv[2],'hook_event_name':'UserPromptSubmit','prompt':'next'}))
" "$sid" "$tx")
  local env_args=(COMPLIANCE_CANARY_STATE_DIR="$STATE_ROOT/$state_sub"
                  COMPLIANCE_CANARY_SKILLS_ROOT="$SKILLS_ROOT/$skills_sub")
  if [ "$#" -gt 0 ]; then
    printf '%s' "$payload" | env "${env_args[@]}" "$@" "${HOOK[@]}"
  else
    printf '%s' "$payload" | env "${env_args[@]}" "${HOOK[@]}"
  fi
}

emitted() {
  [ -n "$1" ] && echo "$1" | grep -q '<system-reminder>'
}

# Tests -----------------------------------------------------------------

echo "[1] forbidden_regex fires when filler phrase present"
PROBES='[{"id":"filler","kind":"forbidden_regex","pattern":"(?i)\\bcertainly\\b","message":"no certainly"}]'
make_skill_with_probes sk1 cv "$PROBES"
TX="$TRANSCRIPT_DIR/t1.jsonl"
write_transcript "$TX" "$(assistant_text 'Certainly! I will do that right away.' u1)"
out=$(call cc1 sk1 "$TX" s1)
if emitted "$out" && echo "$out" | grep -q 'forbidden_regex'; then ok "filler regex fires"; else no "filler regex fires" "got: $(echo "$out" | head -c120)"; fi

echo "[2] forbidden_regex stays silent when phrase absent"
TX="$TRANSCRIPT_DIR/t2.jsonl"
write_transcript "$TX" "$(assistant_text 'Hash signature mismatch on call 5. Trying ls -la.' u2)"
out=$(call cc2 sk1 "$TX" s2)
if [ -z "$out" ]; then ok "no filler → silent"; else no "no filler → silent" "got: $(echo "$out" | head -c80)"; fi

echo "[3] word_count_per_message: avg over threshold fires"
PROBES='[{"id":"creep","kind":"word_count_per_message","threshold":15,"window":3}]'
make_skill_with_probes sk3 cv "$PROBES"
LONG="this is a quite long message intended to push the average word count above the threshold set in the probe"
TX="$TRANSCRIPT_DIR/t3.jsonl"
write_transcript "$TX" \
  "$(assistant_text "$LONG" u1)" \
  "$(assistant_text "$LONG also more words" u2)" \
  "$(assistant_text "$LONG plus extra padding text here" u3)"
out=$(call cc3 sk3 "$TX" s3)
if emitted "$out" && echo "$out" | grep -q 'word_count_per_message'; then ok "word-count probe fires"; else no "word-count probe fires"; fi

echo "[4] word_count_per_message: short messages → silent"
TX="$TRANSCRIPT_DIR/t4.jsonl"
write_transcript "$TX" \
  "$(assistant_text 'ok' u1)" \
  "$(assistant_text 'done' u2)" \
  "$(assistant_text 'next' u3)"
out=$(call cc4 sk3 "$TX" s4)
if [ -z "$out" ]; then ok "short msgs → silent"; else no "short msgs → silent" "got: $(echo "$out" | head -c80)"; fi

echo "[5] claim_without_evidence: claim present, no recent verify tool → fires"
PROBES='[{"id":"unverified","kind":"claim_without_evidence","claim_pattern":"(?i)\\b(done|fixed)\\b","verify_tools":["Bash"],"verify_keywords":["test","make","build"]}]'
make_skill_with_probes sk5 vbc "$PROBES"
TX="$TRANSCRIPT_DIR/t5.jsonl"
# Last assistant message contains "done" — but no Bash tool_use with verify keyword
write_transcript "$TX" \
  "$(assistant_tool_use Edit '{"file_path":"/x","old_string":"a","new_string":"b"}')" \
  "$(assistant_text 'all done!' u1)"
out=$(call cc5 sk5 "$TX" s5)
if emitted "$out" && echo "$out" | grep -q 'claim_without_evidence'; then ok "unverified-done fires"; else no "unverified-done fires" "got: $(echo "$out" | head -c200)"; fi

echo "[6] claim_without_evidence: verify tool_use present → silent"
TX="$TRANSCRIPT_DIR/t6.jsonl"
write_transcript "$TX" \
  "$(assistant_tool_use Bash '{"command":"npm test"}')" \
  "$(assistant_text 'all done!' u1)"
out=$(call cc6 sk5 "$TX" s6)
if [ -z "$out" ]; then ok "verified-done → silent"; else no "verified-done → silent" "got: $(echo "$out" | head -c200)"; fi

echo "[7] cooldown: same probe fires once, suppressed on consecutive turns"
PROBES='[{"id":"filler","kind":"forbidden_regex","pattern":"(?i)\\bcertainly\\b"}]'
make_skill_with_probes sk7 cv "$PROBES"
TX="$TRANSCRIPT_DIR/t7.jsonl"
write_transcript "$TX" "$(assistant_text 'Certainly!' u1)"
out1=$(call cc7 sk7 "$TX" s7)
out2=$(call cc7 sk7 "$TX" s7)
out3=$(call cc7 sk7 "$TX" s7)
if emitted "$out1" && ! emitted "$out2" && ! emitted "$out3"; then
  ok "fires on turn 1, suppressed on 2 + 3 (cooldown=3)"
else
  no "cooldown behaviour" "t1=$(emitted "$out1" && echo y || echo n) t2=$(emitted "$out2" && echo y || echo n) t3=$(emitted "$out3" && echo y || echo n)"
fi

echo "[8] cooldown expires: 4th turn fires again"
out4=$(call cc7 sk7 "$TX" s7)
if emitted "$out4"; then ok "fires again on turn 4 (cooldown expired)"; else no "fires again on turn 4"; fi

echo "[9] COMPLIANCE_CANARY_COOLDOWN=0 → no suppression"
make_skill_with_probes sk9 cv "$PROBES"
TX="$TRANSCRIPT_DIR/t9.jsonl"
write_transcript "$TX" "$(assistant_text 'Certainly again' u1)"
out_a=$(call cc9 sk9 "$TX" s9 COMPLIANCE_CANARY_COOLDOWN=0)
out_b=$(call cc9 sk9 "$TX" s9 COMPLIANCE_CANARY_COOLDOWN=0)
if emitted "$out_a" && emitted "$out_b"; then ok "cooldown=0 → fires every turn"; else no "cooldown=0 → fires every turn"; fi

echo "[10] COMPLIANCE_CANARY_DISABLED=1 → never fires"
TX="$TRANSCRIPT_DIR/t10.jsonl"
write_transcript "$TX" "$(assistant_text 'Certainly!' u1)"
out=$(call cc10 sk1 "$TX" s10 COMPLIANCE_CANARY_DISABLED=1)
if [ -z "$out" ]; then ok "DISABLED=1 silences"; else no "DISABLED=1 silences"; fi

echo "[11] No drift_probes.json files → silent"
mkdir -p "$SKILLS_ROOT/empty"
out=$(call cc11 empty "$TX" s11)
if [ -z "$out" ]; then ok "no probes → silent"; else no "no probes → silent" "got: $(echo "$out" | head -c80)"; fi

echo "[12] Malformed drift_probes.json → skipped, hook proceeds"
mkdir -p "$SKILLS_ROOT/sk12/bad" "$SKILLS_ROOT/sk12/good"
echo 'not json {' > "$SKILLS_ROOT/sk12/bad/drift_probes.json"
echo '[{"id":"filler","kind":"forbidden_regex","pattern":"(?i)certainly"}]' > "$SKILLS_ROOT/sk12/good/drift_probes.json"
TX="$TRANSCRIPT_DIR/t12.jsonl"
write_transcript "$TX" "$(assistant_text 'certainly!' u1)"
out=$(call cc12 sk12 "$TX" s12)
if emitted "$out" && echo "$out" | grep -q 'good'; then ok "good probe still fires despite malformed sibling"; else no "good probe fires" "got: $(echo "$out" | head -c200)"; fi

echo "[13] Empty transcript → silent"
TX="$TRANSCRIPT_DIR/t13.jsonl"
: > "$TX"
out=$(call cc13 sk1 "$TX" s13)
if [ -z "$out" ]; then ok "empty transcript → silent"; else no "empty transcript → silent"; fi

echo "[14] Missing transcript file → silent (graceful)"
out=$(call cc14 sk1 "$TRANSCRIPT_DIR/does-not-exist.jsonl" s14)
if [ -z "$out" ]; then ok "missing transcript → silent"; else no "missing transcript → silent"; fi

echo "[15] Empty / malformed stdin → exit 0"
out=$(printf '' | "${HOOK[@]}"); ec=$?
if [ $ec -eq 0 ]; then ok "empty stdin exit 0"; else no "empty stdin exit 0"; fi
out=$(printf 'garbage' | "${HOOK[@]}" 2>/dev/null); ec=$?
if [ $ec -eq 0 ]; then ok "malformed stdin exit 0"; else no "malformed stdin exit 0"; fi

echo "[16] Two sessions: independent probe_history"
PROBES='[{"id":"filler","kind":"forbidden_regex","pattern":"(?i)\\bcertainly\\b"}]'
make_skill_with_probes sk16 cv "$PROBES"
TX_A="$TRANSCRIPT_DIR/t16a.jsonl"
TX_B="$TRANSCRIPT_DIR/t16b.jsonl"
write_transcript "$TX_A" "$(assistant_text 'Certainly A' u1)"
write_transcript "$TX_B" "$(assistant_text 'Certainly B' u1)"
out_a=$(call cc16 sk16 "$TX_A" sess-alpha)  # fires
out_a2=$(call cc16 sk16 "$TX_A" sess-alpha) # suppressed
out_b=$(call cc16 sk16 "$TX_B" sess-beta)   # fires (different session)
if emitted "$out_a" && ! emitted "$out_a2" && emitted "$out_b"; then
  ok "two sessions independent"
else
  no "two sessions independent" "a1=$(emitted "$out_a" && echo y || echo n) a2=$(emitted "$out_a2" && echo y || echo n) b=$(emitted "$out_b" && echo y || echo n)"
fi

echo "[17] Concurrent invocations → flock-safe (10 parallel)"
make_skill_with_probes sk17 cv '[]'  # no probes, just exercising state lock
mkdir -p "$STATE_ROOT/cc17"
TX="$TRANSCRIPT_DIR/t17.jsonl"
write_transcript "$TX" "$(assistant_text 'x' u1)"
PAYLOAD=$(python3 -c "
import json,sys
print(json.dumps({'session_id':'cc-concur','transcript_path':sys.argv[1],'hook_event_name':'UserPromptSubmit','prompt':'x'}))
" "$TX")
for _ in 1 2 3 4 5 6 7 8 9 10; do
  printf '%s' "$PAYLOAD" | env COMPLIANCE_CANARY_STATE_DIR="$STATE_ROOT/cc17" COMPLIANCE_CANARY_SKILLS_ROOT="$SKILLS_ROOT/sk17" "${HOOK[@]}" > /dev/null &
done
wait
# hook.py names state files by SHA-256(session_id)[:16].json, not the raw id
sid_hash=$(python3 -c "import hashlib;print(hashlib.sha256('cc-concur'.encode('utf-8',errors='replace')).hexdigest()[:16])")
turn_after=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["turn_count"])' "$STATE_ROOT/cc17/$sid_hash.json")
if [ "$turn_after" = "10" ]; then ok "10 parallel → turn_count=10"; else no "10 parallel → turn_count=10" "got $turn_after"; fi

echo "[18] State GC: 8-day-old state files purged at session-start"
mkdir -p "$STATE_ROOT/cc18"
for old in old1 old2; do
  echo '{"turn_count":1}' > "$STATE_ROOT/cc18/$old.json"
  python3 -c "import os,time;os.utime('$STATE_ROOT/cc18/$old.json', (time.time()-8*86400, time.time()-8*86400))"
done
echo '{"turn_count":1}' > "$STATE_ROOT/cc18/keep.json"
TX="$TRANSCRIPT_DIR/t18.jsonl"
write_transcript "$TX" "$(assistant_text 'x' u1)"
out=$(call cc18 sk1 "$TX" cc-new-sid)  # triggers session-start GC
old_count=$(ls "$STATE_ROOT/cc18"/{old1,old2}.json 2>/dev/null | wc -l | tr -d ' ')
keep=$(ls "$STATE_ROOT/cc18"/keep.json 2>/dev/null | wc -l | tr -d ' ')
if [ "$old_count" = "0" ] && [ "$keep" = "1" ]; then ok "stale purged, fresh kept"; else no "GC" "old=$old_count keep=$keep"; fi

echo "[20] Code-block strip: filler word inside fenced code → silent (false-positive fix)"
PROBES='[{"id":"filler","kind":"forbidden_regex","pattern":"(?i)\\bcertainly\\b"}]'
make_skill_with_probes sk20 cv "$PROBES"
TX="$TRANSCRIPT_DIR/t20.jsonl"
# Build a message with the filler word ONLY inside a fenced code block.
# Use Python (no shell quoting) to write the transcript so backticks survive.
python3 <<PY > "$TX"
import json
fence = chr(96) * 3
msg = f"Here is the change:\n\n{fence}python\nprint(\"Certainly!\")  # literal\n{fence}\n\nDone."
print(json.dumps({"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":msg}]}}))
PY
out=$(call cc20 sk20 "$TX" s20)
if [ -z "$out" ]; then ok "code-block 'Certainly' does NOT trigger"; else no "code-block 'Certainly' does NOT trigger" "got: $(echo "$out" | head -c150)"; fi

echo "[21] Code-block strip: filler in PROSE still triggers"
TX="$TRANSCRIPT_DIR/t21.jsonl"
write_transcript "$TX" "$(assistant_text 'Certainly! Glad to help.' u21)"
out=$(call cc21 sk20 "$TX" s21)
if emitted "$out"; then ok "prose 'Certainly' still triggers"; else no "prose 'Certainly' still triggers"; fi

echo "[22] Inline backtick code stripped: inline-coded 'done' does NOT trigger claim probe"
PROBES='[{"id":"unverified","kind":"claim_without_evidence","claim_pattern":"(?i)\\b(done|fixed)\\b","verify_tools":["Bash"]}]'
make_skill_with_probes sk22 vbc "$PROBES"
TX="$TRANSCRIPT_DIR/t22.jsonl"
python3 <<PY > "$TX"
import json
bt = chr(96)
msg = f"I added a {bt}done{bt} flag in the config"
print(json.dumps({"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":msg}]}}))
PY
out=$(call cc22 sk22 "$TX" s22)
if [ -z "$out" ]; then ok "inline backtick 'done' does NOT trigger claim probe"; else no "inline backtick 'done' does NOT trigger" "got: $(echo "$out" | head -c200)"; fi

echo "[23] Multi-probe cooldown interleaving: A+B fire turn 1, C newly fires turn 2 (A+B suppressed)"
PROBES='[
  {"id":"a","kind":"forbidden_regex","pattern":"(?i)\\bfoo\\b"},
  {"id":"b","kind":"forbidden_regex","pattern":"(?i)\\bbar\\b"},
  {"id":"c","kind":"forbidden_regex","pattern":"(?i)\\bbaz\\b"}
]'
make_skill_with_probes sk23 multi "$PROBES"
TX="$TRANSCRIPT_DIR/t23a.jsonl"
write_transcript "$TX" "$(assistant_text 'foo and bar are here' u23)"
out1=$(call cc23 sk23 "$TX" s23)
if emitted "$out1" && echo "$out1" | grep -q ' a' && echo "$out1" | grep -q ' b'; then ok "turn 1: A + B both fire"; else no "turn 1: A + B both fire" "got: $(echo "$out1" | head -c200)"; fi
# Turn 2: text now has all three; A + B suppressed, C newly fires
TX="$TRANSCRIPT_DIR/t23b.jsonl"
write_transcript "$TX" "$(assistant_text 'foo bar baz' u23b)"
out2=$(call cc23 sk23 "$TX" s23)
if emitted "$out2" && echo "$out2" | grep -q "matched 'baz'" && ! echo "$out2" | grep -qE "matched 'foo'|matched 'bar'"; then
  ok "turn 2: C fires (matched 'baz'), A+B suppressed"
else
  no "turn 2: cooldown selective" "got: $(echo "$out2" | head -c300)"
fi

echo "[19] MAX_PROBES_TRIGGERED cap: 6 probes, only 4 in output"
mkdir -p "$SKILLS_ROOT/sk19/many"
python3 -c "
import json
probes = [{'id':f'p{i}','kind':'forbidden_regex','pattern':'(?i)x'} for i in range(6)]
print(json.dumps(probes))
" > "$SKILLS_ROOT/sk19/many/drift_probes.json"
TX="$TRANSCRIPT_DIR/t19.jsonl"
write_transcript "$TX" "$(assistant_text 'x' u1)"
out=$(call cc19 sk19 "$TX" s19)
count=$(echo "$out" | grep -c '^- ' || true)
if [ "$count" -le 4 ]; then ok "probe count capped at 4 (got $count)"; else no "probe cap" "got $count"; fi

echo "[24] repeated_tool_error: 2+ matching tool errors fire"
PROBES='[{"id":"ewr","kind":"repeated_tool_error","pattern":"File has not been read yet","min_count":2,"message":"read before edit"}]'
make_skill_with_probes sk24 cv "$PROBES"
user_tool_error() {
  python3 -c "
import json,sys
print(json.dumps({'type':'user',
                  'message':{'role':'user','content':[{'type':'tool_result','is_error':True,'content':sys.argv[1]}]}}))
" "$1"
}
TX="$TRANSCRIPT_DIR/t24.jsonl"
write_transcript "$TX" \
  "$(assistant_text 'editing now' u1)" \
  "$(user_tool_error '<tool_use_error>File has not been read yet. Read it first before writing to it.</tool_use_error>')" \
  "$(assistant_text 'retrying' u2)" \
  "$(user_tool_error '<tool_use_error>File has not been read yet. Read it first before writing to it.</tool_use_error>')"
out=$(call cc24 sk24 "$TX" s24)
if emitted "$out" && echo "$out" | grep -q 'repeated_tool_error'; then ok "repeated tool error fires at min_count=2"; else no "repeated tool error fires" "got: $(echo "$out" | head -c120)"; fi

echo "[25] repeated_tool_error: single occurrence stays silent"
TX="$TRANSCRIPT_DIR/t25.jsonl"
write_transcript "$TX" \
  "$(assistant_text 'editing now' u1)" \
  "$(user_tool_error '<tool_use_error>File has not been read yet.</tool_use_error>')" \
  "$(assistant_text 'recovered, read then edited' u2)"
out=$(call cc25 sk24 "$TX" s25)
if [ -z "$out" ]; then ok "single error → silent"; else no "single error → silent" "got: $(echo "$out" | head -c100)"; fi

echo "[26] repeated_tool_error: list-of-blocks content shape also detected"
user_tool_error_blocks() {
  python3 -c "
import json,sys
print(json.dumps({'type':'user',
                  'message':{'role':'user','content':[{'type':'tool_result','is_error':True,
                    'content':[{'type':'text','text':sys.argv[1]}]}]}}))
" "$1"
}
TX="$TRANSCRIPT_DIR/t26.jsonl"
write_transcript "$TX" \
  "$(assistant_text 'editing now' u1)" \
  "$(user_tool_error_blocks '<tool_use_error>File has not been read yet.</tool_use_error>')" \
  "$(assistant_text 'retrying' u2)" \
  "$(user_tool_error '<tool_use_error>File has not been read yet.</tool_use_error>')"
out=$(call cc26 sk24 "$TX" s26)
if emitted "$out" && echo "$out" | grep -q 'repeated_tool_error'; then ok "mixed string+blocks content detected"; else no "mixed string+blocks content detected" "got: $(echo "$out" | head -c120)"; fi

echo "[27] user_correction: correction in current prompt fires"
PROBES='[{"id":"uc","kind":"user_correction","pattern":"(?i)(?:^\\s*no[,. ]|don.?t use\\b|i said\\b)","message":"harvest the correction"}]'
make_skill_with_probes sk27 cv "$PROBES"
TX="$TRANSCRIPT_DIR/t27.jsonl"
write_transcript "$TX" "$(assistant_text 'I used tabs for indentation.' u1)"
payload=$(python3 -c "
import json,sys
print(json.dumps({'session_id':'s27','transcript_path':sys.argv[1],'hook_event_name':'UserPromptSubmit','prompt':'no, I said use spaces not tabs'}))
" "$TX")
out=$(printf '%s' "$payload" | env COMPLIANCE_CANARY_STATE_DIR="$STATE_ROOT/cc27" COMPLIANCE_CANARY_SKILLS_ROOT="$SKILLS_ROOT/sk27" "${HOOK[@]}")
if emitted "$out" && echo "$out" | grep -q 'user_correction'; then ok "correction prompt fires"; else no "correction prompt fires" "got: $(echo "$out" | head -c120)"; fi

echo "[28] user_correction: ordinary prompt stays silent"
payload=$(python3 -c "
import json,sys
print(json.dumps({'session_id':'s28','transcript_path':sys.argv[1],'hook_event_name':'UserPromptSubmit','prompt':'now add a unit test for the parser'}))
" "$TX")
out=$(printf '%s' "$payload" | env COMPLIANCE_CANARY_STATE_DIR="$STATE_ROOT/cc28" COMPLIANCE_CANARY_SKILLS_ROOT="$SKILLS_ROOT/sk27" "${HOOK[@]}")
if [ -z "$out" ]; then ok "ordinary prompt silent"; else no "ordinary prompt silent" "got: $(echo "$out" | head -c100)"; fi

echo "[29] malformed transcript events: detection still WORKS with garbage lines present"
# Exit-code-only assertion is vacuous here — hook.sh swallows crashes with
# '|| true' (mutation test 2026-06-12: deleting the normalization survived).
# Real contract: a probe must still FIRE on a transcript laced with
# parseable-but-malformed lines, proving hook.py processed past them.
PROBES='[{"id":"m29","kind":"forbidden_regex","pattern":"(?i)\\bdefinitely-drifted\\b","message":"caught"}]'
make_skill_with_probes sk29 m29skill "$PROBES"
TX="$TRANSCRIPT_DIR/t29.jsonl"
write_transcript "$TX" "$(assistant_text 'normal message' u1)"
# parseable-but-malformed: bare scalar, list, message-as-string (codex round-3)
printf '123\n["a","b"]\n{"type":"assistant","message":"bad"}\n{"type":"user","message":42}\n' >> "$TX"
assistant_text 'this reply is definitely-drifted content' u2 >> "$TX"
out=$(call cc29 sk29 "$TX" s29)
if emitted "$out" && echo "$out" | grep -q 'm29'; then
  ok "probe fires past malformed events"
else
  no "probe fires past malformed events" "got: $(echo "$out" | head -c120)"
fi

echo "[30] trajectory_drift: high error-rate session fires"
PROBES='[{"id":"traj","kind":"trajectory_drift","min_tool_calls":4,"max_error_rate":0.5,"message":"error loop"}]'
make_skill_with_probes sk30 traj "$PROBES"
TX="$TRANSCRIPT_DIR/t30.jsonl"
write_transcript "$TX" \
  "$(assistant_text 'retrying the command' u30)" \
  "$(assistant_tool_use Bash '{"command":"x"}')" \
  "$(user_tool_error 'boom one')" \
  "$(assistant_tool_use Bash '{"command":"y"}')" \
  "$(user_tool_error 'boom two')" \
  "$(assistant_tool_use Read '{"file_path":"/a"}')" \
  "$(assistant_tool_use Read '{"file_path":"/b"}')"
out=$(call cc30 sk30 "$TX" s30)
if emitted "$out" && echo "$out" | grep -q 'trajectory_drift'; then ok "high error rate fires"; else no "high error rate fires" "got: $(echo "$out" | head -c120)"; fi

echo "[31] trajectory_drift: silent below min_tool_calls (cold start)"
TX="$TRANSCRIPT_DIR/t31.jsonl"
write_transcript "$TX" \
  "$(assistant_tool_use Bash '{"command":"x"}')" \
  "$(user_tool_error 'boom')"
out=$(call cc31 sk30 "$TX" s31)
if [ -z "$out" ]; then ok "cold start silent"; else no "cold start silent" "got: $(echo "$out" | head -c100)"; fi

echo "[32] trajectory_drift: silent at healthy error rate"
TX="$TRANSCRIPT_DIR/t32.jsonl"
{ assistant_text 'reading files' u32
  for i in 1 2 3 4 5 6 7 8; do assistant_tool_use Read "{\"file_path\":\"/f$i\"}"; done
  user_tool_error 'single failure'; } > "$TX"
out=$(call cc32 sk30 "$TX" s32)
if [ -z "$out" ]; then ok "healthy rate silent"; else no "healthy rate silent" "got: $(echo "$out" | head -c100)"; fi

echo "[33] tool_use-only transcript (no assistant prose): trajectory_drift still fires"
# Regression guard: main() must NOT early-return when the recent window has no
# assistant TEXT. Error-loop turns are tool_use-only — exactly when the
# non-text detectors must run. (Pre-fix, an `if not messages: return 0` here
# silenced trajectory_drift/repeated_tool_error/user_correction.)
PROBES='[{"id":"traj","kind":"trajectory_drift","min_tool_calls":4,"max_error_rate":0.5,"message":"error loop"}]'
make_skill_with_probes sk33 traj "$PROBES"
TX="$TRANSCRIPT_DIR/t33.jsonl"
# NO assistant_text anywhere — only tool_use + tool_error events
write_transcript "$TX" \
  "$(assistant_tool_use Bash '{"command":"x"}')" \
  "$(user_tool_error 'boom one')" \
  "$(assistant_tool_use Bash '{"command":"y"}')" \
  "$(user_tool_error 'boom two')" \
  "$(assistant_tool_use Read '{"file_path":"/a"}')" \
  "$(assistant_tool_use Read '{"file_path":"/b"}')"
out=$(call cc33 sk33 "$TX" s33)
if emitted "$out" && echo "$out" | grep -q 'trajectory_drift'; then ok "trajectory_drift fires with no assistant prose"; else no "trajectory_drift fires with no assistant prose" "got: $(echo "$out" | head -c150)"; fi

echo "[34] tool_use-only transcript (no assistant prose): user_correction still fires"
# Same regression guard for the prompt-driven detector: correction must fire
# even when no assistant text precedes it.
PROBES='[{"id":"uc","kind":"user_correction","pattern":"(?i)(?:^\\s*no[,. ]|i said\\b)","message":"harvest the correction"}]'
make_skill_with_probes sk34 cv "$PROBES"
TX="$TRANSCRIPT_DIR/t34.jsonl"
write_transcript "$TX" \
  "$(assistant_tool_use Edit '{"file_path":"/x","old_string":"a","new_string":"b"}')"
payload=$(python3 -c "
import json,sys
print(json.dumps({'session_id':'s34','transcript_path':sys.argv[1],'hook_event_name':'UserPromptSubmit','prompt':'no, I said use spaces'}))
" "$TX")
out=$(printf '%s' "$payload" | env COMPLIANCE_CANARY_STATE_DIR="$STATE_ROOT/cc34" COMPLIANCE_CANARY_SKILLS_ROOT="$SKILLS_ROOT/sk34" "${HOOK[@]}")
if emitted "$out" && echo "$out" | grep -q 'user_correction'; then ok "user_correction fires with no assistant prose"; else no "user_correction fires with no assistant prose" "got: $(echo "$out" | head -c150)"; fi

echo "[35] claim_without_evidence: incidental substring ('cat' inside 'category') does NOT count as verification"
# Word-boundary fix: short verify keywords (cat, ls, build) must not match
# inside unrelated words. Bash ran 'mkdir category' — the keyword 'cat' is a
# substring of 'category' but NOT a standalone command, so it is NOT real
# verification and the done-claim must STILL fire.
PROBES='[{"id":"unverified","kind":"claim_without_evidence","claim_pattern":"(?i)\\b(done|fixed)\\b","verify_tools":["Bash"],"verify_keywords":["cat","ls","build"]}]'
make_skill_with_probes sk35 vbc "$PROBES"
TX="$TRANSCRIPT_DIR/t35.jsonl"
write_transcript "$TX" \
  "$(assistant_tool_use Bash '{"command":"mkdir category && echo tools rebuild"}')" \
  "$(assistant_text 'all done!' u1)"
out=$(call cc35 sk35 "$TX" s35)
if emitted "$out" && echo "$out" | grep -q 'claim_without_evidence'; then ok "incidental 'cat'/'ls'/'build' substrings do NOT suppress claim probe"; else no "incidental substrings do NOT suppress claim probe" "got: $(echo "$out" | head -c200)"; fi

echo "[36] claim_without_evidence: a real 'cat' command (word-bounded) DOES count as verification"
# True-positive preservation: the same keyword as a standalone token must still
# register as evidence and silence the claim.
TX="$TRANSCRIPT_DIR/t36.jsonl"
write_transcript "$TX" \
  "$(assistant_tool_use Bash '{"command":"cat build/output.log"}')" \
  "$(assistant_text 'all done!' u1)"
out=$(call cc36 sk35 "$TX" s36)
if [ -z "$out" ]; then ok "real 'cat' counts as verification → silent"; else no "real 'cat' counts as verification → silent" "got: $(echo "$out" | head -c200)"; fi

echo "[37] state_lock: a body exception propagates cleanly (not swallowed/replaced)"
# Exception-safety fix: with state_lock(path) must let a body ValueError
# propagate as ValueError — pre-fix the contextmanager double-yielded and the
# real exception was replaced by RuntimeError('generator didn't stop ...').
LOCKDIR="$STATE_ROOT/lock37"
mkdir -p "$LOCKDIR"
res=$(python3 -c "
import sys
sys.path.insert(0, '$TOOLS_DIR')
from pathlib import Path
from hook import state_lock
try:
    with state_lock(Path('$LOCKDIR/x.json')):
        raise ValueError('boom-body')
except ValueError as e:
    print('VALUEERROR:' + str(e))
except Exception as e:
    print('OTHER:' + type(e).__name__ + ':' + str(e))
" 2>/dev/null)
if [ "$res" = "VALUEERROR:boom-body" ]; then ok "body ValueError propagates cleanly"; else no "body ValueError propagates cleanly" "got: $res"; fi

echo "[38] measure.py offline analyzer honors a probe's declared window (not just --window)"
# Regression: analyze_one used one global --window (default 3), so a probe
# declaring window:5 was scored against only 3 messages — a silent false
# negative for the exact calibration this tool exists to verify. It must now
# mirror the live hook and fetch the largest declared window.
M38_TX="$TRANSCRIPT_DIR/t38.jsonl"
{ assistant_text 'word word word word word word word word word word' u1
  assistant_text 'word word word word word word word word word word' u2
  assistant_text 'one' u3
  assistant_text 'two' u4
  assistant_text 'three' u5; } > "$M38_TX"
# avg over window=5 = (10+10+1+1+1)/5 = 4.6 > threshold 4 ; over default 3 = 1
m38=$(python3 - "$TOOLS_DIR" "$M38_TX" <<'PY' 2>/dev/null
import sys
sys.path.insert(0, sys.argv[1])
import measure
from pathlib import Path
probe = {"_probe_id": "wc5", "kind": "word_count_per_message", "threshold": 4, "window": 5}
r = measure.analyze_one(Path(sys.argv[2]), [probe], 3)  # CLI default window=3
print("%d %d" % (r["n_assistant_messages"], r["n_fires"]))
PY
)
if [ "$m38" = "5 1" ]; then ok "window:5 probe fetched 5 msgs + fired under --window 3"; else no "measure.py per-probe window" "got: $m38 (want '5 1')"; fi

# word_count warrant_pattern: a length-requesting prompt suppresses the creep
# warning (caveman's own spec: "short UNLESS detail is requested"); a trivial
# prompt still fires. The warning governs the NEXT reply, so it warrants on the
# incoming prompt.
WPROBES='[{"id":"wc","kind":"word_count_per_message","threshold":10,"window":3,"warrant_pattern":"(?i)\\b(explain|think (of|about))\\b"}]'
make_skill_with_probes sk39 cv "$WPROBES"
LONGMSG="one two three four five six seven eight nine ten eleven twelve thirteen"  # 13 words > 10
TXW="$TRANSCRIPT_DIR/t39.jsonl"
write_transcript "$TXW" \
  "$(assistant_text "$LONGMSG" u1)" \
  "$(assistant_text "$LONGMSG" u2)" \
  "$(assistant_text "$LONGMSG" u3)"

echo "[39] word_count warrant: detail-requesting prompt suppresses the creep warning"
pay39=$(python3 -c "
import json,sys
print(json.dumps({'session_id':'s39','transcript_path':sys.argv[1],'hook_event_name':'UserPromptSubmit','prompt':'explain how this works in depth'}))
" "$TXW")
out=$(printf '%s' "$pay39" | env COMPLIANCE_CANARY_STATE_DIR="$STATE_ROOT/cc39" COMPLIANCE_CANARY_SKILLS_ROOT="$SKILLS_ROOT/sk39" "${HOOK[@]}")
if [ -z "$out" ]; then ok "warranted (detail) prompt → creep suppressed"; else no "warranted prompt → suppressed" "got: $(echo "$out" | head -c150)"; fi

echo "[40] word_count warrant: trivial prompt still fires"
pay40=$(python3 -c "
import json,sys
print(json.dumps({'session_id':'s40','transcript_path':sys.argv[1],'hook_event_name':'UserPromptSubmit','prompt':'fix the typo'}))
" "$TXW")
out=$(printf '%s' "$pay40" | env COMPLIANCE_CANARY_STATE_DIR="$STATE_ROOT/cc40" COMPLIANCE_CANARY_SKILLS_ROOT="$SKILLS_ROOT/sk39" "${HOOK[@]}")
if emitted "$out" && echo "$out" | grep -q 'word_count_per_message'; then ok "unwarranted (trivial) prompt → creep fires"; else no "trivial prompt → fires" "got: $(echo "$out" | head -c150)"; fi

# ======================================================================
# Periodic re-anchor (absorbed skill-pulse, merged 2026-06-16). The second
# mechanism: every Nth turn, re-state active skills' `pulse_reminder:` rules.
# ======================================================================

make_skill_with_pulse() {
  # make_skill_with_pulse <skills_subdir> <dir_name> <yaml_name> <pulse_reminder> [extra_frontmatter_line]
  local sk_root="$SKILLS_ROOT/$1"; local dir="$2"; local nm="$3"; local pr="$4"; local extra="${5:-}"
  mkdir -p "$sk_root/$dir"
  {
    echo "---"
    echo "name: $nm"
    echo "description: Test skill $nm. Second sentence here."
    [ -n "$pr" ] && echo "pulse_reminder: $pr"
    [ -n "$extra" ] && echo "$extra"
    echo "---"
    echo "body"
  } > "$sk_root/$dir/SKILL.md"
}

EMPTYTX="$TRANSCRIPT_DIR/empty.jsonl"; : > "$EMPTYTX"

echo "[41] re-anchor: silent below cadence, fires on cadence turn (PULSE_EVERY=2)"
make_skill_with_pulse skp1 caveman caveman-ultra "terse — drop filler"
o1=$(call ccp1 skp1 "$EMPTYTX" sp1 COMPLIANCE_CANARY_PULSE_EVERY=2)
o2=$(call ccp1 skp1 "$EMPTYTX" sp1 COMPLIANCE_CANARY_PULSE_EVERY=2)
if [ -z "$o1" ] && emitted "$o2" && echo "$o2" | grep -q 're-anchor (turn 2)' && echo "$o2" | grep -q 'caveman-ultra: terse'; then
  ok "re-anchor fires on cadence turn, silent before"; else no "re-anchor cadence" "t1=[$o1] t2=[$(echo "$o2"|head -c80)]"; fi

echo "[42] re-anchor: repeats on turn 4, silent on turn 3 (off-cadence)"
o3=$(call ccp1 skp1 "$EMPTYTX" sp1 COMPLIANCE_CANARY_PULSE_EVERY=2)   # turn3
o4=$(call ccp1 skp1 "$EMPTYTX" sp1 COMPLIANCE_CANARY_PULSE_EVERY=2)   # turn4
if [ -z "$o3" ] && echo "$o4" | grep -q 're-anchor (turn 4)'; then ok "re-anchor repeats on cadence, silent between"; else no "re-anchor repeat" "t3=[$o3] t4=[$(echo "$o4"|head -c80)]"; fi

echo "[43] re-anchor: skill WITHOUT pulse_reminder is excluded"
make_skill_with_pulse skp2 withpr has-pr "rule A"
make_skill_with_pulse skp2 nopr no-pr ""        # no pulse_reminder line
call ccp2 skp2 "$EMPTYTX" sp2 COMPLIANCE_CANARY_PULSE_EVERY=2 >/dev/null
o=$(call ccp2 skp2 "$EMPTYTX" sp2 COMPLIANCE_CANARY_PULSE_EVERY=2)
if echo "$o" | grep -q 'has-pr: rule A' && ! echo "$o" | grep -q 'no-pr'; then ok "no-pulse_reminder skill excluded"; else no "pulse exclusion" "got: $(echo "$o"|head -c120)"; fi

echo "[44] re-anchor YIELDS to a fired probe on a shared cadence turn (no double-nag)"
# Skill carries BOTH a pulse_reminder AND a filler probe; transcript has filler.
make_skill_with_pulse skp3 caveman caveman-ultra "terse — drop filler"
cat > "$SKILLS_ROOT/skp3/caveman/drift_probes.json" <<'EOF'
[{"id":"filler","kind":"forbidden_regex","pattern":"(?i)\\bcertainly\\b","message":"no certainly"}]
EOF
TXF="$TRANSCRIPT_DIR/t44.jsonl"
write_transcript "$TXF" "$(assistant_text 'Certainly! Proceeding now.' u1)"
# turn1 CLEAN (no fire, no cooldown set); turn2 = cadence AND fresh filler →
# probe fires, re-anchor must yield. (If turn1 had filler too, cooldown would
# suppress the turn2 fire — a separate, already-tested behavior.)
call ccp3 skp3 "$EMPTYTX" sp3 COMPLIANCE_CANARY_PULSE_EVERY=2 >/dev/null   # turn1 clean
o=$(call ccp3 skp3 "$TXF" sp3 COMPLIANCE_CANARY_PULSE_EVERY=2)            # turn2 cadence + filler
if echo "$o" | grep -q 'forbidden_regex' && ! echo "$o" | grep -q 're-anchor'; then ok "probe fires; re-anchor yields"; else no "yield-on-shared-turn" "got: $(echo "$o"|head -c160)"; fi

echo "[45] SKILL_PULSE_DISABLED=1: re-anchor off, but probe STILL fires (fresh session, turn 1)"
o=$(call ccp3b skp3 "$TXF" sp3b COMPLIANCE_CANARY_PULSE_EVERY=2 SKILL_PULSE_DISABLED=1)
if echo "$o" | grep -q 'forbidden_regex' && ! echo "$o" | grep -q 're-anchor'; then ok "pulse-disable ≠ probe-disable"; else no "SKILL_PULSE_DISABLED scope" "got: $(echo "$o"|head -c120)"; fi

echo "[46] COMPLIANCE_CANARY_PULSE_EVERY=0 disables re-anchor (clean transcript → silent)"
call ccp4 skp1 "$EMPTYTX" sp4 COMPLIANCE_CANARY_PULSE_EVERY=0 >/dev/null
o=$(call ccp4 skp1 "$EMPTYTX" sp4 COMPLIANCE_CANARY_PULSE_EVERY=0)
if [ -z "$o" ]; then ok "PULSE_EVERY=0 → re-anchor disabled"; else no "PULSE_EVERY=0" "got: $(echo "$o"|head -c120)"; fi

echo "[47] cadence floor: PULSE_EVERY=1 clamps to 2 (silent on turn 1)"
o1=$(call ccp5 skp1 "$EMPTYTX" sp5 COMPLIANCE_CANARY_PULSE_EVERY=1)   # turn1: if floored to 2, silent
o2=$(call ccp5 skp1 "$EMPTYTX" sp5 COMPLIANCE_CANARY_PULSE_EVERY=1)   # turn2: fires
if [ -z "$o1" ] && echo "$o2" | grep -q 're-anchor (turn 2)'; then ok "cadence floors to 2"; else no "cadence floor" "t1=[$o1] t2=[$(echo "$o2"|head -c80)]"; fi

echo "[48] SKILL_PULSE_EVERY back-compat alias drives cadence"
call ccp6 skp1 "$EMPTYTX" sp6 SKILL_PULSE_EVERY=2 >/dev/null
o=$(call ccp6 skp1 "$EMPTYTX" sp6 SKILL_PULSE_EVERY=2)
if echo "$o" | grep -q 're-anchor (turn 2)'; then ok "SKILL_PULSE_EVERY alias honored"; else no "alias cadence" "got: $(echo "$o"|head -c120)"; fi

echo "[49] BOM-prefixed SKILL.md frontmatter still parses (skill not dropped)"
mkdir -p "$SKILLS_ROOT/skp7/bomskill"
printf '\xef\xbb\xbf---\nname: bom-skill\ndescription: x. y.\npulse_reminder: bom rule\n---\nbody\n' > "$SKILLS_ROOT/skp7/bomskill/SKILL.md"
call ccp7 skp7 "$EMPTYTX" sp7 COMPLIANCE_CANARY_PULSE_EVERY=2 >/dev/null
o=$(call ccp7 skp7 "$EMPTYTX" sp7 COMPLIANCE_CANARY_PULSE_EVERY=2)
if echo "$o" | grep -q 'bom-skill: bom rule'; then ok "BOM frontmatter parsed"; else no "BOM tolerance" "got: $(echo "$o"|head -c120)"; fi

echo "[50] allowlist forces inclusion w/ description first-sentence fallback"
make_skill_with_pulse skp8 nopr no-pr ""    # no pulse_reminder; desc = "Test skill no-pr. Second sentence here."
call ccp8 skp8 "$EMPTYTX" sp8 COMPLIANCE_CANARY_PULSE_EVERY=2 COMPLIANCE_CANARY_PULSE_SKILLS=no-pr >/dev/null
o=$(call ccp8 skp8 "$EMPTYTX" sp8 COMPLIANCE_CANARY_PULSE_EVERY=2 COMPLIANCE_CANARY_PULSE_SKILLS=no-pr)
if echo "$o" | grep -q 'no-pr: Test skill no-pr'; then ok "allowlist + description fallback"; else no "allowlist fallback" "got: $(echo "$o"|head -c120)"; fi

# ======================================================================
# Robustness hardening (adversarial fuzz, 2026-06-16). Always-exit-0 must
# hold against malformed payloads and a catastrophic author regex.
# ======================================================================

echo "[51] non-object JSON payload (42 / \"x\" / [..] / null / true) → exit 0, silent"
bad51=0
for p in '42' '"x"' '[1,2,3]' 'null' 'true'; do
  out=$(printf '%s' "$p" | env COMPLIANCE_CANARY_STATE_DIR="$STATE_ROOT/cc51" "${HOOK[@]}" 2>/dev/null); ec=$?
  { [ "$ec" -ne 0 ] || [ -n "$out" ]; } && { bad51=1; break; }
done
if [ "$bad51" -eq 0 ]; then ok "non-object payloads handled (exit 0, silent)"; else no "non-object payload" "payload=$p exit=$ec out=[$out]"; fi

echo "[52] non-string session_id (7 / 9.9 / [1,2]) → exit 0 (no .encode crash)"
bad52=0
for sid in '7' '9.9' '[1,2]'; do
  out=$(printf '{"session_id":%s,"transcript_path":"x","prompt":"hi"}' "$sid" | env COMPLIANCE_CANARY_STATE_DIR="$STATE_ROOT/cc52" "${HOOK[@]}" 2>/dev/null); ec=$?
  [ "$ec" -ne 0 ] && { bad52=1; break; }
done
if [ "$bad52" -eq 0 ]; then ok "non-string session_id coerced (exit 0)"; else no "non-string session_id" "sid=$sid exit=$ec"; fi

echo "[53] ReDoS probe regex → time-bounded, exit 0, silent (no prompt wedge)"
REDOS='[{"id":"redos","kind":"forbidden_regex","pattern":"(a+)+$","message":"x"}]'
make_skill_with_probes sk53 red "$REDOS"
TXR="$TRANSCRIPT_DIR/t53.jsonl"
write_transcript "$TXR" "$(assistant_text 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa!' u1)"
pay53='{"session_id":"s53","transcript_path":"'"$TXR"'","prompt":"next"}'
t0=$(python3 -c 'import time;print(time.time())')
out=$(printf '%s' "$pay53" | timeout 6 env COMPLIANCE_CANARY_STATE_DIR="$STATE_ROOT/cc53" COMPLIANCE_CANARY_SKILLS_ROOT="$SKILLS_ROOT/sk53" "${HOOK[@]}" 2>/dev/null); ec=$?
t1=$(python3 -c 'import time;print(time.time())')
elapsed=$(python3 -c "print($t1-$t0)")
# exit 0, no output, and well under the 6s timeout wall (budget is 1.5s)
if [ "$ec" -eq 0 ] && [ -z "$out" ] && python3 -c "import sys;sys.exit(0 if $elapsed < 4 else 1)"; then
  ok "ReDoS regex time-bounded (${elapsed%.*}s, exit 0, silent)"; else no "ReDoS guard" "exit=$ec elapsed=$elapsed out=[$out]"; fi

echo "[54] runaway pulse_reminder is length-capped in the re-anchor"
LONG=$(python3 -c "print('x'*600)")
make_skill_with_pulse sk54 big big-skill "$LONG"
call cc54 sk54 "$EMPTYTX" s54 COMPLIANCE_CANARY_PULSE_EVERY=2 >/dev/null
o=$(call cc54 sk54 "$EMPTYTX" s54 COMPLIANCE_CANARY_PULSE_EVERY=2)
line=$(echo "$o" | grep 'big-skill:')
linelen=${#line}
if echo "$line" | grep -q '…' && [ "$linelen" -lt 320 ]; then ok "pulse_reminder capped (line=$linelen chars, ellipsized)"; else no "pulse_reminder cap" "len=$linelen line=$(echo "$line"|head -c80)"; fi

# ----------------------------------------------------------------------
echo
if [ $FAIL -eq 0 ]; then
  echo "compliance-canary test.sh: $PASS/$((PASS+FAIL)) PASS"
  exit 0
else
  echo "compliance-canary test.sh: $PASS/$((PASS+FAIL)) — failures:"
  for n in "${FAIL_NAMES[@]}"; do echo "  - $n"; done
  exit 1
fi
