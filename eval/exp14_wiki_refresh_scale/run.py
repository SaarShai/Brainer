#!/usr/bin/env python3
"""exp14 — wiki-refresh code-grounded drift detection at scale (closes "tiny N").

wiki-refresh's reconcile *decision* (Keep/Update/Replace/Delete) is model
judgment, but its load-bearing DETERMINISTIC core is `wiki.py audit-refs`:
which stored pages cite code paths that no longer exist on disk. The prior
reading was 3/3 (tiny N). This scales it: build N synthetic pages with KNOWN
ground-truth citation health (mix of real repo paths + paths that are gone —
including skills we actually deleted this session, e.g. handoff / loop-breaker),
run audit-refs, and score:

  reliability — precision/recall/F1 of "page is drifted" detection at scale
  signal      — all-refs-gone vs some-refs-gone classification accuracy

Deterministic, local, no model.

Usage: python3 eval/exp14_wiki_refresh_scale/run.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "skills" / "wiki-memory" / "tools"))
from wiki import WikiStore  # noqa: E402

# Paths that DO exist in the repo (extract_refs needs '/' + extension).
PRESENT = [
    "eval/judge.py", "eval/static_cost.py", "skills/wiki-memory/tools/wiki.py",
    "skills/cache-lint/tools/cache_lint.py", "skills/write-gate/tools/write_gate.py",
    "eval/exp9_drift/run_drift.py", "skills/prompt-triage/tools/classify.py",
]
# Paths that do NOT exist — incl. skills we deleted this session (realistic drift).
MISSING = [
    "skills/handoff/SKILL.md", "skills/loop-breaker/tools/hook.py",
    "eval/runner_compress.py", "skills/session-recall/SKILL.md",
    "skills/compress-context/tools/cli.py", "foo/ghost.py", "nonexistent/path.js",
]


def page_md(title: str, refs: list[str]) -> str:
    body_refs = " and ".join(f"`{r}`" for r in refs)
    return (f"---\ntitle: {title}\ntype: fact\nverified: 2026-01-01\n---\n\n"
            f"# {title}\n\nThis fact cites {body_refs} in its explanation.\n")


def build_pages(n: int):
    """Return (specs) where each spec = (title, refs, is_drifted, signal_or_None)."""
    specs = []
    for i in range(n):
        mode = i % 5
        if mode == 0:      # clean: all present
            refs = [PRESENT[i % len(PRESENT)], PRESENT[(i + 2) % len(PRESENT)]]
            specs.append((f"clean-{i}", refs, False, None))
        elif mode == 1:    # some-refs-gone: 1 present + 1 missing
            refs = [PRESENT[i % len(PRESENT)], MISSING[i % len(MISSING)]]
            specs.append((f"partial-{i}", refs, True, "some-refs-gone"))
        elif mode == 2:    # all-refs-gone
            refs = [MISSING[i % len(MISSING)], MISSING[(i + 3) % len(MISSING)]]
            specs.append((f"gone-{i}", refs, True, "all-refs-gone"))
        elif mode == 3:    # clean with 3 present
            refs = [PRESENT[i % len(PRESENT)], PRESENT[(i + 1) % len(PRESENT)], PRESENT[(i + 3) % len(PRESENT)]]
            specs.append((f"clean3-{i}", refs, False, None))
        else:              # some-refs-gone with 2 present + 1 missing
            refs = [PRESENT[i % len(PRESENT)], PRESENT[(i + 2) % len(PRESENT)], MISSING[(i + 1) % len(MISSING)]]
            specs.append((f"partial3-{i}", refs, True, "some-refs-gone"))
    return specs


def main() -> int:
    n = 30
    tmp = Path(tempfile.mkdtemp(prefix="wiki-refresh-scale-"))
    concepts = tmp / "concepts"
    concepts.mkdir(parents=True, exist_ok=True)
    specs = build_pages(n)
    gold = {}  # title -> (is_drifted, signal)
    for title, refs, drifted, signal in specs:
        (concepts / f"{title}.md").write_text(page_md(title, refs), encoding="utf-8")
        gold[title] = (drifted, signal)

    store = WikiStore(tmp)
    res = store.audit_refs(code_root=REPO)
    detected = {Path(d["path"]).stem: d for d in res["drifted"]}

    tp = fp = fn = tn = 0
    signal_ok = signal_tot = 0
    errors = []
    for title, (is_drifted, gsignal) in gold.items():
        flagged = title in detected
        if is_drifted and flagged:
            tp += 1
            signal_tot += 1
            if detected[title]["signal"] == gsignal:
                signal_ok += 1
            else:
                errors.append(f"{title}: signal {detected[title]['signal']} != {gsignal}")
        elif is_drifted and not flagged:
            fn += 1
            errors.append(f"{title}: MISSED drift (refs gone but not flagged)")
        elif (not is_drifted) and flagged:
            fp += 1
            errors.append(f"{title}: FALSE drift (all refs present but flagged: missing={detected[title]['missing_refs']})")
        else:
            tn += 1

    prec = round(tp / (tp + fp), 3) if tp + fp else None
    rec = round(tp / (tp + fn), 3) if tp + fn else None
    f1 = round(2 * prec * rec / (prec + rec), 3) if prec and rec else None
    summary = {
        "experiment": "exp14_wiki_refresh_scale",
        "n_pages": n,
        "scanned": res["scanned"],
        "drifted_detected": res["drifted_count"],
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "precision": prec, "recall": rec, "f1": f1,
        "signal_accuracy": round(signal_ok / signal_tot, 3) if signal_tot else None,
        "signal_correct": f"{signal_ok}/{signal_tot}",
        "errors": errors,
    }
    out = HERE / "results" / "summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2))

    print(f"\n=== exp14 wiki-refresh drift detection @ scale (N={n} pages) ===")
    print(f"  scanned={res['scanned']} detected_drifted={res['drifted_count']}")
    print(f"  precision={prec} recall={rec} F1={f1}  (tp={tp} fp={fp} fn={fn} tn={tn})")
    print(f"  signal (all/some-refs-gone) accuracy: {signal_ok}/{signal_tot}")
    for e in errors[:10]:
        print(f"    ERR {e}")
    if not errors:
        print("    no errors — drift + signal classification exact at scale")
    print(f"  results: {out}")
    return 0 if (f1 == 1.0 and not errors) else 1


if __name__ == "__main__":
    sys.exit(main())
