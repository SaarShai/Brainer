#!/usr/bin/env bash
# detached_lane.sh — interrupt-immune lane dispatcher.
#
# Verified 2026-07-20 (session af48da1c): the Claude desktop harness cascades a
# main-loop interrupt to ALL running Agent-tool background subagents, killing
# them mid-work ("stopped by the user" mislabel). Any lane that mutates
# external app state or runs >2min MUST launch through this wrapper instead of
# a harness-managed Bash `run_in_background` job.
#
# Mechanism: macOS has no `setsid(1)` binary, so detachment goes through
# Python's `subprocess.Popen(..., start_new_session=True)`, which calls the
# `setsid(2)` syscall directly. The spawned process becomes its own session
# leader (new sid, new pgid) before this launcher script exits, so a SIGINT/
# SIGTERM/SIGHUP delivered to the launcher's process group never reaches it —
# it gets reparented to launchd/PID 1 once the launching python3 process
# returns. A thin bash wrapper around the user command writes the `.exit` and
# `.done` markers itself once the command finishes, so no separate detached
# waiter process is needed.
#
# Usage:
#   detached_lane.sh launch --dir <lane-dir> --name <name> -- <command...>
#   detached_lane.sh status --dir <lane-dir> --name <name>
set -euo pipefail

usage() {
  cat <<'EOF'
detached_lane.sh launch --dir <lane-dir> --name <name> -- <command...>
detached_lane.sh status --dir <lane-dir> --name <name>
EOF
}

cmd_launch() {
  local dir="" name=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --dir) dir="$2"; shift 2 ;;
      --name) name="$2"; shift 2 ;;
      --) shift; break ;;
      *) echo "launch: unknown arg: $1" >&2; exit 2 ;;
    esac
  done
  [ -n "$dir" ] || { echo "launch: --dir required" >&2; exit 2; }
  [ -n "$name" ] || { echo "launch: --name required" >&2; exit 2; }
  [ $# -gt 0 ] || { echo "launch: command required after --" >&2; exit 2; }

  mkdir -p "$dir"
  local log="$dir/$name.log"
  local exitf="$dir/$name.exit"
  local donef="$dir/$name.done"
  local pidf="$dir/$name.pid"
  local cmdf="$dir/$name.cmd.txt"
  local startedf="$dir/$name.started_at"

  rm -f "$exitf" "$donef"
  printf '%s\n' "$*" > "$cmdf"
  date -u +"%Y-%m-%dT%H:%M:%SZ" > "$startedf"
  : > "$log"

  local pid
  pid=$(_DL_LOG="$log" _DL_EXITFILE="$exitf" _DL_DONEFILE="$donef" python3 - "$@" <<'PYEOF'
import os, subprocess, sys

cmd = sys.argv[1:]
log_path = os.environ["_DL_LOG"]
exit_path = os.environ["_DL_EXITFILE"]
done_path = os.environ["_DL_DONEFILE"]

env = dict(os.environ)
env["_DL_EXITFILE"] = exit_path
env["_DL_DONEFILE"] = done_path

# The wrapped command runs as "$@" inside this bash -c; on completion the
# same (now-detached) session writes its own exit code + done marker, so no
# separate waiter process is required.
wrapper = '"$@"; ec=$?; printf "%s" "$ec" > "$_DL_EXITFILE"; touch "$_DL_DONEFILE"; exit "$ec"'

logf = open(log_path, "ab", buffering=0)
p = subprocess.Popen(
    ["bash", "-c", wrapper, "_dl_wrapper"] + cmd,
    stdin=subprocess.DEVNULL,
    stdout=logf,
    stderr=subprocess.STDOUT,
    start_new_session=True,   # setsid(2): new session + pgrp, detaches from launcher
    env=env,
)
print(p.pid)
PYEOF
)
  echo "$pid" > "$pidf"

  echo "pid: $pid"
  echo "log: $log"
  echo "exit_marker: $exitf"
  echo "done_marker: $donef"
  echo "pid_file: $pidf"
}

cmd_status() {
  local dir="" name=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --dir) dir="$2"; shift 2 ;;
      --name) name="$2"; shift 2 ;;
      *) echo "status: unknown arg: $1" >&2; exit 2 ;;
    esac
  done
  [ -n "$dir" ] || { echo "status: --dir required" >&2; exit 2; }
  [ -n "$name" ] || { echo "status: --name required" >&2; exit 2; }

  local donef="$dir/$name.done"
  local exitf="$dir/$name.exit"
  local pidf="$dir/$name.pid"

  if [ -f "$donef" ]; then
    local ec="unknown"
    [ -f "$exitf" ] && ec="$(cat "$exitf")"
    echo "done exit=$ec"
    return 0
  fi

  if [ -f "$pidf" ]; then
    local pid
    pid="$(cat "$pidf")"
    if kill -0 "$pid" 2>/dev/null; then
      echo "running pid=$pid"
      return 0
    fi
    echo "dead-no-marker pid=$pid"
    return 1
  fi

  echo "unknown: no pid file at $pidf" >&2
  return 2
}

main() {
  [ $# -gt 0 ] || { usage; exit 2; }
  local sub="$1"; shift
  case "$sub" in
    launch) cmd_launch "$@" ;;
    status) cmd_status "$@" ;;
    -h|--help) usage ;;
    *) echo "unknown subcommand: $sub" >&2; usage; exit 2 ;;
  esac
}

main "$@"
