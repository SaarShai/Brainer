#!/usr/bin/env python3
"""Hot-path perf-budget regression battery (H2 harness, deterministic).

Locks out the super-linear / ReDoS regression class that shipped TWICE in
bug-hunt R5: cache-lint's typography-before-cap went O(n^2) (7s on
'$(date)'*5000) and context-keeper's PATH_RE rewrite went O(n^2) (39s on a
50k-segment slash run, enough to blow the 30s PreCompact subprocess timeout and
lose the whole snapshot). Both passed their scoped unit tests; only an
adversarial perf probe caught them.

Each case runs a real hot-path callable on an ADVERSARIAL input (the worst case
its bug class produces) and asserts wall-time under a BUDGET. Budgets are set
loosely (~60x-7000x the healthy time, measured) so the test never flakes on
machine load, yet a re-introduced quadratic/backtracking bug (which jumps to
seconds) blows the budget and fails.
Timing is best-of-3 (min) to suppress GC/scheduler noise. Deterministic inputs;
no model calls.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import Report, import_skill_module, print_report, write_report  # noqa: E402

os.environ.setdefault("AGENTS_TRIAGE_NO_OLLAMA", "1")  # keep triage deterministic

DOLLAR = chr(36)  # avoid shell/heredoc capture of $(...) in any wrapper


def _best_of_3(fn) -> tuple[float, object]:
    """Return (min_seconds, last_result) over 3 runs."""
    best = float("inf")
    out = None
    for _ in range(3):
        t = time.perf_counter()
        out = fn()
        dt = time.perf_counter() - t
        best = min(best, dt)
    return best, out


def _case(report: Report, name: str, budget_ms: float, fn, expect=None) -> None:
    """Time fn (best of 3); fail if it crashes or exceeds budget_ms."""
    try:
        secs, result = _best_of_3(fn)
    except Exception as e:  # a crash on adversarial input is itself a failure
        report.passed = False
        report.finding(case=name, status="CRASH", error=repr(e)[:200], budget_ms=budget_ms)
        return
    ms = secs * 1000.0
    ok = ms <= budget_ms
    if expect is not None and result != expect:
        ok = False
    if not ok:
        report.passed = False
    report.finding(
        case=name, status="ok" if ok else "FAIL",
        ms=round(ms, 2), budget_ms=budget_ms,
        headroom_x=round(budget_ms / ms, 1) if ms > 0 else None,
    )


def build_cases(report: Report) -> None:
    # 1. context-keeper PATH_RE — adversarial slash run (buggy rewrite: 39s/50k).
    extract = import_skill_module("context-keeper", "extract")
    slashrun = "a/" * 50000 + "a"  # no extension -> worst-case extension search
    _case(report, "context-keeper:PATH_RE:50k-slash-run", 2000.0,
          lambda: extract.PATH_RE.findall(slashrun), expect=[])
    # 1b. regex_extract end-to-end on a 40KB single-token slash block.
    blk = "/".join(["seg"] * 8000)
    ev = {"type": "assistant", "message": {"content": [{"type": "text", "text": blk}]}}
    _case(report, "context-keeper:regex_extract:40kb-slash-block", 3000.0,
          lambda: extract.regex_extract(iter([ev])))

    # 2. cache-lint dynamic-content — typography-before-cap was O(n^2) (7s/5k).
    cache_lint = import_skill_module("cache-lint", "cache_lint")
    import tempfile
    d = Path(tempfile.mkdtemp(prefix="hotpath_cl_"))
    (d / "CLAUDE.md").write_text((DOLLAR + "(date) ") * 5000)
    _case(report, "cache-lint:audit-rule2:5k-substitutions", 2000.0,
          lambda: cache_lint.audit(d, rule_filter=2))
    # 2b. many backticked typography matches (exercises the inline-code span path).
    d2 = Path(tempfile.mkdtemp(prefix="hotpath_cl2_"))
    (d2 / "CLAUDE.md").write_text(("`" + DOLLAR + "(date)`\n") * 5000)
    _case(report, "cache-lint:audit-rule2:5k-typography", 2000.0,
          lambda: cache_lint.audit(d2, rule_filter=2))

    # 3. output-filter — ANSI strip + dedupe on a hostile 10k-line stream.
    of = import_skill_module("output-filter", "output_filter")
    rules = of.load_rules(None)
    ESC = chr(27)
    hostile = "".join(f"{ESC}[?25l{ESC}[32mline {i % 7}{ESC}[0m\n" for i in range(10000))
    _case(report, "output-filter:filter_text:10k-ansi-lines", 2000.0,
          lambda: of.filter_text(hostile, rules=rules))

    # 4. write-gate — WHY word-boundary regex + scorer on a long adversarial text.
    wg = import_skill_module("write-gate", "write_gate")
    bigtext = ("We chose pgvector over Qdrant because latency. " * 4000)
    _case(report, "write-gate:score_text:200kb-decision", 1500.0,
          lambda: wg.score_text(bigtext, "decision"))

    # 5. prompt-triage classify — adversarial 1499-char prompt (under the length
    #    gate so the classifier actually runs all guards/regexes).
    classify = import_skill_module("prompt-triage", "classify")
    advp = ("refactor the api/handler/module and rewrite the parser " * 28)[:1499]
    _case(report, "prompt-triage:classify:1499-char-adversarial", 1500.0,
          lambda: classify.classify(advp, use_ollama_fallback=False))

    # 6. compliance-canary — claim/keyword word-boundary regex on a big haystack.
    hook = import_skill_module("compliance-canary", "hook")
    probe = {"_probe_id": "vbc", "claim_pattern": r"(?i)\b(done|fixed|passes)\b",
             "verify_tools": ["Bash"],
             "verify_keywords": ["test", "ls", "cat", "wc", "rg", "ps", "find"],
             "lookback_tool_uses": 5}
    msgs = [{"text": "All done, the feature works."}]
    tus = [{"name": "Bash", "input": {"command": "echo " + ("results tools " * 4000)}}]
    _case(report, "compliance-canary:claim_without_evidence:big-haystack", 1000.0,
          lambda: hook.detect_claim_without_evidence(probe, msgs, tus))


def main() -> int:
    report = Report(skill="hotpath", shape="perf")
    t0 = time.perf_counter()
    build_cases(report)
    report.elapsed_s = round(time.perf_counter() - t0, 3)
    report.summary = {
        "cases": len(report.findings),
        "failed": sum(1 for f in report.findings if f.get("status") != "ok"),
        "slowest_ms": max((f.get("ms", 0) for f in report.findings), default=0),
    }
    write_report(report)
    print_report(report)
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
