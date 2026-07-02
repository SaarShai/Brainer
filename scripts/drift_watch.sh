#!/usr/bin/env bash
# drift_watch.sh — weekly report-only sibling-drift check (loop spec + lint:
# scripts/drift_watch.loop.md). Writes a timestamped report; NEVER applies.
# Install the schedule:  bash scripts/drift_watch.sh --install-cron
# Run once now:          bash scripts/drift_watch.sh
set -euo pipefail
BRAINER="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$BRAINER/.brainer/drift-reports"
MARKER="# brainer-drift-watch"

if [[ "${1:-}" == "--install-cron" ]]; then
  line="17 9 * * 1 /bin/bash $BRAINER/scripts/drift_watch.sh >/dev/null 2>&1 $MARKER"
  ( crontab -l 2>/dev/null | grep -vF "$MARKER"; echo "$line" ) | crontab -
  echo "installed weekly cron (Mon 09:17): $line"
  exit 0
fi
if [[ "${1:-}" == "--uninstall-cron" ]]; then
  ( crontab -l 2>/dev/null | grep -vF "$MARKER" ) | crontab -
  echo "removed drift-watch cron entry"
  exit 0
fi

mkdir -p "$OUT_DIR"
report="$OUT_DIR/$(date +%Y-%m-%d).md"
tmp="$(mktemp)"
python3 "$BRAINER/scripts/sibling_sync_audit.py" --classify > "$tmp" 2>&1
{
  echo "# drift watch — $(date +%Y-%m-%d\ %H:%M)"
  if grep -qE "STALE|NEW-SKILL" "$tmp"; then
    echo
    echo "**ACTION NEEDED** — stale files or unadopted new skills detected."
    echo "Run the propagate skill (skills/propagate/SKILL.md) per affected sibling."
  else
    echo
    echo "All siblings in sync (only CUSTOMIZED/generated files differ)."
  fi
  echo
  echo '```'
  cat "$tmp"
  echo '```'
} > "$report"
rm -f "$tmp"
# keep the last 12 reports
ls -1t "$OUT_DIR"/*.md 2>/dev/null | tail -n +13 | xargs rm -f 2>/dev/null || true
echo "drift report: $report"
grep -m1 -E "ACTION NEEDED|All siblings" "$report" || true
