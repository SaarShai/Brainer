#!/usr/bin/env bash
# compliance-canary self-test.
set -uo pipefail

# This is the detector/kind-level regression suite (symptomatic probes,
# request ledger, correction ledger) run under the frontier profile — the
# only profile besides `off` since legacy/shadow were retired 2026-07-19.
# Profile-selection/normalization and `off` gates live in test_profiles.py.
# Frontier selects probes by EXACT id (COMPLIANCE_CANARY_PROBE_IDS); since
# every test below declares its own ad hoc probe id under a synthetic skills
# root, `call`/`call34`/`call_p` auto-inject COMPLIANCE_CANARY_PROBE_IDS
# (see _probe_ids_for) so each test's probe is selected without hardcoding
# ids at every call site — this reproduces "run this test's probes" without
# the retired legacy profile's implicit "select every discovered probe".
export COMPLIANCE_CANARY_PROFILE=frontier

TOOLS_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK=(bash "$TOOLS_DIR/hook.sh")
STATE_ROOT="$(mktemp -d -t cc-test-XXXX)"
SKILLS_ROOT="$(mktemp -d -t cc-skills-XXXX)"
TRANSCRIPT_DIR="$(mktemp -d -t cc-tx-XXXX)"
# Isolated project anchor: correction_ledger_armed() falls back to cwd when
# CLAUDE_PROJECT_DIR is unset, so a host repo's real armed
# .brainer/task-retrospective/current.json would flip "unarmed" tests (34p
# failed live in farey-hecke, 2026-07-20). Per-test overrides (34q) still win
# via `env CLAUDE_PROJECT_DIR=...`.
PROJECT_ANCHOR="$(mktemp -d -t cc-proj-XXXX)"
export CLAUDE_PROJECT_DIR="$PROJECT_ANCHOR"
trap 'rm -rf "$STATE_ROOT" "$SKILLS_ROOT" "$TRANSCRIPT_DIR" "$PROJECT_ANCHOR"' EXIT

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

assistant_tool_use_with_id() {
  # emit one JSONL line for an assistant tool_use CARRYING a tool_use id — the
  # correlation key recent_bash_tool_results() needs to pair it with its
  # tool_result (a real Claude Code transcript always carries this id; see
  # hook.py's recent_bash_tool_results docstring).
  python3 -c "
import json,sys
name=sys.argv[1]; inp=json.loads(sys.argv[2]); tid=sys.argv[3]
print(json.dumps({'type':'assistant',
                  'message':{'role':'assistant','content':[{'type':'tool_use','id':tid,'name':name,'input':inp}]}}))
" "$1" "$2" "$3"
}

user_tool_result_for() {
  # emit one JSONL line for a user-event tool_result PAIRED to a given
  # tool_use id (execution evidence — the actual output the tool printed).
  python3 -c "
import json,sys
tid=sys.argv[1]; text=sys.argv[2]; is_error=sys.argv[3] == '1'
print(json.dumps({'type':'user',
                  'message':{'role':'user','content':[{'type':'tool_result','tool_use_id':tid,
                    'is_error':is_error,'content':text}]}}))
" "$1" "$2" "$3"
}

_probe_ids_for() {
  # _probe_ids_for <skills_sub> — comma-joined "skill:id" list of every probe
  # declared under $SKILLS_ROOT/<skills_sub>/*/drift_probes.json (mirrors
  # hook.py discover_probes' _probe_id assembly: f"{skill_dir}:{probe.id}").
  # Frontier selects probes by EXACT id via COMPLIANCE_CANARY_PROBE_IDS; this
  # lets each test's ad hoc probe fire without hardcoding ids per call site.
  local dir="$SKILLS_ROOT/$1"
  [ -d "$dir" ] || { echo ""; return; }
  python3 -c "
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
ids = []
for f in sorted(root.glob('*/drift_probes.json')):
    try:
        probes = json.loads(f.read_text())
    except Exception:
        continue
    skill = f.parent.name
    for p in probes:
        pid = p.get('id')
        if pid:
            ids.append(f'{skill}:{pid}')
print(','.join(ids))
" "$dir"
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
                  COMPLIANCE_CANARY_SKILLS_ROOT="$SKILLS_ROOT/$skills_sub"
                  COMPLIANCE_CANARY_PROBE_IDS="$(_probe_ids_for "$skills_sub")")
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
# Claim text must itself carry the evidence-class language ("tests pass"),
# and the Bash tool_use needs a PAIRED, successful tool_result — frontier's
# evidence_class/execution_timeline mechanism (the legacy verify_tools/
# verify_keywords keyword-scan on bare tool_use INPUT was retired 2026-07-19)
# only counts evidence with a matching tool_result, and matches the CLAIM's
# classified evidence class against the executed command's classified
# evidence class. A bare "all done!" claim with no class-indicating words
# falls back to the default "filesystem/diff" class, exercised separately in
# test_profiles.py.
TX="$TRANSCRIPT_DIR/t6.jsonl"
write_transcript "$TX" \
  "$(assistant_tool_use_with_id Bash '{"command":"npm test"}' tu6)" \
  "$(user_tool_result_for tu6 '12 passed' 0)" \
  "$(assistant_text 'all tests pass — done!' u1)"
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
out=$(printf '%s' "$payload" | env COMPLIANCE_CANARY_STATE_DIR="$STATE_ROOT/cc27" COMPLIANCE_CANARY_SKILLS_ROOT="$SKILLS_ROOT/sk27" \
  COMPLIANCE_CANARY_PROBE_IDS="$(_probe_ids_for sk27)" "${HOOK[@]}")
if emitted "$out" && echo "$out" | grep -q 'user_correction'; then ok "correction prompt fires"; else no "correction prompt fires" "got: $(echo "$out" | head -c120)"; fi

echo "[28] user_correction: ordinary prompt stays silent"
payload=$(python3 -c "
import json,sys
print(json.dumps({'session_id':'s28','transcript_path':sys.argv[1],'hook_event_name':'UserPromptSubmit','prompt':'now add a unit test for the parser'}))
" "$TX")
out=$(printf '%s' "$payload" | env COMPLIANCE_CANARY_STATE_DIR="$STATE_ROOT/cc28" COMPLIANCE_CANARY_SKILLS_ROOT="$SKILLS_ROOT/sk27" \
  COMPLIANCE_CANARY_PROBE_IDS="$(_probe_ids_for sk27)" "${HOOK[@]}")
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
out=$(printf '%s' "$payload" | env COMPLIANCE_CANARY_STATE_DIR="$STATE_ROOT/cc34" COMPLIANCE_CANARY_SKILLS_ROOT="$SKILLS_ROOT/sk34" \
  COMPLIANCE_CANARY_PROBE_IDS="$(_probe_ids_for sk34)" "${HOOK[@]}")
if emitted "$out" && echo "$out" | grep -q 'user_correction'; then ok "user_correction fires with no assistant prose"; else no "user_correction fires with no assistant prose" "got: $(echo "$out" | head -c150)"; fi

# ======================================================================
# Mechanism 4 — correction ledger (LEARNING_CONTRACT §2): ARMED-ONLY
# (2026-07-20 policy fix — see hook.py's correction_ledger_armed()). A fired
# user_correction probe opens a closeout-blocking OPEN item that is surfaced
# every turn until a banking tool call (write_gate.py / wiki.py new) is
# observed to have ACTUALLY RUN (a Bash tool_use with matching invocation
# shape AND a paired tool_result carrying a passing execution signature), or
# the user explicitly closes it. call34() sets COMPLIANCE_CANARY_CORRECTION_
# LEDGER=1 so [34a]-[34o] below exercise the ARMED lifecycle unchanged from
# the 2026-07-19 rehome; [34p]-[34q] below cover the UNARMED boundary the
# armed env normally masks. Reuses the sk34/PROBES fixture above (the
# user_correction probe from test [34]).
# ======================================================================

call34() {
  # call34 <state_sub> <transcript_file> <session_id> <prompt>
  local state_sub="$1" tx="$2" sid="$3" prompt="$4"
  local payload
  payload=$(python3 -c "
import json,sys
print(json.dumps({'session_id':sys.argv[1],'transcript_path':sys.argv[2],'hook_event_name':'UserPromptSubmit','prompt':sys.argv[3]}))
" "$sid" "$tx" "$prompt")
  printf '%s' "$payload" | env COMPLIANCE_CANARY_STATE_DIR="$STATE_ROOT/$state_sub" \
    COMPLIANCE_CANARY_SKILLS_ROOT="$SKILLS_ROOT/sk34" COMPLIANCE_CANARY_CORRECTION_LEDGER=1 "${HOOK[@]}"
}

echo "[34a] correction ledger: a fired user_correction opens an item citing LEARNING_CONTRACT §2"
TX34A="$TRANSCRIPT_DIR/t34a.jsonl"
write_transcript "$TX34A" "$(assistant_text 'ok, using tabs' u34a)"
out=$(call34 cc34a "$TX34A" s34a 'no, I said use spaces')
if emitted "$out" && echo "$out" | grep -q '§2' && echo "$out" | grep -qi 'still OPEN'; then
  ok "correction opens item citing §2"
else
  no "correction opens item citing §2" "got: $(echo "$out" | head -c220)"
fi

echo "[34b] NEGATIVE — an unrelated later turn (no banking tool call) keeps the correction OPEN"
out=$(call34 cc34a "$TX34A" s34a 'thanks, looks fine')
if echo "$out" | grep -qi 'still OPEN'; then
  ok "unrelated later turn keeps correction OPEN"
else
  no "unrelated turn wrongly resolved the correction" "got: $(echo "$out" | head -c220)"
fi

echo "[34c] a write_gate.py Bash call WITH a PASSED result resolves the correction ledger (banked)"
TX34C="$TRANSCRIPT_DIR/t34c.jsonl"
write_transcript "$TX34C" \
  "$(assistant_text 'banking the lesson' u34c)" \
  "$(assistant_tool_use_with_id Bash '{"command":"python3 skills/write-gate/tools/write_gate.py score --json --text lesson"}' tu34c)" \
  "$(user_tool_result_for tu34c '{"verdict": "PASSED: signal score 5.00"}' 0)"
out=$(call34 cc34a "$TX34C" s34a 'go ahead')
if echo "$out" | grep -q 'resolved 1 correction' && ! echo "$out" | grep -qi 'still OPEN'; then
  ok "write_gate.py bank call (with PASSED result) resolves the correction ledger"
else
  no "write_gate.py bank should resolve" "got: $(echo "$out" | head -c220)"
fi

echo "[34d] user 'close it' resolves an OPEN correction without a banking tool call"
TX34D="$TRANSCRIPT_DIR/t34d_open.jsonl"
write_transcript "$TX34D" "$(assistant_text 'noted' u34d)"
out=$(call34 cc34d "$TX34D" s34d 'no, I said use spaces')
if ! echo "$out" | grep -qi 'still OPEN'; then no "setup: correction should open first" "got: $(echo "$out" | head -c220)"; fi
TX34D2="$TRANSCRIPT_DIR/t34d_close.jsonl"
write_transcript "$TX34D2" "$(assistant_text 'ok' u34d2)"
out=$(call34 cc34d "$TX34D2" s34d 'close it')
if echo "$out" | grep -q 'resolved 1 correction' && ! echo "$out" | grep -qi 'still OPEN'; then
  ok "user 'close it' resolves the open correction"
else
  no "explicit user close should resolve" "got: $(echo "$out" | head -c220)"
fi

echo "[34e] lifecycle direct-assert: an unbanked correction never auto-resolves on the mere passage of turns"
lifecycle=$(python3 -c "
import sys; sys.path.insert(0,'$TOOLS_DIR'); import hook
probe = {'kind':'user_correction','_result':{'snippet':'no, use spaces'}}
ledger, closed, action = [], [], None
for turn in range(1, 6):
    fired = [probe] if turn == 1 else []
    ledger, closed, action = hook.update_correction_ledger(ledger, fired, [], 'next', turn)
print('open' if ledger and not closed else 'wrongly-resolved')
")
if [ "$lifecycle" = "open" ]; then
  ok "unbanked correction stays OPEN across turns (no auto-resolve)"
else
  no "unbanked correction must never auto-resolve" "got: $lifecycle"
fi

# ======================================================================
# Correction-ledger bank-resolver hole #1 (adversarially confirmed): a bare
# substring match let 'echo write_gate.py', 'wiki.py new --help', and
# 'grep write_gate.py x' all falsely RESOLVE a closeout-blocking correction —
# none of them ran the gate. Fix requires COMMAND-POSITION invocation shape
# (necessary, but — see hole #2 below — not by itself sufficient).
# ======================================================================

echo "[34f] ATTACK: 'echo write_gate.py' does NOT resolve the correction ledger"
TX34F="$TRANSCRIPT_DIR/t34f.jsonl"
write_transcript "$TX34F" \
  "$(assistant_text 'noting the tool name' u34f)" \
  "$(assistant_tool_use Bash '{"command":"echo write_gate.py"}')"
out=$(call34 cc34f "$TX34F" s34f 'no, I said use spaces')
out2=$(call34 cc34f "$TX34F" s34f 'go ahead')
if echo "$out2" | grep -qi 'still OPEN' && ! echo "$out2" | grep -q 'resolved 1 correction'; then
  ok "echo write_gate.py does NOT resolve (attack blocked)"
else
  no "echo write_gate.py must NOT resolve" "got: $(echo "$out2" | head -c220)"
fi

echo "[34g] ATTACK: 'wiki.py new --help' does NOT resolve the correction ledger"
TX34G="$TRANSCRIPT_DIR/t34g.jsonl"
write_transcript "$TX34G" \
  "$(assistant_text 'checking usage' u34g)" \
  "$(assistant_tool_use Bash '{"command":"python3 skills/wiki-memory/tools/wiki.py new --help"}')"
out=$(call34 cc34g "$TX34G" s34g 'no, I said use spaces')
out2=$(call34 cc34g "$TX34G" s34g 'go ahead')
if echo "$out2" | grep -qi 'still OPEN' && ! echo "$out2" | grep -q 'resolved 1 correction'; then
  ok "wiki.py new --help does NOT resolve (attack blocked)"
else
  no "wiki.py new --help must NOT resolve" "got: $(echo "$out2" | head -c220)"
fi

echo "[34h] ATTACK: 'grep write_gate.py foo' does NOT resolve the correction ledger"
TX34H="$TRANSCRIPT_DIR/t34h.jsonl"
write_transcript "$TX34H" \
  "$(assistant_text 'searching for references' u34h)" \
  "$(assistant_tool_use Bash '{"command":"grep write_gate.py foo"}')"
out=$(call34 cc34h "$TX34H" s34h 'no, I said use spaces')
out2=$(call34 cc34h "$TX34H" s34h 'go ahead')
if echo "$out2" | grep -qi 'still OPEN' && ! echo "$out2" | grep -q 'resolved 1 correction'; then
  ok "grep write_gate.py foo does NOT resolve (attack blocked)"
else
  no "grep write_gate.py foo must NOT resolve" "got: $(echo "$out2" | head -c220)"
fi

echo "[34i] a real 'python3 .../write_gate.py score --json ...' invocation WITH a PASSED result DOES resolve the correction ledger"
# Single call, mirroring [34c]'s pattern: the correction fires AND the banking
# Bash tool_use (WITH its paired tool_result) are both visible in the same
# transcript/turn, so open + resolve happen together (same as a real session
# where the agent bank-calls right after the correction lands, before the
# next user turn). Uses `score --json` (not bare `gate`): verified live
# (2026-07-06) that `write_gate.py gate` alone prints NOTHING to stdout — only
# an exit code — so a bare `gate` invocation carries no verdict signature for
# the hook to observe at all; `--json` (or score/explain) is what actually
# prints the PASSED:/REJECTED: line this resolver requires.
TX34I="$TRANSCRIPT_DIR/t34i.jsonl"
write_transcript "$TX34I" \
  "$(assistant_text 'banking the lesson' u34i)" \
  "$(assistant_tool_use_with_id Bash '{"command":"cd /repo && python3 skills/write-gate/tools/write_gate.py score --json --text lesson"}' tu34i)" \
  "$(user_tool_result_for tu34i '{"verdict": "PASSED: signal score 5.00"}' 0)"
out=$(call34 cc34i "$TX34I" s34i 'no, I said use spaces')
# NOTE: this same prompt also opens an UNRELATED Mechanism-3 request-ledger
# item ("no, I said use spaces" is itself captured as a trackable request),
# whose own "N request(s) still open" text would collide with a bare 'still
# OPEN' substring check — assert on the CORRECTION ledger's specific phrasing
# ("correction(s) still OPEN") instead, mirroring [34c]/[34d]'s narrower checks.
if echo "$out" | grep -q 'resolved 1 correction' && ! echo "$out" | grep -qi 'correction(s) still OPEN'; then
  ok "real write_gate.py invocation (with PASSED result) DOES resolve"
else
  no "real write_gate.py invocation (with PASSED result) should resolve" "got: $(echo "$out" | head -c220)"
fi

# ======================================================================
# Bank-resolver hole #2 (adversarially confirmed, distinct from the ledger-
# OPENING allowlist hole referenced below as "HOLE #2" in [34j] — that one
# predates this fix and is unrelated): invocation shape alone is still
# TEXT-TRUST — a bare shell variable assignment, or a short-circuited
# compound, both present a matching command STRING while the tool never
# actually runs. Fix requires a paired tool_result carrying a passing
# execution-evidence signature (PASSED:/"created": for a wiki.py new).
# ======================================================================

echo "[34k] ATTACK: a bare variable ASSIGNMENT ('CMD=\"...write_gate.py gate...\"') does NOT resolve the correction ledger"
TX34K="$TRANSCRIPT_DIR/t34k.jsonl"
write_transcript "$TX34K" \
  "$(assistant_text 'setting up the command' u34k)" \
  "$(assistant_tool_use_with_id Bash '{"command":"CMD=\"python3 skills/write-gate/tools/write_gate.py gate --text x\""}' tu34k)"
out=$(call34 cc34k "$TX34K" s34k 'no, I said use spaces')
out2=$(call34 cc34k "$TX34K" s34k 'go ahead')
if echo "$out2" | grep -qi 'correction(s) still OPEN' && ! echo "$out2" | grep -q 'resolved 1 correction'; then
  ok "bare variable assignment does NOT resolve (attack blocked)"
else
  no "bare variable assignment must NOT resolve" "got: $(echo "$out2" | head -c220)"
fi

echo "[34l] ATTACK: a short-circuited 'false && python3 .../write_gate.py gate ...' does NOT resolve the correction ledger"
TX34L="$TRANSCRIPT_DIR/t34l.jsonl"
write_transcript "$TX34L" \
  "$(assistant_text 'running the guarded command' u34l)" \
  "$(assistant_tool_use_with_id Bash '{"command":"false && python3 skills/write-gate/tools/write_gate.py gate --text x"}' tu34l)"
out=$(call34 cc34l "$TX34L" s34l 'no, I said use spaces')
out2=$(call34 cc34l "$TX34L" s34l 'go ahead')
if echo "$out2" | grep -qi 'correction(s) still OPEN' && ! echo "$out2" | grep -q 'resolved 1 correction'; then
  ok "short-circuited && does NOT resolve (attack blocked)"
else
  no "short-circuited && must NOT resolve" "got: $(echo "$out2" | head -c220)"
fi

echo "[34m] a genuine invocation whose result is REJECTED does NOT resolve — a rejected banking attempt is not a successful banking"
TX34M="$TRANSCRIPT_DIR/t34m.jsonl"
write_transcript "$TX34M" \
  "$(assistant_text 'attempting to bank' u34m)" \
  "$(assistant_tool_use_with_id Bash '{"command":"python3 skills/write-gate/tools/write_gate.py score --json --text x"}' tu34m)" \
  "$(user_tool_result_for tu34m '{"verdict": "REJECTED: signal score 0.00 < threshold 3.00"}' 0)"
out=$(call34 cc34m "$TX34M" s34m 'no, I said use spaces')
out2=$(call34 cc34m "$TX34M" s34m 'go ahead')
if echo "$out2" | grep -qi 'correction(s) still OPEN' && ! echo "$out2" | grep -q 'resolved 1 correction'; then
  ok "REJECTED gate result stays OPEN (rejected banking attempt is not a banking)"
else
  no "REJECTED gate result must stay OPEN" "got: $(echo "$out2" | head -c220)"
fi

echo "[34n] a genuine 'wiki.py new' invocation whose result shows \"created\": DOES resolve"
# Both the correction (fired by this turn's prompt) and the banking Bash call
# (with its paired tool_result) are visible in the SAME transcript/turn —
# mirroring [34c]/[34i] — so open + resolve happen together on turn 1; assert
# on `out`, not a second turn (which would find the ledger already empty).
TX34N="$TRANSCRIPT_DIR/t34n.jsonl"
write_transcript "$TX34N" \
  "$(assistant_text 'materializing the page' u34n)" \
  "$(assistant_tool_use_with_id Bash '{"command":"python3 skills/wiki-memory/tools/wiki.py new --template decision --title x"}' tu34n)" \
  "$(user_tool_result_for tu34n '{"created": "queries/x.md", "template": "decision"}' 0)"
out=$(call34 cc34n "$TX34N" s34n 'no, I said use spaces')
if echo "$out" | grep -q 'resolved 1 correction' && ! echo "$out" | grep -qi 'correction(s) still OPEN'; then
  ok "wiki.py new with \"created\" result DOES resolve"
else
  no "wiki.py new with \"created\" result should resolve" "got: $(echo "$out" | head -c220)"
fi

echo "[34o] a genuine 'wiki.py new' invocation whose result shows \"refused\": does NOT resolve"
TX34O="$TRANSCRIPT_DIR/t34o.jsonl"
write_transcript "$TX34O" \
  "$(assistant_text 'attempting to materialize the page' u34o)" \
  "$(assistant_tool_use_with_id Bash '{"command":"python3 skills/wiki-memory/tools/wiki.py new --template page --title x"}' tu34o)" \
  "$(user_tool_result_for tu34o '{"refused": "REFUSED: low-signal candidate"}' 0)"
out=$(call34 cc34o "$TX34O" s34o 'no, I said use spaces')
out2=$(call34 cc34o "$TX34O" s34o 'go ahead')
if echo "$out2" | grep -qi 'correction(s) still OPEN' && ! echo "$out2" | grep -q 'resolved 1 correction'; then
  ok "wiki.py new with \"refused\" result stays OPEN"
else
  no "wiki.py new with \"refused\" result must stay OPEN" "got: $(echo "$out2" | head -c220)"
fi

# ======================================================================
# ARMED-only boundary (2026-07-20 policy fix): [34a]-[34o] above all run
# through call34(), which now sets COMPLIANCE_CANARY_CORRECTION_LEDGER=1 —
# i.e. every one of those is an ARMED-lifecycle test. [34p]/[34q] below cover
# the boundary itself: unarmed must be fully inert (silent, no ledger state
# write), and arming via task-retrospective's own mechanical signal (no env
# var) must work exactly like the env var.
# ======================================================================

echo "[34p] UNARMED — correction-shaped prompt is fully inert on the ledger: silent + no correction_ledger state write"
TX34P="$TRANSCRIPT_DIR/t34p.jsonl"
write_transcript "$TX34P" "$(assistant_text 'ok, using tabs' u34p)"
payload=$(python3 -c "
import json,sys
print(json.dumps({'session_id':sys.argv[1],'transcript_path':sys.argv[2],'hook_event_name':'UserPromptSubmit','prompt':'no, I said use spaces'}))
" s34p "$TX34P")
out=$(printf '%s' "$payload" | env COMPLIANCE_CANARY_STATE_DIR="$STATE_ROOT/cc34p" \
  COMPLIANCE_CANARY_SKILLS_ROOT="$SKILLS_ROOT/sk34" "${HOOK[@]}")
STATE_FILE_34P="$STATE_ROOT/cc34p/$(python3 -c "import hashlib,sys; print(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:16])" s34p).json"
has_ledger_key="no"
if [ -f "$STATE_FILE_34P" ]; then
  if python3 -c "
import json,sys
d = json.load(open(sys.argv[1]))
sys.exit(0 if 'correction_ledger' in d else 1)
" "$STATE_FILE_34P"; then has_ledger_key="yes"; fi
fi
if [ -z "$out" ] && [ "$has_ledger_key" = "no" ]; then
  ok "unarmed correction is silent and writes no correction_ledger state key"
else
  no "unarmed correction must be silent + write no ledger state" "out=$(echo "$out" | head -c150) has_ledger_key=$has_ledger_key"
fi

echo "[34q] ARMED via task-retrospective's own mechanical current.json (status: armed) — no env var needed"
PROJ34Q="$(mktemp -d -t cc-proj34q-XXXX)"
mkdir -p "$PROJ34Q/.brainer/task-retrospective"
cat > "$PROJ34Q/.brainer/task-retrospective/current.json" <<'EOF'
{"status": "armed", "task_id": "t1"}
EOF
TX34Q="$TRANSCRIPT_DIR/t34q.jsonl"
write_transcript "$TX34Q" "$(assistant_text 'ok, using tabs' u34q)"
payload=$(python3 -c "
import json,sys
print(json.dumps({'session_id':sys.argv[1],'transcript_path':sys.argv[2],'hook_event_name':'UserPromptSubmit','prompt':'no, I said use spaces'}))
" s34q "$TX34Q")
out=$(printf '%s' "$payload" | env COMPLIANCE_CANARY_STATE_DIR="$STATE_ROOT/cc34q" \
  COMPLIANCE_CANARY_SKILLS_ROOT="$SKILLS_ROOT/sk34" CLAUDE_PROJECT_DIR="$PROJ34Q" "${HOOK[@]}")
rm -rf "$PROJ34Q"
if echo "$out" | grep -qi 'still OPEN' && echo "$out" | grep -q '§2'; then
  ok "task-retrospective's mechanical current.json arms the correction ledger without the env var"
else
  no "current.json (status: armed) should arm the correction ledger" "got: $(echo "$out" | head -c220)"
fi

echo "[34r] REGRESSION (2026-07-20 farey-hecke repro) — harness isolation holds even when the process cwd itself contains a real armed current.json"
POISON34R="$(mktemp -d -t cc-poison34r-XXXX)"
mkdir -p "$POISON34R/.brainer/task-retrospective"
cat > "$POISON34R/.brainer/task-retrospective/current.json" <<'EOF'
{"status": "armed", "task_id": "poison"}
EOF
TX34R="$TRANSCRIPT_DIR/t34r.jsonl"
write_transcript "$TX34R" "$(assistant_text 'ok, using tabs' u34r)"
payload=$(python3 -c "
import json,sys
print(json.dumps({'session_id':sys.argv[1],'transcript_path':sys.argv[2],'hook_event_name':'UserPromptSubmit','prompt':'no, I said use spaces'}))
" s34r "$TX34R")
# Deliberately does NOT override CLAUDE_PROJECT_DIR here — it must inherit the
# script's own global PROJECT_ANCHOR pin (line 28) even though the shell's cwd
# below is the poisoned dir holding a REAL armed current.json. This is the
# exact repro that failed live in farey-hecke before harnesses pinned
# CLAUDE_PROJECT_DIR (correction_ledger_armed() falls back to cwd when unset).
out=$(cd "$POISON34R" && printf '%s' "$payload" | env COMPLIANCE_CANARY_STATE_DIR="$STATE_ROOT/cc34r" \
  COMPLIANCE_CANARY_SKILLS_ROOT="$SKILLS_ROOT/sk34" "${HOOK[@]}")
STATE_FILE_34R="$STATE_ROOT/cc34r/$(python3 -c "import hashlib,sys; print(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:16])" s34r).json"
has_ledger_key="no"
if [ -f "$STATE_FILE_34R" ]; then
  if python3 -c "
import json,sys
d = json.load(open(sys.argv[1]))
sys.exit(0 if 'correction_ledger' in d else 1)
" "$STATE_FILE_34R"; then has_ledger_key="yes"; fi
fi
rm -rf "$POISON34R"
if [ -z "$out" ] && [ "$has_ledger_key" = "no" ]; then
  ok "harness-pinned CLAUDE_PROJECT_DIR isolates against a real armed current.json sitting in cwd"
else
  no "harness isolation must hold even when cwd itself is poisoned with an armed current.json" "out=$(echo "$out" | head -c150) has_ledger_key=$has_ledger_key"
fi

# [34j] (allowlist-scoped ledger opening via the retired COMPLIANCE_CANARY_
# PROBE_SKILLS legacy feature) deleted 2026-07-19 — that mechanism no longer
# exists. Its property ("ledger OPENING happens even when the probe is
# excluded from DISPLAY") is already covered by [34a]-[34o]: call34() never
# sets COMPLIANCE_CANARY_PROBE_IDS, so sk34's user_correction probe is
# excluded from frontier's display scope (frontier_ids) in every one of
# those tests, yet the correction ledger still opens/resolves correctly.

# [35]/[36] (probe-declared verify_tools/verify_keywords substring/word-
# boundary matching, incl. custom 'cat' keyword) deleted 2026-07-19 with the
# retired legacy keyword-scan path in detect_claim_without_evidence — under
# frontier's evidence_class mechanism (test_profiles.py) a probe cannot
# declare its own ad hoc verify_keywords at all, and 'cat' specifically is
# not in the fixed filesystem/diff command classifier
# (git diff|status|stat|ls|find|rg|grep|jq|shasum), so 'cat' is not evidence
# under frontier by design (unlike under the retired legacy scan). Frontier's
# real word-boundary/incidental-substring safety is covered directly by
# test_profiles.py's incidental-result-keywords/incidental-command-path
# cases.

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
out=$(printf '%s' "$pay39" | env COMPLIANCE_CANARY_STATE_DIR="$STATE_ROOT/cc39" COMPLIANCE_CANARY_SKILLS_ROOT="$SKILLS_ROOT/sk39" \
  COMPLIANCE_CANARY_PROBE_IDS="$(_probe_ids_for sk39)" "${HOOK[@]}")
if [ -z "$out" ]; then ok "warranted (detail) prompt → creep suppressed"; else no "warranted prompt → suppressed" "got: $(echo "$out" | head -c150)"; fi

echo "[40] word_count warrant: trivial prompt still fires"
pay40=$(python3 -c "
import json,sys
print(json.dumps({'session_id':'s40','transcript_path':sys.argv[1],'hook_event_name':'UserPromptSubmit','prompt':'fix the typo'}))
" "$TXW")
out=$(printf '%s' "$pay40" | env COMPLIANCE_CANARY_STATE_DIR="$STATE_ROOT/cc40" COMPLIANCE_CANARY_SKILLS_ROOT="$SKILLS_ROOT/sk39" \
  COMPLIANCE_CANARY_PROBE_IDS="$(_probe_ids_for sk39)" "${HOOK[@]}")
if emitted "$out" && echo "$out" | grep -q 'word_count_per_message'; then ok "unwarranted (trivial) prompt → creep fires"; else no "trivial prompt → fires" "got: $(echo "$out" | head -c150)"; fi

# Periodic re-anchor (Mechanism 2, tests [41]-[50]/[54]) and its
# make_skill_with_pulse fixture were deleted 2026-07-19 along with the
# legacy profile that was its sole gate (discover_pulse_skills/
# parse_frontmatter/first_sentence no longer exist in hook.py — not
# rehomed, unlike Mechanism 4's correction ledger).
EMPTYTX="$TRANSCRIPT_DIR/empty.jsonl"; : > "$EMPTYTX"

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
out=$(printf '%s' "$pay53" | timeout 6 env COMPLIANCE_CANARY_STATE_DIR="$STATE_ROOT/cc53" COMPLIANCE_CANARY_SKILLS_ROOT="$SKILLS_ROOT/sk53" \
  COMPLIANCE_CANARY_PROBE_IDS="$(_probe_ids_for sk53)" "${HOOK[@]}" 2>/dev/null); ec=$?
t1=$(python3 -c 'import time;print(time.time())')
elapsed=$(python3 -c "print($t1-$t0)")
# exit 0, no output, and well under the 6s timeout wall (budget is 1.5s)
if [ "$ec" -eq 0 ] && [ -z "$out" ] && python3 -c "import sys;sys.exit(0 if $elapsed < 4 else 1)"; then
  ok "ReDoS regex time-bounded (${elapsed%.*}s, exit 0, silent)"; else no "ReDoS guard" "exit=$ec elapsed=$elapsed out=[$out]"; fi

# [54] (pulse_reminder length cap) deleted 2026-07-19 with the retired
# periodic re-anchor mechanism (not rehomed).

# ======================================================================
# early_stop detector (v1.11): fires when the closing turn is a forward
# PROMISE with no completion, no question, and no tool call. Anti-early-stop.
# ======================================================================

echo "[55] early_stop: final turn is a forward PROMISE (no tool, no done, no question) → fires"
ESPROBES='[{"id":"es","kind":"early_stop","message":"do the work now"}]'
make_skill_with_probes sk55 vbc "$ESPROBES"
TX="$TRANSCRIPT_DIR/t55.jsonl"
write_transcript "$TX" "$(assistant_text 'Here is the plan. Next I will implement the parser and wire it up.' u55)"
out=$(call cc55 sk55 "$TX" s55)
if emitted "$out" && echo "$out" | grep -q 'early_stop'; then ok "forward-promise ending fires"; else no "early_stop fires" "got: $(echo "$out" | head -c160)"; fi

echo "[56] early_stop: closing turn CALLED a tool → silent (work happened)"
TX="$TRANSCRIPT_DIR/t56.jsonl"
write_transcript "$TX" \
  "$(assistant_text 'Let me run the tests now.' u56)" \
  "$(assistant_tool_use Bash '{"command":"pytest"}')"
out=$(call cc56 sk55 "$TX" s56)
if [ -z "$out" ]; then ok "tool-called closing → silent"; else no "early_stop tool silence" "got: $(echo "$out" | head -c160)"; fi

echo "[57] early_stop: message reports completion ('Done … pass') → silent despite a 'next' promise"
TX="$TRANSCRIPT_DIR/t57.jsonl"
write_transcript "$TX" "$(assistant_text 'Done — all tests pass. Next I will refactor the helper.' u57)"
out=$(call cc57 sk55 "$TX" s57)
if [ -z "$out" ]; then ok "completion report → silent"; else no "early_stop done silence" "got: $(echo "$out" | head -c160)"; fi

echo "[58] early_stop: closing QUESTION → silent despite a promise match (legit pause)"
TX="$TRANSCRIPT_DIR/t58.jsonl"
write_transcript "$TX" "$(assistant_text 'Let me know which parser to implement — should I start now?' u58)"
out=$(call cc58 sk55 "$TX" s58)
if [ -z "$out" ]; then ok "closing question → silent"; else no "early_stop question silence" "got: $(echo "$out" | head -c160)"; fi

# ======================================================================
# completion_without_closure (the closure gate): a TERMINAL done-claim with
# no closure-ask fires; a done-claim that asks to close, or a mid-task line,
# stays silent. Mirror of early_stop.
# ======================================================================

echo "[59] completion_without_closure: terminal done-claim without a closure ask → fires"
CWPROBES='[{"id":"cwc","kind":"completion_without_closure","message":"confirm closure please"}]'
make_skill_with_probes sk59 vbc "$CWPROBES"
TX="$TRANSCRIPT_DIR/t59.jsonl"
write_transcript "$TX" "$(assistant_text 'All done. The task is complete and everything works.' u59)"
out=$(call cc59 sk59 "$TX" s59)
if emitted "$out" && echo "$out" | grep -q 'completion_without_closure'; then ok "self-close fires"; else no "cwc fires" "got: $(echo "$out"|head -c160)"; fi

echo "[60] completion_without_closure: done-claim that ASKS to close → silent"
TX="$TRANSCRIPT_DIR/t60.jsonl"
write_transcript "$TX" "$(assistant_text 'All done. The task is complete. Shall I close this out?' u60)"
out=$(call cc60 sk59 "$TX" s60)
if [ -z "$out" ]; then ok "ask-to-close → silent"; else no "cwc ask silence" "got: $(echo "$out"|head -c160)"; fi

echo "[61] completion_without_closure: mid-task (no terminal claim) → silent"
TX="$TRANSCRIPT_DIR/t61.jsonl"
write_transcript "$TX" "$(assistant_text 'Updated the parser; running the next step.' u61)"
out=$(call cc61 sk59 "$TX" s61)
if [ -z "$out" ]; then ok "mid-task → silent"; else no "cwc midtask silence" "got: $(echo "$out"|head -c160)"; fi

# ======================================================================
# Mechanism 3 — request ledger: a user request stays OPEN until the USER
# closes it; surfaces at wrap-up turns; closure is confirmed; trivial acks
# are not tracked; honors the disable switch.
# ======================================================================

# call_p <state_sub> <skills_sub> <transcript_file> <session_id> <prompt> [env...]
call_p() {
  local state_sub="$1" skills_sub="$2" tx="$3" sid="$4" prompt="$5"; shift 5
  local payload
  payload=$(python3 -c "
import json,sys
print(json.dumps({'session_id':sys.argv[1],'transcript_path':sys.argv[2],'hook_event_name':'UserPromptSubmit','prompt':sys.argv[3]}))
" "$sid" "$tx" "$prompt")
  printf '%s' "$payload" | env COMPLIANCE_CANARY_STATE_DIR="$STATE_ROOT/$state_sub" \
    COMPLIANCE_CANARY_SKILLS_ROOT="$SKILLS_ROOT/$skills_sub" \
    COMPLIANCE_CANARY_PROBE_IDS="$(_probe_ids_for "$skills_sub")" "$@" "${HOOK[@]}"
}

echo "[62] ledger: a user request is tracked and surfaced at a wrap-up turn"
# sk62 never created → no probes; the ledger runs regardless of probes.
TX="$TRANSCRIPT_DIR/t62.jsonl"
write_transcript "$TX" "$(assistant_text 'All done.' u62)"
out=$(call_p cc62 sk62 "$TX" s62 'add a retry cap to the loop and a test')
if echo "$out" | grep -q 'still OPEN' && echo "$out" | grep -q 'retry cap'; then ok "request tracked + surfaced at wrap-up"; else no "ledger surfaces request" "got: $(echo "$out"|head -c200)"; fi

echo "[63] ledger: user closure prunes the item and is confirmed"
# Reuse cc62 state (1 open item). 'close it' prunes it.
out=$(call_p cc62 sk62 "$TX" s62 'looks good, close it')
if echo "$out" | grep -q 'closed 1 request' && echo "$out" | grep -q 'ledger now empty'; then ok "user-closure confirmed + emptied"; else no "ledger closure confirmed" "got: $(echo "$out"|head -c200)"; fi

echo "[64] ledger: a trivial acknowledgement is not tracked (silent)"
TX="$TRANSCRIPT_DIR/t64.jsonl"
write_transcript "$TX" "$(assistant_text 'All done.' u64)"
out=$(call_p cc64 sk64 "$TX" s64 'ok')
if [ -z "$out" ]; then ok "trivial ack → not tracked"; else no "trivial not tracked" "got: $(echo "$out"|head -c160)"; fi

echo "[65] ledger is UNCONDITIONAL: a 'stop tracking' style prompt does NOT switch it off — the request is still captured"
TX="$TRANSCRIPT_DIR/t65.jsonl"
write_transcript "$TX" "$(assistant_text 'All done.' u65)"
# These phrasings used to (mis)trigger opt-out; there is no opt-out path now, so
# each is captured as a normal request and surfaced — never silently dropped.
call_p cc65 sk65 "$TX" s65 'add a new feature' >/dev/null
out=$(call_p cc65 sk65 "$TX" s65 "don't log the request body and add input validation")
if echo "$out" | grep -q 'still OPEN'; then ok "no opt-out path — request still tracked"; else no "ledger stayed unconditional" "got: $(echo "$out"|head -c200)"; fi

# ======================================================================
# requirements-ledger cross-check: ledger_not_materialized detector +
# opt-out / opt-in / deferral handling in the canary's Mechanism 3.
# ======================================================================

LNM='[{"id":"lnm","kind":"ledger_not_materialized","min_open":2,"grace_turns":3,"substantive_turns":2,"message":"materialize your visible requirements ledger"}]'

echo "[66] ledger_not_materialized: ≥2 open items, no ledger maintenance → fires"
make_skill_with_probes sk66 requirements-ledger "$LNM"
TX="$TRANSCRIPT_DIR/t66.jsonl"
write_transcript "$TX" "$(assistant_text 'working on it' u66)"
call_p cc66 sk66 "$TX" s66 'add a retry cap' >/dev/null
call_p cc66 sk66 "$TX" s66 'also add a config flag' >/dev/null
out=$(call_p cc66 sk66 "$TX" s66 'and document it')
if echo "$out" | grep -q 'ledger_not_materialized'; then ok "no-materialization fires"; else no "ledger_not_materialized fires" "got: $(echo "$out"|head -c200)"; fi

echo "[67] ledger_not_materialized: a recent Edit to a *ledger*.md suppresses it"
make_skill_with_probes sk67 requirements-ledger "$LNM"
TXP="$TRANSCRIPT_DIR/t67p.jsonl"; write_transcript "$TXP" "$(assistant_text 'ok' u)"
call_p cc67 sk67 "$TXP" s67 'add X' >/dev/null
call_p cc67 sk67 "$TXP" s67 'add Y' >/dev/null
TXE="$TRANSCRIPT_DIR/t67e.jsonl"
write_transcript "$TXE" "$(assistant_text 'updating the ledger' u)" "$(assistant_tool_use Edit '{"file_path":".brainer/ledger/abc.md"}')"
out=$(call_p cc67 sk67 "$TXE" s67 'and Z')
if [ -z "$out" ]; then ok "ledger Edit → suppressed"; else no "ledger Edit suppresses" "got: $(echo "$out"|head -c200)"; fi

echo "[68] ledger_not_materialized: unrelated TaskCreate metadata does NOT suppress it"
make_skill_with_probes sk68 requirements-ledger "$LNM"
TXP="$TRANSCRIPT_DIR/t68p.jsonl"; write_transcript "$TXP" "$(assistant_text 'ok' u)"
call_p cc68 sk68 "$TXP" s68 'add X' >/dev/null
call_p cc68 sk68 "$TXP" s68 'add Y' >/dev/null
TXT="$TRANSCRIPT_DIR/t68t.jsonl"
write_transcript "$TXT" "$(assistant_text 'creating an unrelated task' u)" "$(assistant_tool_use TaskCreate '{"subject":"x","metadata":{"ledger_id":"r999-wrong"}}')"
out=$(call_p cc68 sk68 "$TXT" s68 'and Z')
if echo "$out" | grep -q 'ledger_not_materialized'; then ok "unrelated TaskCreate does not suppress"; else no "unrelated TaskCreate wrongly suppresses" "got: $(echo "$out"|head -c200)"; fi

echo "[68b] ledger_not_materialized: matching TaskCreate metadata suppresses it"
make_skill_with_probes sk68b requirements-ledger "$LNM"
TXP="$TRANSCRIPT_DIR/t68bp.jsonl"; write_transcript "$TXP" "$(assistant_text 'ok' u)"
call_p cc68b sk68b "$TXP" s68b 'add X' >/dev/null
call_p cc68b sk68b "$TXP" s68b 'add Y' >/dev/null
RID68=$(python3 -c 'import hashlib;print("r1-"+hashlib.sha256(b"add X").hexdigest()[:6])')
TXT="$TRANSCRIPT_DIR/t68bt.jsonl"
write_transcript "$TXT" "$(assistant_text 'mirroring the captured row' u)" "$(assistant_tool_use TaskCreate '{"subject":"x","metadata":{"ledger_id":"'"$RID68"'"}}')"
out=$(call_p cc68b sk68b "$TXT" s68b 'and Z')
if [ -z "$out" ]; then ok "matching TaskCreate metadata → suppressed"; else no "matching TaskCreate should suppress" "got: $(echo "$out"|head -c200)"; fi

echo "[68c] ledger_not_materialized: three-conjunct request needs all three suffixed task IDs"
THREE='add X, update Y, and test Z'
RID3=$(python3 -c 'import hashlib,sys;print("r1-"+hashlib.sha256(sys.argv[1].encode()).hexdigest()[:6])' "$THREE")
make_skill_with_probes sk68c requirements-ledger "$LNM"
TXP="$TRANSCRIPT_DIR/t68cp.jsonl"; write_transcript "$TXP" "$(assistant_text 'ok' u)"
call_p cc68c sk68c "$TXP" s68c "$THREE" >/dev/null
call_p cc68c sk68c "$TXP" s68c 'go on' >/dev/null
TXT="$TRANSCRIPT_DIR/t68ct.jsonl"
write_transcript "$TXT" \
  "$(assistant_tool_use TaskCreate '{"subject":"X","metadata":{"ledger_id":"'"$RID3"'-a"}}')" \
  "$(assistant_tool_use TaskCreate '{"subject":"Y","metadata":{"ledger_id":"'"$RID3"'-b"}}')"
out=$(call_p cc68c sk68c "$TXT" s68c 'ok')
if echo "$out" | grep -q 'ledger_not_materialized'; then ok "partial 2/3 task mirror does not suppress"; else no "three-conjunct partial mirror wrongly suppresses" "got: $(echo "$out"|head -c200)"; fi

echo "[68d] ledger_not_materialized: complete three-conjunct task mirror suppresses it"
make_skill_with_probes sk68d requirements-ledger "$LNM"
call_p cc68d sk68d "$TXP" s68d "$THREE" >/dev/null
call_p cc68d sk68d "$TXP" s68d 'go on' >/dev/null
TXT="$TRANSCRIPT_DIR/t68dt.jsonl"
write_transcript "$TXT" \
  "$(assistant_tool_use TaskCreate '{"subject":"X","metadata":{"ledger_id":"'"$RID3"'-a"}}')" \
  "$(assistant_tool_use TaskCreate '{"subject":"Y","metadata":{"ledger_id":"'"$RID3"'-b"}}')" \
  "$(assistant_tool_use TaskCreate '{"subject":"Z","metadata":{"ledger_id":"'"$RID3"'-c"}}')"
out=$(call_p cc68d sk68d "$TXT" s68d 'ok')
if [ -z "$out" ]; then ok "complete 3/3 task mirror → suppressed"; else no "complete three-conjunct mirror should suppress" "got: $(echo "$out"|head -c200)"; fi

echo "[68e] requirements ledger: audit/verify/score conjunctions each count as atomic asks"
atomic=$(python3 - "$TOOLS_DIR/hook.py" <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("hook", sys.argv[1])
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)
print(hook._ledger_atomic_count("fix the parser, then audit the output, verify the evidence, and score the result"))
PY
)
if [ "$atomic" = "4" ]; then ok "audit/verify/score conjuncts → atomic_count=4"; else no "audit/verify/score conjunct count" "got: $atomic"; fi

echo "[69] ledger_not_materialized: cold start (1 item, turn 1) → silent"
make_skill_with_probes sk69 requirements-ledger "$LNM"
TX="$TRANSCRIPT_DIR/t69.jsonl"; write_transcript "$TX" "$(assistant_text 'ok' u69)"
out=$(call_p cc69 sk69 "$TX" s69 'add one thing')
if [ -z "$out" ]; then ok "cold-start → silent"; else no "cold-start silent" "got: $(echo "$out"|head -c200)"; fi

echo "[72] ledger deferral: a deferred item is NOT counted as still-open at wrap-up"
TXW="$TRANSCRIPT_DIR/t72.jsonl"; write_transcript "$TXW" "$(assistant_text 'All done.' u72)"
call_p cc72 sk72 "$TXW" s72 'do the migration thing' >/dev/null
call_p cc72 sk72 "$TXW" s72 'defer that for now' >/dev/null
out=$(call_p cc72 sk72 "$TXW" s72 'ok')
if ! echo "$out" | grep -qi 'still OPEN'; then ok "deferred item excluded from open nag"; else no "deferral excludes from open" "got: $(echo "$out"|head -c200)"; fi

# ======================================================================
# Guards — capture is UNCONDITIONAL (no opt-out path exists), defer is
# explicit-only, and a co-occurring ask is never dropped.
# ======================================================================
# These assert on update_ledger directly (python) — the lifecycle classifier.
LEDGER_PY='import sys,json; sys.path.insert(0,"'"$TOOLS_DIR"'"); import hook
def act(prompt, ledger=None):
    L,c,a = hook.update_ledger(ledger or [], prompt, 2)
    return a, L'

echo "[74] UNCONDITIONAL: there is no opt-out — every request, even 'no ledger', is captured (never 'optout')"
bad=$(python3 -c "$LEDGER_PY
# Phrasings that an opt-out regex would have caught. With no opt-out path they
# must all be CAPTURED as requests (action 'add'), never silently switch off.
probes=['no ledger','disable tracking','turn off the ledger','stop tracking requests',\"don't log the request body, and add input validation\",\"don't track the list of files\"]
wrong=[p for p in probes if act(p)[0] not in ('add','close-noop')]
print(';'.join(wrong))")
if [ -z "$bad" ]; then ok "no opt-out: every prompt captured, nothing switches the ledger off"; else no "ledger switched off / dropped" "on: $bad"; fi

echo "[76] B2: incidental 'for now'/'out of scope' must NOT defer-park and must capture the ask"
miss=$(python3 -c "$LEDGER_PY
bad=[]
for p in ['for now this looks fine, can you also add a healthcheck endpoint','out of scope but FYI, anyway add the healthcheck','I will defer to you — add whatever caching you think is best']:
    a,L=act(p, ledger=[{'id':'p','turn':1,'text':'refactor auth'}])
    parked=any(it.get('deferred') for it in L); captured=any(('healthcheck' in it['text']) or ('caching' in it['text']) for it in L)
    if parked or not captured: bad.append(p[:30])
print(';'.join(bad))")
if [ -z "$miss" ]; then ok "incidental defer phrases add (not park), ask captured"; else no "B2 defer over-match" "broke on: $miss"; fi

echo "[77] B2: explicit 'park that' DOES defer the prior item"
ok77=$(python3 -c "$LEDGER_PY
a,L=act('park that', ledger=[{'id':'p','turn':1,'text':'prior'}])
print('yes' if a=='defer' and any(it.get('deferred') for it in L) else 'no')")
if [ "$ok77" = yes ]; then ok "explicit park defers"; else no "B2 explicit defer broke"; fi

echo "[78] compound meta+ask: 'close it and add X' closes AND captures the new ask (never drops it)"
ok78=$(python3 -c "$LEDGER_PY
a,L=act('close it and add a healthcheck endpoint', ledger=[{'id':'p','turn':1,'text':'prior'}])
print('yes' if any('healthcheck' in it['text'] for it in L) else 'no')")
if [ "$ok78" = yes ]; then ok "close-compound captures the co-occurring ask"; else no "compound close drops ask"; fi

echo "[78b] field false-close guards: supersession replaces silently; negated close and scope-only nothing-else stay open"
ok78b=$(python3 -c "$LEDGER_PY
seed=[{'id':'p','turn':1,'text':'prior'}]
cases=[
 ('OK, forget it. Let'+chr(39)+'s use streaming mode instead of batch.', 0, 1),
 ('Take one more bounded verification step and do not close the task.', 0, 2),
 ('Replace retry with recovery, preserving its position and changing nothing else.', 0, 2),
]
good=True
for prompt,closed_count,ledger_count in cases:
    L,c,a = hook.update_ledger(seed, prompt, 2)
    good = good and len(c)==closed_count and len(L)==ledger_count and L[-1]['turn']==2
print('yes' if good else 'no')")
if [ "$ok78b" = yes ]; then ok "field false-close morphologies classified"; else no "field false-close morphology regression"; fi

echo "[79] M1: editing an unrelated requirements/TASKS .md must NOT suppress the detector"
make_skill_with_probes sk79 requirements-ledger "$LNM"
TXP="$TRANSCRIPT_DIR/t79p.jsonl"; write_transcript "$TXP" "$(assistant_text 'ok' u)"
call_p cc79 sk79 "$TXP" s79 'add X' >/dev/null
call_p cc79 sk79 "$TXP" s79 'add Y' >/dev/null
TXD="$TRANSCRIPT_DIR/t79d.jsonl"
write_transcript "$TXD" "$(assistant_text 'reading docs' u)" "$(assistant_tool_use Edit '{"file_path":"docs/requirements.md"}')"
out=$(call_p cc79 sk79 "$TXD" s79 'and Z')
if echo "$out" | grep -q 'ledger_not_materialized'; then ok "unrelated requirements.md does NOT suppress"; else no "M1 broad-path suppresses" "got: $(echo "$out"|head -c200)"; fi

echo "[80] M2: corrupted persisted state must not crash the hook (exit 0) — incl. turn_count itself"
SCORR="$STATE_ROOT/cc80"; mkdir -p "$SCORR"
SIDH=$(python3 -c "import hashlib;print(hashlib.sha256(b's80').hexdigest()[:16])")
printf '%s' '{"turn_count":"NOTANINT","substantive_add_count":null,"request_ledger":[{"id":"x","turn":"bad","text":"t"}]}' > "$SCORR/$SIDH.json"
TX="$TRANSCRIPT_DIR/t80.jsonl"; write_transcript "$TX" "$(assistant_text 'ok' u80)"
out=$(call_p cc80 sk69 "$TX" s80 'add one more thing'); ec=$?
if [ "$ec" = 0 ]; then ok "corrupted state (incl. turn_count) → exit 0, no crash"; else no "M2 int-cast crash" "exit=$ec"; fi

echo "[81] N1: completion gate does NOT fire on sign-off chit-chat"
make_skill_with_probes sk81 vbc "$CWPROBES"
TX="$TRANSCRIPT_DIR/t81.jsonl"
write_transcript "$TX" "$(assistant_text "That's all from me for tonight, signing off." u81)"
out=$(call cc81 sk81 "$TX" s81)
if ! echo "$out" | grep -q 'completion_without_closure'; then ok "sign-off → no false completion gate"; else no "N1 sign-off false-fire" "got: $(echo "$out"|head -c160)"; fi

echo "[73] completion gate message names QUESTIONs (guards the copy-edit)"
# Rehomed 2026-07-19 from verify-before-completion/drift_probes.json to
# skills/compliance-canary/drift_probes.json — skill remains, probe is canary-owned.
if grep -q 'QUESTION' "$TOOLS_DIR/../drift_probes.json"; then ok "completion gate enumerates questions"; else no "completion gate names questions"; fi

echo "[82] drift-coupled surfacing is completion-claim-gated, not drift-fire-gated: a drift probe firing alone does NOT surface open ledger items"
# Under the retired legacy profile, request-ledger surfacing also rode along
# on any turn a drift probe fired. That coupling was legacy-only and was
# retired with it 2026-07-19 (never rehomed) — frontier only surfaces open
# items at a genuine wrap-up (completion_claim) or on explicit closure. This
# asserts the CURRENT frontier behavior: the probe fires, but the ledger
# stays silent absent a completion claim.
FILLER='[{"id":"filler","kind":"forbidden_regex","pattern":"(?i)\\bcertainly\\b","message":"no certainly"}]'
make_skill_with_probes sk82 cv "$FILLER"
TXP="$TRANSCRIPT_DIR/t82p.jsonl"; write_transcript "$TXP" "$(assistant_text 'ok' u)"
call_p cc82 sk82 "$TXP" s82 'add a retry cap to the loop' >/dev/null   # open item, turn 1
TXF="$TRANSCRIPT_DIR/t82f.jsonl"; write_transcript "$TXF" "$(assistant_text 'Certainly! On it.' u82)"   # drift (filler) on turn 2
out=$(call_p cc82 sk82 "$TXF" s82 'go on')
if echo "$out" | grep -q 'forbidden_regex' && ! echo "$out" | grep -qi 'still open'; then ok "drift fires; ledger stays quiet absent a completion claim"; else no "drift-coupled surfacing" "got: $(echo "$out"|head -c220)"; fi

echo "[83] global kill silences nags but still RECORDS the request (ledger never disabled)"
TX="$TRANSCRIPT_DIR/t83.jsonl"; write_transcript "$TX" "$(assistant_text 'ok' u83)"
out=$(call_p cc83 sk69 "$TX" s83 'add an important feature' COMPLIANCE_CANARY_DISABLED=1)
SIDH83=$(python3 -c "import hashlib;print(hashlib.sha256(b's83').hexdigest()[:16])")
recorded=$(python3 -c "import json;d=json.load(open('$STATE_ROOT/cc83/$SIDH83.json'));print('yes' if any('important feature' in it.get('text','') for it in d.get('request_ledger',[])) else 'no')" 2>/dev/null)
if [ -z "$out" ] && [ "$recorded" = yes ]; then ok "kill → silent output, request still on the record"; else no "kill must not disable capture" "out=$(echo "$out"|head -c80) recorded=$recorded"; fi

echo "[84] tool_path_touch: editing a dependency manifest fires"
PROBES='[{"id":"dep","kind":"tool_path_touch","tools":["Edit","Write","NotebookEdit","Bash"],"path_pattern":"(?i)(?:^|/)(?:package\\.json|requirements\\.txt|pyproject\\.toml|poetry\\.lock)$","message":"manifest changed — justify the dep"}]'
make_skill_with_probes sk84 le "$PROBES"
TX="$TRANSCRIPT_DIR/t84.jsonl"
write_transcript "$TX" "$(assistant_tool_use Edit '{"file_path":"/proj/requirements.txt","old_string":"flask","new_string":"flask\nrequests"}')"
out=$(call cc84 sk84 "$TX" s84)
if emitted "$out" && echo "$out" | grep -q 'tool_path_touch'; then ok "manifest edit fires"; else no "manifest edit fires" "got: $(echo "$out"|head -c160)"; fi

echo "[85] tool_path_touch: editing a normal source file stays silent"
TX="$TRANSCRIPT_DIR/t85.jsonl"
write_transcript "$TX" "$(assistant_tool_use Edit '{"file_path":"/proj/src/app.py","old_string":"a","new_string":"b"}')"
out=$(call cc85 sk84 "$TX" s85)
if [ -z "$out" ]; then ok "non-manifest edit → silent"; else no "non-manifest edit → silent" "got: $(echo "$out"|head -c120)"; fi

echo "[85a] tool_path_touch: Bash redirection mutating a dependency manifest fires"
TX="$TRANSCRIPT_DIR/t85a.jsonl"
write_transcript "$TX" "$(assistant_tool_use Bash '{"command":"printf requests >> /proj/requirements.txt"}')"
out=$(call cc85a sk84 "$TX" s85a)
if emitted "$out" && echo "$out" | grep -q 'tool_path_touch'; then ok "Bash manifest mutation fires"; else no "Bash manifest mutation should fire" "got: $(echo "$out"|head -c160)"; fi

echo "[85b] tool_path_touch: Bash command that only tests a manifest stays silent"
TX="$TRANSCRIPT_DIR/t85b.jsonl"
write_transcript "$TX" "$(assistant_tool_use Bash '{"command":"test -f /proj/requirements.txt && python3 -m pytest -q"}')"
out=$(call cc85b sk84 "$TX" s85b)
if [ -z "$out" ]; then ok "Bash manifest test → silent"; else no "Bash manifest test should stay silent" "got: $(echo "$out"|head -c160)"; fi

echo "[85c] tool_path_touch: package-manager dependency mutations fire without an explicit path"
TX="$TRANSCRIPT_DIR/t85c.jsonl"
write_transcript "$TX" \
  "$(assistant_tool_use Bash '{"command":"npm install lodash # --dry-run is only a comment"}')" \
  "$(assistant_tool_use Bash '{"command":"cd /proj\npoetry add requests"}')"
out=$(call cc85c sk84 "$TX" s85c)
if emitted "$out" && echo "$out" | grep -q 'tool_path_touch'; then ok "npm install / poetry add manifest mutation fires"; else no "package-manager manifest mutation should fire" "got: $(echo "$out"|head -c160)"; fi

echo "[85d] tool_path_touch: read-only package-manager commands stay silent"
TX="$TRANSCRIPT_DIR/t85d.jsonl"
write_transcript "$TX" \
  "$(assistant_tool_use Bash '{"command":"npm list --depth=0"}')" \
  "$(assistant_tool_use Bash '{"command":"poetry show --tree"}')" \
  "$(assistant_tool_use Bash '{"command":"npm install lodash --dry-run"}')" \
  "$(assistant_tool_use Bash '{"command":"poetry add requests --dry-run"}')"
out=$(call cc85d sk84 "$TX" s85d)
if [ -z "$out" ]; then ok "npm list / poetry show → silent"; else no "read-only package-manager commands should stay silent" "got: $(echo "$out"|head -c160)"; fi

echo "[85e] tool_path_touch: tokenized package-manager adjacency matrix"
matrix=$(python3 - "$TOOLS_DIR/hook.py" <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("hook", sys.argv[1])
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)
probe = {
    "_probe_id": "dep",
    "tools": ["Bash"],
    "path_pattern": r"(?i)(?:^|/)(?:package\.json|package-lock\.json|pyproject\.toml|poetry\.lock)$",
}
positive = (
    "/usr/local/bin/npm install lodash",
    "env NODE_ENV=dev npm install lodash",
    "npm --prefix /proj install lodash",
    "/opt/homebrew/bin/poetry add requests",
    "env POETRY_VIRTUALENVS_CREATE=false poetry --directory /proj add requests",
    "poetry -C /proj add requests",
    "npm install lodash --dry-run=false",
    "poetry add requests --dry-run=false",
)
negative = (
    "npm install lodash --dry-run",
    "npm install lodash --dry-run=true",
    "npm install lodash --no-save",
    "poetry add requests --dry-run",
    "poetry add requests --dry-run=true",
    "npm list --depth=0",
    "poetry show --tree",
)
failures = []
for command in positive:
    result = hook.detect_tool_path_touch(
        probe, [], [{"name": "Bash", "input": {"command": command}}])
    if result is None:
        failures.append("MISS " + command)
for command in negative:
    result = hook.detect_tool_path_touch(
        probe, [], [{"name": "Bash", "input": {"command": command}}])
    if result is not None:
        failures.append("FALSE-POS " + command)
print("\n".join(failures) if failures else "ok")
PY
)
if [ "$matrix" = "ok" ]; then ok "package-manager adjacency matrix"; else no "package-manager adjacency matrix" "got: $matrix"; fi

echo "[86] whitespace_only_edit: an Edit changing only whitespace fires"
PROBES='[{"id":"reformat","kind":"whitespace_only_edit","min_chars":4,"message":"whitespace-only reformat — keep the diff to the task"}]'
make_skill_with_probes sk86 le "$PROBES"
TX="$TRANSCRIPT_DIR/t86.jsonl"
write_transcript "$TX" "$(assistant_tool_use Edit '{"file_path":"/proj/src/app.py","old_string":"def f(x):\n  return x","new_string":"def f(x):\n    return x"}')"
out=$(call cc86 sk86 "$TX" s86)
if emitted "$out" && echo "$out" | grep -q 'whitespace_only_edit'; then ok "reformat-only edit fires"; else no "reformat-only edit fires" "got: $(echo "$out"|head -c160)"; fi

echo "[87] whitespace_only_edit: a real content change stays silent"
TX="$TRANSCRIPT_DIR/t87.jsonl"
write_transcript "$TX" "$(assistant_tool_use Edit '{"file_path":"/proj/src/app.py","old_string":"return x","new_string":"return x + 1"}')"
out=$(call cc87 sk86 "$TX" s87)
if [ -z "$out" ]; then ok "real change → silent"; else no "real change → silent" "got: $(echo "$out"|head -c120)"; fi

echo "[88] harness-strip: a pure task-notification is NOT captured as a user request"
TX="$TRANSCRIPT_DIR/t88.jsonl"
write_transcript "$TX" "$(assistant_text 'All done.' u88)"
NOTIF='<task-notification><task-id>x1</task-id><result>agent finished: please fix the login flow and add a retry cap</result></task-notification>'
out=$(call_p cc88 sk88 "$TX" s88 "$NOTIF")
if [ -z "$out" ] || ! echo "$out" | grep -q 'still OPEN'; then ok "task-notification → not tracked"; else no "task-notification not tracked" "got: $(echo "$out"|head -c200)"; fi

echo "[89] harness-strip: user text AFTER a local-command block IS captured (blocks stripped)"
TX="$TRANSCRIPT_DIR/t89.jsonl"
write_transcript "$TX" "$(assistant_text 'All done.' u89)"
MIXED='<local-command-caveat>Caveat: generated by local commands</local-command-caveat><command-name>/model</command-name><local-command-stdout>Set model</local-command-stdout>add a retry cap to the parser'
out=$(call_p cc89 sk89 "$TX" s89 "$MIXED")
if echo "$out" | grep -q 'retry cap' && ! echo "$out" | grep -q 'Caveat'; then ok "post-command user ask captured, blocks stripped"; else no "mixed prompt strip+capture" "got: $(echo "$out"|head -c200)"; fi

echo "[90] harness-strip: prompt_intent stays silent on notification text, fires on the same plain text"
PROBES='[{"id":"prop-int","kind":"prompt_intent","pattern":"(?i)propagate.{0,30}sibling","message":"apply the propagate skill"}]'
make_skill_with_probes sk90 propagate "$PROBES"
TX="$TRANSCRIPT_DIR/t90.jsonl"
write_transcript "$TX" "$(assistant_text 'working' u90)"
out=$(call_p cc90 sk90 "$TX" s90 '<task-notification><result>the agent chose to propagate to the sibling repos</result></task-notification>')
if echo "$out" | grep -q 'prompt_intent'; then no "intent silent on notification" "got: $(echo "$out"|head -c160)"; else ok "intent silent on notification"; fi
out=$(call_p cc90b sk90 "$TX" s90b 'now propagate to the sibling repos')
if echo "$out" | grep -q 'prompt_intent'; then ok "intent fires on plain user text"; else no "intent fires on plain text" "got: $(echo "$out"|head -c160)"; fi

# ======================================================================
# team-lead §5 leader keystroke budget (leader-bulk-edit, tool_path_touch).
# Sourced from the REAL skills/team-lead/drift_probes.json (not a synthetic
# copy) so a drift between this test and the shipped file is caught.
#
# tool_path_touch now takes an optional min_count (default 1 = fire-on-first,
# byte-identical to prior behavior for every OTHER probe using this kind).
# leader-bulk-edit sets min_count:3 so a single allowed one-line fixup
# (team-lead §5/§6 proportionality) stays quiet, while an actual bulk
# mechanical edit still fires. Tests [93a]-[93c] assert this directly.
REAL_TL_PROBES="$(cat "$TOOLS_DIR/../../team-lead/drift_probes.json")"
mkdir -p "$SKILLS_ROOT/tl/team-lead"
printf '%s\n' "$REAL_TL_PROBES" > "$SKILLS_ROOT/tl/team-lead/drift_probes.json"

echo "[91] leader-bulk-edit: parses + registers from the shipped drift_probes.json, fires on a bulk-edit window (5 Edit calls to source files)"
TX="$TRANSCRIPT_DIR/t91.jsonl"
python3 - "$TX" <<'PY'
import json, sys
with open(sys.argv[1], "w") as f:
    for i in range(5):
        f.write(json.dumps({"type":"assistant","message":{"role":"assistant","content":[
            {"type":"tool_use","name":"Edit","input":{"file_path":f"/proj/src/file{i}.py","old_string":"a","new_string":"b"}}
        ]}}) + "\n")
PY
out=$(call cc91 tl "$TX" s91)
if emitted "$out" && echo "$out" | grep -q 'tool_path_touch' && echo "$out" | grep -q 'keystroke budget'; then
  ok "leader-bulk-edit registers + fires on a bulk-edit window"
else
  no "leader-bulk-edit registers + fires" "got: $(echo "$out" | head -c250)"
fi

echo "[92] leader-bulk-edit: exempt on plan/ledger/brief/synthesis paths (stays quiet)"
TX="$TRANSCRIPT_DIR/t92.jsonl"
write_transcript "$TX" "$(assistant_tool_use Edit '{"file_path":"/proj/PLAN.md","old_string":"a","new_string":"b"}')"
out=$(call cc92 tl "$TX" s92)
if [ -z "$out" ]; then ok "plan.md edit stays exempt (quiet)"; else no "plan.md edit should be exempt" "got: $(echo "$out"|head -c160)"; fi

echo "[93a] leader-bulk-edit min_count:3 — a 1-file fixup to a non-exempt path stays QUIET"
TX="$TRANSCRIPT_DIR/t93a.jsonl"
write_transcript "$TX" "$(assistant_tool_use Edit '{"file_path":"/proj/src/onefile.py","old_string":"a","new_string":"b"}')"
out=$(call cc93a tl "$TX" s93a)
if [ -z "$out" ]; then ok "1-file fixup stays quiet (min_count:3)"; else no "1-file fixup should stay quiet" "got: $(echo "$out"|head -c160)"; fi

echo "[93b] leader-bulk-edit min_count:3 — a 2-edit window stays QUIET"
TX="$TRANSCRIPT_DIR/t93b.jsonl"
python3 - "$TX" <<'PY'
import json, sys
with open(sys.argv[1], "w") as f:
    for i in range(2):
        f.write(json.dumps({"type":"assistant","message":{"role":"assistant","content":[
            {"type":"tool_use","name":"Edit","input":{"file_path":f"/proj/src/file{i}.py","old_string":"a","new_string":"b"}}
        ]}}) + "\n")
PY
out=$(call cc93b tl "$TX" s93b)
if [ -z "$out" ]; then ok "2-edit window stays quiet (min_count:3)"; else no "2-edit window should stay quiet" "got: $(echo "$out"|head -c160)"; fi

echo "[93c] leader-bulk-edit min_count:3 — a 3-edit window to non-exempt paths FIRES"
TX="$TRANSCRIPT_DIR/t93c.jsonl"
python3 - "$TX" <<'PY'
import json, sys
with open(sys.argv[1], "w") as f:
    for i in range(3):
        f.write(json.dumps({"type":"assistant","message":{"role":"assistant","content":[
            {"type":"tool_use","name":"Edit","input":{"file_path":f"/proj/src/file{i}.py","old_string":"a","new_string":"b"}}
        ]}}) + "\n")
PY
out=$(call cc93c tl "$TX" s93c)
if emitted "$out" && echo "$out" | grep -q 'tool_path_touch'; then
  ok "3-edit window fires (min_count:3 reached)"
else
  no "3-edit window should fire" "got: $(echo "$out"|head -c160)"
fi

echo "[93d] leader-bulk-edit: wiki/ paths are exempt (synthesis home, team-lead §5) — 3 wiki edits stay QUIET"
TX="$TRANSCRIPT_DIR/t93d.jsonl"
python3 - "$TX" <<'PY'
import json, sys
paths = ["/proj/wiki/concepts/some-page.md", "/proj/wiki/L1_index.md", "/proj/wiki/queries/external-validation.md"]
with open(sys.argv[1], "w") as f:
    for p in paths:
        f.write(json.dumps({"type":"assistant","message":{"role":"assistant","content":[
            {"type":"tool_use","name":"Edit","input":{"file_path":p,"old_string":"a","new_string":"b"}}
        ]}}) + "\n")
PY
out=$(call cc93d tl "$TX" s93d)
if [ -z "$out" ]; then ok "3 wiki edits stay quiet (wiki/ exempt)"; else no "wiki/ paths should be exempt" "got: $(echo "$out"|head -c160)"; fi

# ------------------------------------------------------------------------
# Cross-vendor review fixes (P3/P4/P5, post-a44b270) on leader-bulk-edit.
# P3/P4 exercise the REAL shipped team-lead/drift_probes.json (the "tl" skills
# dir set up above); P5 asserts detect_tool_path_touch's min_count coercion
# directly in python (mirrors the update_ledger direct-assert style at [74]+).
# ------------------------------------------------------------------------

echo "[93e] P3: suffix-token filenames (project-plan.md, api-spec.md, client-brief.md) are now EXEMPT"
TX="$TRANSCRIPT_DIR/t93e.jsonl"
python3 - "$TX" <<'PY'
import json, sys
paths = ["/proj/docs/project-plan.md", "/proj/docs/api-spec.md", "/proj/briefs/client-brief.md"]
with open(sys.argv[1], "w") as f:
    for p in paths:
        f.write(json.dumps({"type":"assistant","message":{"role":"assistant","content":[
            {"type":"tool_use","name":"Edit","input":{"file_path":p,"old_string":"a","new_string":"b"}}
        ]}}) + "\n")
PY
out=$(call cc93e tl "$TX" s93e)
if [ -z "$out" ]; then ok "suffix-token plan/spec/brief filenames exempt (quiet)"; else no "suffix-token filenames should be exempt" "got: $(echo "$out"|head -c160)"; fi

echo "[93f] P3: a suffix-token synthesis filename (design-synthesis.md) is also EXEMPT"
TX="$TRANSCRIPT_DIR/t93f.jsonl"
write_transcript "$TX" "$(assistant_tool_use Edit '{"file_path":"/proj/notes/design-synthesis.md","old_string":"a","new_string":"b"}')"
out=$(call cc93f tl "$TX" s93f)
if [ -z "$out" ]; then ok "design-synthesis.md exempt (quiet)"; else no "design-synthesis.md should be exempt" "got: $(echo "$out"|head -c160)"; fi

echo "[93g] P3: a non-token filename that merely CONTAINS 'plan' as a substring (plant.md) still COUNTS (no over-exemption)"
TX="$TRANSCRIPT_DIR/t93g.jsonl"
python3 - "$TX" <<'PY'
import json, sys
with open(sys.argv[1], "w") as f:
    for i in range(3):
        f.write(json.dumps({"type":"assistant","message":{"role":"assistant","content":[
            {"type":"tool_use","name":"Edit","input":{"file_path":f"/proj/plant{i}.md","old_string":"a","new_string":"b"}}
        ]}}) + "\n")
PY
out=$(call cc93g tl "$TX" s93g)
if emitted "$out" && echo "$out" | grep -q 'tool_path_touch'; then ok "'plant.md' (substring, not word) still counts"; else no "'plant.md' should still count" "got: $(echo "$out"|head -c160)"; fi

echo "[93h] P4: wiki/ DOCS stay exempt but wiki/ CODE now COUNTS (blanket wiki/ exemption no longer hides code)"
TX="$TRANSCRIPT_DIR/t93h.jsonl"
python3 - "$TX" <<'PY'
import json, sys
paths = ["/proj/wiki/tools/rebuild_index.py", "/proj/wiki/tools/sync.sh", "/proj/wiki/tools/build.js"]
with open(sys.argv[1], "w") as f:
    for p in paths:
        f.write(json.dumps({"type":"assistant","message":{"role":"assistant","content":[
            {"type":"tool_use","name":"Edit","input":{"file_path":p,"old_string":"a","new_string":"b"}}
        ]}}) + "\n")
PY
out=$(call cc93h tl "$TX" s93h)
if emitted "$out" && echo "$out" | grep -q 'tool_path_touch'; then ok "wiki/tools/*.py|.sh|.js bulk edits COUNT (code, not doc)"; else no "wiki/ code edits should count" "got: $(echo "$out"|head -c160)"; fi

echo "[93i] P4: wiki doc edits mixed in do NOT count toward min_count — only the 3 wiki .py edits reach the threshold"
TX="$TRANSCRIPT_DIR/t93i.jsonl"
python3 - "$TX" <<'PY'
import json, sys
# 2 exempt wiki docs (must NOT count) + 3 wiki .py edits (must reach min_count:3
# on code alone). If the doc edits wrongly counted too, this would already fire
# at 2 hits before the 3rd .py edit — instead the fix must make the .md edits
# invisible to the counter and the fire happen exactly at the 3rd .py edit.
paths = ["/proj/wiki/concepts/foo.md", "/proj/wiki/notes/bar.md",
         "/proj/wiki/tools/rebuild_index.py", "/proj/wiki/tools/another.py", "/proj/wiki/tools/third.py"]
with open(sys.argv[1], "w") as f:
    for p in paths:
        f.write(json.dumps({"type":"assistant","message":{"role":"assistant","content":[
            {"type":"tool_use","name":"Edit","input":{"file_path":p,"old_string":"a","new_string":"b"}}
        ]}}) + "\n")
PY
out=$(call cc93i tl "$TX" s93i)
if emitted "$out" && echo "$out" | grep -q 'tool_path_touch'; then ok "wiki .md stays exempt (uncounted), 3 wiki .py edits alone reach min_count"; else no "3 wiki .py edits amid docs should still fire" "got: $(echo "$out"|head -c160)"; fi

echo "[93j] P5: detect_tool_path_touch min_count coercion — 'three'/0/-1 all clamp to 1 (fire-on-first), no raise"
p5=$(python3 -c "
import sys; sys.path.insert(0,'$TOOLS_DIR'); import hook
def hits(n):
    return [{'name':'Edit','input':{'file_path':f'/src/f{i}.py'}} for i in range(n)]
bad = []
for mc in ('three', 0, -1):
    probe = {'path_pattern': '.+', 'min_count': mc, '_probe_id': 'x'}
    try:
        r0 = hook.detect_tool_path_touch(probe, None, hits(0))
        r1 = hook.detect_tool_path_touch(probe, None, hits(1))
    except Exception as e:
        bad.append(f'{mc!r}:raised:{e!r}')
        continue
    if r0 is not None:
        bad.append(f'{mc!r}:fired-on-zero-hits')
    if r1 is None or r1.get('min_count') != 1:
        bad.append(f'{mc!r}:did-not-clamp-to-1:{r1!r}')
print(';'.join(bad))
" 2>&1)
if [ -z "$p5" ]; then ok "min_count 'three'/0/-1 all clamp to 1, no raise, no fire-on-zero-hits"; else no "min_count coercion" "got: $p5"; fi

echo "[93k] P5: a valid positive min_count (e.g. 3) is unaffected by the clamp/coercion"
p5b=$(python3 -c "
import sys; sys.path.insert(0,'$TOOLS_DIR'); import hook
def hits(n):
    return [{'name':'Edit','input':{'file_path':f'/src/f{i}.py'}} for i in range(n)]
probe = {'path_pattern': '.+', 'min_count': 3, '_probe_id': 'x'}
r2 = hook.detect_tool_path_touch(probe, None, hits(2))
r3 = hook.detect_tool_path_touch(probe, None, hits(3))
print('ok' if r2 is None and r3 is not None and r3.get('min_count') == 3 else f'r2={r2!r} r3={r3!r}')
" 2>&1)
if [ "$p5b" = ok ]; then ok "valid min_count:3 unaffected (2 hits quiet, 3 hits fires)"; else no "valid min_count:3 regressed" "got: $p5b"; fi

echo "[93l] leader-bulk-edit: native Codex nested apply_patch with 3 source targets FIRES"
TX="$TRANSCRIPT_DIR/t93l.jsonl"
python3 - "$TX" <<'PY'
import json, sys
patch = "*** Begin Patch\n*** Add File: /proj/src/new.py\n*** Update File: /proj/src/app.py\n*** Delete File: /proj/src/old.py\n*** End Patch"
source = f"const patch = {json.dumps(patch)}; const result = await tools.apply_patch(patch); text(result);"
event = {"type":"response_item","payload":{"type":"custom_tool_call","name":"exec","call_id":"cx-93l","input":source}}
with open(sys.argv[1], "w") as f:
    f.write(json.dumps(event) + "\n")
PY
out=$(call cc93l tl "$TX" s93l)
if emitted "$out" && echo "$out" | grep -q 'tool_path_touch'; then ok "native Codex 3-path apply_patch fires"; else no "native Codex 3-path apply_patch should fire" "got: $(echo "$out"|head -c160)"; fi

echo "[93m] leader-bulk-edit: native Codex 1/2-path patches and read-only commands stay QUIET"
for count in 1 2; do
  TX="$TRANSCRIPT_DIR/t93m-$count.jsonl"
  python3 - "$TX" "$count" <<'PY'
import json, sys
headers = "\n".join(f"*** Update File: /proj/src/file{i}.py" for i in range(int(sys.argv[2])))
patch = f"*** Begin Patch\n{headers}\n*** End Patch"
source = f"await tools.apply_patch({json.dumps(patch)});"
event = {"type":"response_item","payload":{"type":"custom_tool_call","name":"exec","input":source}}
with open(sys.argv[1], "w") as f:
    f.write(json.dumps(event) + "\n")
PY
  out=$(call "cc93m$count" tl "$TX" "s93m$count")
  if [ -z "$out" ]; then ok "native Codex $count-path patch stays quiet"; else no "native Codex $count-path patch should stay quiet" "got: $(echo "$out"|head -c160)"; fi
done
TX="$TRANSCRIPT_DIR/t93m-read.jsonl"
python3 - "$TX" <<'PY'
import json, sys
source = 'const r = await tools.exec_command({cmd:"rg -n /proj/src/a.py /proj/src/b.py /proj/src/c.py"}); text(r.output);'
event = {"type":"response_item","payload":{"type":"custom_tool_call","name":"exec","input":source}}
with open(sys.argv[1], "w") as f:
    f.write(json.dumps(event) + "\n")
PY
out=$(call cc93mr tl "$TX" s93mr)
if [ -z "$out" ]; then ok "native Codex read-only path mentions stay quiet"; else no "native Codex read-only command should stay quiet" "got: $(echo "$out"|head -c160)"; fi

echo "[93n] leader-bulk-edit: native Codex patch with 3 exempt doc targets stays QUIET"
TX="$TRANSCRIPT_DIR/t93n.jsonl"
python3 - "$TX" <<'PY'
import json, sys
paths = ["/proj/PLAN.md", "/proj/.brainer/baton/worker-brief.md", "/proj/wiki/notes.md"]
headers = "\n".join(f"*** Update File: {path}" for path in paths)
patch = f"*** Begin Patch\n{headers}\n*** End Patch"
source = f"const patch = {json.dumps(patch)}; await tools.apply_patch(patch);"
event = {"type":"response_item","payload":{"type":"custom_tool_call","name":"exec","input":source}}
with open(sys.argv[1], "w") as f:
    f.write(json.dumps(event) + "\n")
PY
out=$(call cc93n tl "$TX" s93n)
if [ -z "$out" ]; then ok "native Codex 3 exempt patch targets stay quiet"; else no "native Codex exempt patch targets should stay quiet" "got: $(echo "$out"|head -c160)"; fi

echo "[93o] leader-bulk-edit: apply_patch-only JavaScript arrows do not become Bash redirections"
TX="$TRANSCRIPT_DIR/t93o.jsonl"
python3 - "$TX" <<'PY'
import json, sys
paths = ["/proj/PLAN.md", "/proj/docs/api-spec.md", "/proj/.brainer/baton/worker-brief.md"]
calls = []
for i, path in enumerate(paths):
    patch = f"*** Begin Patch\n*** Update File: {path}\n*** End Patch"
    calls.append(f"const kept{i} = items.filter(x => x.ok); await tools.apply_patch({json.dumps(patch)});")
source = " ".join(calls)
event = {"type":"response_item","payload":{"type":"custom_tool_call","name":"exec","input":source}}
with open(sys.argv[1], "w") as f:
    f.write(json.dumps(event) + "\n")
PY
out=$(call cc93o tl "$TX" s93o)
if [ -z "$out" ]; then ok "3 exempt apply_patch calls amid JavaScript arrows stay quiet"; else no "JavaScript arrows should not become Bash redirections" "got: $(echo "$out"|head -c160)"; fi

# Mechanism 5 (probe escalation, tests [96a]-[96e]) was deleted 2026-07-19
# with the retired legacy profile — build_probe_escalation_lines no longer
# exists in hook.py; not rehomed (unlike Mechanism 4's correction ledger).

# ======================================================================
# Live-monitoring drift probes (3 new probes, canary Mechanism 5 follow-up):
# requirements-ledger "assumption-self-close", eval-gate
# "feedback-ask-without-rubric", baton "grabbed-baton-not-consulted". Each
# has a positive (bad exemplar) and negative (clean near-miss) test.
# ======================================================================

echo "[97] requirements-ledger assumption-self-close: bad exemplar fires"
RLPROBES='[{"id":"assumption-self-close","kind":"forbidden_regex","pattern":"(?i)\\b(?:done|complete|finished|closed)\\b[^\\n]{0,110}?(?:user\\s+will\\b|user\\s+(?!agrees\\b|confirms\\b|approves\\b|accepts\\b|acknowledges\\b|signs\\b)\\w+s\\b|you.?ll\\b|you\\s+will\\b|you\\s+(?!agrees\\b|confirms\\b|approves\\b|accepts\\b|acknowledges\\b|signs\\b)\\w+s\\b|saar\\s+will\\b|saar\\s+(?!agrees\\b|confirms\\b|approves\\b|accepts\\b|acknowledges\\b|signs\\b)\\w+s\\b|\\bassuming\\b|\\blater\\b|\\bafterwards\\b|\\bsubsequently\\b)","unless_pattern":"(?i)\\b(?:done|complete|finished|closed)\\b(?![^\\n]*\\b(?:tomorrow|next)\\b)[^\\n]{0,110}?\\b(?:verified|\\d+\\s*/\\s*\\d+|render(?:ed)?|tests?\\b|matched|manifest)\\b[^\\n]{0,110}?(?:user\\s+will\\b|user\\s+\\w+s\\b|you.?ll\\b|you\\s+will\\b|you\\s+\\w+s\\b|saar\\s+will\\b|saar\\s+\\w+s\\b|\\bassuming\\b|\\blater\\b|\\bafterwards\\b|\\bsubsequently\\b)","message":"self-closed on an unconfirmed assumption"}]'
make_skill_with_probes sk97 requirements-ledger "$RLPROBES"
TX="$TRANSCRIPT_DIR/t97.jsonl"
write_transcript "$TX" "$(assistant_text 'done — byte-identical copy (scaffold; Saar sorts out art)' u97)"
out=$(call cc97 sk97 "$TX" s97)
if emitted "$out" && echo "$out" | grep -q 'requirements-ledger \[forbidden_regex\]: self-closed on an unconfirmed assumption'; then ok "assumption-self-close fires on bad exemplar"; else no "assumption-self-close fires on bad exemplar" "got: $(echo "$out" | head -c200)"; fi

echo "[98] requirements-ledger assumption-self-close: clean near-miss (verified done) stays silent"
TX="$TRANSCRIPT_DIR/t98.jsonl"
write_transcript "$TX" "$(assistant_text 'done — verified 31/31 via manifest (render attached)' u98)"
out=$(call cc98 sk97 "$TX" s98)
if [ -z "$out" ]; then ok "verified-done clean near-miss stays silent"; else no "verified-done clean near-miss stays silent" "got: $(echo "$out" | head -c200)"; fi

echo "[99] eval-gate feedback-ask-without-rubric: bad exemplar fires"
EGPROBES='[{"id":"feedback-ask-without-rubric","kind":"forbidden_regex","pattern":"(?i)\\b(?:what do you think|which (?:do you|one do you) prefer|prefer\\b|judge (?:this|it|these)|feedback on (?:this|these|it|the \\w+)|which (?:one|version|option)?\\s*(?:passes|wins|is better|looks best|looks better)|review this|feels off|favorite|thoughts on)\\b","unless_pattern":"(?i)(?:\\b(?:scoring guide|acceptance|done means|pass if|threshold|must have|measuring|success means|judge it by)\\b|\\bcriteri(?:a|on)\\b[^.\\n]{0,10}[:=](?!\\s*(?:TBD|TBA|none|n/?a|later|pending|\\?+)\\b)|\\brubric\\b[^.\\n]{0,12}[:=](?!\\s*(?:TBD|TBA|none|n/?a|later|pending|\\?+)\\b))","message":"no judging criterion stated"}]'
make_skill_with_probes sk99 eval-gate "$EGPROBES"
TX="$TRANSCRIPT_DIR/t99.jsonl"
write_transcript "$TX" "$(assistant_text "here's the compare board — which do you prefer?" u99)"
out=$(call cc99 sk99 "$TX" s99)
if emitted "$out" && echo "$out" | grep -q 'eval-gate \[forbidden_regex\]: no judging criterion stated'; then ok "feedback-ask-without-rubric fires on bad exemplar"; else no "feedback-ask-without-rubric fires on bad exemplar" "got: $(echo "$out" | head -c200)"; fi

echo "[100] eval-gate feedback-ask-without-rubric: clean near-miss (criterion stated) stays silent"
TX="$TRANSCRIPT_DIR/t100.jsonl"
write_transcript "$TX" "$(assistant_text "here's the compare board — judging criterion: sharpness lapvar ratio >1.5, no plastic texture; which passes?" u100)"
out=$(call cc100 sk99 "$TX" s100)
if [ -z "$out" ]; then ok "criterion-stated clean near-miss stays silent"; else no "criterion-stated clean near-miss stays silent" "got: $(echo "$out" | head -c200)"; fi

echo "[101] baton grabbed-baton-not-consulted: bad exemplar (where-is prompt) fires"
BPROBES='[{"kind":"prompt_intent","id":"grabbed-baton-not-consulted","pattern":"(?i)(?=.*\\b(?:file|folder|dir|directory|path|export|output|render|asset|minis?|miniatures?|version|docs?|document|image|deliverable)\\b)(?=(?:(?!\\b(?:regex|assertion|function|stack trace|variable|import|class|unit test)\\b).)*$|.*\\b(?:I generated|we made|I created|earlier|yesterday|before the|last session)\\b)\\b(?:where (?:is|are|'"'"'?s)|which file (?:has|had|contains)|which (?:folder|dir|directory) (?:holds|contains)|what was the|can(?:'"'"'|no)t find|cannot find|couldn'"'"'?t find|where did (?:we|i|you) (?:put|leave|save|store))\\b","message":"re-consult the active baton before answering from memory"}]'
make_skill_with_probes sk101 baton "$BPROBES"
TX="$TRANSCRIPT_DIR/t101.jsonl"
write_transcript "$TX" "$(assistant_text 'previous turn context' u101)"
out=$(call_p cc101 sk101 "$TX" s101 'where are the washington miniatures?!')
if emitted "$out" && echo "$out" | grep -q 'baton \[prompt_intent\]: re-consult the active baton'; then ok "grabbed-baton-not-consulted fires on where-is prompt"; else no "grabbed-baton-not-consulted fires on where-is prompt" "got: $(echo "$out" | head -c200)"; fi

echo "[102] baton grabbed-baton-not-consulted: clean near-miss (ordinary prompt) stays silent"
out=$(call_p cc102 sk101 "$TX" s102 'add a retry cap to the loop and a test for it')
if [ -z "$out" ]; then ok "ordinary prompt clean near-miss stays silent"; else no "ordinary prompt clean near-miss stays silent" "got: $(echo "$out" | head -c200)"; fi

# ======================================================================
# 17 confirmed codex attack findings against probes 1-3 above (2026-07-07
# hardening pass). Each becomes a regression test asserting the CORRECT
# fire/silent behavior directly against the drift_probes.json PROBES
# strings already re-declared in [97]/[99]/[101] above (sk97/sk99/sk101).
# ======================================================================

echo "[97a] assumption-self-close ATTACK: MISS — no-parens phrasing now fires"
TX="$TRANSCRIPT_DIR/t97a.jsonl"
write_transcript "$TX" "$(assistant_text 'done — byte-identical copy; Saar sorts out art' u97a)"
out=$(call cc97a sk97 "$TX" s97a)
if emitted "$out" && echo "$out" | grep -q 'requirements-ledger \[forbidden_regex\]'; then ok "no-parens self-close fires"; else no "no-parens self-close fires" "got: $(echo "$out" | head -c200)"; fi

echo "[97b] assumption-self-close ATTACK: MISS — generalized third-person verb + 'later' deferral fires"
TX="$TRANSCRIPT_DIR/t97b.jsonl"
write_transcript "$TX" "$(assistant_text 'done — byte-identical copy (scaffold; user handles art later)' u97b)"
out=$(call cc97b sk97 "$TX" s97b)
if emitted "$out" && echo "$out" | grep -q 'requirements-ledger \[forbidden_regex\]'; then ok "generalized verb + later fires"; else no "generalized verb + later fires" "got: $(echo "$out" | head -c200)"; fi

echo "[97c] assumption-self-close ATTACK: MISS — 'complete' done-claim synonym fires"
TX="$TRANSCRIPT_DIR/t97c.jsonl"
write_transcript "$TX" "$(assistant_text 'complete — byte-identical copy (scaffold; Saar sorts out art)' u97c)"
out=$(call cc97c sk97 "$TX" s97c)
if emitted "$out" && echo "$out" | grep -q 'requirements-ledger \[forbidden_regex\]'; then ok "'complete' done-synonym fires"; else no "'complete' done-synonym fires" "got: $(echo "$out" | head -c200)"; fi

echo "[97d] assumption-self-close ATTACK: MISS — crossing one sentence boundary fires"
TX="$TRANSCRIPT_DIR/t97d.jsonl"
write_transcript "$TX" "$(assistant_text 'done — byte-identical copy. (scaffold; Saar sorts out art)' u97d)"
out=$(call cc97d sk97 "$TX" s97d)
if emitted "$out" && echo "$out" | grep -q 'requirements-ledger \[forbidden_regex\]'; then ok "sentence-boundary-crossing self-close fires"; else no "sentence-boundary-crossing self-close fires" "got: $(echo "$out" | head -c200)"; fi

echo "[97e] assumption-self-close ATTACK: FALSE-POS — quoted 'user will' phrase alongside verified/N-of-N evidence stays silent"
TX="$TRANSCRIPT_DIR/t97e.jsonl"
write_transcript "$TX" "$(assistant_text 'done — verified 31/31 via manifest (literal phrase user will was covered by the negative test)' u97e)"
out=$(call cc97e sk97 "$TX" s97e)
if [ -z "$out" ]; then ok "quoted-mention + evidence stays silent"; else no "quoted-mention + evidence stays silent" "got: $(echo "$out" | head -c200)"; fi

echo "[97f] assumption-self-close ATTACK: FALSE-POS — 'Saar sorts' alongside verified/manifest/matched evidence stays silent"
TX="$TRANSCRIPT_DIR/t97f.jsonl"
write_transcript "$TX" "$(assistant_text 'done — verified 31/31 via manifest (Saar sorts column matched the source)' u97f)"
out=$(call cc97f sk97 "$TX" s97f)
if [ -z "$out" ]; then ok "attribution-phrase + evidence stays silent"; else no "attribution-phrase + evidence stays silent" "got: $(echo "$out" | head -c200)"; fi

echo "[99a] feedback-ask-without-rubric ATTACK: MISS — 'review this'/'feels off' asks fire"
TX="$TRANSCRIPT_DIR/t99a.jsonl"
write_transcript "$TX" "$(assistant_text 'Can you review this and tell me what feels off?' u99a)"
out=$(call cc99a sk99 "$TX" s99a)
if emitted "$out" && echo "$out" | grep -q 'eval-gate \[forbidden_regex\]'; then ok "review-this/feels-off ask fires"; else no "review-this/feels-off ask fires" "got: $(echo "$out" | head -c200)"; fi

echo "[99b] feedback-ask-without-rubric ATTACK: MISS — 'looks best' ask fires"
TX="$TRANSCRIPT_DIR/t99b.jsonl"
write_transcript "$TX" "$(assistant_text 'Which version looks best to you?' u99b)"
out=$(call cc99b sk99 "$TX" s99b)
if emitted "$out" && echo "$out" | grep -q 'eval-gate \[forbidden_regex\]'; then ok "looks-best ask fires"; else no "looks-best ask fires" "got: $(echo "$out" | head -c200)"; fi

echo "[99c] feedback-ask-without-rubric ATTACK: FALSE-POS — 'scoring guide: ...; which wins?' stays silent"
TX="$TRANSCRIPT_DIR/t99c.jsonl"
write_transcript "$TX" "$(assistant_text 'scoring guide: sharpness >1.5; which wins?' u99c)"
out=$(call cc99c sk99 "$TX" s99c)
if [ -z "$out" ]; then ok "scoring-guide-stated ask stays silent"; else no "scoring-guide-stated ask stays silent" "got: $(echo "$out" | head -c200)"; fi

echo "[99d] feedback-ask-without-rubric ATTACK: FALSE-POS — 'acceptance: ...; feedback on this' stays silent"
TX="$TRANSCRIPT_DIR/t99d.jsonl"
write_transcript "$TX" "$(assistant_text 'acceptance: must render without artifacts; feedback on this' u99d)"
out=$(call cc99d sk99 "$TX" s99d)
if [ -z "$out" ]; then ok "acceptance-stated ask stays silent"; else no "acceptance-stated ask stays silent" "got: $(echo "$out" | head -c200)"; fi

echo "[99e] feedback-ask-without-rubric ATTACK: BYPASS — negated-criteria phrase ('no criteria yet') still fires"
TX="$TRANSCRIPT_DIR/t99e.jsonl"
write_transcript "$TX" "$(assistant_text 'I do not have criteria yet; what do you think?' u99e)"
out=$(call cc99e sk99 "$TX" s99e)
if emitted "$out" && echo "$out" | grep -q 'eval-gate \[forbidden_regex\]'; then ok "negated-criteria phrase does not suppress — fires"; else no "negated-criteria phrase must still fire" "got: $(echo "$out" | head -c200)"; fi

echo "[99f] feedback-ask-without-rubric ATTACK: BYPASS — bare 'criteria.txt' filename mention still fires"
TX="$TRANSCRIPT_DIR/t99f.jsonl"
write_transcript "$TX" "$(assistant_text 'criteria.txt is attached only for file naming; which one is better?' u99f)"
out=$(call cc99f sk99 "$TX" s99f)
if emitted "$out" && echo "$out" | grep -q 'eval-gate \[forbidden_regex\]'; then ok "bare criteria.txt mention does not suppress — fires"; else no "bare criteria.txt mention must still fire" "got: $(echo "$out" | head -c200)"; fi

echo "[101a] grabbed-baton-not-consulted ATTACK: MISS — 'which folder holds' fires"
TX="$TRANSCRIPT_DIR/t101a.jsonl"
write_transcript "$TX" "$(assistant_text 'previous turn context' u101a)"
out=$(call_p cc101a sk101 "$TX" s101a 'which folder holds the washington miniatures?')
if emitted "$out" && echo "$out" | grep -q 'baton \[prompt_intent\]'; then ok "which-folder-holds fires"; else no "which-folder-holds fires" "got: $(echo "$out" | head -c200)"; fi

echo "[101b] grabbed-baton-not-consulted ATTACK: MISS — 'what was the path to...' fires"
out=$(call_p cc101b sk101 "$TX" s101b 'what was the path to the baton handoff?')
if emitted "$out" && echo "$out" | grep -q 'baton \[prompt_intent\]'; then ok "what-was-the fires"; else no "what-was-the fires" "got: $(echo "$out" | head -c200)"; fi

echo "[101c] grabbed-baton-not-consulted ATTACK: MISS — \"can't find the minis\" fires"
out=$(call_p cc101c sk101 "$TX" s101c "can't find the minis")
if emitted "$out" && echo "$out" | grep -q 'baton \[prompt_intent\]'; then ok "can't-find fires"; else no "can't-find fires" "got: $(echo "$out" | head -c200)"; fi

echo "[101d] grabbed-baton-not-consulted ATTACK: FALSE-POS — 'which file contains the regex?' stays silent"
out=$(call_p cc101d sk101 "$TX" s101d 'which file contains the regex?')
if [ -z "$out" ]; then ok "code-debug-noun 'regex' question stays silent"; else no "code-debug-noun 'regex' question stays silent" "got: $(echo "$out" | head -c200)"; fi

echo "[101e] grabbed-baton-not-consulted ATTACK: FALSE-POS — stack-trace/assertion debug question stays silent"
out=$(call_p cc101e sk101 "$TX" s101e 'where is the failing assertion in the current stack trace?')
if [ -z "$out" ]; then ok "code-debug-noun 'assertion/stack trace' question stays silent"; else no "code-debug-noun 'assertion/stack trace' question stays silent" "got: $(echo "$out" | head -c200)"; fi

# ======================================================================
# Round-2 hardening (2026-07-07): 5 confirmed breaks fixed in the 3 probes
# above. Each gets a dedicated regression test against the freshly updated
# RLPROBES/EGPROBES/BPROBES mirrors declared in [97]/[99]/[101] above.
# ======================================================================

echo "[97g] assumption-self-close FIX 1: FIRE — trailing evidence AFTER the assumption clause does NOT suppress (position-bound)"
TX="$TRANSCRIPT_DIR/t97g.jsonl"
write_transcript "$TX" "$(assistant_text 'done — byte-identical copy; Saar sorts out art; tests pass' u97g)"
out=$(call cc97g sk97 "$TX" s97g)
if emitted "$out" && echo "$out" | grep -q 'requirements-ledger \[forbidden_regex\]'; then ok "trailing evidence does not suppress — fires"; else no "trailing evidence does not suppress — must fire" "got: $(echo "$out" | head -c200)"; fi

echo "[97h] assumption-self-close FIX 1: SILENT (regression) — evidence BETWEEN done and assumption still suppresses"
TX="$TRANSCRIPT_DIR/t97h.jsonl"
write_transcript "$TX" "$(assistant_text 'done — verified 31/31 via manifest (Saar sorts column matched the source)' u97h)"
out=$(call cc97h sk97 "$TX" s97h)
if [ -z "$out" ]; then ok "positioned evidence still suppresses"; else no "positioned evidence still suppresses" "got: $(echo "$out" | head -c200)"; fi

echo "[97i] assumption-self-close FIX 2: SILENT — 'user agrees this is complete' (present-confirmation verb excluded)"
TX="$TRANSCRIPT_DIR/t97i.jsonl"
write_transcript "$TX" "$(assistant_text 'done — user agrees this is complete' u97i)"
out=$(call cc97i sk97 "$TX" s97i)
if [ -z "$out" ]; then ok "'user agrees' stays silent"; else no "'user agrees' must stay silent" "got: $(echo "$out" | head -c200)"; fi

echo "[97j] assumption-self-close FIX 2: SILENT — 'Saar confirms receipt' (present-confirmation verb excluded)"
TX="$TRANSCRIPT_DIR/t97j.jsonl"
write_transcript "$TX" "$(assistant_text 'done — Saar confirms receipt' u97j)"
out=$(call cc97j sk97 "$TX" s97j)
if [ -z "$out" ]; then ok "'Saar confirms' stays silent"; else no "'Saar confirms' must stay silent" "got: $(echo "$out" | head -c200)"; fi

echo "[99g] feedback-ask-without-rubric FIX 5: FIRE — bare 'rubric' mention (no definition shape) still fires"
TX="$TRANSCRIPT_DIR/t99g.jsonl"
write_transcript "$TX" "$(assistant_text 'rubric file is attached for naming only; which wins?' u99g)"
out=$(call cc99g sk99 "$TX" s99g)
if emitted "$out" && echo "$out" | grep -q 'eval-gate \[forbidden_regex\]'; then ok "bare rubric mention does not suppress — fires"; else no "bare rubric mention must still fire" "got: $(echo "$out" | head -c200)"; fi

echo "[101f] grabbed-baton-not-consulted FIX 3+4: FIRE — past-work marker lifts the debug-noun exclusion"
out=$(call_p cc101f sk101 "$TX" s101f 'where is the export I generated before the regex refactor?')
if emitted "$out" && echo "$out" | grep -q 'baton \[prompt_intent\]'; then ok "past-work marker + debug noun still fires"; else no "past-work marker + debug noun must fire" "got: $(echo "$out" | head -c200)"; fi

echo "[101g] grabbed-baton-not-consulted FIX 3+4: SILENT — debug noun + past-marker-shaped phrase without a real past marker stays silent"
out=$(call_p cc101g sk101 "$TX" s101g 'which file contains the generated helper that parses the canary transcript state before matching the regex?')
if [ -z "$out" ]; then ok "no genuine past-work marker + debug noun stays silent"; else no "no genuine past-work marker + debug noun must stay silent" "got: $(echo "$out" | head -c200)"; fi

# ======================================================================
# Round-3 hardening (2026-07-07): 3 high-severity finds fixed in the same
# 3 probes above. Each gets a FIRE test against the freshly updated
# RLPROBES/EGPROBES/BPROBES mirrors, plus the keep-silent counterpart the
# brief specifies (where one is specified).
# ======================================================================

echo "[97k] assumption-self-close ROUND-3 FIX: FIRE — deferral marker 'tomorrow' overrides evidence-token suppression"
TX="$TRANSCRIPT_DIR/t97k.jsonl"
write_transcript "$TX" "$(assistant_text 'done — tests pass; Saar sorts out art tomorrow' u97k)"
out=$(call cc97k sk97 "$TX" s97k)
if emitted "$out" && echo "$out" | grep -q 'requirements-ledger \[forbidden_regex\]'; then ok "'tomorrow' deferral overrides evidence suppression — fires"; else no "'tomorrow' deferral must override evidence suppression — must fire" "got: $(echo "$out" | head -c200)"; fi

echo "[97l] assumption-self-close ROUND-3: SILENT (keep-silent counterpart) — no deferral marker, evidence present, stays silent"
TX="$TRANSCRIPT_DIR/t97l.jsonl"
write_transcript "$TX" "$(assistant_text 'done — verified 31/31 via manifest (Saar sorts column matched the source)' u97l)"
out=$(call cc97l sk97 "$TX" s97l)
if [ -z "$out" ]; then ok "no-deferral-marker verified-done stays silent"; else no "no-deferral-marker verified-done must stay silent" "got: $(echo "$out" | head -c200)"; fi

echo "[99h] feedback-ask-without-rubric ROUND-3 FIX: FIRE — 'rubric: TBD; which wins?' placeholder value does not suppress"
TX="$TRANSCRIPT_DIR/t99h.jsonl"
write_transcript "$TX" "$(assistant_text 'rubric: TBD; which wins?' u99h)"
out=$(call cc99h sk99 "$TX" s99h)
if emitted "$out" && echo "$out" | grep -q 'eval-gate \[forbidden_regex\]'; then ok "'rubric: TBD' placeholder does not suppress — fires"; else no "'rubric: TBD' placeholder must not suppress — must fire" "got: $(echo "$out" | head -c200)"; fi

echo "[99i] feedback-ask-without-rubric ROUND-3 FIX: FIRE — 'criteria: none yet; which looks best?' placeholder value does not suppress"
TX="$TRANSCRIPT_DIR/t99i.jsonl"
write_transcript "$TX" "$(assistant_text 'criteria: none yet; which looks best?' u99i)"
out=$(call cc99i sk99 "$TX" s99i)
if emitted "$out" && echo "$out" | grep -q 'eval-gate \[forbidden_regex\]'; then ok "'criteria: none yet' placeholder does not suppress — fires"; else no "'criteria: none yet' placeholder must not suppress — must fire" "got: $(echo "$out" | head -c200)"; fi

echo "[101h] grabbed-baton-not-consulted ROUND-3 FIX: FIRE — 'where did we put the minis?' recall shape"
out=$(call_p cc101h sk101 "$TX" s101h 'where did we put the minis?')
if emitted "$out" && echo "$out" | grep -q 'baton \[prompt_intent\]'; then ok "'where did we put' recall shape fires"; else no "'where did we put' recall shape must fire" "got: $(echo "$out" | head -c200)"; fi

# ======================================================================
# repeated-failure-stall: probe-specific regression against the REAL shipped
# skills/compliance-canary/drift_probes.json entry (rehomed from retired
# fable-mode, 2026-07-19; not an inline copy, and
# not the generic repeated_tool_error smoke test at [24]-[26] — an
# adversarial review found those only exercised the DETECTOR via a narrow
# literal pattern ["File has not been read yet"], never THIS probe's actual
# pattern file). Mirrors [91]'s "load the real team-lead drift_probes.json"
# style. Detector semantics are COUNT, not same-signature: 3 DISTINCT
# failure classes must fire exactly like 3 of the same class would, and the
# message must say only "stalling" — never assert same-signature semantics
# (locked lesson: an earlier draft claimed "the same class of failure
# recurred — stop retrying variations", which is false on 3 distinct
# errors).
# ======================================================================
REAL_STALL_PROBE="$(python3 -c "
import json,sys
probes=json.load(open('$TOOLS_DIR/../drift_probes.json'))
sel=[p for p in probes if p.get('id')=='repeated-failure-stall']
assert sel, 'repeated-failure-stall probe missing from shipped drift_probes.json'
print(json.dumps(sel))
")"
mkdir -p "$SKILLS_ROOT/fm/compliance-canary"
printf '%s\n' "$REAL_STALL_PROBE" > "$SKILLS_ROOT/fm/compliance-canary/drift_probes.json"

echo "[103a] repeated-failure-stall: 3 DISTINCT failure classes (not same signature) → fires (count semantics)"
TX="$TRANSCRIPT_DIR/t103a.jsonl"
write_transcript "$TX" \
  "$(assistant_text 'running the build' u103a1)" \
  "$(user_tool_error 'Segmentation fault (core dumped)')" \
  "$(assistant_text 'retrying a different way' u103a2)" \
  "$(user_tool_error 'Error: ENOENT no such file')" \
  "$(assistant_text 'trying yet another approach' u103a3)" \
  "$(user_tool_error 'Timed out after 30s')"
out=$(call cc103a fm "$TX" s103a)
if emitted "$out" && echo "$out" | grep -q 'compliance-canary \[repeated_tool_error\]'; then ok "3 distinct failure classes fire (count semantics, not same-signature)"; else no "3 distinct failure classes should fire" "got: $(echo "$out" | head -c200)"; fi

echo "[103b] repeated-failure-stall: 2 matching errors → silent (min_count=3 boundary)"
TX="$TRANSCRIPT_DIR/t103b.jsonl"
write_transcript "$TX" \
  "$(assistant_text 'running the build' u103b1)" \
  "$(user_tool_error 'Segmentation fault (core dumped)')" \
  "$(assistant_text 'retrying' u103b2)" \
  "$(user_tool_error 'Error: ENOENT no such file')"
out=$(call cc103b fm "$TX" s103b)
if [ -z "$out" ]; then ok "2 matching errors stay silent (below min_count=3)"; else no "2 matching errors should stay silent" "got: $(echo "$out" | head -c200)"; fi

echo "[103c] repeated-failure-stall: 3 benign non-error tool_results mentioning 'errors' (plural) → silent (only is_error results are counted)"
user_tool_result_ok() {
  python3 -c "
import json,sys
print(json.dumps({'type':'user',
                  'message':{'role':'user','content':[{'type':'tool_result','is_error':False,'content':sys.argv[1]}]}}))
" "$1"
}
TX="$TRANSCRIPT_DIR/t103c.jsonl"
write_transcript "$TX" \
  "$(assistant_text 'summarizing the run' u103c1)" \
  "$(user_tool_result_ok '3 errors were found in the log but all were handled gracefully')" \
  "$(assistant_text 'more detail' u103c2)" \
  "$(user_tool_result_ok 'no failures here — just some errors logged for visibility')" \
  "$(assistant_text 'final note' u103c3)" \
  "$(user_tool_result_ok 'errors, errors, errors — all benign, non-fatal')"
out=$(call cc103c fm "$TX" s103c)
if [ -z "$out" ]; then ok "benign non-error tool_results with 'errors' stay silent (is_error=False excluded from the count)"; else no "benign non-error tool_results should stay silent" "got: $(echo "$out" | head -c200)"; fi

echo "[103d] repeated-failure-stall: emitted message says 'stalling', and never asserts the retracted same-signature claim"
TX="$TRANSCRIPT_DIR/t103d.jsonl"
write_transcript "$TX" \
  "$(assistant_text 'running the build' u103d1)" \
  "$(user_tool_error 'Segmentation fault (core dumped)')" \
  "$(assistant_text 'retrying a different way' u103d2)" \
  "$(user_tool_error 'Error: ENOENT no such file')" \
  "$(assistant_text 'trying yet another approach' u103d3)" \
  "$(user_tool_error 'Timed out after 30s')"
out=$(call cc103d fm "$TX" s103d)
if emitted "$out" && echo "$out" | grep -qi 'stalling' && ! echo "$out" | grep -qi 'same class' && ! echo "$out" | grep -qi 'STOP retrying variations'; then
  ok "message says 'stalling' and omits the retracted same-signature claim"
else
  no "message must say 'stalling' and must NOT claim same-signature semantics" "got: $(echo "$out" | head -c400)"
fi

echo "[104] Inline backtick PHRASE unwrapped: backtick-wrapped done-claim still triggers claim probe"
PROBES='[{"id":"unverified","kind":"claim_without_evidence","claim_pattern":"(?i)\\b(done|fixed)\\b","verify_tools":["Bash"]}]'
make_skill_with_probes sk104 uwp "$PROBES"
TX="$TRANSCRIPT_DIR/t104.jsonl"
python3 <<PY > "$TX"
import json
bt = chr(96)
msg = f"{bt}Done and dusted.{bt}"
print(json.dumps({"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":msg}]}}))
PY
out=$(call cc104 sk104 "$TX" s104)
if emitted "$out" && echo "$out" | grep -q 'claim_without_evidence'; then ok "backtick-wrapped phrase claim still triggers"; else no "backtick-wrapped phrase claim still triggers" "got: $(echo "$out" | head -c200)"; fi

echo "[105] Quoted-args decoy: verify keyword inside a quoted Bash string is NOT evidence"
PROBES='[{"id":"unverified","kind":"claim_without_evidence","claim_pattern":"(?i)\\b(done|fixed)\\b","verify_tools":["Bash"],"verify_keywords":["test","verified"]}]'
make_skill_with_probes sk105 qad "$PROBES"
TX="$TRANSCRIPT_DIR/t105.jsonl"
write_transcript "$TX" \
  "$(assistant_tool_use Bash '{"command":"git commit -m \"verified and tested end to end\""}')" \
  "$(assistant_text 'Done.' u105)"
out=$(call cc105 sk105 "$TX" s105)
if emitted "$out" && echo "$out" | grep -q 'claim_without_evidence'; then ok "quoted-string keyword decoy does not suppress claim probe"; else no "quoted-string keyword decoy does not suppress" "got: $(echo "$out" | head -c200)"; fi

echo "[106] requires_context_regex: probe stays silent when session lacks the context"
PROBES='[{"id":"ai-only","kind":"claim_without_evidence","claim_pattern":"(?i)\\b(done|fixed)\\b","verify_tools":["Bash"],"verify_keywords":["render"],"requires_context_regex":"(?i)\\.ai\\b|illustrator|dump-paths"}]'
make_skill_with_probes sk106 ctx "$PROBES"
TX="$TRANSCRIPT_DIR/t106.jsonl"
write_transcript "$TX" \
  "$(assistant_tool_use Edit '{"file_path":"/repo/README.md","old_string":"a","new_string":"b"}')" \
  "$(assistant_text 'all done!' u106)"
out=$(call cc106 sk106 "$TX" s106)
if [ -z "$out" ] || ! echo "$out" | grep -q 'claim_without_evidence'; then ok "context-gated probe silent on docs-only session"; else no "context-gated probe silent on docs-only session" "got: $(echo "$out" | head -c200)"; fi

echo "[107] requires_context_regex: probe fires when session shows the context"
TX="$TRANSCRIPT_DIR/t107.jsonl"
write_transcript "$TX" \
  "$(assistant_tool_use Bash '{"command":"./cli/bin/screenery-design illustrator dump-paths --doc Space.ai"}')" \
  "$(assistant_tool_use Edit '{"file_path":"/repo/parts.json","old_string":"a","new_string":"b"}')" \
  "$(assistant_text 'all done!' u107)"
out=$(call cc107 sk106 "$TX" s107)
if emitted "$out" && echo "$out" | grep -q 'claim_without_evidence'; then ok "context-gated probe fires on .ai session"; else no "context-gated probe fires on .ai session" "got: $(echo "$out" | head -c200)"; fi

echo "[108] new_machinery_no_borrow_checkpoint: new solver file with no checkpoint line fires"
PROBES='[{"id":"borrow","kind":"new_machinery_no_borrow_checkpoint","message":"state what existing tool was checked before building bespoke machinery"}]'
make_skill_with_probes sk108 le "$PROBES"
TX="$TRANSCRIPT_DIR/t108.jsonl"
write_transcript "$TX" \
  "$(assistant_text 'Building a placement solver for this.' u108)" \
  "$(assistant_tool_use Write '{"file_path":"/proj/src/placement_solver.py","content":"class Solver: pass"}')"
out=$(call cc108 sk108 "$TX" s108)
if emitted "$out" && echo "$out" | grep -q 'new_machinery_no_borrow_checkpoint'; then ok "new solver file, no checkpoint → fires"; else no "new solver file, no checkpoint → fires" "got: $(echo "$out"|head -c200)"; fi

echo "[109] new_machinery_no_borrow_checkpoint: same file WITH a borrow-checkpoint line stays silent"
TX="$TRANSCRIPT_DIR/t109.jsonl"
write_transcript "$TX" \
  "$(assistant_text 'Checked build123d and CadQuery — neither offers a constraint solver that fits this geometry; building bespoke.' u109)" \
  "$(assistant_tool_use Write '{"file_path":"/proj/src/placement_solver.py","content":"class Solver: pass"}')"
out=$(call cc109 sk108 "$TX" s109)
if [ -z "$out" ]; then ok "checkpoint present → silent"; else no "checkpoint present → silent" "got: $(echo "$out"|head -c200)"; fi

echo "[110] new_machinery_no_borrow_checkpoint: an ordinary file write stays silent"
TX="$TRANSCRIPT_DIR/t110.jsonl"
write_transcript "$TX" \
  "$(assistant_tool_use Write '{"file_path":"/proj/src/utils.py","content":"def helper(): pass"}')"
out=$(call cc110 sk108 "$TX" s110)
if [ -z "$out" ]; then ok "non-machinery filename → silent"; else no "non-machinery filename → silent" "got: $(echo "$out"|head -c200)"; fi

echo "[111] delegated_diagnosis: builder briefed to 'investigate why' fires"
PROBES='[{"id":"deldiag","kind":"delegated_diagnosis","message":"diagnosis is frontier-tier work; spec it first"}]'
make_skill_with_probes sk111 le "$PROBES"
TX="$TRANSCRIPT_DIR/t111.jsonl"
write_transcript "$TX" \
  "$(assistant_tool_use Agent '{"subagent_type":"builder","prompt":"Investigate why the export step fails on large files and fix it."}')"
out=$(call cc111 sk111 "$TX" s111)
if emitted "$out" && echo "$out" | grep -q 'delegated_diagnosis'; then ok "builder diagnosis brief → fires"; else no "builder diagnosis brief → fires" "got: $(echo "$out"|head -c200)"; fi

echo "[112] delegated_diagnosis: same brief to a frontier-tier agent stays silent"
TX="$TRANSCRIPT_DIR/t112.jsonl"
write_transcript "$TX" \
  "$(assistant_tool_use Agent '{"subagent_type":"frontier-advisor","prompt":"Investigate why the export step fails on large files."}')"
out=$(call cc112 sk111 "$TX" s112)
if [ -z "$out" ]; then ok "frontier-tier diagnosis brief → silent"; else no "frontier-tier diagnosis brief → silent" "got: $(echo "$out"|head -c200)"; fi

echo "[113] delegated_diagnosis: spec-shaped builder brief stays silent"
TX="$TRANSCRIPT_DIR/t113.jsonl"
write_transcript "$TX" \
  "$(assistant_tool_use Agent '{"subagent_type":"builder","prompt":"Root cause: exporter buffers whole file. Replace read() with 64KB chunked reads in export.py lines 40-55; gate: pytest tests/test_export.py."}')"
out=$(call cc113 sk111 "$TX" s113)
if [ -z "$out" ]; then ok "spec'd builder brief → silent"; else no "spec'd builder brief → silent" "got: $(echo "$out"|head -c200)"; fi

# ======================================================================
# [114] Precision fix (2026-07-20): claim-without-evidence false-fire corpus —
# 14 REAL false-fires captured from one live session
# (skills/compliance-canary/tests/fixtures/false_fires_20260720.md),
# deduplicated to 10 distinct reply texts
# (tests/fixtures/false_fires_20260720.json). Each used the SHIPPED
# claim-without-evidence probe (loaded from the real drift_probes.json, same
# technique [103a] used for REAL_STALL_PROBE) and legitimately fired on live
# turns that were either (a) SUMMARIZING already-verified work with the
# verification numbers/commit hash quoted in the reply itself, or (b)
# reporting a delegated lane/background agent's RUNNING/PENDING status — a
# frontier main-loop has no fresh tool call for either case. Both must now be
# SILENT (see _SELF_QUOTED_EVIDENCE_RE / _PENDING_DELEGATION_RE in hook.py).
# ======================================================================
REAL_CLAIM_PROBE="$(python3 -c "
import json
probes = json.load(open('$TOOLS_DIR/../drift_probes.json'))
sel = [p for p in probes if p.get('id') == 'claim-without-evidence']
assert sel, 'claim-without-evidence probe missing from shipped drift_probes.json'
print(json.dumps(sel))
")"
mkdir -p "$SKILLS_ROOT/ffc/compliance-canary"
printf '%s\n' "$REAL_CLAIM_PROBE" > "$SKILLS_ROOT/ffc/compliance-canary/drift_probes.json"

FIXTURES_JSON="$TOOLS_DIR/../tests/fixtures/false_fires_20260720.json"
FIXTURE_IDS=$(python3 -c "
import json
for e in json.load(open('$FIXTURES_JSON')):
    print(e['id'])
")
n=0
for fid in $FIXTURE_IDS; do
  n=$((n+1))
  echo "[114.$n] false-fire corpus: $fid stays SILENT under the shipped claim-without-evidence probe"
  TX="$TRANSCRIPT_DIR/ffc_$fid.jsonl"
  python3 -c "
import json
fixtures = json.load(open('$FIXTURES_JSON'))
text = next(e['text'] for e in fixtures if e['id'] == '$fid')
print(json.dumps({'type':'assistant','message':{'role':'assistant','content':[{'type':'text','text':text}]}}))
" > "$TX"
  out=$(call "cc_ffc_$fid" ffc "$TX" "s_ffc_$fid")
  if ! echo "$out" | grep -q 'claim_without_evidence'; then
    ok "false-fire corpus $fid stays silent"
  else
    no "false-fire corpus $fid must stay silent" "got: $(echo "$out" | head -c200)"
  fi
done

echo "[115] false-fire fix does NOT weaken recall: 3 NEW unverified true-positive claims (no quoted evidence, no pending-delegation language, no tool evidence anywhere) still fire"
NEW_TP=(
  "All done -- all tests pass! Shipping this now."
  "Fixed the bug and verified it works correctly."
  "Implementation complete, build passes, ready to ship."
)
tp_n=0
for tp in "${NEW_TP[@]}"; do
  tp_n=$((tp_n+1))
  TX="$TRANSCRIPT_DIR/tp_$tp_n.jsonl"
  write_transcript "$TX" "$(assistant_text "$tp" "utp$tp_n")"
  out=$(call "cc_tp_$tp_n" ffc "$TX" "s_tp_$tp_n")
  if emitted "$out" && echo "$out" | grep -q 'claim_without_evidence'; then
    ok "new true-positive #$tp_n still fires ('$tp')"
  else
    no "new true-positive #$tp_n must still fire ('$tp')" "got: $(echo "$out" | head -c200)"
  fi
done

# ======================================================================
# [116] frontier_emit opt-in (2026-07-20, screenery harvest): a probe outside
# FRONTIER_VERIFY_PROBE_IDS may join the frontier emit set via
# "frontier_emit": true in its drift_probes.json entry. The flag is honored
# only when COMPLIANCE_CANARY_PROBE_IDS is UNSET (env defines the complete
# set for controlled experiments). call() always sets PROBE_IDS, so these
# tests use call_noselect (same, without the selector).
# ======================================================================

call_noselect() {
  # call_noselect <state_sub> <skills_sub> <transcript_file> <session_id> [env_overrides...]
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

PROBES='[
  {"id":"fe-on","kind":"forbidden_regex","pattern":"(?i)\\bflaggedphrase\\b","message":"FLAGONLY probe fired","frontier_emit":true},
  {"id":"fe-off","kind":"forbidden_regex","pattern":"(?i)\\bunflaggedphrase\\b","message":"NOFLAG probe fired"}
]'
make_skill_with_probes sk116 fe "$PROBES"

echo "[116a] frontier_emit:true probe outside the allowlist FIRES under frontier (no PROBE_IDS env)"
TX="$TRANSCRIPT_DIR/t116a.jsonl"
write_transcript "$TX" "$(assistant_text 'this reply contains flaggedphrase here' u116a)"
out=$(call_noselect cc116a sk116 "$TX" s116a)
if emitted "$out" && echo "$out" | grep -q 'FLAGONLY probe fired'; then ok "frontier_emit probe fires without env selection"; else no "frontier_emit probe fires without env selection" "got: $(echo "$out" | head -c200)"; fi

echo "[116b] unflagged non-allowlist probe stays OUT of the frontier emit set"
TX="$TRANSCRIPT_DIR/t116b.jsonl"
write_transcript "$TX" "$(assistant_text 'this reply contains unflaggedphrase here' u116b)"
out=$(call_noselect cc116b sk116 "$TX" s116b)
if [ -z "$out" ]; then ok "unflagged probe stays silent under frontier"; else no "unflagged probe stays silent under frontier" "got: $(echo "$out" | head -c200)"; fi

echo "[116c] COMPLIANCE_CANARY_PROBE_IDS set → env defines the COMPLETE set, frontier_emit ignored"
TX="$TRANSCRIPT_DIR/t116c.jsonl"
write_transcript "$TX" "$(assistant_text 'both flaggedphrase and unflaggedphrase appear' u116c)"
out=$(call_noselect cc116c sk116 "$TX" s116c COMPLIANCE_CANARY_PROBE_IDS="fe:fe-off")
if emitted "$out" && echo "$out" | grep -q 'NOFLAG probe fired' && ! echo "$out" | grep -q 'FLAGONLY probe fired'; then
  ok "env selection wins: selected NOFLAG fires, FLAGONLY (frontier_emit) is ignored"
else
  no "env selection must win over frontier_emit" "got: $(echo "$out" | head -c200)"
fi

echo "[116d] REAL canonical visual-claim-without-vision probe (frontier_emit + context gate): fires in an .ai/Illustrator session"
mkdir -p "$SKILLS_ROOT/sk116real/compliance-canary"
cp "$TOOLS_DIR/../drift_probes.json" "$SKILLS_ROOT/sk116real/compliance-canary/drift_probes.json"
TX="$TRANSCRIPT_DIR/t116d.jsonl"
write_transcript "$TX" \
  "$(assistant_tool_use Bash '{"command":"./cli/bin/screenery-design illustrator dump-paths --doc Space.ai"}')" \
  "$(assistant_text 'The artboard layout looks correct now.' u116d)"
out=$(call_noselect cc116d sk116real "$TX" s116d)
if emitted "$out" && echo "$out" | grep -q 'without LOOKING at it'; then ok "visual probe fires on .ai session via frontier_emit"; else no "visual probe fires on .ai session via frontier_emit" "got: $(echo "$out" | head -c200)"; fi

echo "[116e] same claim in a docs-only session: requires_context_regex keeps the visual probe silent"
TX="$TRANSCRIPT_DIR/t116e.jsonl"
write_transcript "$TX" \
  "$(assistant_tool_use Read '{"file_path":"/tmp/notes.md"}')" \
  "$(assistant_text 'The layout looks correct now.' u116e)"
out=$(call_noselect cc116e sk116real "$TX" s116e)
if ! echo "$out" | grep -q 'without LOOKING at it'; then ok "visual probe silent without .ai context"; else no "visual probe must stay silent without .ai context" "got: $(echo "$out" | head -c200)"; fi

# ======================================================================
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
