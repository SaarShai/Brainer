#!/usr/bin/env python3
"""Quality + staleness probes for graphify graphs.

Three probes on a built graph (defaults to the small brainer
corpus). All are automatic — no judge model needed.

1. EDGE PRECISION (sample-based, automatic)
   Sample N random edges where graphify claims EXTRACTED confidence.
   For each (source, target, relation, source_file, source_location):
     - open the source_file at source_location
     - check that the target's label appears within ±5 lines (proxy for
       "the AST claim points at real code")
   Report precision and the failing sample.

2. PATH SOUNDNESS (curated, automatic)
   For a small set of known-true paths in the corpus, ask
   `graphify path <A> <B>` and verify the returned hops are real edges.
   Failed = no path returned, or any hop's edge isn't present in the graph.

3. STALENESS (active, automatic)
   Make a controlled mutation to one source file (rename a function),
   then re-query graphify WITHOUT --update. Measure whether stale
   answers persist. Then run graphify update . and re-check.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GRAPHIFY_BIN = REPO_ROOT / ".venvs" / "graphify" / "bin" / "graphify"


def load_graph(p: Path) -> tuple[list, list]:
    g = json.loads(p.read_text())
    nodes = g.get("nodes", [])
    edges = g.get("edges") or g.get("links") or []
    return nodes, edges


def node_index(nodes: list) -> dict:
    by_id = {}
    for n in nodes:
        nid = n.get("id") or n.get("node_id")
        by_id[nid] = n
    return by_id


def normalize_label(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "", s or "")


def edge_precision_probe(graph_json: Path, repo: Path, k: int = 30, seed: int = 42) -> dict:
    nodes, edges = load_graph(graph_json)
    by_id = node_index(nodes)

    # Restrict to high-signal edge relations grounded in code (skip
    # 'rationale_for' which is inferred narrative).
    candidates = [e for e in edges
                  if e.get("confidence") == "EXTRACTED"
                  and e.get("source_file")
                  and e.get("source_location")
                  and e.get("relation") in {"calls", "imports", "imports_from", "contains", "method", "defines"}]
    rng = random.Random(seed)
    sample = rng.sample(candidates, min(k, len(candidates)))

    hits, misses = [], []
    for e in sample:
        src_path = repo / e["source_file"]
        if not src_path.exists():
            misses.append({**e, "reason": "source_file missing"})
            continue
        m = re.match(r"L(\d+)", str(e.get("source_location", "")))
        if not m:
            misses.append({**e, "reason": "unparseable source_location"})
            continue
        line = int(m.group(1))
        try:
            lines = src_path.read_text(errors="ignore").splitlines()
        except Exception as ex:
            misses.append({**e, "reason": f"read error {ex}"}); continue
        lo, hi = max(0, line - 6), min(len(lines), line + 6)
        window = "\n".join(lines[lo:hi])
        target_node = by_id.get(e["target"], {})
        target_label = normalize_label(target_node.get("label", "") or e["target"])
        if not target_label:
            misses.append({**e, "reason": "empty target label"}); continue
        if target_label in normalize_label(window):
            hits.append(e)
        else:
            misses.append({**e, "reason": "target label not in ±5 lines",
                           "window_excerpt": window[:200]})

    return {
        "n_candidates": len(candidates),
        "n_sampled": len(sample),
        "n_hits": len(hits),
        "precision_pct": round(100 * len(hits) / max(len(sample), 1), 1),
        "miss_examples": misses[:5],
    }


CURATED_PATHS = [
    # (start_label, end_label, expected_hops_minimum, expected_hops_maximum)
    ("WikiStore", ".search()", 1, 1),
    ("WikiStore", "._ensure_db()", 1, 2),
    ("_cli_main()", ".search()", 2, 3),
]


def path_soundness_probe(graph_json: Path) -> dict:
    nodes, edges = load_graph(graph_json)
    # Build adjacency for verification
    adj: dict[str, set[tuple[str, str]]] = {}
    label_to_id = {}
    for n in nodes:
        nid = n.get("id") or n.get("node_id")
        label_to_id.setdefault(n.get("label", ""), nid)
    for e in edges:
        s, t, r = e.get("source"), e.get("target"), e.get("relation")
        if not s or not t: continue
        adj.setdefault(s, set()).add((t, r))
        adj.setdefault(t, set()).add((s, r))  # treat undirected for verification

    results = []
    for a, b, lo, hi in CURATED_PATHS:
        cmd = [str(GRAPHIFY_BIN), "path", a, b, "--graph", str(graph_json)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        out = r.stdout
        # Parse hop lines: "  A --rel [conf]--> B"
        hops = re.findall(r"^\s+(\S.+?)\s+--(\w+)\s+\[[^\]]+\]-->\s+(.+?)\s*$", out, re.MULTILINE)
        hop_count = len(hops)
        verdict = "no_path"
        bad_hops: list = []
        if hops:
            verdict = "ok"
            for src_lbl, rel, tgt_lbl in hops:
                src_id = label_to_id.get(src_lbl)
                tgt_id = label_to_id.get(tgt_lbl)
                if not src_id or not tgt_id:
                    bad_hops.append((src_lbl, rel, tgt_lbl, "unknown label"))
                    verdict = "label_unknown"; continue
                if (tgt_id, rel) not in adj.get(src_id, set()) and (src_id, rel) not in adj.get(tgt_id, set()):
                    bad_hops.append((src_lbl, rel, tgt_lbl, "edge not in graph"))
                    verdict = "phantom_hop"
        results.append({
            "start": a, "end": b, "hops": hop_count, "verdict": verdict,
            "expected_hops_min": lo, "expected_hops_max": hi,
            "within_expected": (lo <= hop_count <= hi) if verdict == "ok" else False,
            "bad_hops": bad_hops,
            "raw_excerpt": out[:300],
        })
    n_ok = sum(1 for r in results if r["verdict"] == "ok" and r["within_expected"])
    return {"n": len(results), "n_ok": n_ok, "soundness_pct": round(100 * n_ok / len(results), 1), "per_case": results}


def staleness_probe(corpus_root: Path, graph_path: Path) -> dict:
    """Mutate one source file and see if graphify still serves the old answer.

    Works on a TEMPORARY COPY so the original corpus is untouched.
    """
    work = Path("/tmp/graphify-stale-probe")
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(corpus_root, work, symlinks=False, ignore=shutil.ignore_patterns("graphify-out", "__pycache__"))

    # Build a fresh graph on the copy
    t0 = time.time()
    subprocess.run([str(GRAPHIFY_BIN), "extract", ".",
                    "--backend", "ollama", "--api-timeout", "5", "--max-concurrency", "1"],
                   cwd=work, capture_output=True, text=True, timeout=300)
    build_s = round(time.time() - t0, 2)

    work_graph = work / "graphify-out" / "graph.json"
    if not work_graph.exists():
        return {"error": "could not build graph on copy"}

    # Find a real function to rename. Pick wiki.py:read_page → read_page_RENAMED.
    target = work / "skills" / "wiki-memory" / "tools" / "wiki.py"
    if not target.exists():
        return {"error": f"target file not in copy: {target}"}

    # Baseline: graphify explain ".read_page()" should match
    baseline = subprocess.run(
        [str(GRAPHIFY_BIN), "explain", ".read_page()", "--graph", str(work_graph)],
        capture_output=True, text=True, timeout=30,
    ).stdout
    baseline_found = ".read_page()" in baseline and "Connections" in baseline

    # Mutate the source
    src = target.read_text()
    if "def read_page" not in src:
        return {"error": "function read_page not found in target"}
    target.write_text(src.replace("def read_page", "def read_page_RENAMED"))

    # Query WITHOUT update — should still find old name (proves staleness risk)
    stale = subprocess.run(
        [str(GRAPHIFY_BIN), "explain", ".read_page()", "--graph", str(work_graph)],
        capture_output=True, text=True, timeout=30,
    ).stdout
    stale_still_found = ".read_page()" in stale and "Connections" in stale

    # Now run update
    upd_t0 = time.time()
    upd = subprocess.run([str(GRAPHIFY_BIN), "update", ".", "--force"],
                        cwd=work, capture_output=True, text=True, timeout=300)
    upd_s = round(time.time() - upd_t0, 2)

    fresh = subprocess.run(
        [str(GRAPHIFY_BIN), "explain", ".read_page()", "--graph", str(work_graph)],
        capture_output=True, text=True, timeout=30,
    ).stdout
    fresh_still_found = ".read_page()" in fresh and "Connections" in fresh

    # The renamed function should now be queryable
    renamed = subprocess.run(
        [str(GRAPHIFY_BIN), "explain", ".read_page_RENAMED()", "--graph", str(work_graph)],
        capture_output=True, text=True, timeout=30,
    ).stdout
    renamed_found = "read_page_RENAMED" in renamed and "Connections" in renamed

    return {
        "build_s": build_s,
        "baseline_found_old_name": baseline_found,
        "stale_still_found_old_name": stale_still_found,  # expected True — that's the staleness risk
        "update_s": upd_s,
        "update_rc": upd.returncode,
        "update_tail": (upd.stdout or "").splitlines()[-3:],
        "after_update_still_finds_old": fresh_still_found,  # expected False after good update
        "after_update_finds_renamed": renamed_found,         # expected True
        "verdict": (
            "good_staleness_signal" if stale_still_found and not fresh_still_found and renamed_found
            else ("update_broke_things" if not renamed_found
                  else "staleness_undetectable")
        ),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--corpus", required=True, help="repo root (with graphify-out/)")
    p.add_argument("--out", default="eval/results/graphify_quality.json")
    p.add_argument("--edge-k", type=int, default=30)
    args = p.parse_args()

    corpus = Path(args.corpus).resolve()
    graph = corpus / "graphify-out" / "graph.json"
    if not graph.exists():
        print(f"ERROR: graph not found at {graph}", file=sys.stderr)
        return 1

    edge = edge_precision_probe(graph, corpus, k=args.edge_k)
    path = path_soundness_probe(graph)
    stale = staleness_probe(corpus, graph)

    out = {"corpus": str(corpus), "edge_precision": edge, "path_soundness": path, "staleness": stale}
    out_path = REPO_ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str))

    print(f"\n=== graphify quality ===")
    print(f"  EDGE PRECISION   {edge['n_hits']}/{edge['n_sampled']}  = {edge['precision_pct']}%")
    print(f"  PATH SOUNDNESS   {path['n_ok']}/{path['n']}  = {path['soundness_pct']}%")
    print(f"  STALENESS        verdict={stale.get('verdict', '-')}")
    print(f"                   baseline_found={stale.get('baseline_found_old_name')}  "
          f"stale_found={stale.get('stale_still_found_old_name')}  "
          f"after_update_renamed_found={stale.get('after_update_finds_renamed')}")
    print(f"  results: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
