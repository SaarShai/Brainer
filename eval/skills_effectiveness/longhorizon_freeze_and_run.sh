#!/bin/bash
# Freeze the long-horizon experiment bundle, then run the 12 GPT-stratum main
# sessions sequentially. Aborts before any paid session if the gate report is
# not PASS or the repo is dirty. Arm order per scenarios/README.md: odd
# scenario indices FRONTIER-first, even indices OFF-first.
set -euo pipefail
cd "$(dirname "$0")/../.."   # repo root

GATE=eval/results/skills-effectiveness/longhorizon-rehearsal/gate-report.json
RESULTS=eval/results/skills-effectiveness/longhorizon-main
FREEZE=eval/results/skills-effectiveness/longhorizon-freeze-bundle.json
SCEN=eval/skills_effectiveness/scenarios
VENUE=/Users/za/Documents/PROMPTER

python3 - <<'EOF'
import json, sys
d = json.load(open("eval/results/skills-effectiveness/longhorizon-rehearsal/gate-report.json"))
if d["overall"] != "PASS":
    sys.exit("gate-report overall is not PASS; refusing to freeze or run")
EOF

if [ -n "$(git status --porcelain)" ]; then
  echo "repo dirty; refusing to freeze" >&2; exit 1
fi

SHA=$(git rev-parse HEAD)
python3 - "$SHA" <<'EOF'
import hashlib, json, sys
from pathlib import Path
sha = sys.argv[1]
assert len(sha) == 40
def h(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
bundle = {
    "frozen_at_commit": sha,
    "grader_model_id": "glm-5.2",
    "kappa_threshold": 0.7,
    "scenarios": {f"scenario-{i:02d}.md": h(f"eval/skills_effectiveness/scenarios/scenario-{i:02d}.md") for i in range(1, 7)},
    "scenarios_readme": h("eval/skills_effectiveness/scenarios/README.md"),
    "extractor_blinded": h("eval/skills_effectiveness/longhorizon_extract_blinded.py"),
    "extractor_mechanism": h("eval/skills_effectiveness/longhorizon_extract_mechanism.py"),
    "gate_script": h("eval/skills_effectiveness/longhorizon_gate.py"),
    "grader_prompt": h("eval/skills_effectiveness/longhorizon_grader_prompt.md"),
    "run_driver": h("eval/skills_effectiveness/longhorizon_run_session.py"),
    "gate_report": h("eval/results/skills-effectiveness/longhorizon-rehearsal/gate-report.json"),
}
out = Path("eval/results/skills-effectiveness/longhorizon-freeze-bundle.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n")
print("freeze bundle written:", out)
EOF

git add "$FREEZE"
git commit -m "Binding freeze: long-horizon experiment bundle at $SHA

Rehearsal gate PASS (all components incl. grader kappa). Bundle hashes the
six scenario scripts, both extractors, gate script, grader prompt, run
driver, gate report, and glm-5.2 grader id at commit $SHA. From the first
counted session through the last, the Brainer checkout must stay at the
freeze-commit content and PROMPTER config must not change, per the
preregistration.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"

mkdir -p "$RESULTS"
for i in 1 2 3 4 5 6; do
  id=$(printf "scenario-%02d" "$i")
  if [ $((i % 2)) -eq 1 ]; then arms="frontier off"; else arms="off frontier"; fi
  for arm in $arms; do
    out="$RESULTS/$id-$arm"
    if [ -f "$out/manifest.json" ]; then
      echo "SKIP $id/$arm — manifest exists"
      continue
    fi
    echo "=== $(date -u +%FT%TZ) START $id $arm ==="
    python3 eval/skills_effectiveness/longhorizon_run_session.py \
      --scenario "$SCEN/$id.md" --arm "$arm" --venue "$VENUE" --out-dir "$out"
    echo "=== $(date -u +%FT%TZ) DONE $id $arm ==="
  done
done
echo "ALL 12 MAIN SESSIONS COMPLETE"
