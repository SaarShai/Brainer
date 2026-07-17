#!/usr/bin/env python3
"""Pair valid campaign outcomes and apply preregistered decision gates."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from statistics import exact_mcnemar, paired_bootstrap_delta, paired_sign_test


def median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def load_campaign(root: Path) -> tuple[list[dict], list[dict]]:
    rows = []
    for path in sorted((root / "outcomes").glob("*.json")):
        row = json.loads(path.read_text())
        if (row.get("record_status") == "completed" and row.get("arm_valid") and
                row.get("returncode") == 0):
            rows.append(row)
    blockers = []
    for path in sorted((root / "blockers").glob("*.json")):
        blockers.append(json.loads(path.read_text()))
    return rows, blockers


def _attempt_cost(rows: list[dict], blockers: list[dict]) -> dict:
    partials = [b.get("partial_record") for b in blockers if isinstance(b.get("partial_record"), dict)]
    records = rows + partials
    costs = [r.get("monetary_cost_usd") for r in records if isinstance(r.get("monetary_cost_usd"), (int, float))]
    return {"attempted": len(rows) + len(blockers), "valid": len(rows),
            "cost_usd_known_total": sum(costs) if costs else None,
            "cost_missing_attempts": len(rows) + len(blockers) - len(costs),
            "cost_per_attempted_usd": sum(costs) / (len(rows) + len(blockers)) if costs and rows + blockers else None,
            "cost_per_valid_usd": sum(costs) / len(rows) if costs and rows else None}


def compare(off: list[dict], treatment: list[dict], off_blockers: list[dict] | None = None,
            treatment_blockers: list[dict] | None = None) -> dict:
    off_blockers, treatment_blockers = off_blockers or [], treatment_blockers or []
    left = {r["case"]["id"]: r for r in off}
    right = {r["case"]["id"]: r for r in treatment}
    ids = sorted(set(left) & set(right))
    a, b = [left[i] for i in ids], [right[i] for i in ids]
    attempts_off = len(off) + len(off_blockers)
    attempts_treatment = len(treatment) + len(treatment_blockers)
    exclusions = {"off": len(off_blockers) / attempts_off if attempts_off else None,
                  "treatment": len(treatment_blockers) / attempts_treatment if attempts_treatment else None}
    if not ids:
        return {"pairs": 0, "status": "insufficient", "exclusion_rates": exclusions,
                "cost": {"off": _attempt_cost(off, off_blockers),
                         "treatment": _attempt_cost(treatment, treatment_blockers)}}
    ap = [bool(r["deterministic_task_pass"]) for r in a]
    bp = [bool(r["deterministic_task_pass"]) for r in b]
    boot = paired_bootstrap_delta([float(x) for x in ap], [float(x) for x in bp])
    scope_introduced = sum(not x.get("material_scope_violation") and y.get("material_scope_violation")
                           for x, y in zip(a, b))
    token_pairs = [(x.get("total_tokens_all_agents"), y.get("total_tokens_all_agents")) for x, y in zip(a, b)]
    token_pairs = [(x, y) for x, y in token_pairs if isinstance(x, (int, float)) and isinstance(y, (int, float))]
    overhead = None
    token_sign = None
    if token_pairs:
        ratios = [(y - x) / x for x, y in token_pairs if x]
        overhead = median(ratios) if ratios else None
        token_sign = paired_sign_test([x for x, _ in token_pairs], [y for _, y in token_pairs])
    complete_status = "complete" if len(ids) == 50 else "partial_no_verdict"
    protocol_valid = all(r.get("causal_protocol_valid", True) for r in a + b)
    if not protocol_valid:
        complete_status = "protocol_invalid_no_verdict"
    off_by_id = {**{r["case"]["id"]: bool(r["deterministic_task_pass"]) for r in off},
                 **{b.get("case_id"): True for b in off_blockers}}
    tx_by_id = {**{r["case"]["id"]: bool(r["deterministic_task_pass"]) for r in treatment},
                **{b.get("case_id"): False for b in treatment_blockers}}
    itt_ids = sorted((set(off_by_id) & set(tx_by_id)) - {None})
    itt_delta = (sum(tx_by_id[i] for i in itt_ids) - sum(off_by_id[i] for i in itt_ids)) / len(itt_ids) if itt_ids else None
    mcnemar = exact_mcnemar(ap, bp)
    return {"pairs": len(ids), "missing_pairs": 50 - len(ids),
            "pass_rate_off": sum(ap) / len(ap), "pass_rate_treatment": sum(bp) / len(bp),
            "pass_rate_delta": boot["delta"], "pass_delta_ci95": boot["ci95"],
            "mcnemar": mcnemar, "discordant_pairs": mcnemar["discordant"],
            "power_limit": {"underpowered_discordance": mcnemar["discordant"] < 10,
                            "five_percentage_points_equals_cases": 2.5},
            "scope_violations_introduced": scope_introduced,
            "median_token_overhead": overhead, "token_sign_test": token_sign,
            "exclusion_rates": exclusions,
            "differential_exclusion_rate": (exclusions["treatment"] - exclusions["off"]
                if exclusions["treatment"] is not None and exclusions["off"] is not None else None),
            "itt_worst_case": {"paired_attempts": len(itt_ids), "pass_rate_delta": itt_delta,
                               "treatment_blocker_as_failure": True, "off_blocker_as_success": True},
            "complete_case_secondary": True,
            "cost": {"off": _attempt_cost(off, off_blockers),
                     "treatment": _attempt_cost(treatment, treatment_blockers)},
            "causal_protocol_valid": protocol_valid, "status": complete_status}


def gate(result: dict, *, mid_tier: bool = False, primary: bool = False) -> str:
    if result.get("status") != "complete":
        return "NO_VERDICT_PROTOCOL" if result.get("status") == "protocol_invalid_no_verdict" else "NO_VERDICT_INCOMPLETE"
    if primary and result.get("holm_adjusted_p", 1.0) >= 0.05:
        return "NO_VERDICT_MULTIPLICITY"
    delta = result["pass_rate_delta"]
    low, high = result["pass_delta_ci95"]
    overhead = result["median_token_overhead"]
    scope = result["scope_violations_introduced"]
    if delta <= -0.05 or scope:
        return "DISABLE_HARMFUL"
    if mid_tier and delta >= 0.05 and low > 0:
        return "DEMOTE_ROLE_BRIEF"
    if delta >= 0.05 and low > 0 and scope == 0 and overhead is not None and overhead <= 0.15:
        return "KEEP_DEFAULT_ON"
    if high <= 0 or (delta <= 0 and overhead is not None and overhead >= 0.10):
        return "RETIRE"
    if overhead is not None and overhead <= 0.10:
        return "MANUAL_QUARANTINE"
    return "NO_VERDICT_AMBIGUOUS"


def analyze(rows: list[dict], blockers: list[dict] | None = None) -> dict:
    blockers = blockers or []
    groups = defaultdict(list)
    for row in rows:
        groups[(row["candidate"], row["lane"], row["arm"], row.get("treatment_kind", "BODY_CARRIER"))].append(row)
    blocked_groups = defaultdict(list)
    for row in blockers:
        blocked_groups[(row.get("candidate"), row.get("lane"), row.get("arm"),
                        row.get("treatment_kind", "BODY_CARRIER"))].append(row)
    comparisons = []
    candidates = sorted({r["candidate"] for r in rows if r["candidate"] != "stack-comparison"})
    for candidate in candidates:
        treatment_kind = "PROBE_HOOK" if candidate == "prompt-triage" else "BODY_CARRIER"
        for lane in sorted({k[1] for k in groups if k[0] == candidate and k[3] == treatment_kind}):
            off = groups.get((candidate, lane, "OFF", treatment_kind), [])
            for arm in ("FULL", "COMPACT", "PLACEBO"):
                result = compare(off, groups.get((candidate, lane, arm, treatment_kind), []),
                    blocked_groups.get((candidate, lane, "OFF", treatment_kind), []),
                    blocked_groups.get((candidate, lane, arm, treatment_kind), []))
                primary = arm == "FULL" and lane in {"codex-default", "claude-opus"}
                result.update({"candidate": candidate, "lane": lane, "arm_vs_off": arm,
                               "treatment_kind": treatment_kind,
                               "primary_endpoint": "deterministic_task_pass" if primary else None,
                               "primary_comparison": primary})
                comparisons.append(result)
    for lane in sorted({r["lane"] for r in comparisons if r["primary_comparison"]}):
        family = sorted((r for r in comparisons if r["primary_comparison"] and r["lane"] == lane),
                        key=lambda r: r.get("mcnemar", {}).get("p_two_sided", 1.0))
        running = 0.0
        for rank, result in enumerate(family):
            raw = result.get("mcnemar", {}).get("p_two_sided", 1.0)
            running = max(running, min(1.0, raw * (len(family) - rank)))
            result["holm_adjusted_p"] = running
            result["multiplicity_family"] = f"{lane}:FULL-vs-OFF:{len(family)}-candidates"
    for result in comparisons:
        result["gate"] = gate(result, mid_tier="mid-tier" in result["lane"],
                              primary=result["primary_comparison"])
    stack_comparisons = []
    for lane in sorted({k[1] for k in groups if k[0] == "stack-comparison" and k[3] == "STACK_RESIDENT_CONTEXT"}):
        installed = groups.get(("stack-comparison", lane, "installed", "STACK_RESIDENT_CONTEXT"), [])
        for arm in ("minimal-protection", "placebo"):
            result = compare(installed, groups.get(("stack-comparison", lane, arm, "STACK_RESIDENT_CONTEXT"), []),
                blocked_groups.get(("stack-comparison", lane, "installed", "STACK_RESIDENT_CONTEXT"), []),
                blocked_groups.get(("stack-comparison", lane, arm, "STACK_RESIDENT_CONTEXT"), []))
            result.update({"candidate": "stack-comparison", "lane": lane,
                           "arm_vs_installed": arm,
                           "treatment_kind": "STACK_RESIDENT_CONTEXT",
                           "gate": gate(result) if arm == "minimal-protection" else "PLACEBO_CONTROL"})
            stack_comparisons.append(result)
    return {"schema_version": 2, "valid_outcomes": len(rows), "blocked_attempts": len(blockers),
            "analysis_policy": "ITT worst-case primary for exclusions; complete-case secondary; Holm within host family",
            "comparisons": comparisons,
            "stack_comparisons": stack_comparisons,
            "probe_hook_protocol_blockers": [b for b in blockers if b.get("treatment_kind") == "PROBE_HOOK"],
            "note": "Safety-exception and subjective gates require separately recorded blinded P0/P1 labels."}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("campaign", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    outcomes, blockers = load_campaign(args.campaign)
    report = analyze(outcomes, blockers)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"valid_outcomes": report["valid_outcomes"],
                      "comparisons": len(report["comparisons"]),
                      "stack_comparisons": len(report["stack_comparisons"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
