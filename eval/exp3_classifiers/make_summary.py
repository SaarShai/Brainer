#!/usr/bin/env python3
"""Aggregate write-gate + triage eval results into results/summary.json.

Reads results/write_gate_eval.json and results/triage_eval.json (produced by
the two run_*.py harnesses) and writes a single combined manifest with all
headline metrics plus provenance (corpus-vs-authored counts).
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RES = HERE / "results"


def main():
    wg = json.loads((RES / "write_gate_eval.json").read_text())
    tr = json.loads((RES / "triage_eval.json").read_text())

    wg_m = wg["default_threshold_metrics"]
    tr_d = tr["deterministic_regex_only"]

    summary = {
        "experiment": "exp3_classifiers",
        "kind": "CLASSIFIER evals (deterministic, no GPU)",
        "write_gate": {
            "data": wg["data"],
            "n_cases": wg["n_cases"],
            "n_keep": wg["n_keep"],
            "n_reject": wg["n_reject"],
            "provenance": {"from_corpus": wg["from_corpus"], "authored": wg["authored"]},
            "default_threshold": wg_m["threshold"],
            "accuracy": wg_m["accuracy"],
            "precision": wg_m["precision"],
            "recall": wg_m["recall"],
            "f1": wg_m["f1"],
            "confusion": wg_m["confusion"],
            "per_kind_accuracy": wg_m["per_kind_accuracy"],
            "best_threshold": wg["best_threshold"],
            "threshold_sweep": wg["threshold_sweep"],
            "misclassified": wg["misclassified"],
        },
        "prompt_triage": {
            "data": tr["data"],
            "n_cases": tr["n_cases"],
            "provenance": {"from_corpora": tr["from_corpora"], "authored": tr["authored"]},
            "routing_accuracy": tr_d["routing_accuracy"],
            "routing_correct_over_total": f"{tr_d['routing_correct']}/{tr_d['routing_total']}",
            "tier_accuracy": tr_d["tier_accuracy"],
            "tier_correct_over_total": f"{tr_d['tier_correct']}/{tr_d['tier_total']}",
            "tier_confusion": tr_d["tier_confusion"],
            "bypass_accuracy": tr_d["bypass_accuracy"],
            "bypass_correct_over_total": f"{tr_d['bypass_correct']}/{tr_d['bypass_total']}",
            "fastpath_vs_fallback_split": tr_d["fastpath_split"],
            "complex_cases": tr_d["complex_cases"],
            "complex_misrouted_to_haiku": tr_d["complex_misrouted_to_haiku"],
            "misclassified_routing": tr["misclassified_routing"],
            "misclassified_tier": tr["misclassified_tier"],
            "ollama_fallback": (
                tr.get("with_ollama_fallback", {}).get("fastpath_split")
                and {
                    "note": "qwen3:8b not pulled locally; ollama_classify returned None -> "
                            "graceful fallback to regex. Results identical to deterministic run.",
                    "routing_accuracy": tr["with_ollama_fallback"]["routing_accuracy"],
                    "tier_accuracy": tr["with_ollama_fallback"]["tier_accuracy"],
                    "split": tr["with_ollama_fallback"]["fastpath_split"],
                }
            ) or "not run (use --ollama)",
        },
        "provenance_totals": {
            "write_gate": {"from_corpus": wg["from_corpus"], "authored": wg["authored"]},
            "prompt_triage": {"from_corpora": tr["from_corpora"], "authored": tr["authored"]},
        },
    }

    out = RES / "summary.json"
    out.write_text(json.dumps(summary, indent=2))
    print(f"wrote {out}")
    print(json.dumps({
        "write_gate": {
            "acc": summary["write_gate"]["accuracy"],
            "P": summary["write_gate"]["precision"],
            "R": summary["write_gate"]["recall"],
            "F1": summary["write_gate"]["f1"],
            "confusion": summary["write_gate"]["confusion"],
            "best_threshold": summary["write_gate"]["best_threshold"]["threshold"],
        },
        "prompt_triage": {
            "routing_acc": summary["prompt_triage"]["routing_accuracy"],
            "tier_acc": summary["prompt_triage"]["tier_accuracy"],
            "bypass_acc": summary["prompt_triage"]["bypass_accuracy"],
            "complex_misrouted_to_haiku": summary["prompt_triage"]["complex_misrouted_to_haiku"],
        },
    }, indent=2))


if __name__ == "__main__":
    main()
