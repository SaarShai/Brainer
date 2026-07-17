#!/usr/bin/env python3
"""Score a 500-case trigger result file against preregistered gates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from cases import case_digest, trigger_cases
from statistics import trigger_metrics, wilson_upper_one_sided


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("results", type=Path, help="JSONL rows with id and fired")
    ap.add_argument("--profile", choices=["frontier", "shadow", "legacy", "off"], default="frontier")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    corpus = trigger_cases()
    observed = {r["id"]: bool(r["fired"]) for r in
                (json.loads(line) for line in args.results.read_text().splitlines() if line.strip())}
    missing = [c["id"] for c in corpus if c["id"] not in observed]
    if missing:
        raise SystemExit(f"missing {len(missing)} cases (first: {missing[0]})")
    metrics = trigger_metrics([c["profile_expect"][args.profile] == "fire" for c in corpus],
                              [observed[c["id"]] for c in corpus])
    hard_negatives = [c for c in corpus if c["expect"] == "silent"]
    hard_fp = sum(observed[c["id"]] for c in hard_negatives)
    hard_rate = hard_fp / len(hard_negatives)
    hard_upper = wilson_upper_one_sided(hard_fp, len(hard_negatives))
    suppressed = [c for c in corpus if c["expect"] == "fire" and
                  c["profile_expect"][args.profile] == "silent"]
    suppressed_unexpected = sum(observed[c["id"]] for c in suppressed)
    metrics["gates"]["false_injection_below_1pct"] = hard_rate < 0.01
    metrics["gates"]["false_injection_upper_below_1pct"] = hard_upper < 0.01
    metrics["gates"]["policy_suppressed_cases_silent"] = suppressed_unexpected == 0
    report = {"corpus_version": "skills-effectiveness-v1", "corpus_sha256": case_digest(corpus),
              "cases": len(corpus),
              "semantic_positives": sum(c["expect"] == "fire" for c in corpus),
              "profile": args.profile,
              "profile_expected_emissions": sum(c["profile_expect"][args.profile] == "fire" for c in corpus),
              "hard_negative_false_injections": hard_fp,
              "hard_negative_false_injection_rate": hard_rate,
              "hard_negative_false_injection_upper_95_one_sided": hard_upper,
              "policy_suppressed_unexpected_emissions": suppressed_unexpected,
              **metrics}
    if args.profile == "shadow":
        shadow_rows = [json.loads(line) for line in args.results.read_text().splitlines() if line.strip()]
        expected_suppressed = [r for r in shadow_rows if r.get("kind") in {"correction", "error_loop"}]
        report["shadow_suppressed_telemetry_complete"] = bool(expected_suppressed) and all(
            r.get("suppressed_probe_ids") for r in expected_suppressed)
        report["shadow_frontier_output_identical"] = all(r.get("frontier_output_identical") for r in shadow_rows)
        metrics["gates"]["shadow_suppressed_telemetry_complete"] = report["shadow_suppressed_telemetry_complete"]
        metrics["gates"]["shadow_frontier_output_identical"] = report["shadow_frontier_output_identical"]
    print(json.dumps(report, indent=2) if args.json else report)
    return 0 if all(metrics["gates"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
