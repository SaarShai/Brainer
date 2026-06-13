#!/usr/bin/env python3
"""H3 — gain-vs-baseline runner (deterministic).

Produces one headline gain number per skill, each in its own honest unit, vs an
EXPLICIT baseline. Prioritizes gains that were previously UNMEASURED (cache-lint
flagged its >=30% cache uplift as unmeasured in EVAL.md; skill-pulse and
write-gate had no token-economy number). No model calls, no host — pure
arithmetic + the real skill code on small fixtures, so the numbers are
reproducible and can be quoted regardless of plan/usage.

Run:  python3 eval/gains.py [--json]
Each row: skill · metric · value+unit · baseline. Exit 0 always (measurement,
not a pass/fail gate).
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "sims"))
from _lib import import_skill_module, repo_root  # noqa: E402

REPO = repo_root()
sys.path.insert(0, str(REPO / "skills" / "_shared"))
from tokens import estimate_tokens  # noqa: E402

DOLLAR = chr(36)


def gain_output_filter() -> dict:
    """% tokens removed from a realistic noisy tool-output stream, 0% signal loss."""
    of = import_skill_module("output-filter", "output_filter")
    rules = of.load_rules(None)
    ESC = chr(27)
    # realistic build/test log: a redrawing progress bar (same line emitted many
    # times, as real spinners/downloaders do) wrapped in ANSI, a block of cycling
    # compile lines, then the real failure lines that MUST survive.
    lines = []
    for _ in range(300):  # progress bar redrawing the identical line (adjacent dups)
        lines.append(f"{ESC}[?25l{ESC}[36mDownloading deps... 42%{ESC}[0m")
    for i in range(100):  # cycling compile output (not adjacent-identical)
        lines.append(f"{ESC}[32mCompiling module {i % 5}...{ESC}[0m")
    lines.append("ERROR: test_auth.py::test_login FAILED — assert 401 == 200")
    lines.append("FAILED tests/test_auth.py::test_login")
    raw = "\n".join(lines) + "\n"
    out, stats = of.filter_text(raw, rules=rules)
    tin, tout = estimate_tokens(raw), estimate_tokens(out)
    pct = round((tin - tout) / tin * 100, 1) if tin else 0.0
    signal_kept = ("ERROR: test_auth" in out) and ("FAILED tests/test_auth" in out)
    return {"skill": "output-filter", "metric": "token reduction on noisy log",
            "value": pct, "unit": "% fewer tokens (est)",
            "baseline": "unfiltered stream", "signal_preserved": signal_kept,
            "detail": f"{tin}->{tout} est tokens"}


def gain_skill_pulse() -> dict:
    """Pulse-reminder payload vs re-injecting full SKILL.md bodies, per 1000 turns."""
    hook = import_skill_module("skill-pulse", "hook")
    pulse = hook.discover_skills(REPO / "skills", set())[: hook.MAX_SKILLS_IN_PULSE]
    pulse_block = "\n".join(f"- {n}: {r}" for n, r in pulse)
    pulse_tok = estimate_tokens(pulse_block)
    # baseline: re-read the FULL SKILL.md body (sans frontmatter) of the same skills
    full_tok = 0
    for n, _ in pulse:
        for d in (REPO / "skills").iterdir():
            md = d / "SKILL.md"
            if md.is_file() and hook.parse_frontmatter(md.read_text()).get("name", d.name) == n:
                body = md.read_text().split("---", 2)[-1]
                full_tok += estimate_tokens(body)
                break
    cadence = hook.CADENCE_DEFAULT
    injections = 1000 // cadence
    pulse_per_1k = pulse_tok * injections
    full_per_1k = full_tok * injections
    pct = round((full_per_1k - pulse_per_1k) / full_per_1k * 100, 2) if full_per_1k else 0.0
    return {"skill": "skill-pulse", "metric": "re-anchor payload / 1000 turns",
            "value": pct, "unit": "% fewer tokens vs full-body re-injection",
            "baseline": f"re-inject {len(pulse)} full SKILL.md bodies every {cadence} turns",
            "detail": f"{pulse_per_1k:,} vs {full_per_1k:,} tok/1000-turns ({len(pulse)} skills)"}


def gain_write_gate() -> dict:
    """% candidate-memory tokens the gate keeps OUT (noise rejected) on the labeled set."""
    wg = import_skill_module("write-gate", "write_gate")
    corpus = [json.loads(l) for l in
              (REPO / "eval/exp3_classifiers/write_gate_labeled.jsonl").read_text().splitlines() if l.strip()]
    total = admitted = 0
    for c in corpus:
        t = estimate_tokens(c["text"])
        total += t
        s = wg.score_text(c["text"], c["kind"])
        passed, _ = wg.decide(s, c["kind"], wg.DEFAULT_THRESHOLD, True)
        if passed:
            admitted += t
    pct = round((total - admitted) / total * 100, 1) if total else 0.0
    return {"skill": "write-gate", "metric": "candidate-memory noise rejected",
            "value": pct, "unit": "% of candidate tokens kept out of durable memory",
            "baseline": "ungated (admit every candidate)",
            "detail": f"{admitted}/{total} est tokens admitted"}


def gain_cache_lint() -> dict:
    """Static prompt-cache cost model: billed prefix tokens before/after fixing a
    Rule-2 dynamic-content FAIL, over an N-turn session. Fills EVAL.md's
    flagged-but-unmeasured '>=30% uplift' number, entirely statically."""
    cache_lint = import_skill_module("cache-lint", "cache_lint")
    # representative prefix with a dynamic-content FAIL
    d = Path(tempfile.mkdtemp(prefix="gains_cl_"))
    prefix = "# Project rules\n" + ("Guidance line that stays stable. " * 200)
    (d / "CLAUDE.md").write_text(prefix + f"\nLast updated: {DOLLAR}(date)\n")
    rep = cache_lint.audit(d, rule_filter=2)
    has_fail = any(f.severity == "FAIL" for f in rep.findings)
    T = len(prefix) // 4  # tool's own bytes/4 token estimate
    N, WRITE, READ = 20, 1.25, 0.1
    dirty = T * (N * WRITE)               # dynamic content re-keys cache every turn
    clean = T * (WRITE + (N - 1) * READ)  # one write, then cache reads
    pct = round((dirty - clean) / dirty * 100, 1)
    return {"skill": "cache-lint", "metric": "billed prefix tokens saved by fixing a Rule-2 FAIL",
            "value": pct, "unit": f"% fewer billed prefix tokens over {N} turns",
            "baseline": "unfixed dynamic-content FAIL (full cache-write each turn)",
            "detail": f"FAIL detected={has_fail}; {int(dirty):,}->{int(clean):,} billed tok @N={N}",
            "hitrate_uplift_pp": round((N - 1) / N * 100, 1)}


GAINS = [gain_output_filter, gain_skill_pulse, gain_write_gate, gain_cache_lint]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    rows = []
    for fn in GAINS:
        try:
            rows.append(fn())
        except Exception as e:
            rows.append({"skill": fn.__name__, "error": repr(e)[:200]})
    out = REPO / "eval/results"; out.mkdir(parents=True, exist_ok=True)
    (out / "gains.json").write_text(json.dumps(rows, indent=2) + "\n")
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    print("\n=== H3 gain-vs-baseline (deterministic) ===\n")
    for r in rows:
        if "error" in r:
            print(f"  {r['skill']:14}  ERROR: {r['error']}"); continue
        print(f"  {r['skill']:14}  {r['value']}{r['unit'].split()[0]:>6}  {r['unit']}")
        print(f"  {'':14}  {r['metric']}  ·  vs {r['baseline']}")
        print(f"  {'':14}  ({r['detail']})\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
