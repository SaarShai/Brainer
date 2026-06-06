#!/usr/bin/env bash
# Stage the minimal Kaggle dataset for the Ollama T4 eval run.
#
# Produces a clean dir (default /tmp/te-kaggle-dataset) containing:
#   eval/                      (minus results/ and sims/results/, no venv/pyc/sqlite)
#   skills/<name>/SKILL.md      (runner.py loads these at runtime via load_skill_body)
#   skills/prompt-triage/tools/ (classify.py + agents, needed by the triage runner)
#   eval/kaggle_ollama/*.py     (the notebook + ollama triage runner — already under eval/)
#   dataset-metadata.json
#
# Then push (requires a WRITE-scoped Kaggle token — see README_OLLAMA.md):
#   export PATH="$HOME/.local/bin:$PATH"
#   kaggle datasets create -p /tmp/te-kaggle-dataset -r zip      # first time
#   kaggle datasets version -p /tmp/te-kaggle-dataset -r zip -m "rerun"  # subsequent
set -euo pipefail

SRC="${SRC:-$(cd "$(dirname "$0")/../.." && pwd)}"   # repo root (token-economy)
STAGE="${STAGE:-/tmp/te-kaggle-dataset}"

echo "repo root: $SRC"
echo "stage dir: $STAGE"
rm -rf "$STAGE"; mkdir -p "$STAGE"

rsync -a \
  --exclude '.venv/' --exclude '__pycache__/' --exclude '*.pyc' \
  --exclude '*.sqlite3' \
  --exclude 'results/' \
  --exclude 'sims/results/' \
  "$SRC/eval/" "$STAGE/eval/"

# all SKILL.md bodies (runner.load_skill_body reads skills/<name>/SKILL.md)
while IFS= read -r -d '' md; do
  rel="${md#"$SRC"/}"
  mkdir -p "$STAGE/$(dirname "$rel")"
  cp "$md" "$STAGE/$rel"
done < <(find "$SRC/skills" -name SKILL.md -not -path '*/.venv/*' -not -path '*/__pycache__/*' -print0)

# prompt-triage tools (classify.py + agents) for the triage runner
rsync -a --exclude '.venv/' --exclude '__pycache__/' --exclude '*.pyc' \
  "$SRC/skills/prompt-triage/tools/" "$STAGE/skills/prompt-triage/tools/"

cp "$(dirname "$0")/dataset-metadata.json" "$STAGE/dataset-metadata.json"

echo "SKILL.md count: $(find "$STAGE/skills" -name SKILL.md | wc -l | tr -d ' ')"
echo "total size:    $(du -sh "$STAGE" | cut -f1)"
echo "done -> $STAGE"
