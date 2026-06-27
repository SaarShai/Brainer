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

# --- per-criterion rubric mode (offline stub) ---
# weights 0.4/0.3/0.3, threshold 0.7: failing the required 'complete' leaves mean==0.7
# (would pass on the mean alone) — proving the required-block is what fails the gate.
CRIT='[{"id":"correct","weight":0.4,"required":true,"description":"factually correct"},{"id":"complete","weight":0.3,"required":true,"description":"answers every ask"},{"id":"concise","weight":0.3,"required":false,"description":"no filler"}]'
printf 'cand' | "${EG[@]}" score --criteria-json "$CRIT" --stub-criteria '{"correct":"pass","complete":"pass","concise":"pass"}' >/dev/null 2>&1; chk $? 0 "criteria all-pass -> exit 0"
printf 'cand' | "${EG[@]}" score --criteria-json "$CRIT" --stub-criteria '{"correct":"pass","complete":"fail","concise":"pass"}' >/dev/null 2>&1; chk $? 1 "criteria required-fail blocks even at mean==threshold (exit 1)"
printf 'cand' | "${EG[@]}" score --criteria-json "$CRIT" --stub-criteria '{"correct":"pass","complete":"pass","concise":"fail"}' >/dev/null 2>&1; chk $? 0 "criteria optional-fail still passes when mean>=threshold"
out=$(printf 'cand' | "${EG[@]}" score --criteria-json "$CRIT" --stub-criteria '{"correct":"fail","complete":"pass","concise":"pass"}' 2>/dev/null)
echo "$out" | python3 -c 'import json,sys;d=json.load(sys.stdin);assert d["verdict"]=="fail",d;assert d["blocking_criteria"]==["correct"],d;assert any(c["id"]=="correct" and not c["pass"] for c in d["criteria"]),d' >/dev/null 2>&1; chk $? 0 "criteria output names the failed/blocking criterion"
echo "$CRIT" > "$TMP/crit.json"
printf 'cand' | "${EG[@]}" score --criteria-file "$TMP/crit.json" --stub-criteria '{"correct":"pass","complete":"pass","concise":"pass"}' >/dev/null 2>&1; chk $? 0 "criteria from --criteria-file"
# --stub-criteria via bare path and @path (exercise the non-inline branches)
echo '{"correct":"pass","complete":"pass","concise":"pass"}' > "$TMP/stub.json"
printf 'cand' | "${EG[@]}" score --criteria-json "$CRIT" --stub-criteria "$TMP/stub.json" >/dev/null 2>&1; chk $? 0 "criteria --stub-criteria from bare path"
printf 'cand' | "${EG[@]}" score --criteria-json "$CRIT" --stub-criteria "@$TMP/stub.json" >/dev/null 2>&1; chk $? 0 "criteria --stub-criteria from @path"
printf 'cand' | "${EG[@]}" score --criteria-json "$CRIT" --stub-criteria '{"complete":"pass","concise":"pass"}' >/dev/null 2>&1; chk $? 1 "criteria missing verdict fail-safe -> exit 1"
printf 'cand' | "${EG[@]}" score --criteria-json '[{"id":"x"}]' --stub-criteria '{"x":"pass"}' >/dev/null 2>&1; chk $? 2 "criteria missing description -> exit 2"
printf 'cand' | "${EG[@]}" score --criteria-json '[{"id":"a","description":"y"},{"id":"a","description":"z"}]' --stub-criteria '{"a":"pass"}' >/dev/null 2>&1; chk $? 2 "criteria duplicate id -> exit 2"
printf 'cand' | "${EG[@]}" score --criteria-json '[]' >/dev/null 2>&1; chk $? 2 "criteria empty list -> exit 2"
printf 'cand' | "${EG[@]}" score --criteria-json '[{"id":"a","description":"y","weight":0}]' --stub-criteria '{"a":"pass"}' >/dev/null 2>&1; chk $? 2 "criteria weight<=0 -> exit 2"
# adversarial regression: sub-threshold true ratio must NOT round up into a pass (142/203=0.6995 < 0.7)
printf 'cand' | "${EG[@]}" score --criteria-json '[{"id":"a","weight":142,"required":false,"description":"x"},{"id":"b","weight":61,"required":false,"description":"y"}]' --stub-criteria '{"a":"pass","b":"fail"}' --threshold 0.7 >/dev/null 2>&1; chk $? 1 "criteria sub-threshold ratio not rounded up to pass"
# adversarial regression: exact-boundary float (0.4+0.3+0.3) must still PASS at threshold 0.7
printf 'cand' | "${EG[@]}" score --criteria-json "$CRIT" --stub-criteria '{"correct":"pass","complete":"pass","concise":"fail"}' --threshold 0.7 >/dev/null 2>&1; chk $? 0 "criteria exact-boundary ratio passes (epsilon, no float false-fail)"
# adversarial regression: non-finite (inf/nan) weight rejected -> exit 2 (no NaN-pass / invalid JSON)
printf 'cand' | "${EG[@]}" score --criteria-json '[{"id":"a","description":"d","weight":1e400}]' --stub-criteria '{"a":"pass"}' >/dev/null 2>&1; chk $? 2 "criteria non-finite weight -> exit 2"
# backward-compat: holistic score with NO criteria is unchanged (stub 5 passes)
printf 'x' | "${EG[@]}" score --stub-score 5 >/dev/null 2>&1; chk $? 0 "holistic path unchanged when no --criteria"
# suite with per-case inline stub_criteria
printf '%s\n' '{"id":"c1","candidate":"x","stub_criteria":{"correct":"pass","complete":"pass","concise":"pass"}}' '{"id":"c2","candidate":"y","stub_criteria":{"correct":"pass","complete":"pass","concise":"pass"}}' > "$TMP/crit_cases.jsonl"
"${EG[@]}" suite --cases "$TMP/crit_cases.jsonl" --criteria-json "$CRIT" >/dev/null 2>&1; chk $? 0 "suite criteria all-pass -> exit 0"
printf '%s\n' '{"id":"c1","candidate":"x","stub_criteria":{"correct":"fail","complete":"pass","concise":"pass"}}' > "$TMP/crit_fail.jsonl"
"${EG[@]}" suite --cases "$TMP/crit_fail.jsonl" --criteria-json "$CRIT" >/dev/null 2>&1; chk $? 1 "suite criteria required-fail case -> exit 1"
# _parse_criteria robustness (unit; no model)
pres2=$(python3 - "$HERE" <<'PY'
import sys; sys.path.insert(0, sys.argv[1])
import eval_gate as e
out = "correct: PASS - grounded\n- complete: FAIL — missed ask 3\n2. concise: yes, terse\nsafe: ✓ no issues"
v = e._parse_criteria(out, ["correct", "complete", "concise", "safe"])
ok = (v["correct"][0] is True and v["complete"][0] is False
      and v["concise"][0] is True and v["safe"][0] is True)
none_all_missing = e._parse_criteria("totally unrelated prose", ["a", "b"]) is None
partial = e._parse_criteria("correct: looks fine", ["correct"])  # present but tokenless
fs = partial["correct"][0] is False
# real-model regression: llama3.1 NUMBERS criteria instead of echoing ids -> must
# still parse positionally (this exact shape returned None before the fix).
pos = e._parse_criteria("1: FAIL — only two\n2: FAIL — no third\n3: PASS — terse", ["correct", "complete", "concise"])
pos_ok = pos["correct"][0] is False and pos["complete"][0] is False and pos["concise"][0] is True
# mixed: one id-echoed, one numbered, one id-echoed — all in order
mix = e._parse_criteria("correct: PASS ok\n2: FAIL nope\nconcise: PASS fine", ["correct", "complete", "concise"])
mix_ok = mix["correct"][0] is True and mix["complete"][0] is False and mix["concise"][0] is True
# cold-review MEDIUM: a prose preamble ('Yes, here goes:') must NOT steal a positional
# slot — the model's FAIL on the required 'safety' criterion must survive.
steal = e._parse_criteria("Yes, here goes:\nPASS\nPASS\nPASS\nFAIL unsafe", ["a", "b", "c", "safety"])
steal_ok = steal["safety"][0] is False
# count mismatch (a stray leading PASS-word) -> fail-safe, never a fabricated pass
mism = e._parse_criteria("PASS, details:\n1: FAIL\n2: PASS\n3: FAIL", ["a", "b", "c"])
mism_ok = all(mism[k][0] is False for k in ("a", "b", "c"))
# numeric-id cross-map fixed (prefix no longer eats leading digits)
numid = e._parse_criteria("12: PASS\n2: FAIL", ["2", "12"])
numid_ok = numid["2"][0] is False and numid["12"][0] is True
# id-keyed reason opening with a prose word before the real PASS reads PASS (no inversion)
inv = e._parse_criteria("correct: no major issues, PASS", ["correct"])
inv_ok = inv["correct"][0] is True
allok = ok and none_all_missing and fs and pos_ok and mix_ok and steal_ok and mism_ok and numid_ok and inv_ok
print("PARSE2_OK" if allok else f"PARSE2_FAIL pos={pos} mix={mix} steal={steal} mism={mism} numid={numid} inv={inv}")
PY
)
case "$pres2" in PARSE2_OK*) chk 0 0 "_parse_criteria handles bullets/tokens/fail-safe";; *) echo "  FAIL: $pres2"; fail=1;; esac

echo
[ "$fail" = "0" ] && echo "ALL PASS" || echo "FAILURES ABOVE"
exit $fail
