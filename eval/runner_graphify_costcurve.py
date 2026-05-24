#!/usr/bin/env python3
"""Build-cost curve for graphify.

For each (label, code-only directory) tuple, run `graphify extract` once
with semantic-extraction disabled (small/medium/large code-only corpora),
then `cluster-only` to populate communities. Record:
  - file count
  - on-disk source size (bytes)
  - wall time for extract
  - wall time for cluster
  - graph.json size (bytes)
  - node/edge/community count
  - peak RSS (rusage, best-effort)

Output: eval/results/graphify_costcurve.json
"""
from __future__ import annotations

import argparse
import json
import resource
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GRAPHIFY_BIN = REPO_ROOT / ".venvs" / "graphify" / "bin" / "graphify"


def dir_stats(d: Path) -> dict:
    n = 0
    total = 0
    for p in d.rglob("*"):
        if p.is_file():
            n += 1
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return {"file_count": n, "source_bytes": total}


def graph_stats(graph_json: Path) -> dict:
    """Handle BOTH graphify schemas:
    - post-`extract --no-cluster`: keys = nodes/edges/hyperedges
    - post-`cluster-only` or `extract` w/clustering: networkx node-link
      format with keys = nodes/links/...
    """
    if not graph_json.exists():
        return {"error": "graph.json not written"}
    g = json.loads(graph_json.read_text())
    nodes = g.get("nodes", [])
    edges = g.get("edges") or g.get("links") or []
    comms = {n.get("community") for n in nodes if n.get("community") not in (None, "")}
    return {
        "schema": "node-link" if "links" in g else "edges",
        "nodes": len(nodes),
        "edges": len(edges),
        "communities": len(comms),
        "graph_bytes": graph_json.stat().st_size,
        "extraction_input_tokens": g.get("input_tokens", 0),
        "extraction_output_tokens": g.get("output_tokens", 0),
    }


def timed(cmd: list[str], cwd: Path) -> dict:
    pre_rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    t0 = time.time()
    r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=1800)
    elapsed = time.time() - t0
    post_rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    # ru_maxrss on macOS is bytes; on Linux it's KB. Report both.
    return {
        "cmd": " ".join(cmd),
        "elapsed_s": round(elapsed, 2),
        "returncode": r.returncode,
        "child_maxrss_delta_bytes_or_kb": post_rss - pre_rss,
        "stdout_tail": (r.stdout or "").splitlines()[-3:],
        "stderr_tail": (r.stderr or "").splitlines()[-3:],
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--targets", nargs="+", required=True,
                   help="label:path pairs, e.g. small:/tmp/te medium:/tmp/flask large:/tmp/django")
    p.add_argument("--out", default="eval/results/graphify_costcurve.json")
    args = p.parse_args()

    results = []
    for spec in args.targets:
        if ":" not in spec:
            print(f"skip bad target: {spec}", file=sys.stderr); continue
        label, path = spec.split(":", 1)
        d = Path(path).resolve()
        if not d.exists():
            print(f"skip missing: {d}", file=sys.stderr); continue

        # Wipe any previous run
        gout = d / "graphify-out"
        if gout.exists():
            shutil.rmtree(gout)

        pre = dir_stats(d)
        # Single-shot extract with clustering enabled (matches recommended recipe).
        # Backend=ollama is just to avoid api-key prompt; we run code-only corpora
        # so semantic extraction is a no-op anyway.
        extract = timed(
            [str(GRAPHIFY_BIN), "extract", ".",
             "--backend", "ollama",
             "--api-timeout", "5", "--max-concurrency", "1"],
            cwd=d,
        )
        cluster = {"elapsed_s": 0.0, "skipped": "clustering built into extract"}
        gs = graph_stats(d / "graphify-out" / "graph.json")
        results.append({
            "label": label,
            "path": str(d),
            "source": pre,
            "extract": extract,
            "cluster": cluster,
            "graph": gs,
        })
        # Per-target print
        print(f"[{label:6}] files={pre['file_count']:5}  src={pre['source_bytes']:>10}B  "
              f"extract={extract['elapsed_s']:>6}s  "
              f"nodes={gs.get('nodes', '-'):>5}  edges={gs.get('edges', '-'):>6}  "
              f"comms={gs.get('communities', '-'):>4}  graph={gs.get('graph_bytes', 0):>9}B  "
              f"schema={gs.get('schema', '-')}")

    out_path = REPO_ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"results": results}, indent=2))
    print(f"\nresults: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
