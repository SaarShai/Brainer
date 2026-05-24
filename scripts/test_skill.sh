#!/usr/bin/env bash
# Test one skill thoroughly. Runs:
#   1. lint SKILL.md (agentskills.io schema)
#   2. unit tests (tools/test_*.py)
#   3. simulations matching the skill name (eval/sims/<skill>_*.py)
#   4. emits boilerplate prompts for cold-reviewer + external-validator
#      agents (you launch those separately)
#
# Usage:
#   scripts/test_skill.sh write-gate
#   scripts/test_skill.sh write-gate --skip-sims     # just lint + unit
#   scripts/test_skill.sh write-gate --emit-prompts  # only show review prompts
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

SKILL=""
SKIP_SIMS=0
EMIT_PROMPTS_ONLY=0

while (( "$#" )); do
  case "$1" in
    --skip-sims) SKIP_SIMS=1; shift ;;
    --emit-prompts) EMIT_PROMPTS_ONLY=1; shift ;;
    -h|--help)
      grep -E '^# ' "$0" | sed 's/^# //'
      exit 0 ;;
    *) [ -z "$SKILL" ] && SKILL="$1" || { echo "extra arg: $1" >&2; exit 2; }; shift ;;
  esac
done

if [ -z "$SKILL" ]; then
  echo "usage: $0 <skill-name> [--skip-sims | --emit-prompts]" >&2
  exit 2
fi

SKILL_DIR="skills/$SKILL"
if [ ! -d "$SKILL_DIR" ]; then
  echo "no such skill: $SKILL_DIR" >&2
  exit 2
fi

# --- Phase 4: review prompts -------------------------------------------------
emit_prompts() {
  cat <<EOF
=== Cold review prompts for $SKILL ===

Copy ONE of these into a fresh Claude Code session (or Agent tool call) for
independent review. Each is self-contained — the agent has no memory of any
prior conversation.

------ 1. Cold code review ------
You are doing a cold independent code review of skills/$SKILL/ at
$REPO_ROOT/. Read the SKILL.md, tools/*.py, and tools/test_*.py.

Look for: regex catastrophic backtracking, edge cases not covered by tests
(empty inputs, CRLF/BOM, Unicode, non-UTF-8, huge files, concurrent writes),
security issues (path traversal, unsafe yaml.load, command injection),
performance gotchas (O(n²), full-file reads in hot path), test gaps (tests
that pass trivially or don't test what they're named after).

Specifically check for the recurring bugs we keep finding in this codebase:
  - quoted YAML scalars breaking rewrite-style edits
  - frontmatter parsers rejecting CRLF / UTF-8 BOM
  - fallback YAML parsers stringifying nested keys
  - regex matching inside Markdown code fences when it shouldn't
  - O(n²) list.count loops
  - non-UTF-8 file crashes
  - patterns matching read-only commands when only writes matter
  - discovery globs missing common project layouts

Severity: CRITICAL / HIGH / MEDIUM / LOW with file:line citations.
≤700 words.

------ 2. External validation (if applicable) ------
Test skills/$SKILL/ against 2-3 real projects on GitHub that the skill
plausibly applies to. Clone to /tmp/, run the skill's CLI, judge each finding
as true-positive / false-positive / ambiguous by inspecting the cited file
yourself. Report TP/FP rates per project + any crashes. ≤600 words.

EOF
}

if [ "$EMIT_PROMPTS_ONLY" = 1 ]; then
  emit_prompts
  exit 0
fi

echo "=== test_skill: $SKILL ==="

# --- Phase 1: lint ----------------------------------------------------------
echo "--- lint SKILL.md ---"
python3 scripts/lint_skill_md.py "$SKILL_DIR/SKILL.md"

# --- Phase 2: unit tests ----------------------------------------------------
TESTS=$(find "$SKILL_DIR/tools" -name 'test_*.py' 2>/dev/null || true)
if [ -n "$TESTS" ]; then
  echo "--- unit tests ---"
  for t in $TESTS; do
    echo "  running $t"
    python3 "$t"
  done
else
  echo "--- no unit tests found ($SKILL_DIR/tools/test_*.py) ---"
fi

# --- Phase 3: sims ----------------------------------------------------------
if [ "$SKIP_SIMS" = 0 ]; then
  SKILL_UNDERSCORE="${SKILL//-/_}"
  SIMS=$(find eval/sims -maxdepth 1 -name "${SKILL_UNDERSCORE}_*.py" 2>/dev/null || true)
  if [ -n "$SIMS" ]; then
    echo "--- simulations ---"
    for s in $SIMS; do
      echo "  running $s"
      python3 "$s"
    done
  else
    echo "--- no sims found (eval/sims/${SKILL_UNDERSCORE}_*.py) ---"
    echo "    tip: copy eval/sims/TEMPLATE_calibration.py or TEMPLATE_fuzz.py"
  fi
fi

# --- Phase 4: prompts -------------------------------------------------------
echo
emit_prompts
echo "=== done ==="
