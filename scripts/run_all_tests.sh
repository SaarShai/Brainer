#!/usr/bin/env bash
# Single deterministic test entrypoint — exit code is the verdict.
#
# Runs every offline test the repo ships: SKILL.md lint, per-skill unit
# tests, hook self-tests, carrier sync. Model-dependent evals (eval/exp*,
# eval/longrun) are NOT here — they need ollama/GPU and live behind their
# own runners.
#
# Usage: bash scripts/run_all_tests.sh [--quiet]
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

QUIET=${1:-}
PASS=0; FAIL=0
declare -a FAILED

run() {
  # run <label> <cmd...>
  local label="$1"; shift
  if out=$("$@" 2>&1); then
    PASS=$((PASS+1))
    [ "$QUIET" = "--quiet" ] || echo "PASS $label"
  else
    FAIL=$((FAIL+1)); FAILED+=("$label")
    echo "FAIL $label"
    echo "$out" | tail -8 | sed 's/^/  | /'
  fi
}

# 1. SKILL.md lint — every skill, one call each so the failing file is named
for f in skills/*/SKILL.md; do
  run "lint:$(basename "$(dirname "$f")")" python3 scripts/lint_skill_md.py "$f"
done

# 2. Carrier catalogs in sync (CLAUDE.md / AGENTS.md / GEMINI.md sentinels)
run "carrier-sync" python3 scripts/check_carrier_sync.py

# 3. Tracked JSON validity (mirrors CI)
run "json-valid" bash -c "git ls-files -z '*.json' | xargs -0 -n1 python3 -m json.tool > /dev/null"

# 4. Python syntax (mirrors CI)
run "py-compile" bash -c "git ls-files -z '*.py' | xargs -0 python3 -m py_compile"

# 5. Per-skill unit tests (plain-python, no pytest dep)
UNIT_TESTS=(
  skills/cache-lint/tools/test_cache_lint.py
  skills/context-keeper/tools/tests/test_extract.py
  skills/prompt-triage/tools/test_classify.py
  skills/write-gate/tools/test_write_gate.py
  skills/wiki-memory/tools/test_consolidate.py
  skills/wiki-memory/tools/test_decay.py
  skills/wiki-memory/tools/test_lint_hygiene.py
  skills/wiki-memory/tools/test_provenance.py
  skills/wiki-memory/tools/test_refresh.py
  skills/wiki-memory/tools/test_resolve.py
)
# semantic-diff needs tree-sitter; SKIP (not FAIL) where the dep is absent
# (e.g. bare CI runners) — semdiff's own suite covers it on dev machines.
if python3 -c "import tree_sitter" 2>/dev/null; then
  UNIT_TESTS+=(
    skills/semantic-diff/tools/tests/test_basic.py
    skills/semantic-diff/tools/tests/test_multilang.py
    skills/semantic-diff/tools/tests/test_rename.py
    skills/semantic-diff/tools/tests/test_syntax_error.py
    skills/semantic-diff/tools/tests/test_whitespace.py
    skills/semantic-diff/tools/tests/test_realistic.py
  )
else
  echo "SKIP semantic-diff suite (tree_sitter not importable)"
fi
for t in "${UNIT_TESTS[@]}"; do
  [ -f "$t" ] || { echo "FAIL missing:$t"; FAIL=$((FAIL+1)); FAILED+=("missing:$t"); continue; }
  run "unit:$(basename "$t" .py)" python3 "$t"
done

# 6. Hook self-test suites
run "hook:compliance-canary" bash skills/compliance-canary/tools/test.sh

# 7. Triage replay audit — re-classifies every historically-routed prompt with
# the current classifier; fails on local-model / low-conf / length-gate
# violations. Needs real session transcripts, so skip where none exist (CI).
if ls ~/.claude/projects/-Users-za-Documents-Brainer/*.jsonl >/dev/null 2>&1; then
  run "audit:triage-replay" python3 scripts/replay_triage.py
else
  echo "SKIP triage replay audit (no local transcripts)"
fi

echo
if [ "$FAIL" -eq 0 ]; then
  echo "run_all_tests: $PASS/$PASS PASS"
  exit 0
else
  echo "run_all_tests: $PASS passed, $FAIL FAILED:"
  printf '  - %s\n' "${FAILED[@]}"
  exit 1
fi
