#!/usr/bin/env python3
"""Build SKILLS_INDEX_RATED.md.

Combines:
  - static_cost.json (description-tax, body-cost, tools-payload)
  - eval/results/<id>.json (live A/B input/output token deltas)
  - eval/results/<id>.judged.json (judge Δscore, optional)

Ratings:
  efficiency = net token savings relative to per-call output baseline
  gain       = % output-token reduction with the skill loaded
  reliability = qualitative based on body length + tools-present + judge pass rate
  quality_loss = Δjudge score (positive = better quality, negative = quality loss)

Skills with no live A/B yet show "pending" for the live columns.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def grade_letter(score: float, thresholds: list[tuple[float, str]]) -> str:
    for threshold, letter in thresholds:
        if score >= threshold:
            return letter
    return thresholds[-1][1]


def rate_efficiency(input_delta_pct: float | None, output_delta_pct: float | None) -> str:
    """Efficiency = output savings amortized with low-weighted input cost.

    Rationale: the skill body is prepended once per session and benefits from
    prompt caching, so its input cost is effectively a fixed footprint, not
    a per-call multiplier. Output tokens are uncacheable and generated every
    call, so output savings dominate net cost over a session of N calls.
    Weight input growth at 0.02× to reflect cache amortization across ~50 calls.
    """
    if input_delta_pct is None or output_delta_pct is None:
        return "?"
    net = (-output_delta_pct) - 0.02 * input_delta_pct
    return grade_letter(net, [(60, "A"), (30, "B"), (10, "C"), (0, "D"), (-1e9, "F")])


def rate_gain(output_delta_pct: float | None) -> str:
    if output_delta_pct is None:
        return "?"
    return grade_letter(-output_delta_pct, [(60, "A"), (30, "B"), (10, "C"), (0, "D"), (-1e9, "F")])


def rate_reliability(body_tokens: int, tools_kb: float, has_eval: bool) -> str:
    score = 0
    if has_eval:
        score += 30
    if body_tokens >= 200:
        score += 25
    if tools_kb > 0:
        score += 35
    if body_tokens >= 400 and tools_kb > 0:
        score += 10
    return grade_letter(score, [(80, "A"), (55, "B"), (30, "C"), (10, "D"), (-1e9, "F")])


def rate_quality_loss(judge_delta: float | None) -> str:
    if judge_delta is None:
        return "?"
    return grade_letter(judge_delta, [(0.0, "A"), (-0.25, "B"), (-0.5, "C"), (-1.0, "D"), (-1e9, "F")])


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    static_path = root / "eval" / "results" / "static_cost.json"
    if not static_path.exists():
        print("missing static_cost.json; run static_cost.py first", file=sys.stderr)
        return 2
    static = {r["name"]: r for r in json.loads(static_path.read_text())}

    rated = []
    for name, s in static.items():
        ab_path = root / "eval" / "results" / f"{name}.json"
        judge_path = root / "eval" / "results" / f"{name}.judged.json"
        in_delta = out_delta = j_delta = None
        sample_n = None
        if ab_path.exists():
            d = json.loads(ab_path.read_text())
            summ = d.get("summary", {})
            in_delta = summ.get("delta_input_pct")
            out_delta = summ.get("delta_output_pct")
            sample_n = d.get("n")
            # Alternative-shape harnesses:
            # runner_triage.py reports `delta_total_pct` (end-to-end input+output
            # tokens including routing); map onto out_delta so rate_gain treats
            # it as the headline savings number.
            if out_delta is None and "delta_total_pct" in summ:
                out_delta = summ["delta_total_pct"]
                in_delta = 0  # cache-amortized; routing cost is negligible after warm-up
                sample_n = d.get("n", "?")
            # runner_keeper.py is a fidelity test, not a per-call A/B; it produces
            # `compression_ratio` instead. We surface that as a strong negative
            # output_delta (since the sidecar replaces the transcript for recall).
            if out_delta is None and "compression_ratio" in d:
                out_delta = -100 * (1 - d["compression_ratio"])
                in_delta = 0
                sample_n = 1
        if judge_path.exists():
            jd = json.loads(judge_path.read_text())
            j_delta = jd.get("judge_summary", {}).get("delta")

        rated.append({
            **s,
            "input_delta_pct": in_delta,
            "output_delta_pct": out_delta,
            "judge_delta": j_delta,
            "sample_n": sample_n,
            "efficiency": rate_efficiency(in_delta, out_delta),
            "gain": rate_gain(out_delta),
            "reliability": rate_reliability(s["body_tokens"], s["tools_kb"], s.get("has_eval_template", False)),
            "quality_loss": rate_quality_loss(j_delta),
        })

    rated.sort(key=lambda r: (
        {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4, "?": 5}[r["efficiency"]],
        -r["body_tokens"],
    ))

    md = ["# Skills — Rated Index\n",
          f"All {len(rated)} skills, rated on efficiency, gain, reliability, and quality loss.",
          "Static columns are deterministic. Live columns require a live A/B run via `eval/runner.py`.",
          "",
          "### Rating scale\n",
          "- **Efficiency**: net token savings (output cut weighted high, input cost weighted low). A ≥ 60%, B ≥ 30%, C ≥ 10%, D ≥ 0, F < 0.",
          "- **Gain**: percentage output-token reduction when the skill is loaded. A ≥ 60%, B ≥ 30%, C ≥ 10%, D ≥ 0, F < 0 (worse).",
          "- **Reliability**: qualitative, based on body length + bundled tools + EVAL.md presence. A = comprehensive, F = minimal.",
          "- **Quality loss**: Δjudge score from A/B (negative = worse). A = 0 or positive, B ≥ −0.25, C ≥ −0.5, D ≥ −1.0, F < −1.0.",
          "",
          "`?` = pending live measurement.\n",
          "## Ranked table\n",
          "| Rank | Skill | Eff | Gain | Reliab | Quality | desc tok | body tok | Δin% | Δout% | Δjudge | N |",
          "|---:|---|:-:|:-:|:-:|:-:|---:|---:|---:|---:|---:|---:|"]

    def fmt_pct(v):
        return f"{v:+.0f}%" if v is not None else "—"

    def fmt_score(v):
        return f"{v:+.2f}" if v is not None else "—"

    for i, r in enumerate(rated, 1):
        md.append(
            f"| {i} | [{r['name']}](../skills/{r['name']}/SKILL.md) "
            f"| **{r['efficiency']}** | **{r['gain']}** | **{r['reliability']}** | **{r['quality_loss']}** "
            f"| {r['description_tokens']} | {r['body_tokens']} "
            f"| {fmt_pct(r['input_delta_pct'])} "
            f"| {fmt_pct(r['output_delta_pct'])} "
            f"| {fmt_score(r['judge_delta'])} "
            f"| {r['sample_n'] or '—'} |"
        )

    md.extend([
        "",
        "## What the columns mean\n",
        "- **desc tok**: always-resident description size; sum across the catalog = the context tax for having the skill available.",
        "- **body tok**: skill protocol size; loaded only when the skill triggers.",
        "- **Δin%**: change in input tokens per call with the skill loaded (positive = skill adds context cost).",
        "- **Δout%**: change in output tokens per call (negative = skill makes output tighter — usually what we want).",
        "- **Δjudge**: change in judge quality score (0–5 scale).",
        "- **N**: live-run sample size.",
        "",
        "## Notes\n",
        "- **caveman-ultra, lean-execution, plan-first-execute, verify-before-completion**: in-context A/B (`eval/runner.py`). Δout% is output-token reduction per call.",
        "- **prompt-triage**: end-to-end routing A/B (`eval/runner_triage.py`). Δout% maps to **delta_total_pct** — total input+output tokens summed across the corpus when the cheap/expensive router is active.",
        "- **context-keeper**: fidelity test (`eval/runner_keeper.py`), not a per-call A/B. Δout% maps to **compression of the extracted sidecar vs. the raw transcript** — the sidecar at 2.3% of raw size IS the value, since it survives compaction and the raw transcript usually doesn't. See its `EVAL.md` for per-category recall (URLs 100%, numbers 67%, commands 46%, errors 25%).",
        "- **handoff, context-refresh, output-filter, wiki-memory, delegate, compress-context, semantic-diff**: live measurement pending. See each skill's `EVAL.md` for the methodology and any prior numbers.",
        "- Hook skills (`prompt-triage`, `context-keeper`, `output-filter`) do NOT prepend to the system message in normal use; their cost is the hook script's transcript footprint, not in-context tokens.",
        "- A `?` in any column means the live A/B hasn't been run for that skill yet; the static cost is always populated.",
    ])

    out = root / "skills" / "SKILLS_INDEX_RATED.md"
    out.write_text("\n".join(md))
    print(f"wrote {out}")
    print(f"\nsummary:")
    print(f"  measured: {sum(1 for r in rated if r['output_delta_pct'] is not None)} / {len(rated)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
