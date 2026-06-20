#!/usr/bin/env python3
"""Cost-quality eval harness for the prompt-triage router.

WHY THIS EXISTS (research 2026-06-19, see wiki/projects/delegate-router.md):
production-router literature is unanimous (3-0) that you must benchmark a router
against simple BEST-SINGLE baselines on a cost-quality basis before trusting it
(RouterBench arXiv:2403.12031 AIQ; "benchmark the simple baseline first"
arXiv:2505.12601). The unit suite (test_classify.py) checks per-rule correctness;
it does NOT measure whether routing as a whole beats "always use opus".

This is a deliberately SIMPLE baseline benchmark, not full AIQ (which needs
per-prompt per-model quality labels we don't have). It is the verifier that is
SEPARATE from the router it grades.

GATE (exit code): the asymmetric-cost error is routing a `needs_frontier` prompt
to a cheap worker (misroute-down) — that ships high-stakes work to a weak model.
The gate FAILS (exit 1) if misroute-down rate exceeds --max-misroute-down
(default 0.0). missed-savings (cheap prompt sent to opus) is only wasted cost, so
it is reported but does not fail the gate.

Run:  python3 router_eval.py [--corpus FILE] [--max-misroute-down 0.0] [--json]
Ollama is OFF here: the eval must be deterministic and reproducible.
"""
from __future__ import annotations
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from classify import classify  # noqa: E402

# Relative per-route cost weights (input-token $/M proxy; GLM coordinator is
# haiku + a cheap out-of-platform call, treated as ~haiku-tier for this proxy).
COST = {"haiku": 0.25, "sonnet": 3.0, "opus": 15.0}
GLM_COST = 0.5  # glm-executor: haiku coordinator + cheap z.ai call


def _routed_cheap(verdict: dict) -> bool:
    """A verdict counts as a cheap route iff it actually dispatches a non-opus
    worker. tier=hard or agent=none is a defer-to-main-model (frontier)."""
    if verdict.get("tier") == "hard" or verdict.get("agent") == "none":
        return False
    return True


def _route_cost(verdict: dict) -> float:
    if not _routed_cheap(verdict):
        return COST["opus"]
    if verdict.get("agent") == "glm-executor":
        return GLM_COST
    return COST.get(verdict.get("model", "opus"), COST["opus"])


def load_corpus(path: str) -> list[dict]:
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def evaluate(corpus: list[dict]) -> dict:
    n = len(corpus)
    misroute_down = []   # gold needs_frontier, router sent cheap (COSTLY)
    missed_savings = []  # gold cheap_ok, router sent opus (wasted cost)
    correct = 0
    router_cost = 0.0
    for row in corpus:
        gold = row["gold"]
        v = classify(row["prompt"], use_ollama_fallback=False)
        cheap = _routed_cheap(v)
        router_cost += _route_cost(v)
        if gold == "needs_frontier" and cheap:
            misroute_down.append({"prompt": row["prompt"], "routed": v.get("agent"),
                                  "model": v.get("model"), "source": v.get("source")})
        elif gold == "cheap_ok" and not cheap:
            missed_savings.append({"prompt": row["prompt"], "source": v.get("source")})
        else:
            correct += 1
    n_frontier = sum(1 for r in corpus if r["gold"] == "needs_frontier")
    n_cheap = sum(1 for r in corpus if r["gold"] == "cheap_ok")
    # Best-single baselines (the research's required reference points).
    always_opus_cost = COST["opus"] * n
    always_cheap_cost = COST["haiku"] * n  # naive floor
    return {
        "n": n, "correct": correct, "accuracy": round(correct / n, 3) if n else 0.0,
        "misroute_down": {
            "count": len(misroute_down),
            "rate": round(len(misroute_down) / n_frontier, 3) if n_frontier else 0.0,
            "cases": misroute_down,
        },
        "missed_savings": {
            "count": len(missed_savings),
            "rate": round(len(missed_savings) / n_cheap, 3) if n_cheap else 0.0,
            "cases": [c["prompt"] for c in missed_savings],
        },
        "cost_proxy": {
            "router": round(router_cost, 2),
            "always_opus_baseline": round(always_opus_cost, 2),
            "vs_opus_pct": round(100 * router_cost / always_opus_cost, 1) if always_opus_cost else 0.0,
            "always_cheap_floor": round(always_cheap_cost, 2),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--corpus", default=os.path.join(here, "router_eval_corpus.jsonl"))
    ap.add_argument("--max-misroute-down", type=float, default=0.0,
                    help="gate: fail if misroute-down rate exceeds this (default 0.0)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    report = evaluate(load_corpus(args.corpus))
    gate_pass = report["misroute_down"]["rate"] <= args.max_misroute_down

    if args.json:
        print(json.dumps({**report, "gate_pass": gate_pass}, indent=2))
    else:
        r = report
        print(f"router accuracy:   {r['accuracy']:.0%} ({r['correct']}/{r['n']})")
        print(f"misroute-DOWN:     {r['misroute_down']['count']} "
              f"({r['misroute_down']['rate']:.0%} of needs_frontier)  <- gate")
        print(f"missed-savings:    {r['missed_savings']['count']} "
              f"({r['missed_savings']['rate']:.0%} of cheap_ok)  (cost only)")
        c = r["cost_proxy"]
        print(f"cost proxy:        router={c['router']}  vs always-opus={c['always_opus_baseline']}  "
              f"({c['vs_opus_pct']}% of baseline)")
        if r["misroute_down"]["cases"]:
            print("  misroute-down cases (HIGH-STAKES sent cheap):")
            for case in r["misroute_down"]["cases"]:
                print(f"    - {case['prompt'][:60]!r} -> {case['routed']}/{case['model']} [{case['source']}]")
        print(f"GATE: {'PASS' if gate_pass else 'FAIL'} "
              f"(misroute-down {r['misroute_down']['rate']:.0%} <= {args.max_misroute_down:.0%})")
    return 0 if gate_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
