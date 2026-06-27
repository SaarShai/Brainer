#!/usr/bin/env python3
"""Standalone tests for impact.py (no pytest; assert + sys.exit(1) on failure).

Covers the spec's E1-E4 probes against a hand-built fixture: a temp git repo
with 3-4 python files and KNOWN call edges, plus a fixture graph.json that
mirrors graphify-out/graph.json's networkx node-link shape (nodes + `links`
with `relation: "calls"`). The graph path is driven by pointing the tool at the
fixture graph; the degrade path needs no graphify at all.

  E1  precision  — change a leaf fn -> reported dependents match ground truth.
  E2  degraded   — graphify absent -> grep-based report + WARNING, never errors.
  E3  risk       — LOW (private helper, 1 caller) vs HIGH (>10 callers).
  E4  structure  — output is parseable JSON with the documented shape.

Run: python3 skills/impact-of-change/tools/test_impact.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import impact  # noqa: E402  (sys.path tweak above is intentional)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _run(cmd, cwd):
    return subprocess.run(
        cmd, cwd=cwd, check=True, capture_output=True, text=True,
        env={**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null",
             "GIT_CONFIG_SYSTEM": "/dev/null"},
    )


def _git(args, cwd):
    return _run(["git", *args], cwd)


def make_repo(root: Path) -> None:
    """3 python files with known call edges.

    api.py:    handler1..handler12() each call leaf_fn()   (12 entry callers)
    core.py:   leaf_fn(); private_helper() called once by core_main()
    util.py:   core_main() calls private_helper()
    """
    handlers = "\n\n".join(
        f"def handler{i}():\n    return leaf_fn() + {i}" for i in range(1, 13)
    )
    (root / "api.py").write_text(
        "from core import leaf_fn\n\n" + handlers + "\n"
    )
    (root / "core.py").write_text(
        "def leaf_fn():\n"
        "    return 41 + 1\n\n"
        "def private_helper():\n"
        "    return 7\n"
    )
    (root / "util.py").write_text(
        "from core import private_helper\n\n"
        "def core_main():\n"
        "    return private_helper()\n"
    )
    _git(["init", "-q"], root)
    _git(["config", "user.email", "t@t"], root)
    _git(["config", "user.name", "t"], root)
    _git(["add", "-A"], root)
    _git(["commit", "-qm", "init"], root)


def write_graph(root: Path) -> Path:
    """Fixture graph.json mirroring graphify-out/graph.json (networkx node-link).

    Node ids/labels follow graphify's real conventions:
      function node label == "name()"; method label == ".name()";
      class label == bare name. Inbound callers == links with
      relation=="calls" and target==<node id>.
    """

    def fn(node_id, name, file, line):
        return {
            "id": node_id, "label": f"{name}()", "file_type": "code",
            "source_file": file, "source_location": f"L{line}",
        }

    nodes = [
        {"id": "core_py", "label": "core.py", "source_file": "core.py",
         "source_location": "L1", "file_type": "code"},
        fn("core_leaf_fn", "leaf_fn", "core.py", 1),
        fn("core_private_helper", "private_helper", "core.py", 4),
        fn("util_core_main", "core_main", "util.py", 3),
    ]
    for i in range(1, 13):
        nodes.append(fn(f"api_handler{i}", f"handler{i}", "api.py", i))

    links = []
    # 12 entry handlers all CALL leaf_fn  -> HIGH
    for i in range(1, 13):
        links.append({"relation": "calls", "source": f"api_handler{i}",
                      "target": "core_leaf_fn", "confidence": "EXTRACTED"})
    # exactly ONE internal caller of private_helper -> LOW
    links.append({"relation": "calls", "source": "util_core_main",
                  "target": "core_private_helper", "confidence": "EXTRACTED"})

    graph = {"directed": True, "multigraph": False, "graph": {},
             "nodes": nodes, "links": links}
    out_dir = root / "graphify-out"
    out_dir.mkdir(exist_ok=True)
    p = out_dir / "graph.json"
    p.write_text(json.dumps(graph))
    return p


# --------------------------------------------------------------------------
# E1 — precision: changed leaf fn -> dependents match ground truth
# --------------------------------------------------------------------------
def test_e1_precision(root: Path) -> None:
    write_graph(root)
    # modify leaf_fn body (a real diff that touches the leaf symbol)
    (root / "core.py").write_text(
        "def leaf_fn():\n"
        "    return 99  # changed\n\n"
        "def private_helper():\n"
        "    return 7\n"
    )
    rep = impact.analyze(repo=str(root), diff_spec="working")
    assert rep["mode"] == "graph", f"E1 expected graph mode, got {rep['mode']}"
    changed = {c["symbol"] for c in rep["changed_symbols"]}
    assert "leaf_fn" in changed, f"E1 leaf_fn not detected as changed: {changed}"
    # ground truth: leaf_fn is called by handler1..handler12 (12 callers)
    affected_for_leaf = next(
        a for a in rep["affected"] if a["symbol"] == "leaf_fn"
    )
    callers = {c["caller"] for c in affected_for_leaf["callers"]}
    expected = {f"handler{i}" for i in range(1, 13)}
    assert callers == expected, (
        f"E1 dependents mismatch.\n expected={sorted(expected)}\n got={sorted(callers)}"
    )
    print("PASS E1 precision: leaf_fn -> 12 handlers matched ground truth")


# --------------------------------------------------------------------------
# E2 — degraded: graphify absent -> grep report + WARNING, never errors
# --------------------------------------------------------------------------
def test_e2_degraded(root: Path) -> None:
    # No graph written / present at all.
    assert not (root / "graphify-out" / "graph.json").exists(), \
        "E2 setup: graph.json must be absent"
    (root / "core.py").write_text(
        "def leaf_fn():\n"
        "    return 0  # degraded-path edit\n\n"
        "def private_helper():\n"
        "    return 7\n"
    )
    rep = impact.analyze(repo=str(root), diff_spec="working")
    assert rep["mode"] == "degraded", f"E2 expected degraded mode, got {rep['mode']}"
    assert rep["warnings"], "E2 expected a non-empty warnings list"
    assert any("graphify" in w.lower() for w in rep["warnings"]), \
        f"E2 warning should mention graphify: {rep['warnings']}"
    # grep fallback still finds the lexical references to leaf_fn (api.py uses it)
    affected_for_leaf = next(
        (a for a in rep["affected"] if a["symbol"] == "leaf_fn"), None
    )
    assert affected_for_leaf is not None, "E2 expected leaf_fn in affected list"
    assert all(c.get("verified") is False for c in affected_for_leaf["callers"]), \
        "E2 all degraded hits must be marked unverified"
    files_hit = {c["file"] for c in affected_for_leaf["callers"]}
    assert "api.py" in files_hit, f"E2 grep should find api.py reference: {files_hit}"
    # markdown render must NOT raise and must carry the degraded label
    md = impact.render_markdown(rep)
    assert "degraded" in md.lower(), "E2 markdown must carry degraded-mode label"
    print("PASS E2 degraded: grep fallback + warning, leaf_fn refs in api.py, unverified")


# --------------------------------------------------------------------------
# E3 — risk classification: LOW vs HIGH
# --------------------------------------------------------------------------
def test_e3_risk(root: Path) -> None:
    write_graph(root)
    # change BOTH leaf_fn (12 callers -> HIGH) and private_helper (1 -> LOW)
    (root / "core.py").write_text(
        "def leaf_fn():\n"
        "    return 1  # changed\n\n"
        "def private_helper():\n"
        "    return 8  # changed\n"
    )
    rep = impact.analyze(repo=str(root), diff_spec="working")
    by_sym = {a["symbol"]: a for a in rep["affected"]}
    assert by_sym["leaf_fn"]["risk"] == "HIGH", \
        f"E3 leaf_fn (12 callers) must be HIGH, got {by_sym['leaf_fn']['risk']}"
    assert by_sym["private_helper"]["risk"] == "LOW", \
        f"E3 private_helper (1 caller) must be LOW, got {by_sym['private_helper']['risk']}"
    # overall report risk is the max of per-symbol risks
    assert rep["risk"] == "HIGH", f"E3 overall risk must be HIGH, got {rep['risk']}"
    print("PASS E3 risk: leaf_fn=HIGH (12 callers), private_helper=LOW (1 caller)")


# --------------------------------------------------------------------------
# E4 — output is structured / parseable
# --------------------------------------------------------------------------
def test_e4_structure(root: Path) -> None:
    write_graph(root)
    (root / "core.py").write_text(
        "def leaf_fn():\n    return 2  # changed\n\n"
        "def private_helper():\n    return 7\n"
    )
    rep = impact.analyze(repo=str(root), diff_spec="working")
    # round-trips through JSON (proves it is a plain serializable structure)
    rep2 = json.loads(json.dumps(rep))
    for key in ("mode", "risk", "changed_symbols", "affected",
                "recommendations", "warnings", "summary"):
        assert key in rep2, f"E4 missing top-level key: {key}"
    assert isinstance(rep2["changed_symbols"], list)
    assert isinstance(rep2["affected"], list)
    for a in rep2["affected"]:
        for key in ("symbol", "risk", "caller_count", "max_depth", "callers", "files"):
            assert key in a, f"E4 affected row missing {key}: {a}"
        assert a["risk"] in ("LOW", "UNKNOWN", "MEDIUM", "HIGH")
    md = impact.render_markdown(rep2)
    assert md.startswith("#"), "E4 markdown should start with a heading"
    assert "Summary" in md and "Changed symbols" in md, \
        "E4 markdown missing required sections"
    print("PASS E4 structure: JSON round-trips, all keys present, markdown renders")


# --------------------------------------------------------------------------
# E5 — inheritance: a changed base class reaches its subclasses (blast radius)
# --------------------------------------------------------------------------
def test_e5_inheritance(root: Path) -> None:
    """graphify emits `child -inherits-> base`; impact must reverse it so a
    base-class change names its subclasses as dependents. This was the missed
    delta — the consumer previously indexed only `calls`. Drives build_indexes +
    callers_of directly (deterministic; no git-diff attribution needed)."""
    # Base <- Child (inherits);  use() CALLS Child  (transitive dependent)
    nodes = [
        {"id": "m_Base", "label": "Base", "file_type": "code",
         "source_file": "models.py", "source_location": "L1"},
        {"id": "v_Child", "label": "Child", "file_type": "code",
         "source_file": "views.py", "source_location": "L1"},
        {"id": "v_use", "label": "use()", "file_type": "code",
         "source_file": "views.py", "source_location": "L5"},
    ]
    links = [
        {"relation": "inherits", "source": "v_Child", "target": "m_Base"},
        {"relation": "calls", "source": "v_use", "target": "v_Child"},
    ]
    graph = {"directed": True, "multigraph": False, "graph": {},
             "nodes": nodes, "links": links}
    idx = impact.build_indexes(graph)
    deps = impact.callers_of("m_Base", idx, depth=impact.DEFAULT_DEPTH)
    by_name = {d["caller"]: d for d in deps}
    # the subclass is a direct (depth-1) dependent reached via the inherits edge
    assert "Child" in by_name, f"E5 subclass Child not in base-class dependents: {by_name}"
    assert by_name["Child"]["via"] == "subclass", \
        f"E5 Child must be labelled via=subclass, got {by_name['Child'].get('via')}"
    assert by_name["Child"]["depth"] == 1, "E5 direct subclass is depth 1"
    # transitive: a caller of the subclass is also in the base's blast radius
    assert "use" in by_name, f"E5 transitive caller of subclass missing: {by_name}"
    assert by_name["use"]["via"] == "caller" and by_name["use"]["depth"] == 2, \
        f"E5 use() should be a depth-2 caller: {by_name.get('use')}"
    # regression guard: the OLD code consumed only `calls`, so Base (no inbound
    # `calls`) would have had ZERO dependents. The fix must surface the subclass.
    assert deps, "E5 base class must have dependents now that inherits is consumed"
    print("PASS E5 inheritance: Base -> Child (via=subclass, d1) + use() (via=caller, d2)")


# --------------------------------------------------------------------------
# E6 — coverage gap: a changed symbol ABSENT from the graph -> UNKNOWN, not LOW
# --------------------------------------------------------------------------
def test_e6_coverage_gap(root: Path) -> None:
    """A changed symbol absent from the graph must score UNKNOWN (+ a COVERAGE
    warning), NOT a confident LOW. The old code returned LOW for any empty caller
    set regardless of whether the symbol was even a graph node, so a scoped/stale
    graph silently under-reported real risk. Also guards that the genuine leaf case
    (in graph, zero callers) still reads LOW."""
    # unit: in-graph zero-caller -> LOW ; absent-from-graph -> UNKNOWN
    assert impact.classify_risk([], in_graph=True)[0] == "LOW", \
        "E6 in-graph zero-caller symbol must stay LOW"
    unk_risk, unk_why = impact.classify_risk([], in_graph=False)
    assert unk_risk == "UNKNOWN", f"E6 absent-from-graph must be UNKNOWN, got {unk_risk}"
    assert "graph" in unk_why.lower(), f"E6 UNKNOWN reason must mention the graph: {unk_why}"
    # analyze: a PARTIAL graph (only leaf_fn) must not score the changed, real,
    # in-code private_helper LOW just because the graph omits it.
    out_dir = root / "graphify-out"
    out_dir.mkdir(exist_ok=True)
    partial = {"directed": True, "multigraph": False, "graph": {},
               "nodes": [{"id": "core_leaf_fn", "label": "leaf_fn()", "file_type": "code",
                          "source_file": "core.py", "source_location": "L1"}],
               "links": []}
    (out_dir / "graph.json").write_text(json.dumps(partial))
    (root / "core.py").write_text(
        "def leaf_fn():\n    return 41 + 1\n\n"
        "def private_helper():\n    return 99  # changed, but absent from the graph\n"
    )
    rep = impact.analyze(repo=str(root), diff_spec="working")
    assert rep["mode"] == "graph", f"E6 expected graph mode, got {rep['mode']}"
    ph = next(a for a in rep["affected"] if a["symbol"] == "private_helper")
    assert ph["risk"] == "UNKNOWN", f"E6 coverage-gap symbol must be UNKNOWN, got {ph['risk']}"
    assert ph["covered"] is False, f"E6 coverage-gap symbol must be covered=False: {ph}"
    # regression guard: the OLD code returned a confident LOW here (false-safe under-report)
    assert ph["risk"] != "LOW", "E6 coverage-gap symbol must not be a confident LOW"
    assert any("coverage" in w.lower() for w in rep["warnings"]), \
        f"E6 expected a COVERAGE warning: {rep['warnings']}"
    print("PASS E6 coverage-gap: absent-from-graph symbol -> UNKNOWN + warning (not false-LOW)")


# --------------------------------------------------------------------------
def main() -> int:
    cases = [
        ("E1", test_e1_precision),
        ("E2", test_e2_degraded),
        ("E3", test_e3_risk),
        ("E4", test_e4_structure),
        ("E5", test_e5_inheritance),
        ("E6", test_e6_coverage_gap),
    ]
    failures = 0
    for name, fn in cases:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            root.mkdir()
            make_repo(root)
            try:
                fn(root)
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
            except Exception as exc:  # any crash is a hard failure (E2: never error)
                failures += 1
                print(f"FAIL {name}: unexpected {type(exc).__name__}: {exc}")
    print()
    if failures:
        print(f"test_impact: {len(cases) - failures}/{len(cases)} passed, {failures} FAILED")
        return 1
    print(f"test_impact: {len(cases)}/{len(cases)} PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
