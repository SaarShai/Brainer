#!/usr/bin/env bash
# verify_artifact offline self-test — no model, no network.
# Covers: all-pass, missing-evidence-fails, vision-without-screenshot-fails.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
VA=(python3 "$HERE/verify_artifact.py")
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fail=0
chk() { if [ "$1" = "$2" ]; then echo "  ok: $3"; else echo "  FAIL: $3 (got rc=$1 want $2)"; fail=1; fi; }

echo "[verify_artifact self-test]"

# --- rubric fixtures -------------------------------------------------------
cat > "$TMP/rubric.md" <<'EOF'
# criterion-per-line rubric written AT TASK START
[evidence: 7 passed] all unit tests pass
[evidence: exit 0]   build is clean
EOF

cat > "$TMP/rubric_vision.md" <<'EOF'
[vision] chart renders without overlap
EOF

# --- 1. ALL-PASS: every criterion has a backing evidence line -> exit 0 ----
printf 'pytest: 7 passed in 0.3s\nbuild finished exit 0\n' \
  | "${VA[@]}" --rubric "$TMP/rubric.md" >/dev/null 2>&1
chk $? 0 "all criteria backed by evidence -> exit 0"

# --- 2. MISSING-EVIDENCE-FAILS: one criterion has no backing line -> exit 1
printf 'pytest: 7 passed in 0.3s\n' \
  | "${VA[@]}" --rubric "$TMP/rubric.md" >/dev/null 2>&1
chk $? 1 "criterion with no evidence line -> NOT-DONE -> exit 1"

# missing-evidence row is explicitly marked NO in the JSON (not silently passed)
got=$(printf 'pytest: 7 passed in 0.3s\n' \
  | "${VA[@]}" --rubric "$TMP/rubric.md" --json 2>/dev/null \
  | python3 -c 'import json,sys; r=json.load(sys.stdin); print(sum(1 for c in r["criteria"] if not c["done"]))')
chk "$got" 1 "exactly one criterion flagged NOT-DONE"

# --- 3. VISION-WITHOUT-SCREENSHOT-FAILS ------------------------------------
# text evidence mentions the criterion but NO screenshot/render reference -> fail
printf 'the chart renders without overlap, verified the data\n' \
  | "${VA[@]}" --rubric "$TMP/rubric_vision.md" >/dev/null 2>&1
chk $? 1 "vision criterion with text-only evidence -> exit 1"

# same criterion WITH a screenshot reference -> exit 0
printf 'the chart renders without overlap\nscreenshot saved to /tmp/chart.png\n' \
  | "${VA[@]}" --rubric "$TMP/rubric_vision.md" >/dev/null 2>&1
chk $? 0 "vision criterion WITH screenshot reference -> exit 0"

# --vision flag promotes a plain rubric to require visual evidence too
printf 'pytest: 7 passed in 0.3s\nbuild finished exit 0\n' \
  | "${VA[@]}" --rubric "$TMP/rubric.md" --vision >/dev/null 2>&1
chk $? 1 "--vision flag: text-only evidence on visual artifact -> exit 1"

# --- 4. [judge] criterion defers to eval_gate (reuse, not reimplement) -----
cat > "$TMP/rubric_judge.md" <<'EOF'
[judge] the summary reads coherently
EOF
# stub-score 5 -> norm 1.0 >= 0.7 -> done -> exit 0
printf 'some summary text under review\n' \
  | "${VA[@]}" --rubric "$TMP/rubric_judge.md" --stub-score 5 >/dev/null 2>&1
chk $? 0 "[judge] criterion via eval_gate stub5 -> exit 0"
# stub-score 2 -> norm 0.4 < 0.7 -> NOT done -> exit 1
printf 'some summary text under review\n' \
  | "${VA[@]}" --rubric "$TMP/rubric_judge.md" --stub-score 2 >/dev/null 2>&1
chk $? 1 "[judge] criterion via eval_gate stub2 -> exit 1"

# --- 5. empty rubric -> usage error exit 2 ---------------------------------
printf '# only comments\n' > "$TMP/empty.md"
printf 'x\n' | "${VA[@]}" --rubric "$TMP/empty.md" >/dev/null 2>&1
chk $? 2 "rubric with no criteria -> exit 2"

echo
[ "$fail" = "0" ] && echo "ALL PASS" || echo "FAILURES ABOVE"
exit $fail
