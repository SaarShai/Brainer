#!/usr/bin/env python3
"""impact-of-change — map a git diff to its blast radius (forward impact only).

Given uncommitted edits (or a commit range), extract the changed symbols, then
query graphify's call graph (`graphify-out/graph.json`) for inbound dependents
(who CALLS the changed symbols), bounded to depth<=3. Score each changed symbol
LOW/MEDIUM/HIGH by caller breadth + chain depth, and emit a structured,
parseable report (dict -> JSON or markdown).

Scope decisions (resolved from the spec's OPEN QUESTIONS):
  - Dead-symbol detection is OUT of scope — forward impact only.
  - graphify absent  -> single-pass lexical grep for the symbol names; every
    hit marked "unverified", clearly labelled degraded-mode. Never errors.
  - graphify stale (graph older than HEAD) -> a drift WARNING, not a blocker.

This skill does NOT run tests, modify code, or decide for the user. It is
graph-based planning that composes with verify-before-completion (which runs
the fresh tests on the high-risk zones this report names).

CLI:
  python3 impact.py [--repo DIR] [--diff working|<sha>|<a>..<b>]
                    [--depth N] [--graph PATH] [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import deque
from pathlib import Path
from typing import Any

DEFAULT_DEPTH = 3
CALL_RELATIONS = {"calls"}  # graphify relation labels are lowercase
# Heuristic: a caller file is "entry/critical" if its basename looks like a
# surface (CLI/main/app/api/server/handler/route/__main__). Used by risk scoring.
ENTRY_HINTS = ("main", "__main__", "cli", "app", "api", "server",
               "handler", "handlers", "route", "routes", "view", "views")


# ==========================================================================
# git diff -> changed symbols
# ==========================================================================
def _git(args: list[str], repo: str) -> str:
    res = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True,
        env={**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null",
             "GIT_CONFIG_SYSTEM": "/dev/null"},
    )
    if res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {res.stderr.strip()}")
    return res.stdout


def _diff_args(diff_spec: str) -> list[str]:
    """Translate a diff spec into `git diff` arguments.

    working      -> uncommitted (working tree + index) vs HEAD
    <a>..<b>     -> range
    <sha>        -> that commit vs its parent (git diff <sha>^! semantics)
    """
    if diff_spec in ("working", "", None):
        return ["diff", "HEAD"]
    if ".." in diff_spec:
        return ["diff", diff_spec]
    # single commit: compare it to its first parent
    return ["diff", f"{diff_spec}^", diff_spec]


# A def/class line in a diff hunk. Captures whether it was added/removed and the
# symbol name. Methods (indented def) and classes are all caught here.
_DEF_RE = re.compile(r"^([+\- ])\s*(?:async\s+)?(def|class)\s+([A-Za-z_]\w*)")
_FILE_RE = re.compile(r"^\+\+\+ b/(.+)$")


def extract_changed_symbols(repo: str, diff_spec: str) -> list[dict[str, Any]]:
    """Parse `git diff` output into changed symbols.

    A symbol is reported when a `def`/`class` line is added or removed. A symbol
    whose own header line is unchanged but whose body changed is also reported
    by tracking the most-recent enclosing def/class for each changed body line.

    Returns rows: {symbol, kind, file, change} where change in
    {added, deleted, modified}.
    """
    raw = _git(_diff_args(diff_spec), repo)
    cur_file: str | None = None
    # state per file: list of (header_change, kind, name) seen in hunks, and the
    # most recent enclosing symbol for context-line body edits.
    found: dict[tuple[str, str], dict[str, Any]] = {}  # (file, name) -> row
    enclosing: str | None = None
    enclosing_kind: str | None = None
    body_touched: set[tuple[str, str]] = set()

    for line in raw.splitlines():
        fm = _FILE_RE.match(line)
        if fm:
            cur_file = fm.group(1)
            enclosing = None
            enclosing_kind = None
            continue
        if cur_file is None or not cur_file.endswith(".py"):
            continue
        if line.startswith("@@"):
            # new hunk: enclosing context resets (we don't trust cross-hunk nesting)
            enclosing = None
            enclosing_kind = None
            continue
        m = _DEF_RE.match(line)
        if m:
            sign, kind, name = m.group(1), m.group(2), m.group(3)
            enclosing, enclosing_kind = name, kind
            key = (cur_file, name)
            if sign == "+":
                cur = found.get(key)
                if cur and cur["change"] == "deleted":
                    cur["change"] = "modified"  # del+add same name = modified
                elif not cur:
                    found[key] = {"symbol": name, "kind": kind,
                                  "file": cur_file, "change": "added"}
            elif sign == "-":
                cur = found.get(key)
                if cur and cur["change"] == "added":
                    cur["change"] = "modified"
                elif not cur:
                    found[key] = {"symbol": name, "kind": kind,
                                  "file": cur_file, "change": "deleted"}
            else:  # context line that is itself a def/class header (unchanged)
                enclosing, enclosing_kind = name, kind
            continue
        # a changed body line (added/removed, not a header) -> mark enclosing modified
        if line and line[0] in "+-" and enclosing is not None:
            body_touched.add((cur_file, enclosing))

    # promote body-touched enclosing symbols to "modified" if not already a row
    for (f, name) in body_touched:
        key = (f, name)
        if key not in found:
            # kind unknown from body alone; default to function unless name TitleCase
            kind = "class" if name[:1].isupper() and "_" not in name else "function"
            found[key] = {"symbol": name, "kind": kind, "file": f,
                          "change": "modified"}

    # normalize kind label: graphify uses function/method/class; def -> function
    rows = []
    for row in found.values():
        if row["kind"] == "def":
            row["kind"] = "function"
        rows.append(row)
    rows.sort(key=lambda r: (r["file"], r["symbol"]))
    return rows


# ==========================================================================
# graph loading + traversal
# ==========================================================================
def graph_path_for(repo: str, explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    return Path(repo) / "graphify-out" / "graph.json"


def load_graph(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    nodes = data.get("nodes", [])
    # networkx node-link uses "links"; tolerate "edges"/"relationships" too.
    links = data.get("links") or data.get("edges") or data.get("relationships") or []
    return {"nodes": nodes, "links": links}


def _node_symbol(label: str) -> str:
    """graphify label -> bare symbol name.

    function -> "name()"   ; method -> ".name()" ; class -> "Name".
    """
    lbl = label.strip()
    if lbl.endswith("()"):
        lbl = lbl[:-2]
    if lbl.startswith("."):
        lbl = lbl[1:]
    return lbl


def is_stale(graph_file: Path, repo: str) -> bool:
    """Graph is stale if HEAD moved after the graph was written.

    Compares the graph file mtime to the committer time of HEAD. Best-effort:
    if HEAD time is unavailable, returns False (no false drift warning).
    """
    try:
        head_ts = int(_git(["log", "-1", "--format=%ct"], repo).strip())
    except Exception:
        return False
    try:
        graph_ts = int(graph_file.stat().st_mtime)
    except OSError:
        return False
    return head_ts > graph_ts


def build_indexes(graph: dict[str, Any]) -> dict[str, Any]:
    nodes_by_id = {n["id"]: n for n in graph["nodes"] if "id" in n}
    # symbol name -> set of node ids (one name may resolve to multiple nodes)
    name_to_ids: dict[str, set[str]] = {}
    for n in graph["nodes"]:
        if n.get("file_type") and n["file_type"] != "code":
            continue
        sym = _node_symbol(n.get("label", ""))
        if sym:
            name_to_ids.setdefault(sym, set()).add(n["id"])
    # inbound CALLS adjacency: target_id -> [source_id, ...]
    inbound: dict[str, list[str]] = {}
    for link in graph["links"]:
        if link.get("relation") in CALL_RELATIONS:
            inbound.setdefault(link["target"], []).append(link["source"])
    return {"nodes_by_id": nodes_by_id, "name_to_ids": name_to_ids,
            "inbound": inbound}


def callers_of(node_id: str, idx: dict[str, Any], depth: int) -> list[dict[str, Any]]:
    """BFS inbound CALLS edges from node_id up to `depth`. Direct callers = depth 1."""
    nodes_by_id = idx["nodes_by_id"]
    inbound = idx["inbound"]
    seen = {node_id}
    out: list[dict[str, Any]] = []
    q: deque[tuple[str, int]] = deque((src, 1) for src in inbound.get(node_id, []))
    while q:
        cid, d = q.popleft()
        if cid in seen or d > depth:
            continue
        seen.add(cid)
        node = nodes_by_id.get(cid, {})
        out.append({
            "caller": _node_symbol(node.get("label", cid)),
            "file": node.get("source_file", "?"),
            "depth": d,
            "verified": True,
        })
        if d < depth:
            for nxt in inbound.get(cid, []):
                if nxt not in seen:
                    q.append((nxt, d + 1))
    return out


# ==========================================================================
# risk classification (spec thresholds)
# ==========================================================================
def classify_risk(callers: list[dict[str, Any]]) -> tuple[str, str]:
    """Score a changed symbol from its caller set. Returns (risk, justification).

    LOW    : <=2 direct callers, all in tests/deprecated paths.
    MEDIUM : 3-10 direct callers, or 1+ indirect callers at depth 2.
    HIGH   : >10 direct callers, OR callers in entry/critical paths,
             OR transitive depth >=3.
    """
    direct = [c for c in callers if c["depth"] == 1]
    n_direct = len(direct)
    max_depth = max((c["depth"] for c in callers), default=0)
    indirect = [c for c in callers if c["depth"] >= 2]

    def _is_test_or_dep(c: dict[str, Any]) -> bool:
        f = (c.get("file") or "").lower()
        return ("test" in f or "deprecat" in f)

    def _is_entry(c: dict[str, Any]) -> bool:
        base = Path(c.get("file") or "").name.lower()
        stem = base[:-3] if base.endswith(".py") else base
        parts = set(re.split(r"[_.]", stem))
        return bool(parts & set(ENTRY_HINTS))

    # HIGH triggers
    if n_direct > 10:
        return "HIGH", f">10 direct callers ({n_direct}) — broad blast radius"
    entry_callers = [c for c in callers if _is_entry(c)]
    if entry_callers:
        names = ", ".join(sorted({c["file"] for c in entry_callers})[:3])
        return "HIGH", f"caller(s) in entry/critical paths ({names})"
    if max_depth >= 3:
        return "HIGH", f"transitive dependency chain reaches depth {max_depth}"

    # LOW: <=2 direct callers, all tests/deprecated, no deeper chain
    if n_direct <= 2 and max_depth <= 1 and all(_is_test_or_dep(c) for c in direct) \
            and direct:
        return "LOW", f"<=2 callers ({n_direct}), all in tests/deprecated paths"
    if n_direct == 0 and not callers:
        return "LOW", "no inbound callers in the graph (new or isolated symbol)"

    # MEDIUM: 3-10 direct, or any indirect at depth 2
    if 3 <= n_direct <= 10:
        return "MEDIUM", f"{n_direct} direct callers"
    if indirect:
        return "MEDIUM", f"indirect caller(s) at depth {max_depth}"

    # remaining: 1-2 direct callers in non-test code, no deeper chain
    return "LOW", f"{n_direct} direct caller(s), shallow chain"


_RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def _max_risk(risks: list[str]) -> str:
    if not risks:
        return "LOW"
    return max(risks, key=lambda r: _RISK_ORDER[r])


# ==========================================================================
# degraded grep fallback (graphify absent)
# ==========================================================================
_TEXT_EXT = {".py"}


def grep_callers(repo: str, symbol: str, exclude_file: str | None) -> list[dict[str, Any]]:
    """Single-pass lexical search for `\\bsymbol\\s*\\(` across tracked .py files.

    Every hit is marked unverified (verified=False). Best-effort, depth=1 only —
    this is the degraded path: no graph, no transitive chain.
    """
    pat = re.compile(r"\b" + re.escape(symbol) + r"\s*\(")
    hits: list[dict[str, Any]] = []
    try:
        tracked = _git(["ls-files", "*.py"], repo).splitlines()
    except Exception:
        tracked = [str(p.relative_to(repo)) for p in Path(repo).rglob("*.py")]
    for rel in tracked:
        if exclude_file and rel == exclude_file:
            # skip the defining file's own def line; still report internal calls
            pass
        fpath = Path(repo) / rel
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            # skip the definition line itself
            if re.match(r"\s*(?:async\s+)?def\s+" + re.escape(symbol) + r"\b", line):
                continue
            if pat.search(line):
                hits.append({"caller": f"{rel}:{i}", "file": rel,
                             "depth": 1, "verified": False})
    return hits


# ==========================================================================
# top-level analysis
# ==========================================================================
def analyze(repo: str, diff_spec: str = "working", depth: int = DEFAULT_DEPTH,
            graph: str | None = None) -> dict[str, Any]:
    repo = str(Path(repo).resolve())
    changed = extract_changed_symbols(repo, diff_spec)
    warnings: list[str] = []
    gpath = graph_path_for(repo, graph)

    use_graph = gpath.exists()
    if use_graph and is_stale(gpath, repo):
        warnings.append(
            "DRIFT: graphify graph is older than HEAD — impact may be stale; "
            "run `graphify update . --force` (or re-extract after renames/deletes)."
        )

    affected: list[dict[str, Any]] = []
    if use_graph:
        mode = "graph"
        try:
            g = load_graph(gpath)
            idx = build_indexes(g)
        except Exception as exc:  # malformed graph -> degrade, never crash
            warnings.append(f"graph load failed ({exc}); falling back to grep.")
            use_graph = False
        if use_graph:
            for row in changed:
                ids = idx["name_to_ids"].get(row["symbol"], set())
                callers: list[dict[str, Any]] = []
                seen_pairs = set()
                for nid in ids:
                    for c in callers_of(nid, idx, depth):
                        k = (c["caller"], c["file"], c["depth"])
                        if k not in seen_pairs:
                            seen_pairs.add(k)
                            callers.append(c)
                risk, why = classify_risk(callers)
                affected.append(_affected_row(row, callers, risk, why))

    if not use_graph:
        mode = "degraded"
        warnings.append(
            "impact estimated WITHOUT graph; results are lexical and unverified. "
            "Run `graphify extract . --backend ollama` for precision."
        )
        for row in changed:
            callers = grep_callers(repo, row["symbol"], row["file"])
            # degraded risk: lexical breadth only (no entry/depth signal)
            risk, why = _degraded_risk(callers)
            affected.append(_affected_row(row, callers, risk, why))

    overall = _max_risk([a["risk"] for a in affected])
    summary = (
        f"{len(changed)} symbol(s) changed, "
        f"{sum(a['caller_count'] for a in affected)} affected caller(s), "
        f"risk = {overall}"
        + ("  [degraded-mode: lexical estimate]" if mode == "degraded" else "")
    )
    recs = _recommendations(affected, mode)
    return {
        "mode": mode,
        "risk": overall,
        "summary": summary,
        "changed_symbols": changed,
        "affected": affected,
        "recommendations": recs,
        "warnings": warnings,
    }


def _affected_row(row, callers, risk, why):
    files = sorted({c["file"] for c in callers})
    return {
        "symbol": row["symbol"],
        "kind": row["kind"],
        "change": row["change"],
        "source_file": row["file"],
        "risk": risk,
        "risk_reason": why,
        "caller_count": len([c for c in callers if c["depth"] == 1]),
        "max_depth": max((c["depth"] for c in callers), default=0),
        "callers": callers,
        "files": files,
    }


def _degraded_risk(callers: list[dict[str, Any]]) -> tuple[str, str]:
    """Coarse risk from lexical hit count (no graph signal)."""
    n = len(callers)
    if n == 0:
        return "LOW", "no lexical references found (unverified)"
    if n > 10:
        return "HIGH", f">10 lexical references ({n}) — broad but unverified"
    if n >= 3:
        return "MEDIUM", f"{n} lexical references (unverified)"
    return "LOW", f"{n} lexical reference(s) (unverified)"


def _recommendations(affected, mode) -> list[str]:
    recs: list[str] = []
    high = [a for a in affected if a["risk"] == "HIGH"]
    med = [a for a in affected if a["risk"] == "MEDIUM"]
    for a in high:
        recs.append(
            f"HIGH `{a['symbol']}` ({a['caller_count']} direct callers): "
            f"run the broad test suite / verify entry points before shipping."
        )
    for a in med:
        recs.append(
            f"MEDIUM `{a['symbol']}`: run targeted tests on "
            f"{', '.join(a['files'][:3]) or 'its callers'}."
        )
    if mode == "degraded":
        recs.append(
            "Build the graph (`graphify extract . --backend ollama`) and re-run "
            "for precise, verified dependents."
        )
    if not recs:
        recs.append("No dependents found — a unit test on the changed symbol suffices.")
    recs.append("Then hand the high-risk list to verify-before-completion to run fresh tests.")
    return recs


# ==========================================================================
# markdown rendering
# ==========================================================================
def render_markdown(rep: dict[str, Any]) -> str:
    L: list[str] = []
    badge = " (DEGRADED-MODE)" if rep["mode"] == "degraded" else ""
    L.append(f"# Impact of change{badge}")
    L.append("")
    for w in rep.get("warnings", []):
        L.append(f"> WARNING: {w}")
    if rep.get("warnings"):
        L.append("")
    L.append("## Summary")
    L.append("")
    L.append(rep["summary"])
    L.append("")
    L.append("## Changed symbols")
    L.append("")
    L.append("| symbol | kind | file | change |")
    L.append("| --- | --- | --- | --- |")
    for c in rep["changed_symbols"]:
        L.append(f"| `{c['symbol']}` | {c['kind']} | {c['file']} | {c['change']} |")
    if not rep["changed_symbols"]:
        L.append("| _(none detected in diff)_ | | | |")
    L.append("")
    L.append("## Affected symbols (dependents)")
    L.append("")
    L.append("| symbol | risk | direct callers | max depth | files | why |")
    L.append("| --- | --- | --- | --- | --- | --- |")
    for a in rep["affected"]:
        files = ", ".join(a["files"][:4]) or "—"
        L.append(
            f"| `{a['symbol']}` | {a['risk']} | {a['caller_count']} | "
            f"{a['max_depth']} | {files} | {a['risk_reason']} |"
        )
    if not rep["affected"]:
        L.append("| _(no changed symbols)_ | | | | | |")
    L.append("")
    # critical paths: high-risk callers at depth <= 2
    crit = []
    for a in rep["affected"]:
        if a["risk"] == "HIGH":
            for c in a["callers"]:
                if c["depth"] <= 2:
                    tag = "" if c.get("verified", True) else " (unverified)"
                    crit.append(f"- `{c['caller']}` → `{a['symbol']}` "
                                f"(depth {c['depth']}, {c['file']}){tag}")
    if crit:
        L.append("## Critical paths")
        L.append("")
        L.extend(crit[:25])
        L.append("")
    L.append("## Recommendations")
    L.append("")
    for r in rep["recommendations"]:
        L.append(f"- {r}")
    L.append("")
    return "\n".join(L)


# ==========================================================================
# CLI
# ==========================================================================
def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Map a git diff to its blast radius.")
    ap.add_argument("--repo", default=".", help="repo root (default: cwd)")
    ap.add_argument("--diff", default="working",
                    help="working | <sha> | <a>..<b> (default: working)")
    ap.add_argument("--depth", type=int, default=DEFAULT_DEPTH,
                    help=f"max inbound-call depth (default: {DEFAULT_DEPTH})")
    ap.add_argument("--graph", default=None,
                    help="explicit path to graph.json (default: <repo>/graphify-out/graph.json)")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of markdown")
    args = ap.parse_args(argv[1:])
    try:
        rep = analyze(repo=args.repo, diff_spec=args.diff,
                      depth=args.depth, graph=args.graph)
    except Exception as exc:
        # Degrade, never block the user (spec req 4). Emit a minimal report.
        print(f"# Impact of change (ERROR)\n\n> Could not analyze: {exc}",
              file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        print(render_markdown(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
