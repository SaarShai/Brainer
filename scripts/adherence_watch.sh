#!/usr/bin/env bash
# adherence_watch.sh — weekly report-only skill-adherence check (loop spec:
# scripts/adherence_watch.loop.md). Two mechanical layers, no model calls:
#  (1) trigger_suite --mode probe : do the prompt_intent probes still hit the
#      adversarial corpora (trigger recall/precision regression)?
#  (2) measure.py over the week's transcripts: which drift probes actually
#      fired in real sessions (obedience telemetry trend).
# Install:  bash scripts/adherence_watch.sh --install-cron
set -euo pipefail
BRAINER="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$BRAINER/.brainer/adherence-reports"
MARKER="# brainer-adherence-watch"

if [[ "${1:-}" == "--install-cron" ]]; then
  line="23 9 * * 1 /bin/bash $BRAINER/scripts/adherence_watch.sh >/dev/null 2>&1 $MARKER"
  ( crontab -l 2>/dev/null | grep -vF "$MARKER"; echo "$line" ) | crontab -
  echo "installed weekly cron (Mon 09:23): $line"
  exit 0
fi
if [[ "${1:-}" == "--uninstall-cron" ]]; then
  ( crontab -l 2>/dev/null | grep -vF "$MARKER" ) | crontab -
  echo "removed adherence-watch cron entry"
  exit 0
fi

mkdir -p "$OUT_DIR"
report="$OUT_DIR/$(date +%Y-%m-%d).md"
{
  echo "# adherence watch — $(date +%Y-%m-%d\ %H:%M)"
  echo
  echo "## Trigger probes vs adversarial corpora (regression)"
  echo '```'
  python3 "$BRAINER/eval/adherence/trigger_suite.py" --mode probe 2>&1
  echo '```'
  echo
  echo "## Drift-probe fires in the last 7 days of real sessions"
  echo '```'
  proj_dir="$HOME/.claude/projects/-Users-za-Documents-Brainer"
  if [ -d "$proj_dir" ]; then
    files=$( (find "$proj_dir" -name '*.jsonl' -mtime -7 2>/dev/null | sort | head -15) || true )
    for tx in $files; do
      echo "--- $(basename "$tx")"
      ( python3 "$BRAINER/skills/compliance-canary/tools/measure.py" "$tx" 2>/dev/null \
        | grep -E "fired|triggered|:" | head -8 ) || true
    done
    [ -n "$files" ] || echo "(no transcripts in the last 7 days)"
  else
    echo "(no transcript dir found)"
  fi
  echo '```'
} > "$report"
ls -1t "$OUT_DIR"/*.md 2>/dev/null | tail -n +13 | xargs rm -f 2>/dev/null || true
echo "adherence report: $report"
if grep -q "FAIL" "$report"; then
  echo "ACTION NEEDED — a trigger probe regressed against its corpus."
fi
