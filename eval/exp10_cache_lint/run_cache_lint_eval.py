#!/usr/bin/env python3
"""exp10_cache_lint — does cache-lint actually CATCH real prompt-cache busts without
false alarms? Closes the TP≥80% / FP≤10% target that cache-lint's EVAL.md lists as
unrun (only fuzz/robustness was measured — that it runs, not that it helps).

Method (mirrors exp3's labeled-corpus classifier eval, but the units are fixture project
DIRECTORIES since cache-lint audits a tree): a balanced corpus of small project fixtures,
each labeled for ONE rule as a positive (genuinely violates it) or a negative (a clean /
near-miss case that must NOT trip it — e.g. inline-code prose, dynamic-inside-a-fence,
read-only hooks). Run `cache-lint audit <fixture> --json` on each, compare the detection
to the label, and report per-rule + overall precision / recall / F1 / false-alarm rate.

Covers the 4 single-run rules:
  rule 2 — dynamic content above the prefix (FAIL on $(date)/{{env.*}}; WARN if fenced)
  rule 4 — model switching across the prefix (WARN)
  rule 5 — breakpoint sizing (WARN on a tiny prefix)
  rule 6 — fork safety: a Stop/SessionEnd hook MUTATING a prefix file (FAIL)
Rules 1 & 3 (ordering / tool-stability) are STATEFUL — they diff against a stored baseline
across runs — so they need a 2-run protocol and are out of scope for this single-audit
corpus (documented, not silently skipped).

This measures DETECTION accuracy. The separate "≥30% cache-hit uplift" claim (does fixing
a finding actually save cached tokens) needs a cache-aware host (MiMo cached_tokens /
Claude) and remains unmeasured — flagged, not hidden.

Usage: python3 eval/exp10_cache_lint/run_cache_lint_eval.py [--json] [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
CACHE_LINT = REPO_ROOT / "skills" / "cache-lint" / "tools" / "cache_lint.py"
RESULTS_DIR = HERE / "results"

BIG = "# Project\n\n## Rules\n\nUse type hints and write tests. " * 120  # static, big enough


def C(model="claude-sonnet-4.6"):
    return json.dumps({"model": model})


# Each case: id, rule (under test), polarity (pos = should fire, neg = must NOT fire),
# severity (the severity that counts as "fired" for a positive), files {relpath: content}.
CORPUS: list[dict[str, Any]] = [
    # ---- rule 2: dynamic content (FAIL unfenced, WARN fenced) ----
    {"id": "r2_pos_date", "rule": 2, "pol": "pos", "sev": "FAIL",
     "files": {"CLAUDE.md": "# P\n\nCurrent date: $(date)\nbuild at $(date +%s)\n" + BIG, ".claude/settings.json": C()}},
    {"id": "r2_pos_env", "rule": 2, "pol": "pos", "sev": "FAIL",
     "files": {"CLAUDE.md": "# P\n\nUser: {{env.USER}}\nHome: {{env.HOME}}\n" + BIG, ".claude/settings.json": C()}},
    {"id": "r2_pos_cmdsub", "rule": 2, "pol": "pos", "sev": "FAIL",
     "files": {"CLAUDE.md": "# P\n\nbranch: $(git rev-parse HEAD)\n" + BIG, ".claude/settings.json": C()}},
    {"id": "r2_neg_inlinecode", "rule": 2, "pol": "neg", "sev": "FAIL",
     "files": {"CLAUDE.md": "# P\n\nSee `CLAUDE.md` and run `npm test` and `git status`. " + BIG, ".claude/settings.json": C()}},
    {"id": "r2_neg_fenced", "rule": 2, "pol": "neg", "sev": "FAIL",  # fenced dynamic => WARN, NOT FAIL
     "files": {"CLAUDE.md": "# P\n\n```bash\necho $(date)\n```\n" + BIG, ".claude/settings.json": C()}},
    {"id": "r2_neg_prose", "rule": 2, "pol": "neg", "sev": "FAIL",
     "files": {"CLAUDE.md": "# P\n\nKeep the date format ISO-8601. Use the current model. " + BIG, ".claude/settings.json": C()}},
    # ---- rule 4: model switching (WARN) ----
    {"id": "r4_pos_two_models", "rule": 4, "pol": "pos", "sev": "WARN",
     "files": {"CLAUDE.md": BIG, ".claude/settings.json": C("claude-haiku-4.6"),
               ".claude/hooks/triage.json": C("claude-sonnet-4.6")}},
    {"id": "r4_pos_three", "rule": 4, "pol": "pos", "sev": "WARN",
     "files": {"CLAUDE.md": BIG, ".claude/settings.json": C("claude-haiku-4.6"),
               ".claude/hooks/a.json": C("claude-sonnet-4.6"), ".claude/hooks/b.json": C("claude-opus-4.1")}},
    {"id": "r4_neg_single", "rule": 4, "pol": "neg", "sev": "WARN",
     "files": {"CLAUDE.md": BIG, ".claude/settings.json": C("claude-sonnet-4.6"),
               ".claude/hooks/triage.json": C("claude-sonnet-4.6")}},
    {"id": "r4_neg_nomodel", "rule": 4, "pol": "neg", "sev": "WARN",
     "files": {"CLAUDE.md": BIG, ".claude/settings.json": json.dumps({"permissions": {}})}},
    # ---- rule 5: breakpoint sizing (WARN on a tiny prefix) ----
    {"id": "r5_pos_tiny", "rule": 5, "pol": "pos", "sev": "WARN",
     "files": {"CLAUDE.md": "# Tiny\n", ".claude/settings.json": C()}},
    {"id": "r5_pos_tiny2", "rule": 5, "pol": "pos", "sev": "WARN",
     "files": {"CLAUDE.md": "use tabs\n", ".claude/settings.json": C()}},
    {"id": "r5_neg_big", "rule": 5, "pol": "neg", "sev": "WARN",
     "files": {"CLAUDE.md": BIG, ".claude/settings.json": C()}},
    # ---- rule 6: fork safety (FAIL on a hook mutating a prefix file) ----
    {"id": "r6_pos_append", "rule": 6, "pol": "pos", "sev": "FAIL",
     "files": {"CLAUDE.md": BIG, ".claude/settings.json": json.dumps(
         {"model": "claude-sonnet-4.6", "hooks": {"Stop": [{"command": "echo done >> CLAUDE.md"}]}})}},
    {"id": "r6_pos_tee", "rule": 6, "pol": "pos", "sev": "FAIL",
     "files": {"CLAUDE.md": BIG, ".claude/settings.json": json.dumps(
         {"model": "claude-sonnet-4.6", "hooks": {"SessionEnd": [{"command": "date | tee -a AGENTS.md"}]}}),
               "AGENTS.md": BIG}},
    {"id": "r6_neg_readonly", "rule": 6, "pol": "neg", "sev": "FAIL",
     "files": {"CLAUDE.md": BIG, ".claude/settings.json": json.dumps(
         {"model": "claude-sonnet-4.6", "hooks": {"Stop": [{"command": "grep TODO CLAUDE.md || true"}]}})}},
    {"id": "r6_neg_cat", "rule": 6, "pol": "neg", "sev": "FAIL",
     "files": {"CLAUDE.md": BIG, ".claude/settings.json": json.dumps(
         {"model": "claude-sonnet-4.6", "hooks": {"SessionEnd": [{"command": "cat AGENTS.md"}]}}), "AGENTS.md": BIG}},
    {"id": "r6_neg_nohooks", "rule": 6, "pol": "neg", "sev": "FAIL",
     "files": {"CLAUDE.md": BIG, ".claude/settings.json": C()}},
]


def run_audit(fixture_root: Path) -> list[dict[str, Any]]:
    out = subprocess.run([sys.executable, str(CACHE_LINT), "audit", str(fixture_root), "--json"],
                         text=True, capture_output=True)
    try:
        return json.loads(out.stdout).get("findings", [])
    except json.JSONDecodeError:
        return []


def fired(findings: list[dict], rule: int, sev: str) -> bool:
    """Did cache-lint flag `rule` at >= the expected severity? FAIL counts for a WARN ask."""
    order = {"OK": 0, "WARN": 1, "FAIL": 2}
    want = order.get(sev, 1)
    return any(f.get("rule") == rule and order.get(f.get("severity"), 0) >= want
               and f.get("severity") != "OK" for f in findings)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", default=str(RESULTS_DIR / "summary.json"))
    args = ap.parse_args()

    records = []
    for case in CORPUS:
        tmp = Path(tempfile.mkdtemp(prefix=f"clint-{case['id']}-"))
        for rel, content in case["files"].items():
            p = tmp / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        findings = run_audit(tmp)
        did_fire = fired(findings, case["rule"], case["sev"])
        correct = (did_fire == (case["pol"] == "pos"))
        records.append({"id": case["id"], "rule": case["rule"], "pol": case["pol"],
                        "expected_fire": case["pol"] == "pos", "fired": did_fire, "correct": correct})

    # per-rule + overall confusion
    by_rule: dict[int, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "tn": 0})
    for r in records:
        cell = by_rule[r["rule"]]
        if r["expected_fire"] and r["fired"]:
            cell["tp"] += 1
        elif r["expected_fire"] and not r["fired"]:
            cell["fn"] += 1
        elif not r["expected_fire"] and r["fired"]:
            cell["fp"] += 1
        else:
            cell["tn"] += 1

    def prf(c):
        tp, fp, fn, tn = c["tp"], c["fp"], c["fn"], c["tn"]
        prec = round(tp / (tp + fp), 3) if tp + fp else None
        rec = round(tp / (tp + fn), 3) if tp + fn else None
        f1 = round(2 * prec * rec / (prec + rec), 3) if prec and rec else None
        fpr = round(fp / (fp + tn), 3) if fp + tn else None
        return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": prec, "recall": rec,
                "f1": f1, "false_alarm_rate": fpr}

    per_rule = {f"rule_{k}": prf(v) for k, v in sorted(by_rule.items())}
    agg = {"tp": sum(v["tp"] for v in by_rule.values()), "fp": sum(v["fp"] for v in by_rule.values()),
           "fn": sum(v["fn"] for v in by_rule.values()), "tn": sum(v["tn"] for v in by_rule.values())}
    overall = prf(agg)

    summary = {
        "experiment": "exp10_cache_lint",
        "method": "labeled fixture-dir corpus; detection accuracy vs cache-lint audit --json",
        "rules_covered": [2, 4, 5, 6], "rules_out_of_scope": [1, 3],
        "n_cases": len(CORPUS), "n_correct": sum(r["correct"] for r in records),
        "overall": overall, "per_rule": per_rule, "records": records,
        "verdict": {
            "recall": overall["recall"], "false_alarm_rate": overall["false_alarm_rate"],
            "f1": overall["f1"],
            "meets_TP_target_80": (overall["recall"] or 0) >= 0.80,
            "meets_FP_target_10": (overall["false_alarm_rate"] or 1) <= 0.10,
            "headline": (f"cache-lint detection on a {len(CORPUS)}-case labeled corpus (rules 2/4/5/6): "
                         f"recall {overall['recall']} (TP target ≥0.80), false-alarm {overall['false_alarm_rate']} "
                         f"(FP target ≤0.10), F1 {overall['f1']}. Cache-$ uplift remains unmeasured "
                         f"(needs a cache-aware host)."),
        },
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(summary, indent=2))

    print(f"exp10_cache_lint: {len(CORPUS)} cases, {summary['n_correct']} correct", flush=True)
    for r in records:
        print(f"  {'OK ' if r['correct'] else 'XX '} {r['id']:<20} rule{r['rule']} "
              f"{r['pol']} expected_fire={int(r['expected_fire'])} fired={int(r['fired'])}", flush=True)
    print("\nper-rule precision/recall/F1/false-alarm:", flush=True)
    for k, v in per_rule.items():
        print(f"  {k}: P={v['precision']} R={v['recall']} F1={v['f1']} FP-rate={v['false_alarm_rate']} "
              f"(tp{v['tp']} fp{v['fp']} fn{v['fn']} tn{v['tn']})", flush=True)
    print(f"\n=== verdict ===\n{summary['verdict']['headline']}", flush=True)
    print(f"results: {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
