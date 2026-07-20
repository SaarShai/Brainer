#!/usr/bin/env bash
# detached_lane.sh self-test — offline, no network, scratch-dir only.
#
# Case (a) is the load-bearing one: proves a lane launched through
# detached_lane.sh survives a SIGINT+SIGTERM+SIGHUP blast to the process
# group that launched it (the failure mode from the 2026-07-20 incident,
# af48da1c). The other cases cover the `status` verb's contract.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
DL="$HERE/detached_lane.sh"
TMP="$(mktemp -d -t dl-test-XXXX)"
trap 'rm -rf "$TMP"' EXIT
fail=0
chk() { if [ "$1" = "$2" ]; then echo "  ok: $3"; else echo "  FAIL: $3 (got rc=$1 want $2)"; fail=1; fi; }

echo "[detached_lane self-test]"

# --- (a) IMMUNITY: signal-blast the launcher's process group; lane must
# survive and complete. ------------------------------------------------
#
# A `&` background job in a non-interactive bash SHARES the parent shell's
# process group, so `kill -SIG -$$` from the test would also kill the test
# itself. To reproduce "harness cascades an interrupt to a lane launcher's
# group" without self-destructing, spawn the launching subshell via
# `python3 -c ... start_new_session=True` (the same setsid(2) mechanism
# detached_lane.sh itself uses): that subshell gets a NEW pgid, so blasting
# it is isolated from the test's own group. The launched lane process,
# once detached_lane.sh's own python3 layer runs, gets its OWN further
# setsid — that's the mechanism under test, not the harness plumbing here.
LANE_DIR="$TMP/immunity"
LAUNCH_PGID=$(python3 - "$DL" "$LANE_DIR" <<'PY'
import subprocess, sys
dl, lane_dir = sys.argv[1], sys.argv[2]
script = (
    f'"{dl}" launch --dir "{lane_dir}" --name immunity -- bash -c "sleep 4; echo OK" '
    f'>/dev/null 2>&1; sleep 10'
)
p = subprocess.Popen(
    ["bash", "-c", script],
    start_new_session=True,  # new pgid, isolated from this test's own group
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
print(p.pid)
PY
)
# Give the launcher subshell time to actually call `launch` before blasting.
sleep 1
kill -INT  -"$LAUNCH_PGID" 2>/dev/null
kill -TERM -"$LAUNCH_PGID" 2>/dev/null
kill -HUP  -"$LAUNCH_PGID" 2>/dev/null

# Poll for completion (lane sleeps 4s total; give it up to 8s).
elapsed=0
status_out=""
while [ "$elapsed" -lt 8 ]; do
  status_out="$(bash "$DL" status --dir "$LANE_DIR" --name immunity 2>/dev/null)"
  case "$status_out" in
    "done "*) break ;;
  esac
  sleep 0.5
  elapsed=$((elapsed + 1))
done
case "$status_out" in
  "done exit=0") chk 0 0 "immunity: lane survives signal-blast, status='$status_out'" ;;
  *) chk 1 0 "immunity: lane survives signal-blast, status='$status_out'" ;;
esac
grep -q "^OK$" "$LANE_DIR/immunity.log" 2>/dev/null
chk $? 0 "immunity: log contains OK"

# --- (b) status on a running lane ---------------------------------------
bash "$DL" launch --dir "$TMP" --name running -- bash -c "sleep 2" >/dev/null 2>&1
out=$(bash "$DL" status --dir "$TMP" --name running 2>&1); rc=$?
case "$out" in
  "running pid="*) chk "$rc" 0 "status: running lane -> 'running pid=N', exit 0" ;;
  *) chk 1 0 "status: running lane -> 'running pid=N' (got '$out')" ;;
esac

# --- (c) status after completion -----------------------------------------
bash "$DL" launch --dir "$TMP" --name done0 -- bash -c "exit 0" >/dev/null 2>&1
for _ in $(seq 1 20); do
  [ -f "$TMP/done0.done" ] && break
  sleep 0.2
done
out=$(bash "$DL" status --dir "$TMP" --name done0 2>&1); rc=$?
chk "$out" "done exit=0" "status: completed lane -> 'done exit=0'"
chk "$rc" 0 "status: completed lane exit code 0"

# --- (d) nonzero exit propagation -----------------------------------------
bash "$DL" launch --dir "$TMP" --name done7 -- bash -c "exit 7" >/dev/null 2>&1
for _ in $(seq 1 20); do
  [ -f "$TMP/done7.done" ] && break
  sleep 0.2
done
out=$(bash "$DL" status --dir "$TMP" --name done7 2>&1); rc=$?
chk "$out" "done exit=7" "status: nonzero exit propagates -> 'done exit=7'"
chk "$rc" 0 "status: nonzero-exit lane status call itself exits 0"

# --- (e) dead-no-marker ----------------------------------------------------
# Fabricate a pid file pointing at a pid that is (almost certainly) dead,
# with no .done marker.
DEADPID=99999
while kill -0 "$DEADPID" 2>/dev/null; do DEADPID=$((DEADPID - 1)); done
echo "$DEADPID" > "$TMP/deadmark.pid"
out=$(bash "$DL" status --dir "$TMP" --name deadmark 2>&1); rc=$?
chk "$rc" 1 "status: dead-no-marker -> exit 1"
case "$out" in
  "dead-no-marker"*) chk 0 0 "status: dead-no-marker output names the case" ;;
  *) chk 1 0 "status: dead-no-marker output names the case (got '$out')" ;;
esac

# --- (f) missing pid file ---------------------------------------------------
bash "$DL" status --dir "$TMP" --name never-launched >/dev/null 2>&1
chk "$?" 2 "status: missing pid file -> exit 2"

echo
[ "$fail" = "0" ] && echo "ALL PASS" || echo "FAILURES ABOVE"
exit "$fail"
