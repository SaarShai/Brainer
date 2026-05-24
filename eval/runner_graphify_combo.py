#!/usr/bin/env python3
"""Combo test: graphify + wiki-memory.

Four arms over a mixed question set:

  A. grep baseline — `rg <symbol>` then read top-3 files (200 lines each)
  B. wiki-memory alone — `wiki.py search` for top-3 hits
  C. graphify-explain alone — exact-label lookup
  D. graphify + wiki — both contexts concatenated

Question set has three intended kinds:
  - CODE-ONLY:    answer is in source (graphify should win)
  - PROJECT-ONLY: answer is in wiki (wiki should win)
  - HYBRID:       answer needs both (combo should win)

Headline question: does D dominate B and C, or is there a clear cleanup
boundary (only fetch the store that matches the question type)?

Metric: tokens (char/4), evidence rate (≥1 expected keyword in output).

Usage:
  python3 eval/runner_graphify_combo.py \\
      --repo /tmp/te-graphify-test \\
      --graph /tmp/te-graphify-test/graphify-out/graph.json \\
      --wiki ./wiki
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GRAPHIFY_BIN = REPO_ROOT / ".venvs" / "graphify" / "bin" / "graphify"
WIKI_TOOL = REPO_ROOT / "skills" / "wiki-memory" / "tools" / "wiki.py"

CODE_EXT = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
            ".c", ".h", ".cpp", ".hpp", ".rb", ".swift", ".kt", ".sh", ".lua"}


# kind ∈ {code, project, hybrid}. symbol used for grep and graphify lookups.
# wiki_query feeds wiki.py search. expect_any drives evidence.
QUESTIONS = [
    # CODE-ONLY
    {"kind": "code", "q": "What calls WikiStore in the code?",
     "symbol": "WikiStore", "wiki_query": "WikiStore",
     "expect_any": ["_cli_main", "_store", "wiki_search"]},
    {"kind": "code", "q": "What methods does WikiStore expose?",
     "symbol": "WikiStore", "wiki_query": "WikiStore methods",
     "expect_any": ["search", "fetch", "timeline", "ingest"]},
    {"kind": "code", "q": "What does code_map.py expose?",
     "symbol": "code_map", "wiki_query": "code_map symbol navigation",
     "expect_any": ["code_map", "symbol", "render"]},
    {"kind": "code", "q": "What functions handle lint operations?",
     "symbol": "lint", "wiki_query": "lint validation",
     "expect_any": ["lint_pages", "lint", "strict"]},

    # PROJECT-ONLY (answer lives in the wiki, not the code)
    {"kind": "project", "q": "What was the semdiff prior-art survey conclusion about Difftastic?",
     "symbol": "Difftastic", "wiki_query": "semdiff difftastic survey",
     "expect_any": ["Difftastic", "rename", "lineage", "AST"]},
    {"kind": "project", "q": "What is the write-gate's purpose?",
     "symbol": "write_gate", "wiki_query": "write-gate gate write",
     "expect_any": ["gate", "block", "write", "verified"]},
    {"kind": "project", "q": "What does relay-session do?",
     "symbol": "relay", "wiki_query": "relay session",
     "expect_any": ["relay", "session", "handoff"]},
    {"kind": "project", "q": "Why was delegate-router built and where did it land?",
     "symbol": "delegate", "wiki_query": "delegate router",
     "expect_any": ["delegate", "router", "tiny", "model"]},
    {"kind": "project", "q": "What is the Karpathy LLM wiki pattern?",
     "symbol": "karpathy", "wiki_query": "karpathy wiki pattern",
     "expect_any": ["karpathy", "wiki", "markdown", "Obsidian"]},
    {"kind": "project", "q": "What is wiki-governance about?",
     "symbol": "wiki", "wiki_query": "wiki governance",
     "expect_any": ["governance", "gate", "rules"]},

    # HYBRID (need both the code + the rationale)
    {"kind": "hybrid", "q": "How does WikiStore implement progressive retrieval, and why was it designed that way?",
     "symbol": "WikiStore", "wiki_query": "wiki progressive retrieval",
     "expect_any": ["search", "rank", "preview", "retrieval"]},
    {"kind": "hybrid", "q": "What does compound compression do in code and why was it chosen?",
     "symbol": "compress", "wiki_query": "compound compression pipeline",
     "expect_any": ["compress", "LLMLingua", "pipeline"]},
]


def char_tokens(s: str) -> int:
    return (len(s) + 3) // 4


def evidence_hits(output: str, expect: list[str]) -> dict:
    matched = [w for w in expect if w.lower() in output.lower()]
    return {"hits": len(matched), "of": len(expect), "matched": matched}


def _walk_code(repo: Path):
    skip = {"__pycache__", ".git", "node_modules", ".venv", ".venvs", "graphify-out"}
    for p in repo.rglob("*"):
        if not p.is_file(): continue
        if any(part in skip for part in p.parts): continue
        if p.suffix.lower() not in CODE_EXT: continue
        yield p


def run_grep(symbol: str, repo: Path, max_files: int = 3, head_lines: int = 200) -> dict:
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
            if len(files) >= max_files: break
    parts = []
    for f in files:
        try:
            parts.append(f"=== {f.relative_to(repo)} ===\n" + "\n".join(f.read_text(errors="ignore").splitlines()[:head_lines]))
        except Exception:
            continue
    out = "\n\n".join(parts)
    return {"tokens": char_tokens(out), "elapsed_ms": int((time.time() - t0) * 1000),
            "tool_calls": 1 + len(files), "output": out}


def run_wiki(query: str, wiki_root: Path, k: int = 3) -> dict:
    t0 = time.time()
    cmd = ["python3", str(WIKI_TOOL), "--root", str(wiki_root), "search", query]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    try:
        hits = json.loads(r.stdout) if r.stdout.strip() else []
    except Exception:
        hits = []
    # take top-k previews
    parts = []
    for h in hits[:k]:
        parts.append(f"### {h.get('title', h.get('id', '?'))}  ({h.get('id', '')})\n{h.get('preview', '')}")
    out = "\n\n".join(parts)
    return {"tokens": char_tokens(out), "elapsed_ms": int((time.time() - t0) * 1000),
            "tool_calls": 1, "n_hits": len(hits), "output": out}


def run_graphify_explain(symbol: str, graph: Path) -> dict:
    t0 = time.time()
    cmd = [str(GRAPHIFY_BIN), "explain", symbol, "--graph", str(graph)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    out = r.stdout or ""
    return {"tokens": char_tokens(out), "elapsed_ms": int((time.time() - t0) * 1000),
            "tool_calls": 1, "output": out}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True)
    p.add_argument("--graph", required=True)
    p.add_argument("--wiki", required=True)
    p.add_argument("--out", default="eval/results/graphify_combo.json")
    args = p.parse_args()

    repo, graph, wiki = Path(args.repo).resolve(), Path(args.graph).resolve(), Path(args.wiki).resolve()

    rows = []
    for item in QUESTIONS:
        sym, wq, expect, kind = item["symbol"], item["wiki_query"], item["expect_any"], item["kind"]
        A = run_grep(sym, repo)
        B = run_wiki(wq, wiki)
        C = run_graphify_explain(sym, graph)
        D_output = (C.get("output", "") + "\n\n---WIKI---\n\n" + B.get("output", ""))
        D = {"tokens": char_tokens(D_output), "elapsed_ms": C["elapsed_ms"] + B["elapsed_ms"],
             "tool_calls": C["tool_calls"] + B["tool_calls"], "output": D_output}

        rows.append({
            "question": item["q"], "kind": kind, "symbol": sym, "wiki_query": wq,
            "A_grep": {k: v for k, v in A.items() if k != "output"} | {"evidence": evidence_hits(A.get("output", ""), expect)},
            "B_wiki": {k: v for k, v in B.items() if k != "output"} | {"evidence": evidence_hits(B.get("output", ""), expect)},
            "C_graphify": {k: v for k, v in C.items() if k != "output"} | {"evidence": evidence_hits(C.get("output", ""), expect)},
            "D_combo": {k: v for k, v in D.items() if k != "output"} | {"evidence": evidence_hits(D.get("output", ""), expect)},
        })

    def sum_field(arm, k, subset=None):
        rs = [r for r in rows if subset is None or r["kind"] == subset]
        return sum(r[arm].get(k, 0) for r in rs)

    def ev_rate(arm, subset=None):
        rs = [r for r in rows if subset is None or r["kind"] == subset]
        good = sum(1 for r in rs if r[arm]["evidence"]["hits"] >= 1)
        return round(100 * good / max(len(rs), 1), 1)

    summary = {"n_questions": len(rows)}
    for subset in (None, "code", "project", "hybrid"):
        label = subset or "ALL"
        n = len([r for r in rows if subset is None or r["kind"] == subset])
        summary[label] = {"n": n}
        for arm in ("A_grep", "B_wiki", "C_graphify", "D_combo"):
            summary[label][arm] = {
                "tokens": sum_field(arm, "tokens", subset),
                "tool_calls": sum_field(arm, "tool_calls", subset),
                "evidence_rate_pct": ev_rate(arm, subset),
            }

    out_path = REPO_ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"summary": summary, "per_question": rows}, indent=2))

    print(f"\n=== graphify + wiki combo ({len(rows)} questions) ===")
    for subset in ("ALL", "code", "project", "hybrid"):
        s = summary[subset]
        print(f"\n  [{subset}] n={s['n']}")
        for arm in ("A_grep", "B_wiki", "C_graphify", "D_combo"):
            print(f"    {arm:<12} tokens={s[arm]['tokens']:>6}  calls={s[arm]['tool_calls']:>3}  evidence={s[arm]['evidence_rate_pct']:>5}%")
    print(f"\n  results: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
