#!/usr/bin/env python3
"""team_lead_eval — cost-structure measurement harness for team-lead's cost
claim (ORCHESTRATION.md Â§6: "orchestrator/worker splits measure 58–74% cheaper
than end-to-end top-model").

WHAT THIS MEASURES: token spend and its distribution across pricing tiers,
from real lane telemetry, plus one derived metric — cost_per_accepted_change
— and a counterfactual: the SAME total token volume priced entirely at the
frontier rate. WHAT THIS DOES NOT MEASURE: output QUALITY. A cheap lane that
produces garbage costs less per token and is NOT rewarded here as "efficient";
quality lift/regression is eval-gate's job (skills/eval-gate), not this tool's.
See EVAL.md for the full method writeup and the counterfactual's honesty
caveat (token-count parity is assumed, which likely UNDERSTATES real savings
per the 58–74% external anchor, or OVERSTATES them if frontier models are more
token-efficient per task — this tool cannot tell which without a paired run).

INPUTS (either or both; empty input is a valid, reportable state):

1. --trace <path>: JSONL written by skills/_shared/orchestration_trace.py
   (record_lane_event). Known fields: role, lane, vendor, ok, usage
   ({"prompt_tokens": int, "completion_tokens": int}), latency_ms,
   served_model, task_digest. Tolerant of missing/extra fields; malformed
   lines (bad JSON) are SKIPPED and counted, never fatal.

2. --lanes <path>: manual records (CSV or JSONL) for lanes whose token spend
   is reported out-of-band — the brief's stated case is Claude-harness Agent
   subagents, whose token totals are surfaced by the harness, not by
   orchestration_trace's dispatch path. Columns/fields: lane_label, tier,
   tokens, accepted (true/false). Malformed rows are SKIPPED and counted.

Records with no discoverable token count (no `usage` on a trace event, no
`tokens` on a manual record) are still counted in totals-by-tier bookkeeping
but flagged UNPRICED and excluded from cost math (there is nothing to price).

PRICING: a built-in $/Mtok table, one entry per tier (frontier, mid, small,
glm, local=0), overridable per-tier via BRAINER_PRICE_<TIER> (e.g.
BRAINER_PRICE_FRONTIER=15). These are placeholder ESTIMATES, not looked-up
real prices — absolute $ rot the day a vendor reprices; the durable output of
this tool is the RATIO (leader-share vs delegate-share, savings% vs the
frontier counterfactual), not the absolute dollar figure. Treat the $ column
as illustrative only.

GATE MODE: --gate --min-savings <pct> exits 1 (instead of 0) when savings% is
below the threshold, OR when there are zero accepted lanes (a savings% is not
even meaningful with no accepted work) — so an unattended run can fail loudly
on regression instead of silently reporting a number nobody reads.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------
# Tier pricing (placeholder $/Mtok estimates; override with BRAINER_PRICE_<TIER>)
# --------------------------------------------------------------------------

TIERS = ("frontier", "mid", "small", "glm", "local")

# Illustrative only — see module docstring. Blended $/Mtok across
# prompt+completion at a rough real-world ratio; NOT a vendor-quoted price.
DEFAULT_PRICE_PER_MTOK: dict[str, float] = {
    "frontier": 12.0,   # e.g. Opus/GPT-5.x-class flagship blended rate
    "mid": 3.0,          # e.g. Sonnet-class
    "small": 0.5,        # e.g. Haiku-class / research-lite
    "glm": 0.3,          # glm-5.2 via z.ai — near-zero
    "local": 0.0,        # ollama — no metered cost
}

# lane (orchestration_trace vocabulary) -> pricing tier. A lane/vendor not in
# this table falls back to "mid" (a deliberately conservative middle guess,
# never silently priced as free or as the most expensive tier).
LANE_TO_TIER: dict[str, str] = {
    "gpt": "frontier",
    "claude": "mid",
    "gemini": "frontier",
    "glm": "glm",
    "local": "local",
}

FALLBACK_TIER = "mid"

UNPRICED = "UNPRICED"


def price_per_mtok(tier: str) -> float:
    """$/Mtok for `tier`, honoring BRAINER_PRICE_<TIER> if set."""
    env_key = f"BRAINER_PRICE_{tier.upper()}"
    override = os.environ.get(env_key)
    if override:
        try:
            return float(override)
        except ValueError:
            pass  # malformed override -> fall through to the built-in default
    return DEFAULT_PRICE_PER_MTOK.get(tier, DEFAULT_PRICE_PER_MTOK[FALLBACK_TIER])


# --------------------------------------------------------------------------
# Record loading
# --------------------------------------------------------------------------

def _tokens_from_usage(usage: Any) -> int | None:
    if not isinstance(usage, dict):
        return None
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    total = usage.get("total_tokens")
    if isinstance(total, (int, float)):
        return int(total)
    if isinstance(prompt, (int, float)) or isinstance(completion, (int, float)):
        return int(prompt or 0) + int(completion or 0)
    return None


def load_trace(path: str) -> tuple[list[dict[str, Any]], int]:
    """Read one JSONL trace file into normalized records.

    Returns (records, malformed_count). Never raises — a missing file yields
    ([], 0); a bad JSON line is skipped and counted, not fatal.
    """
    records: list[dict[str, Any]] = []
    malformed = 0
    p = Path(path)
    if not p.exists():
        return records, malformed
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except Exception:
        return records, malformed
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except Exception:
            malformed += 1
            continue
        if not isinstance(event, dict):
            malformed += 1
            continue
        lane = event.get("lane") or ""
        role = event.get("role") or ""
        tier = LANE_TO_TIER.get(str(lane).lower(), FALLBACK_TIER)
        tokens = _tokens_from_usage(event.get("usage"))
        # `ok` (dispatch succeeded) is used as an ACCEPTANCE PROXY for trace
        # records — it is not the same thing as "the change was accepted by
        # a reviewer", only the closest signal orchestration_trace carries
        # today. See EVAL.md caveat.
        ok = event.get("ok")
        accepted = bool(ok) if ok is not None else None
        records.append({
            "source": "trace",
            "lane_label": str(lane) or "unknown",
            "role": str(role) or "unknown",
            "tier": tier,
            "tokens": tokens,
            "accepted": accepted,
            "priced": tokens is not None,
        })
    return records, malformed


def _truthy(val: Any) -> bool:
    return str(val).strip().lower() in ("true", "1", "yes", "y", "accepted")


def load_manual_lanes(path: str) -> tuple[list[dict[str, Any]], int]:
    """Read manual lane records — CSV or JSONL, auto-detected by extension
    (falling back to sniffing the first non-blank line for JSON-ness).

    Fields: lane_label, tier, tokens, accepted. Malformed rows are skipped
    and counted, never fatal. `role` defaults to "delegate" (manual records
    are, per the brief, out-of-band builder/Agent-lane token totals — never
    the leader's own context).
    """
    records: list[dict[str, Any]] = []
    malformed = 0
    p = Path(path)
    if not p.exists():
        return records, malformed
    try:
        text = p.read_text(encoding="utf-8")
    except Exception:
        return records, malformed
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return records, malformed

    is_jsonl = p.suffix.lower() == ".jsonl" or lines[0].lstrip().startswith("{")

    if is_jsonl:
        for line in lines:
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError("not an object")
            except Exception:
                malformed += 1
                continue
            rec = _normalize_manual_row(row)
            if rec is None:
                malformed += 1
                continue
            records.append(rec)
    else:
        try:
            reader = csv.DictReader(lines)
        except Exception:
            return records, len(lines)
        for row in reader:
            if row is None:
                malformed += 1
                continue
            rec = _normalize_manual_row(row)
            if rec is None:
                malformed += 1
                continue
            records.append(rec)
    return records, malformed


def _normalize_manual_row(row: dict[str, Any]) -> dict[str, Any] | None:
    lane_label = row.get("lane_label")
    if lane_label is None or str(lane_label).strip() == "":
        return None  # a row with no lane identity is not a usable record
    tier_raw = str(row.get("tier") or "").strip().lower()
    tier = tier_raw if tier_raw in DEFAULT_PRICE_PER_MTOK else FALLBACK_TIER
    tokens_raw = row.get("tokens")
    tokens: int | None
    try:
        tokens = int(float(tokens_raw)) if tokens_raw not in (None, "") else None
    except (ValueError, TypeError):
        tokens = None
    accepted_raw = row.get("accepted")
    accepted = _truthy(accepted_raw) if accepted_raw not in (None, "") else None
    return {
        "source": "manual",
        "lane_label": str(lane_label),
        "role": "delegate",
        "tier": tier,
        "tokens": tokens,
        "accepted": accepted,
        "priced": tokens is not None,
    }


# --------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------

def aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_tier: dict[str, dict[str, Any]] = {
        t: {"tokens": 0, "cost": 0.0, "lanes": 0, "unpriced_lanes": 0} for t in TIERS
    }
    leader_tokens = 0
    delegate_tokens = 0
    accepted_lanes = 0
    rejected_lanes = 0
    unknown_accept_lanes = 0
    total_tokens = 0
    total_cost = 0.0
    unpriced_total = 0

    for rec in records:
        tier = rec["tier"] if rec["tier"] in by_tier else FALLBACK_TIER
        bucket = by_tier[tier]
        bucket["lanes"] += 1
        tokens = rec["tokens"]
        if tokens is None:
            bucket["unpriced_lanes"] += 1
            unpriced_total += 1
        else:
            bucket["tokens"] += tokens
            cost = tokens / 1_000_000.0 * price_per_mtok(tier)
            bucket["cost"] += cost
            total_tokens += tokens
            total_cost += cost
            if rec["role"] == "leader":
                leader_tokens += tokens
            else:
                delegate_tokens += tokens

        if rec["accepted"] is True:
            accepted_lanes += 1
        elif rec["accepted"] is False:
            rejected_lanes += 1
        else:
            unknown_accept_lanes += 1

    counterfactual_cost = total_tokens / 1_000_000.0 * price_per_mtok("frontier")
    cost_per_accepted = (total_cost / accepted_lanes) if accepted_lanes else None
    savings_pct = (1.0 - (total_cost / counterfactual_cost)) if counterfactual_cost > 0 else None
    leader_share = (leader_tokens / total_tokens) if total_tokens else None
    delegate_share = (delegate_tokens / total_tokens) if total_tokens else None

    return {
        "by_tier": by_tier,
        "total_tokens": total_tokens,
        "total_cost": total_cost,
        "unpriced_lane_count": unpriced_total,
        "leader_tokens": leader_tokens,
        "delegate_tokens": delegate_tokens,
        "leader_share": leader_share,
        "delegate_share": delegate_share,
        "accepted_lanes": accepted_lanes,
        "rejected_lanes": rejected_lanes,
        "unknown_accept_lanes": unknown_accept_lanes,
        "cost_per_accepted_change": cost_per_accepted,
        "counterfactual_cost": counterfactual_cost,
        "savings_pct": savings_pct,
    }


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def _money(x: float) -> str:
    return f"${x:,.4f}"


def render_markdown(agg: dict[str, Any], *, malformed_trace: int, malformed_manual: int) -> str:
    lines: list[str] = []
    lines.append("# team-lead cost eval")
    lines.append("")
    lines.append("Cost-STRUCTURE only — see EVAL.md; this does NOT measure output quality.")
    lines.append("")
    lines.append("## Per-tier totals")
    lines.append("")
    lines.append("| tier | lanes | unpriced | tokens | est. cost | $/Mtok |")
    lines.append("|---|---|---|---|---|---|")
    for tier in TIERS:
        b = agg["by_tier"][tier]
        lines.append(
            f"| {tier} | {b['lanes']} | {b['unpriced_lanes']} | {b['tokens']:,} | "
            f"{_money(b['cost'])} | {price_per_mtok(tier):.2f} |"
        )
    lines.append("")
    lines.append("## Leader vs delegate share")
    lines.append("")
    lines.append(f"- leader tokens: {agg['leader_tokens']:,} ({_pct(agg['leader_share'])})")
    lines.append(f"- delegate tokens: {agg['delegate_tokens']:,} ({_pct(agg['delegate_share'])})")
    lines.append("")
    lines.append("## Acceptance")
    lines.append("")
    lines.append(f"- accepted lanes: {agg['accepted_lanes']}")
    lines.append(f"- rejected lanes: {agg['rejected_lanes']}")
    lines.append(f"- unknown-acceptance lanes: {agg['unknown_accept_lanes']}")
    lines.append(f"- unpriced lane records (no usage/tokens found): {agg['unpriced_lane_count']}")
    lines.append("")
    lines.append("## Cost")
    lines.append("")
    lines.append(f"- total tokens (priced records only): {agg['total_tokens']:,}")
    lines.append(f"- total blended cost: {_money(agg['total_cost'])}")
    cpac = agg["cost_per_accepted_change"]
    lines.append(
        "- cost_per_accepted_change: "
        + (_money(cpac) if cpac is not None else "n/a (0 accepted lanes)")
    )
    lines.append("")
    lines.append("## Counterfactual — same tokens, all at frontier rate")
    lines.append("")
    lines.append(f"- counterfactual cost: {_money(agg['counterfactual_cost'])}")
    lines.append(f"- savings%: {_pct(agg['savings_pct'])}")
    lines.append(
        "- CAVEAT: this counterfactual assumes TOKEN-COUNT PARITY — that a "
        "single frontier model doing the whole task end-to-end would burn "
        "the same number of tokens this lane split burned. It might use "
        "fewer (no brief/report overhead, no re-derivation across lane "
        "boundaries) or more (no cheap-lane parallel bulk work). The "
        "external anchor for orchestrator/worker savings is 58–74% cheaper "
        "than end-to-end top-model (architect-loop DESIGN.md §2, PEAR) — "
        "treat the number above as this run's structural ratio, not a "
        "validated absolute dollar saving."
    )
    lines.append("")
    lines.append("## Input health")
    lines.append("")
    lines.append(f"- malformed trace lines skipped: {malformed_trace}")
    lines.append(f"- malformed manual rows skipped: {malformed_manual}")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="team_lead_eval.py",
        description="Cost-structure eval for team-lead: cost_per_accepted_change "
                    "and savings vs an all-frontier counterfactual, from real lane telemetry.",
    )
    ap.add_argument("--trace", help="path to a JSONL orchestration_trace file")
    ap.add_argument("--lanes", help="path to a manual lane-records CSV or JSONL file")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of markdown")
    ap.add_argument("--gate", action="store_true",
                    help="exit non-zero if savings%% < --min-savings, or 0 accepted lanes")
    ap.add_argument("--min-savings", type=float, default=0.0,
                    help="gate threshold, 0-100 (percent); only used with --gate")
    args = ap.parse_args(argv)

    if not args.trace and not args.lanes:
        print("team_lead_eval: at least one of --trace or --lanes is required", file=sys.stderr)
        return 2

    records: list[dict[str, Any]] = []
    malformed_trace = 0
    malformed_manual = 0

    if args.trace:
        trace_records, malformed_trace = load_trace(args.trace)
        records.extend(trace_records)
    if args.lanes:
        manual_records, malformed_manual = load_manual_lanes(args.lanes)
        records.extend(manual_records)

    agg = aggregate(records)

    if args.json:
        payload = dict(agg)
        payload["malformed_trace_lines"] = malformed_trace
        payload["malformed_manual_rows"] = malformed_manual
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(render_markdown(agg, malformed_trace=malformed_trace, malformed_manual=malformed_manual))

    if args.gate:
        savings = agg["savings_pct"]
        if agg["accepted_lanes"] == 0:
            print("GATE FAIL: 0 accepted lanes — savings%% is not meaningful", file=sys.stderr)
            return 1
        if savings is None or savings * 100.0 < args.min_savings:
            print(
                f"GATE FAIL: savings {_pct(savings)} below --min-savings {args.min_savings}%",
                file=sys.stderr,
            )
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
