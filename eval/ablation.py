#!/usr/bin/env python3
"""H1 — ablation / attribution harness (deterministic).

Answers "which internal rule actually earns its keep?" by disabling one
rule/feature at a time and measuring how the skill's decisions change on a
labeled corpus. For each ablated rule it reports:

  - flips:     # of corpus cases whose verdict changed vs the full skill
  - acc_delta: accuracy(ablated) - accuracy(full)   (negative = rule helps)

Interpretation (this is the actionable part, the reason the harness exists):
  - flips == 0            → the rule changes NO decision on this corpus: either
                            dead weight (trim candidate) or a corpus gap.
  - acc_delta < 0         → removing it HURTS accuracy: load-bearing, keep.
  - acc_delta > 0         → removing it HELPS accuracy: the rule is net-HARMFUL
                            on the corpus — a real fix candidate.
  - acc_delta == 0, flips>0 → changes decisions but net-neutral: redundant-ish.

Reuses the existing labeled corpora (no new fixtures). Run:
  python3 eval/ablation.py            # all skills, human report
  python3 eval/ablation.py --json     # machine report
Exit 1 only if a rule is net-HARMFUL (acc_delta > 0) — a genuine defect signal,
not a flaky threshold. 0-flip rules are reported as warnings, not failures
(corpus-incompleteness must not break CI).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "sims"))
from _lib import import_skill_module, repo_root  # noqa: E402

REPO = repo_root()


# --------------------------- write-gate ------------------------------------

def ablate_write_gate() -> dict:
    wg = import_skill_module("write-gate", "write_gate")
    corpus = [json.loads(l) for l in
              (REPO / "eval/exp3_classifiers/write_gate_labeled.jsonl").read_text().splitlines() if l.strip()]
    thr = wg.DEFAULT_THRESHOLD

    def run(weights, require_why):
        verdicts, correct = [], 0
        for c in corpus:
            s = wg.score_text(c["text"], c["kind"], weights=weights)
            passed, _ = wg.decide(s, c["kind"], thr, require_why)
            verdicts.append(passed)
            correct += int(passed == (c["label"] == "keep"))
        return verdicts, correct / len(corpus)

    base_v, base_acc = run(wg.DEFAULT_WEIGHTS, True)
    rows = []
    # one row per signal weight (zeroed)
    for feat in wg.DEFAULT_WEIGHTS:
        w = dict(wg.DEFAULT_WEIGHTS); w[feat] = 0.0
        v, acc = run(w, True)
        rows.append({"rule": f"weight:{feat}",
                     "flips": sum(a != b for a, b in zip(v, base_v)),
                     "acc_delta": round(acc - base_acc, 4)})
    # the why-gate (a hard reject path, independent of score)
    v, acc = run(wg.DEFAULT_WEIGHTS, False)
    rows.append({"rule": "why_gate(require_why)",
                 "flips": sum(a != b for a, b in zip(v, base_v)),
                 "acc_delta": round(acc - base_acc, 4)})
    return {"skill": "write-gate", "n": len(corpus), "acc_reliable": True,
            "baseline_acc": round(base_acc, 4), "rules": rows}


# --------------------------- prompt-triage ---------------------------------

def ablate_prompt_triage() -> dict:
    import os
    os.environ.setdefault("AGENTS_TRIAGE_NO_OLLAMA", "1")
    m = import_skill_module("prompt-triage", "classify")
    corpus = [json.loads(l) for l in
              (REPO / "eval/exp3_classifiers/triage_labeled.jsonl").read_text().splitlines() if l.strip()]

    def decision(p):
        # the routing decision a guard can change: (does it emit, tier, source)
        emitted = bool(m.emit_context(p, use_ollama_fallback=False))
        r = m.classify(p, use_ollama_fallback=False)
        return (emitted, r.get("tier"), r.get("agent"))

    def accuracy():
        ok = 0
        for c in corpus:
            r = m.classify(c["prompt"], use_ollama_fallback=False)
            # "correct" = tier matches when we route; bypass cases must stay non-emitting
            if c.get("expect_bypass"):
                ok += int(not bool(m.emit_context(c["prompt"], use_ollama_fallback=False)))
            else:
                ok += int(r.get("tier") == c.get("expected_tier"))
        return ok / len(corpus)

    base_dec = [decision(c["prompt"]) for c in corpus]
    base_acc = accuracy()

    # each guard: a (save, restore) monkeypatch that disables it
    guards = {
        "context-guard(_needs_session_context)": ("_needs_session_context", lambda p: False),
        "brief-gate(_multi_objective)": ("_multi_objective", lambda p: False),
        "complex-hints(_looks_complex)": ("_looks_complex", lambda p: False),
    }
    rows = []
    for name, (attr, stub) in guards.items():
        if not hasattr(m, attr):
            continue
        orig = getattr(m, attr)
        setattr(m, attr, stub)
        try:
            dec = [decision(c["prompt"]) for c in corpus]
            acc = accuracy()
        finally:
            setattr(m, attr, orig)
        rows.append({"rule": name,
                     "flips": sum(a != b for a, b in zip(dec, base_dec)),
                     "acc_delta": round(acc - base_acc, 4)})
    # length-gate via the constant
    orig = m.LENGTH_GATE_CHARS
    m.LENGTH_GATE_CHARS = 10 ** 9
    try:
        dec = [decision(c["prompt"]) for c in corpus]; acc = accuracy()
    finally:
        m.LENGTH_GATE_CHARS = orig
    rows.append({"rule": "length-gate(LENGTH_GATE_CHARS)",
                 "flips": sum(a != b for a, b in zip(dec, base_dec)),
                 "acc_delta": round(acc - base_acc, 4)})
    # acc_reliable=False: the triage corpus's expected_tier/expected_model schema
    # predates the current defer-heavy / fail-closed / platform-only classifier
    # (context-guard, brief-gate, short-unmatched all deliberately return
    # unknown/hard/defer that the old schema cannot express). So acc_delta is
    # NOT a valid defect signal here — only the FLIP counts (which guard changes
    # which decision) are trustworthy. Never raise a "harmful" verdict from it.
    return {"skill": "prompt-triage", "n": len(corpus), "acc_reliable": False,
            "baseline_acc": round(base_acc, 4),
            "baseline_note": "acc indicative only — corpus schema predates current guards",
            "rules": rows}


# ablate_cache_lint removed: cache-lint deleted (Great Pruning A2, 2026-07-22,
# zero clean-signal usage) — see skills/SKILLS_INDEX.md "Removed after measurement".

SKILLS = [ablate_write_gate, ablate_prompt_triage]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    reports = [fn() for fn in SKILLS]
    harmful = []   # acc_delta > 0 on an acc_reliable skill => net-harmful (defect)
    dead = []      # flips == 0 => no effect on corpus (review)
    for rep in reports:
        for r in rep["rules"]:
            # Only trust acc_delta where the corpus gold cleanly maps to outputs.
            if rep.get("acc_reliable") and r["acc_delta"] > 0:
                harmful.append((rep["skill"], r["rule"], r["acc_delta"]))
            if r["flips"] == 0:
                dead.append((rep["skill"], r["rule"]))
    if os.environ.get("BRAINER_CHECK_NO_WRITE") != "1":
        out_dir = REPO / "eval/results"; out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "ablation.json").write_text(json.dumps(
            {"reports": reports, "harmful": harmful, "dead": dead}, indent=2) + "\n")
    if args.json:
        print(json.dumps({"reports": reports, "harmful": harmful, "dead": dead}, indent=2))
        return 1 if harmful else 0
    for rep in reports:
        accnote = "" if rep.get("acc_reliable") else "  [acc indicative — flips are the signal]"
        print(f"\n=== {rep['skill']}  (n={rep['n']}, baseline acc {rep['baseline_acc']}){accnote} ===")
        for r in sorted(rep["rules"], key=lambda x: (x["acc_delta"], -x["flips"])):
            if rep.get("acc_reliable"):
                tag = "  HARMFUL" if r["acc_delta"] > 0 else ("  dead?" if r["flips"] == 0 else "")
            else:
                tag = "  unexercised(corpus)" if r["flips"] == 0 else ""
            print(f"  {r['rule']:42} flips={r['flips']:3}  acc_delta={r['acc_delta']:+.4f}{tag}")
    print()
    if harmful:
        print("NET-HARMFUL rules (removing IMPROVES accuracy on a reliable corpus — real fix candidates):")
        for s, r, d in harmful:
            print(f"  - {s}: {r} (+{d})")
    if dead:
        print("0-flip rules (not decisive on this corpus — low-impact/defense-in-depth OR a corpus gap;")
        print("             do NOT trim on this signal alone — confirm against inputs the corpus lacks):")
        for s, r in dead:
            print(f"  - {s}: {r}")
    if not harmful:
        print("\nNo net-harmful rule on any reliable corpus. Skills are well-tuned on what is measured.")
    return 1 if harmful else 0


if __name__ == "__main__":
    sys.exit(main())
