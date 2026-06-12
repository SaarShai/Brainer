#!/usr/bin/env bash
# Re-measure against eval/BASELINE_2026-06-12.md — one command, five answers.
# Usage: bash scripts/remeasure_baseline.sh
set -uo pipefail
cd "$(dirname "$0")/.."

echo "=== remeasure vs eval/BASELINE_2026-06-12.md ($(date +%F)) ==="
echo
echo "--- Q1 cache hit ratio (baseline: aggregate 0.9477) ---"
python3 scripts/mine_transcripts.py 2>&1 | sed -n '/CACHE/,/^$/p'
echo
echo "--- Q2 triage replay, both repos (baseline: 4/28 + 2/12 routed, 0 violations) ---"
python3 scripts/replay_triage.py | head -3
python3 scripts/replay_triage.py "$HOME/.claude/projects/-Users-za-Documents-PROMPTER/*.jsonl" | head -3
echo
echo "--- Q3 misroute incidents (baseline: 6 locked on 2026-06-12) ---"
grep -c "^[0-9]*\. \|^## 2026.*incident" skills/prompt-triage/EVAL.md 2>/dev/null || true
echo "  (manual: count NEW incident entries in skills/prompt-triage/EVAL.md after 2026-06-12)"
echo
echo "--- Q4 compaction snapshots present ---"
ls -lt .brainer/sessions/ 2>/dev/null | head -5 || echo "  none"
echo
echo "--- Q5 always-on tax (baseline: 1,078 tok @16 skills) ---"
python3 eval/static_cost.py 2>/dev/null | tail -2
echo
echo "=== suite sanity ==="
bash scripts/run_all_tests.sh 2>&1 | tail -1
