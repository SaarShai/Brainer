#!/usr/bin/env python3
"""exp13 — cache-lint OUT-OF-DISTRIBUTION (closes exp10's "in-distribution" caveat).

exp10 got F1 1.0, but I authored both the fixtures AND the expectations, so it
only proves cache-lint catches the *exact shapes* I thought of. This adds two
harder, less-circular tests:

  Part 1 — NEW-SHAPE labeled fixtures built from first principles (I did NOT read
  the detector regexes while writing these), using dynamic-content / model-switch
  / fork-unsafe forms that differ on the surface from exp10's. If a genuinely
  cache-busting form slips through, that is a REAL recall gap to report, not hide.

  Part 2 — run cache-lint on this repo's REAL configs (actual CLAUDE.md +
  .claude/settings.json hooks) — true out-of-distribution input nobody built as a
  fixture. The repo's hooks are simple/read-ish, so the honest expectation is
  "no FAIL false-alarms on real clean config"; any FAIL is surfaced for adjudication.

Usage: python3 eval/exp13_cache_lint_ood/run.py
"""
from __future__ import annotations

import json
import statistics  # noqa: F401  (kept for parity / future use)
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "eval" / "exp10_cache_lint"))
from run_cache_lint_eval import BIG, C, fired, run_audit  # noqa: E402


# New surface forms, built without consulting the detector. pos = a genuine
# cache-bust that SHOULD fire; neg = must NOT fire.
OOD: list[dict[str, Any]] = [
    # rule 2 — dynamic content, NEW forms (backticks, ${VAR}, $VAR, jinja, py-interp)
    {"id": "o_r2_backtick", "rule": 2, "pol": "pos", "sev": "FAIL",
     "files": {"CLAUDE.md": "# P\n\nHEAD is `git rev-parse --short HEAD` today\n" + BIG, ".claude/settings.json": C()}},
    {"id": "o_r2_braced_env", "rule": 2, "pol": "pos", "sev": "FAIL",
     "files": {"CLAUDE.md": "# P\n\nRunning as ${USER} on ${HOSTNAME}\n" + BIG, ".claude/settings.json": C()}},
    {"id": "o_r2_bare_env", "rule": 2, "pol": "pos", "sev": "FAIL",
     "files": {"CLAUDE.md": "# P\n\nHome=$HOME shell=$SHELL\n" + BIG, ".claude/settings.json": C()}},
    {"id": "o_r2_random", "rule": 2, "pol": "pos", "sev": "FAIL",
     "files": {"CLAUDE.md": "# P\n\nnonce: ${RANDOM}-$(uuidgen)\n" + BIG, ".claude/settings.json": C()}},
    {"id": "o_r2_jinja", "rule": 2, "pol": "pos", "sev": "FAIL",
     "files": {"CLAUDE.md": "# P\n\nGenerated {{ now() }} / {% now 'iso' %}\n" + BIG, ".claude/settings.json": C()}},
    {"id": "o_r2_pyinterp", "rule": 2, "pol": "pos", "sev": "FAIL",
     "files": {"CLAUDE.md": "# P\n\nts={time.time()} day={datetime.now():%Y-%m-%d}\n" + BIG, ".claude/settings.json": C()}},
    # rule 2 negatives — look dynamic-ish but are static prose / inline code / fenced
    {"id": "o_r2_neg_price", "rule": 2, "pol": "neg", "sev": "FAIL",
     "files": {"CLAUDE.md": "# P\n\nBudget is $500 and the $variable naming uses $camelCase in prose. " + BIG, ".claude/settings.json": C()}},
    {"id": "o_r2_neg_inline", "rule": 2, "pol": "neg", "sev": "FAIL",
     "files": {"CLAUDE.md": "# P\n\nRun `echo $(date)` only as an example in inline code. " + BIG, ".claude/settings.json": C()}},

    # rule 4 — model switching, NEW encodings (provider-prefixed, bedrock ARN-ish, nested key)
    {"id": "o_r4_provider_prefix", "rule": 4, "pol": "pos", "sev": "WARN",
     "files": {"CLAUDE.md": BIG, ".claude/settings.json": C("anthropic/claude-opus-4.1"),
               ".claude/hooks/t.json": C("anthropic/claude-haiku-4.6")}},
    {"id": "o_r4_bedrock", "rule": 4, "pol": "pos", "sev": "WARN",
     "files": {"CLAUDE.md": BIG, ".claude/settings.json": C("us.anthropic.claude-sonnet-4.6-v1:0"),
               ".claude/hooks/t.json": C("us.anthropic.claude-haiku-4.6-v1:0")}},

    # rule 6 — fork-unsafe hooks, NEW mutation commands (sed -i, python append, cp)
    {"id": "o_r6_sed_inplace", "rule": 6, "pol": "pos", "sev": "FAIL",
     "files": {"CLAUDE.md": BIG, ".claude/settings.json": json.dumps(
         {"model": "claude-sonnet-4.6", "hooks": {"Stop": [{"command": "sed -i '' 's/x/y/' CLAUDE.md"}]}})}},
    {"id": "o_r6_py_append", "rule": 6, "pol": "pos", "sev": "FAIL",
     "files": {"CLAUDE.md": BIG, ".claude/settings.json": json.dumps(
         {"model": "claude-sonnet-4.6", "hooks": {"SessionEnd": [{"command": "python3 -c \"open('CLAUDE.md','a').write('x')\""}]}})}},
    {"id": "o_r6_neg_tmp", "rule": 6, "pol": "neg", "sev": "FAIL",  # writes a NON-prefix temp file => safe
     "files": {"CLAUDE.md": BIG, ".claude/settings.json": json.dumps(
         {"model": "claude-sonnet-4.6", "hooks": {"Stop": [{"command": "date >> /tmp/log.txt"}]}})}},
]


def main() -> int:
    # ---- Part 1: OOD labeled fixtures ----
    records = []
    for case in OOD:
        tmp = Path(tempfile.mkdtemp(prefix=f"clint-ood-{case['id']}-"))
        for rel, content in case["files"].items():
            p = tmp / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        findings = run_audit(tmp)
        did_fire = fired(findings, case["rule"], case["sev"])
        correct = did_fire == (case["pol"] == "pos")
        records.append({"id": case["id"], "rule": case["rule"], "pol": case["pol"],
                        "expected_fire": case["pol"] == "pos", "fired": did_fire, "correct": correct})

    by_rule: dict[int, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "tn": 0})
    for r in records:
        c = by_rule[r["rule"]]
        if r["expected_fire"] and r["fired"]: c["tp"] += 1
        elif r["expected_fire"] and not r["fired"]: c["fn"] += 1
        elif (not r["expected_fire"]) and r["fired"]: c["fp"] += 1
        else: c["tn"] += 1
    tp = sum(c["tp"] for c in by_rule.values()); fp = sum(c["fp"] for c in by_rule.values())
    fn = sum(c["fn"] for c in by_rule.values()); tn = sum(c["tn"] for c in by_rule.values())
    recall = round(tp / (tp + fn), 3) if tp + fn else None
    prec = round(tp / (tp + fp), 3) if tp + fp else None

    # ---- Part 2: REAL repo configs (unlabeled OOD; adjudicate FAILs) ----
    real = run_audit(REPO)
    real_fail = [f for f in real if f.get("severity") == "FAIL"]
    real_warn = [f for f in real if f.get("severity") == "WARN"]

    summary = {
        "experiment": "exp13_cache_lint_ood",
        "part1_labeled_ood": {
            "n": len(records), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "recall": recall, "precision": prec,
            "misses": [r["id"] for r in records if not r["correct"]],
            "records": records,
        },
        "part2_real_repo": {
            "root": str(REPO),
            "n_findings": len(real),
            "n_fail": len(real_fail),
            "n_warn": len(real_warn),
            "fails": [{"rule": f.get("rule"), "msg": f.get("message", "")[:140]} for f in real_fail],
            "warns": [{"rule": f.get("rule"), "msg": f.get("message", "")[:140]} for f in real_warn],
        },
    }
    out = HERE / "results" / "summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2))

    print(f"\n=== exp13 cache-lint OOD ===")
    print(f"  Part 1 (new-shape labeled, n={len(records)}): "
          f"recall={recall} precision={prec}  tp={tp} fp={fp} fn={fn} tn={tn}")
    for r in records:
        if not r["correct"]:
            kind = "MISSED (recall gap)" if r["expected_fire"] else "FALSE ALARM"
            print(f"    {kind}: {r['id']} (rule {r['rule']})")
    if not summary["part1_labeled_ood"]["misses"]:
        print("    all OOD cases correct — detection generalizes to new surface forms")
    print(f"  Part 2 (REAL repo {REPO.name}): {len(real)} findings, {len(real_fail)} FAIL, {len(real_warn)} WARN")
    for f in real_fail:
        print(f"    FAIL rule {f.get('rule')}: {f.get('message','')[:120]}")
    print(f"  results: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
