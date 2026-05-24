#!/usr/bin/env python3
"""Retrieval A/B for graphify integration in `index-first`.

For each question, compare two retrieval strategies that an agent might run
before answering "where is X / what calls Y / what connects A to B" type
questions on a codebase:

  A. grep-baseline:  rg <symbol>  →  read top-K files (capped)
  B. graphify:       graphify query "<question>" --budget N

Both arms emit a single context blob the agent would have to ingest.
Measure: bytes, approximate tokens (char/4), wall time, tool-call count.

Headline metric: did graphify produce a smaller, denser context that
still contains the answer the agent needs?

This runner does NOT call a judge model (no MIMO_API_KEY in env at time
of writing). Correctness is asserted by spot-check questions whose
answers we know from the corpus, with the expected node label embedded
in the question for ground-truth grep.

Usage:
  python3 eval/runner_graphify.py \\
      --repo /tmp/te-graphify-test \\
      --graph /tmp/te-graphify-test/graphify-out/graph.json \\
      --out eval/results/graphify_retrieval.json
"""
from __future__ import annotations

import argparse
import json
import re
import shlex
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GRAPHIFY_BIN = REPO_ROOT / ".venvs" / "graphify" / "bin" / "graphify"


# Question set. Each item: question text, expected symbol (for grep + ground
# truth), expected_answer_keywords (the agent's reply should mention at least
# one — used in the optional correctness spot-check).
QUESTIONS = [
    {
        "q": "What calls WikiStore?",
        "symbol": "WikiStore",
        "expect_any": ["_cli_main", "_store", "wiki_search", "wiki_mcp"],
    },
    {
        "q": "What methods does WikiStore expose?",
        "symbol": "WikiStore",
        "expect_any": ["search", "fetch", "timeline", "new_page", "index", "ingest"],
    },
    {
        "q": "What does write_gate enforce?",
        "symbol": "write_gate",
        "expect_any": ["WriteGate", "block", "gate", "raw"],
    },
    {
        "q": "What is the wiki CLI entry point?",
        "symbol": "_cli_main",
        "expect_any": ["_cli_main", "argparse", "search", "fetch"],
    },
    {
        "q": "Which functions handle lint operations?",
        "symbol": "lint",
        "expect_any": ["lint_pages", "lint", "strict"],
    },
    {
        "q": "What does code_map.py expose?",
        "symbol": "code_map",
        "expect_any": ["code_map", "symbol", "render"],
    },
    {
        "q": "What are the methods of class WikiStore?",
        "symbol": "WikiStore",
        "expect_any": ["search", "fetch", "timeline", "_ensure_db", "context"],
    },
    {
        "q": "How is import_audit related to WikiStore?",
        "symbol": "import_audit",
        "expect_any": ["WikiStore", "method", "import_audit"],
    },
    {
        "q": "What imports the WikiStore class?",
        "symbol": "WikiStore",
        "expect_any": ["wiki_search", "wiki_mcp", "imports"],
    },
    {
        "q": "What does the rank_pages function do?",
        "symbol": "_rank_pages",
        "expect_any": ["WikiStore", "method", "rank"],
    },
    {
        "q": "Where is 'progressive retrieval' implemented?",  # concept, no symbol
        "symbol": "search",
        "expect_any": ["search", "fetch", "rank"],
    },
    {
        "q": "What class has a method named ingest?",
        "symbol": "ingest",
        "expect_any": ["WikiStore", "ingest"],
    },
]


def char_tokens(s: str) -> int:
    """~4 chars/token English heuristic. Good enough for relative compare."""
    return (len(s) + 3) // 4


CODE_EXT = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
            ".c", ".h", ".cpp", ".hpp", ".rb", ".swift", ".kt", ".sh", ".lua"}


def _walk_code(repo: Path):
    skip = {"__pycache__", ".git", "node_modules", ".venv", ".venvs", "graphify-out"}
    for p in repo.rglob("*"):
        if not p.is_file():
            continue
        if any(part in skip for part in p.parts):
            continue
        if p.suffix.lower() not in CODE_EXT:
            continue
        yield p


def run_grep_baseline(symbol: str, repo: Path, max_files: int = 3, head_lines: int = 200) -> dict:
    """Simulate the cheapest competent grep+read an agent would do.

    1. walk code files, find those containing <symbol>     (1 logical tool call)
    2. for each of the top max_files, read first head_lines (1 tool call each)

    This is intentionally generous to the grep arm: an agent would often
    do more — re-grep with context lines, follow imports, etc.
    """
    t0 = time.time()
    pat = re.compile(re.escape(symbol))
    files: list[Path] = []
    for p in _walk_code(repo):
        try:
            txt = p.read_text(errors="ignore")
        except Exception:
            continue
        if pat.search(txt):
            files.append(p)
            if len(files) >= max_files:
                break
    tool_calls = 1  # the search

    if not files:
        elapsed = int((time.time() - t0) * 1000)
        return {"tokens": 0, "bytes": 0, "elapsed_ms": elapsed, "tool_calls": tool_calls, "files": [], "output": ""}

    parts: list[str] = []
    for f in files:
        try:
            lines = f.read_text(errors="ignore").splitlines()[:head_lines]
            parts.append(f"=== {f.relative_to(repo)} ===\n" + "\n".join(lines))
            tool_calls += 1
        except Exception:
            continue

    blob = "\n\n".join(parts)
    elapsed = int((time.time() - t0) * 1000)
    return {
        "tokens": char_tokens(blob),
        "bytes": len(blob.encode("utf-8")),
        "elapsed_ms": elapsed,
        "tool_calls": tool_calls,
        "files": [str(f.relative_to(repo)) for f in files],
        "output": blob,
    }


def run_graphify(question: str, graph: Path, budget: int = 1500) -> dict:
    """Run `graphify query` (NL) and capture its stdout."""
    t0 = time.time()
    cmd = [str(GRAPHIFY_BIN), "query", question, "--budget", str(budget), "--graph", str(graph)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        elapsed = int((time.time() - t0) * 1000)
        out = r.stdout
        if r.returncode != 0:
            out = (r.stderr or "") + "\n" + out
        return {
            "tokens": char_tokens(out),
            "bytes": len(out.encode("utf-8")),
            "elapsed_ms": elapsed,
            "tool_calls": 1,
            "returncode": r.returncode,
            "output": out,
        }
    except Exception as e:
        elapsed = int((time.time() - t0) * 1000)
        return {"tokens": 0, "bytes": 0, "elapsed_ms": elapsed, "tool_calls": 1, "error": str(e), "output": ""}


def run_graphify_explain(symbol: str, graph: Path) -> dict:
    """Run `graphify explain <Symbol>` — exact-label lookup of a node and its
    neighborhood. This is the symbol-precision path we recommend in
    index-first/SKILL.md alongside `query`.
    """
    t0 = time.time()
    cmd = [str(GRAPHIFY_BIN), "explain", symbol, "--graph", str(graph)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        elapsed = int((time.time() - t0) * 1000)
        out = r.stdout or r.stderr or ""
        return {
            "tokens": char_tokens(out),
            "bytes": len(out.encode("utf-8")),
            "elapsed_ms": elapsed,
            "tool_calls": 1,
            "returncode": r.returncode,
            "output": out,
        }
    except Exception as e:
        elapsed = int((time.time() - t0) * 1000)
        return {"tokens": 0, "bytes": 0, "elapsed_ms": elapsed, "tool_calls": 1, "error": str(e), "output": ""}


def evidence_hits(output: str, expect_any: list[str]) -> dict:
    """Simple "did the context contain the expected evidence" check.

    Counts how many of the expect_any tokens appear in the output. This is
    coarse — a grep-style check, not a judge — but it catches the case
    where graphify returned the wrong neighborhood.
    """
    hits = [w for w in expect_any if w in output]
    return {"hits": len(hits), "of": len(expect_any), "matched": hits}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True, help="repo root to grep against")
    p.add_argument("--graph", required=True, help="path to graphify-out/graph.json")
    p.add_argument("--out", default="eval/results/graphify_retrieval.json")
    p.add_argument("--budget", type=int, default=1500)
    args = p.parse_args()

    repo = Path(args.repo).resolve()
    graph = Path(args.graph).resolve()
    if not graph.exists():
        print(f"ERROR: graph not found: {graph}", file=sys.stderr)
        return 1
    if not GRAPHIFY_BIN.exists():
        print(f"ERROR: graphify binary not found: {GRAPHIFY_BIN}", file=sys.stderr)
        return 1

    per_q: list[dict] = []
    for item in QUESTIONS:
        q, sym, expect = item["q"], item["symbol"], item["expect_any"]
        grep = run_grep_baseline(sym, repo)
        gx = run_graphify(q, graph, budget=args.budget)
        gxe = run_graphify_explain(sym, graph)
        per_q.append({
            "question": q,
            "symbol": sym,
            "grep": {k: v for k, v in grep.items() if k != "output"} | {"evidence": evidence_hits(grep.get("output", ""), expect)},
            "graphify_query": {k: v for k, v in gx.items() if k != "output"} | {"evidence": evidence_hits(gx.get("output", ""), expect)},
            "graphify_explain": {k: v for k, v in gxe.items() if k != "output"} | {"evidence": evidence_hits(gxe.get("output", ""), expect)},
            "grep_output_excerpt": (grep.get("output") or "")[:400],
            "graphify_query_excerpt": (gx.get("output") or "")[:400],
            "graphify_explain_excerpt": (gxe.get("output") or "")[:400],
        })

    def sum_field(rows, arm, k):
        return sum(r[arm].get(k, 0) for r in rows)

    def evidence_rate(rows, arm):
        good = sum(1 for r in rows if r[arm]["evidence"]["hits"] >= 1)
        return round(100 * good / len(rows), 1)

    grep_tokens = sum_field(per_q, "grep", "tokens")
    gxq_tokens = sum_field(per_q, "graphify_query", "tokens")
    gxe_tokens = sum_field(per_q, "graphify_explain", "tokens")
    summary = {
        "n_questions": len(per_q),
        "grep": {
            "total_tokens": grep_tokens,
            "total_bytes": sum_field(per_q, "grep", "bytes"),
            "total_tool_calls": sum_field(per_q, "grep", "tool_calls"),
            "mean_elapsed_ms": round(statistics.mean(r["grep"]["elapsed_ms"] for r in per_q), 1),
            "evidence_rate_pct": evidence_rate(per_q, "grep"),
        },
        "graphify_query": {
            "total_tokens": gxq_tokens,
            "total_bytes": sum_field(per_q, "graphify_query", "bytes"),
            "total_tool_calls": sum_field(per_q, "graphify_query", "tool_calls"),
            "mean_elapsed_ms": round(statistics.mean(r["graphify_query"]["elapsed_ms"] for r in per_q), 1),
            "evidence_rate_pct": evidence_rate(per_q, "graphify_query"),
            "delta_tokens_pct_vs_grep": round(100 * (gxq_tokens - grep_tokens) / max(grep_tokens, 1), 1),
        },
        "graphify_explain": {
            "total_tokens": gxe_tokens,
            "total_bytes": sum_field(per_q, "graphify_explain", "bytes"),
            "total_tool_calls": sum_field(per_q, "graphify_explain", "tool_calls"),
            "mean_elapsed_ms": round(statistics.mean(r["graphify_explain"]["elapsed_ms"] for r in per_q), 1),
            "evidence_rate_pct": evidence_rate(per_q, "graphify_explain"),
            "delta_tokens_pct_vs_grep": round(100 * (gxe_tokens - grep_tokens) / max(grep_tokens, 1), 1),
        },
    }

    results = {"summary": summary, "per_question": per_q}
    out_path = REPO_ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2))

    print(f"\n=== graphify retrieval A/B ({len(per_q)} questions) ===")
    for arm in ("grep", "graphify_query", "graphify_explain"):
        s = summary[arm]
        dtxt = f"  Δvs grep: {s.get('delta_tokens_pct_vs_grep', 0):+.1f}%" if arm != "grep" else ""
        print(f"  {arm:<17} tokens={s['total_tokens']:6}  bytes={s['total_bytes']:7}  "
              f"calls={s['total_tool_calls']:3}  evidence={s['evidence_rate_pct']}%{dtxt}")
    print(f"  results:  {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
