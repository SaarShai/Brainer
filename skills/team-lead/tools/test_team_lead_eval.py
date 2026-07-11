#!/usr/bin/env python3
"""Tests for team_lead_eval.py — plain-python (no pytest dep), runnable
standalone. Shape mirrors skills/_shared/test_orchestration_trace.py: a list
of test_* functions, a main() that runs them and returns the failure count
(exit 0 == all pass).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import team_lead_eval as tle  # noqa: E402


def test_mixed_tiers_totals_and_shares():
    with tempfile.TemporaryDirectory() as td:
        trace = Path(td) / "lanes.jsonl"
        trace.write_text(
            "\n".join([
                json.dumps({"role": "leader", "lane": "gpt", "ok": True,
                            "usage": {"prompt_tokens": 1000, "completion_tokens": 1000}}),
                json.dumps({"role": "builder", "lane": "glm", "ok": True,
                            "usage": {"prompt_tokens": 5000, "completion_tokens": 5000}}),
                json.dumps({"role": "builder", "lane": "local", "ok": True,
                            "usage": {"prompt_tokens": 9000, "completion_tokens": 1000}}),
            ]) + "\n",
            encoding="utf-8",
        )
        records, malformed = tle.load_trace(str(trace))
        agg = tle.aggregate(records)
        return (
            malformed == 0
            and agg["total_tokens"] == 2000 + 10000 + 10000
            and agg["by_tier"]["frontier"]["tokens"] == 2000
            and agg["by_tier"]["glm"]["tokens"] == 10000
            and agg["by_tier"]["local"]["tokens"] == 10000
            and agg["leader_tokens"] == 2000
            and agg["delegate_tokens"] == 20000
            and agg["accepted_lanes"] == 3
        )


def test_unpriced_records_flagged_and_excluded_from_cost():
    with tempfile.TemporaryDirectory() as td:
        trace = Path(td) / "lanes.jsonl"
        trace.write_text(
            "\n".join([
                json.dumps({"role": "builder", "lane": "claude", "ok": True}),  # no usage
                json.dumps({"role": "builder", "lane": "claude", "ok": True,
                            "usage": {"prompt_tokens": 100, "completion_tokens": 100}}),
            ]) + "\n",
            encoding="utf-8",
        )
        records, malformed = tle.load_trace(str(trace))
        agg = tle.aggregate(records)
        return (
            malformed == 0
            and agg["unpriced_lane_count"] == 1
            and agg["by_tier"]["mid"]["unpriced_lanes"] == 1
            and agg["by_tier"]["mid"]["lanes"] == 2
            and agg["total_tokens"] == 200
        )


def test_zero_accepted_gate_fires():
    with tempfile.TemporaryDirectory() as td:
        trace = Path(td) / "lanes.jsonl"
        trace.write_text(
            json.dumps({"role": "builder", "lane": "gpt", "ok": False,
                        "usage": {"prompt_tokens": 10, "completion_tokens": 10}}) + "\n",
            encoding="utf-8",
        )
        rc = tle.main(["--trace", str(trace), "--gate", "--min-savings", "0", "--json"])
        return rc == 1


def test_env_price_override_changes_cost():
    with tempfile.TemporaryDirectory() as td:
        trace = Path(td) / "lanes.jsonl"
        trace.write_text(
            json.dumps({"role": "builder", "lane": "glm", "ok": True,
                        "usage": {"prompt_tokens": 500000, "completion_tokens": 500000}}) + "\n",
            encoding="utf-8",
        )
        records, _ = tle.load_trace(str(trace))
        agg_default = tle.aggregate(records)
        default_cost = agg_default["by_tier"]["glm"]["cost"]

        orig = os.environ.get("BRAINER_PRICE_GLM")
        os.environ["BRAINER_PRICE_GLM"] = "100"
        try:
            agg_override = tle.aggregate(records)
        finally:
            if orig is None:
                os.environ.pop("BRAINER_PRICE_GLM", None)
            else:
                os.environ["BRAINER_PRICE_GLM"] = orig
        override_cost = agg_override["by_tier"]["glm"]["cost"]
        # 1M tokens at $100/Mtok == $100.00, unambiguous regardless of the default
        return override_cost == 100.0 and override_cost != default_cost


def test_malformed_trace_lines_skipped_and_counted_never_crash():
    with tempfile.TemporaryDirectory() as td:
        trace = Path(td) / "lanes.jsonl"
        trace.write_text(
            "\n".join([
                "{not valid json",
                json.dumps({"role": "builder", "lane": "gpt", "ok": True,
                            "usage": {"prompt_tokens": 10, "completion_tokens": 10}}),
                "[]",  # valid JSON, not an object
                "",
            ]) + "\n",
            encoding="utf-8",
        )
        records, malformed = tle.load_trace(str(trace))
        return malformed == 2 and len(records) == 1


def test_manual_lanes_csv_parses_and_prices():
    with tempfile.TemporaryDirectory() as td:
        lanes = Path(td) / "lanes.csv"
        lanes.write_text(
            "lane_label,tier,tokens,accepted\n"
            "agent-builder-1,mid,4000,true\n"
            "agent-builder-2,small,2000,false\n",
            encoding="utf-8",
        )
        records, malformed = tle.load_manual_lanes(str(lanes))
        agg = tle.aggregate(records)
        return (
            malformed == 0
            and len(records) == 2
            and agg["accepted_lanes"] == 1
            and agg["rejected_lanes"] == 1
            and agg["by_tier"]["mid"]["tokens"] == 4000
            and agg["by_tier"]["small"]["tokens"] == 2000
        )


def test_manual_lanes_jsonl_parses():
    with tempfile.TemporaryDirectory() as td:
        lanes = Path(td) / "lanes.jsonl"
        lanes.write_text(
            json.dumps({"lane_label": "agent-x", "tier": "frontier", "tokens": 1500, "accepted": "true"}) + "\n",
            encoding="utf-8",
        )
        records, malformed = tle.load_manual_lanes(str(lanes))
        return malformed == 0 and len(records) == 1 and records[0]["tier"] == "frontier"


def test_manual_jsonl_boolean_tokens_are_unpriced():
    with tempfile.TemporaryDirectory() as td:
        lanes = Path(td) / "lanes.jsonl"
        lanes.write_text(
            json.dumps({"lane_label": "boolean", "tier": "small",
                        "tokens": True, "accepted": True}) + "\n",
            encoding="utf-8",
        )
        records, malformed = tle.load_manual_lanes(str(lanes))
        agg = tle.aggregate(records)
        return (
            malformed == 0
            and len(records) == 1
            and records[0]["tokens"] is None
            and records[0]["priced"] is False
            and agg["total_tokens"] == 0
            and agg["unpriced_lane_count"] == 1
        )


def test_manual_lanes_malformed_rows_skipped_and_counted():
    with tempfile.TemporaryDirectory() as td:
        lanes = Path(td) / "lanes.jsonl"
        lanes.write_text(
            "\n".join([
                "not json at all",
                json.dumps({"lane_label": "ok-lane", "tier": "mid", "tokens": 10, "accepted": "true"}),
                json.dumps({"tier": "mid", "tokens": 10}),  # missing lane_label -> unusable
            ]) + "\n",
            encoding="utf-8",
        )
        records, malformed = tle.load_manual_lanes(str(lanes))
        return malformed == 2 and len(records) == 1


def test_non_finite_and_negative_tokens_are_unpriced():
    with tempfile.TemporaryDirectory() as td:
        trace = Path(td) / "trace.jsonl"
        trace.write_text(
            "\n".join([
                json.dumps({"role": "builder", "lane": "glm", "ok": True,
                            "usage": {"total_tokens": -10}}),
                json.dumps({"role": "builder", "lane": "glm", "ok": True,
                            "usage": {"total_tokens": float("nan")}}),
            ]) + "\n",
            encoding="utf-8",
        )
        lanes = Path(td) / "lanes.jsonl"
        lanes.write_text(
            "\n".join([
                json.dumps({"lane_label": "negative", "tier": "small",
                            "tokens": -5, "accepted": True}),
                json.dumps({"lane_label": "infinite", "tier": "small",
                            "tokens": float("inf"), "accepted": True}),
            ]) + "\n",
            encoding="utf-8",
        )

        trace_records, malformed_trace = tle.load_trace(str(trace))
        manual_records, malformed_manual = tle.load_manual_lanes(str(lanes))
        records = trace_records + manual_records
        agg = tle.aggregate(records)
        return (
            malformed_trace == 0
            and malformed_manual == 0
            and len(records) == 4
            and all(r["tokens"] is None and r["priced"] is False for r in records)
            and agg["total_tokens"] == 0
            and agg["unpriced_lane_count"] == 4
        )


def test_partial_corrupt_and_fractional_tokens_are_unpriced():
    with tempfile.TemporaryDirectory() as td:
        trace = Path(td) / "trace.jsonl"
        trace.write_text(
            "\n".join([
                json.dumps({"role": "builder", "lane": "glm", "ok": True,
                            "usage": {"prompt_tokens": 100, "completion_tokens": "corrupt"}}),
                json.dumps({"role": "builder", "lane": "glm", "ok": True,
                            "usage": {"prompt_tokens": "corrupt", "completion_tokens": 100}}),
                json.dumps({"role": "builder", "lane": "glm", "ok": True,
                            "usage": {"total_tokens": 12.5}}),
                json.dumps({"role": "builder", "lane": "glm", "ok": True,
                            "usage": {"prompt_tokens": True, "completion_tokens": 10}}),
            ]) + "\n",
            encoding="utf-8",
        )
        records, malformed = tle.load_trace(str(trace))
        agg = tle.aggregate(records)
        return (
            malformed == 0
            and len(records) == 4
            and all(r["tokens"] is None and r["priced"] is False for r in records)
            and agg["total_tokens"] == 0
            and agg["unpriced_lane_count"] == 4
        )


def test_one_sided_trace_usage_is_unpriced():
    with tempfile.TemporaryDirectory() as td:
        trace = Path(td) / "trace.jsonl"
        trace.write_text(
            "\n".join([
                json.dumps({"role": "builder", "lane": "glm", "ok": True,
                            "usage": {"prompt_tokens": 100}}),
                json.dumps({"role": "builder", "lane": "glm", "ok": True,
                            "usage": {"completion_tokens": 25}}),
            ]) + "\n",
            encoding="utf-8",
        )
        records, malformed = tle.load_trace(str(trace))
        agg = tle.aggregate(records)
        return (
            malformed == 0
            and len(records) == 2
            and all(r["tokens"] is None and r["priced"] is False for r in records)
            and agg["total_tokens"] == 0
            and agg["unpriced_lane_count"] == 2
        )


def test_valid_total_or_complete_pair_is_priced():
    with tempfile.TemporaryDirectory() as td:
        trace = Path(td) / "trace.jsonl"
        trace.write_text(
            "\n".join([
                json.dumps({"role": "builder", "lane": "glm", "ok": True,
                            "usage": {"total_tokens": 20}}),
                json.dumps({"role": "builder", "lane": "glm", "ok": True,
                            "usage": {"prompt_tokens": 100, "completion_tokens": 5}}),
                json.dumps({"role": "builder", "lane": "glm", "ok": True,
                            "usage": {"total_tokens": 20, "prompt_tokens": "corrupt"}}),
                json.dumps({"role": "builder", "lane": "glm", "ok": True,
                            "usage": {"total_tokens": "corrupt", "prompt_tokens": 10,
                                      "completion_tokens": 5}}),
            ]) + "\n",
            encoding="utf-8",
        )
        records, malformed = tle.load_trace(str(trace))
        agg = tle.aggregate(records)
        return (
            malformed == 0
            and [r["tokens"] for r in records] == [20, 105, 20, 15]
            and all(r["priced"] is True for r in records)
            and agg["total_tokens"] == 160
            and agg["unpriced_lane_count"] == 0
        )


def test_missing_trace_file_returns_empty_not_crash():
    records, malformed = tle.load_trace("/nonexistent/path/does/not/exist.jsonl")
    return records == [] and malformed == 0


def test_unknown_lane_falls_back_to_mid_tier():
    with tempfile.TemporaryDirectory() as td:
        trace = Path(td) / "lanes.jsonl"
        trace.write_text(
            json.dumps({"role": "builder", "lane": "some-new-vendor", "ok": True,
                        "usage": {"prompt_tokens": 100, "completion_tokens": 100}}) + "\n",
            encoding="utf-8",
        )
        records, _ = tle.load_trace(str(trace))
        return records[0]["tier"] == "mid"


def test_cost_per_accepted_change_and_counterfactual_savings():
    with tempfile.TemporaryDirectory() as td:
        trace = Path(td) / "lanes.jsonl"
        trace.write_text(
            "\n".join([
                json.dumps({"role": "leader", "lane": "gpt", "ok": True,
                            "usage": {"prompt_tokens": 100000, "completion_tokens": 100000}}),
                json.dumps({"role": "builder", "lane": "local", "ok": True,
                            "usage": {"prompt_tokens": 900000, "completion_tokens": 900000}}),
            ]) + "\n",
            encoding="utf-8",
        )
        records, _ = tle.load_trace(str(trace))
        agg = tle.aggregate(records)
        expected_cpac = agg["total_cost"] / agg["accepted_lanes"]
        # counterfactual: total tokens all priced at frontier rate
        expected_counterfactual = agg["total_tokens"] / 1_000_000.0 * tle.price_per_mtok("frontier")
        return (
            abs(agg["cost_per_accepted_change"] - expected_cpac) < 1e-9
            and abs(agg["counterfactual_cost"] - expected_counterfactual) < 1e-9
            and agg["savings_pct"] is not None
            and agg["savings_pct"] > 0  # local+gpt blend must be cheaper than all-frontier
        )


def test_gate_passes_when_savings_meets_threshold():
    with tempfile.TemporaryDirectory() as td:
        trace = Path(td) / "lanes.jsonl"
        trace.write_text(
            json.dumps({"role": "builder", "lane": "local", "ok": True,
                        "usage": {"prompt_tokens": 1000, "completion_tokens": 1000}}) + "\n",
            encoding="utf-8",
        )
        rc = tle.main(["--trace", str(trace), "--gate", "--min-savings", "50", "--json"])
        return rc == 0


def test_no_input_args_errors_cleanly():
    rc = tle.main([])
    return rc == 2


def test_json_output_is_valid_json(capsys=None):
    with tempfile.TemporaryDirectory() as td:
        trace = Path(td) / "lanes.jsonl"
        trace.write_text(
            json.dumps({"role": "builder", "lane": "glm", "ok": True,
                        "usage": {"prompt_tokens": 10, "completion_tokens": 10}}) + "\n",
            encoding="utf-8",
        )
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = tle.main(["--trace", str(trace), "--json"])
        try:
            payload = json.loads(buf.getvalue())
        except Exception:
            return False
        return rc == 0 and "total_tokens" in payload and "savings_pct" in payload


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]


def main() -> int:
    failures = 0
    for t in TESTS:
        try:
            ok = t()
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"ERROR {t.__name__}: {e}")
        if ok:
            print(f"PASS {t.__name__}")
        else:
            failures += 1
            print(f"FAIL {t.__name__}")
    total = len(TESTS)
    print(f"\n{total - failures}/{total} passed")
    return failures


if __name__ == "__main__":
    sys.exit(main())
