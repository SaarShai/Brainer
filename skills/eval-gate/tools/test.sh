#!/usr/bin/env bash
# eval-gate offline self-test — no model, no network (uses --stub-score).
# Exercises all three verbs and their exit-code gate semantics.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
EG=(python3 "$HERE/eval_gate.py")
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fail=0
chk() { if [ "$1" = "$2" ]; then echo "  ok: $3"; else echo "  FAIL: $3 (got rc=$1 want $2)"; fail=1; fi; }

echo "[eval-gate self-test]"

# score: stub 5 -> norm 1.0 >= 0.7 -> pass -> exit 0
printf 'hello' | "${EG[@]}" score --stub-score 5 >/dev/null 2>&1; chk $? 0 "score stub5 passes gate"
# score: stub 2 -> norm 0.4 < 0.7 -> fail -> exit 1
printf 'hello' | "${EG[@]}" score --stub-score 2 >/dev/null 2>&1; chk $? 1 "score stub2 fails gate (exit 1)"
# score: empty candidate -> usage error -> exit 2
printf '' | "${EG[@]}" score --stub-score 5 >/dev/null 2>&1; chk $? 2 "score empty candidate -> exit 2"

# add-case: thin reason rejected -> exit 1
printf 'bad reply' | "${EG[@]}" add-case --cases "$TMP/c.jsonl" --reason "bad" >/dev/null 2>&1; chk $? 1 "add-case rejects thin reason"
# add-case: reasonless (no why) rejected -> exit 1
printf 'bad reply' | "${EG[@]}" add-case --cases "$TMP/c.jsonl" --reason "this output is not great at all" >/dev/null 2>&1; chk $? 1 "add-case rejects reasonless"
# add-case: why-bearing reason accepted -> exit 0, appends one line
printf 'bad reply' | "${EG[@]}" add-case --cases "$TMP/c.jsonl" --task "sum the items" \
  --reason "wrong total because it hallucinated a line item" >/dev/null 2>&1; chk $? 0 "add-case accepts why-reason"
n=$(wc -l < "$TMP/c.jsonl" | tr -d ' '); chk "$n" 1 "add-case appended exactly one case"
# add-case: --force overrides the gate -> exit 0
printf 'bad reply' | "${EG[@]}" add-case --cases "$TMP/c.jsonl" --reason "x" --force >/dev/null 2>&1; chk $? 0 "add-case --force overrides gate"

# suite: all cases stub-pass -> exit 0
"${EG[@]}" suite --cases "$TMP/c.jsonl" --stub-score 5 >/dev/null 2>&1; chk $? 0 "suite all-pass -> exit 0"
# suite: a case below threshold -> exit 1
"${EG[@]}" suite --cases "$TMP/c.jsonl" --stub-score 1 >/dev/null 2>&1; chk $? 1 "suite below-threshold -> exit 1"
# suite: save then re-run with a drop -> regression -> exit 1
"${EG[@]}" suite --cases "$TMP/c.jsonl" --stub-score 5 --save-baseline "$TMP/base.json" >/dev/null 2>&1
chk $? 0 "suite save-baseline -> exit 0"
"${EG[@]}" suite --cases "$TMP/c.jsonl" --stub-score 3 --baseline "$TMP/base.json" >/dev/null 2>&1; chk $? 1 "suite mean-regression vs baseline -> exit 1"
# regression guard: an IDENTICAL re-run must NOT false-positive (float rounding)
"${EG[@]}" suite --cases "$TMP/c.jsonl" --stub-score 4 --save-baseline "$TMP/b4.json" >/dev/null 2>&1
"${EG[@]}" suite --cases "$TMP/c.jsonl" --stub-score 4 --baseline "$TMP/b4.json" >/dev/null 2>&1; chk $? 0 "suite identical re-run -> no false regression"

# multi-line / tabbed candidate round-trips add-case -> suite (JSONL integrity)
printf 'line one\nline two\twith tab\nline three' | "${EG[@]}" add-case --cases "$TMP/ml.jsonl" \
  --reason "missing the summary because it stops after three lines" >/dev/null 2>&1; chk $? 0 "add-case multi-line candidate accepted"
got=$("${EG[@]}" suite --cases "$TMP/ml.jsonl" --stub-score 5 2>/dev/null | python3 -c 'import json,sys;print(json.load(sys.stdin)["n"])')
chk "$got" 1 "suite reads multi-line candidate back (n=1)"

# corrupt cases file -> graceful exit 2 (no traceback) for both readers
printf '{not valid json}\n' > "$TMP/bad.jsonl"
"${EG[@]}" suite --cases "$TMP/bad.jsonl" --stub-score 5 >/dev/null 2>&1; chk $? 2 "suite corrupt cases -> exit 2"
# reason must PASS the gate so we reach (and fault on) the corrupt-file read, not bounce at the gate
"${EG[@]}" add-case --cases "$TMP/bad.jsonl" --text q --reason "wrong total because a line item was dropped" >/dev/null 2>&1; chk $? 2 "add-case onto corrupt cases -> exit 2"

# threshold boundary: stub 3 -> norm 0.6 ; >=0.6 passes, 0.61 fails
printf 'x' | "${EG[@]}" score --stub-score 3 --threshold 0.6 >/dev/null 2>&1; chk $? 0 "score norm==threshold passes (>=)"
printf 'x' | "${EG[@]}" score --stub-score 3 --threshold 0.61 >/dev/null 2>&1; chk $? 1 "score just under threshold fails"

# _parse_score robustness against real-model reply shapes (unit; no model)
pres=$(python3 - "$HERE" <<'PY'
import sys; sys.path.insert(0, sys.argv[1])
import eval_gate as e
cases = [("5", 5), ("5 - solid, ships as-is", 5), ("Score: 4\nminor verbosity", 4),
         ("**3**/5", 3), ("2/5 partial", 2), ("0\nblank", 0),
         ("I cannot rate this output", None), ("", None)]
bad = [f"{inp!r}=>{e._parse_score(inp)[0]}(want {w})" for inp, w in cases if e._parse_score(inp)[0] != w]
print("PARSE_OK" if not bad else "PARSE_FAIL " + "; ".join(bad))
PY
)
case "$pres" in PARSE_OK*) chk 0 0 "_parse_score handles 8 reply shapes";; *) echo "  FAIL: $pres"; fail=1;; esac

echo
[ "$fail" = "0" ] && echo "ALL PASS" || echo "FAILURES ABOVE"
exit $fail
