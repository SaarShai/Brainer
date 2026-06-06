#!/usr/bin/env bash
# session-recall self-test. Two checks, both runnable on a bare machine:
#
#   (1) no-raw-into-context guardrail — the load-bearing invariant. Run the
#       skeleton extractor on the LARGEST real session with --output; assert
#       its stdout (the only thing an orchestrator ever sees) is a single
#       _meta JSON line carrying zero transcript content, and that the bulk
#       went to a scratch file on disk. A 1-7MB transcript must collapse to a
#       sub-2KB constant-size status line regardless of input size.
#
#   (2) end-to-end smoke — discover -> metadata -> skeleton across THIS
#       machine's real Claude Code / Codex / Cursor sessions. Asserts >=1
#       session discovered, metadata pipeline returns files_processed>0, and a
#       non-empty skeleton lands in scratch.
#
# Exit 0 = pass (or SKIP when no local sessions exist for the repo/window).
# Exit 1 = a guardrail or smoke assertion failed.
#
# Usage: selftest.sh [repo-name] [days]   (defaults: token-economy 30)
# bash 3.2 compatible (macOS /bin/bash) — no mapfile, no associative arrays.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="${1:-token-economy}"
DAYS="${2:-30}"
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  [pass] %s\n' "$*"; }
bad() { FAIL=$((FAIL+1)); printf '  [FAIL] %s\n' "$*"; }

SCRATCH="$(mktemp -d -t session-recall-selftest-XXXXXX)"
trap 'rm -rf "$SCRATCH"' EXIT

printf '== discover (repo=%s days=%s) ==\n' "$REPO" "$DAYS"
FILES=()
while IFS= read -r f; do [ -n "$f" ] && FILES+=("$f"); done \
  < <(bash "$HERE/discover-sessions.sh" "$REPO" "$DAYS" 2>/dev/null)
printf '  discovered %s session file(s)\n' "${#FILES[@]}"

if [ "${#FILES[@]}" -eq 0 ]; then
  printf '  no sessions for repo=%s within %sd — guardrail needs a real file.\n' "$REPO" "$DAYS"
  printf 'RESULT: SKIP (no local sessions found; rerun with a different repo/days)\n'
  exit 0
fi

# metadata smoke — first 10 files, batch mode (null-delimited, ce hardening)
printf '== metadata pipeline ==\n'
META_TAIL="$(printf '%s\n' "${FILES[@]}" | head -10 | tr '\n' '\0' \
  | xargs -0 python3 "$HERE/extract-metadata.py" --cwd-filter "$REPO" 2>/dev/null | tail -1)"
if printf '%s' "$META_TAIL" | python3 -c 'import sys,json; m=json.loads(sys.stdin.read()); assert m.get("_meta") and m.get("files_processed",0)>0' 2>/dev/null; then
  ok "metadata _meta line reports files_processed>0"
else
  bad "metadata pipeline did not report files_processed>0 (tail=$META_TAIL)"
fi

# pick the largest file — worst case for the no-raw guardrail
BIG=""; BIGSZ=0
for f in "${FILES[@]}"; do
  sz=$(wc -c < "$f" 2>/dev/null || echo 0)
  if [ "$sz" -gt "$BIGSZ" ]; then BIGSZ=$sz; BIG="$f"; fi
done
printf '  largest session: %s (%s bytes)\n' "$BIG" "$BIGSZ"

printf '== guardrail: skeleton --output stdout is _meta-only ==\n'
OUT="$(python3 "$HERE/extract-skeleton.py" --output "$SCRATCH/g.skeleton.txt" < "$BIG")"
STDOUT_BYTES=$(printf '%s' "$OUT" | wc -c | tr -d ' ')
SCRATCH_BYTES=$(wc -c < "$SCRATCH/g.skeleton.txt" 2>/dev/null | tr -d ' ')

if printf '%s' "$OUT" | python3 -c '
import sys, json
out = sys.stdin.read()
lines = [l for l in out.splitlines() if l.strip()]
assert len(lines) == 1, f"stdout has {len(lines)} lines, expected exactly 1"
obj = json.loads(lines[0])
assert obj.get("_meta") is True and "wrote" in obj, "stdout is not a _meta status line"
for marker in ("[user]", "[assistant]", "[tool]", "[tools]"):
    assert marker not in out, f"transcript marker {marker!r} leaked into stdout"
'; then
  ok "stdout = single _meta line, no transcript content markers"
else
  bad "stdout guardrail (raw transcript content may have leaked to orchestrator)"
fi

if [ "$STDOUT_BYTES" -lt 2048 ]; then
  ok "stdout ${STDOUT_BYTES}B < 2048B (constant, input-size-independent)"
else
  bad "stdout ${STDOUT_BYTES}B >= 2048B — not constant-size"
fi

if [ "$SCRATCH_BYTES" -gt 0 ]; then
  ok "scratch skeleton ${SCRATCH_BYTES}B written (bulk stays on disk, off-context)"
else
  bad "scratch skeleton empty — extraction did not file-mediate"
fi

if [ "$STDOUT_BYTES" -gt 0 ]; then
  printf '  ratio: input %sB / stdout %sB = %sx kept out of orchestrator context\n' \
    "$BIGSZ" "$STDOUT_BYTES" "$((BIGSZ / STDOUT_BYTES))"
fi

printf 'RESULT: %s pass, %s fail\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
