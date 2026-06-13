import tempfile
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from semdiff import read_smart
from semdiff.rename_detect import detect_renames


def run():
    with tempfile.TemporaryDirectory() as tmpdir:
        f = os.path.join(tmpdir, "w.py")

        # Create initial file
        with open(f, 'w') as fp:
            fp.write("def alpha(x): return x + 1\n")

        # First read
        _text, meta = read_smart(f, "sess")

        # Rewrite file
        with open(f, 'w') as fp:
            fp.write("def beta(x): return x + 1\n")

        # Second read
        _text2, meta2 = read_smart(f, "sess")

        # Exactly one rename, and it is the 1:1 alpha -> beta mapping.
        assert meta2["renamed"] == [("alpha", "beta", 1.0)], meta2["renamed"]


def run_greedy_one_to_one():
    """N removed + M added boilerplate functions sharing an identifier set must
    produce a greedy 1:1 rename assignment, not the full cross-product. A
    genuinely-new function must stay in `added` with its body rendered."""
    # Two removed + two added functions whose bodies share the same identifier
    # set (boilerplate). With unconstrained matching every (old,new) pair scores
    # 1.0, yielding 4 spurious edges; greedy 1:1 must yield exactly 2.
    prev_bodies = {
        "get_alpha": b"def get_alpha(self):\n    return self.data.get(\"value\")\n",
        "get_beta":  b"def get_beta(self):\n    return self.data.get(\"value\")\n",
    }
    curr_bodies = {
        "get_gamma": b"def get_gamma(self):\n    return self.data.get(\"value\")\n",
        "get_delta": b"def get_delta(self):\n    return self.data.get(\"value\")\n",
    }
    prev_snap = {k: "h" for k in prev_bodies}
    curr_snap = {k: "h" for k in curr_bodies}

    res = detect_renames(prev_snap, curr_snap, prev_bodies, curr_bodies)

    # Exact cardinality: 2 removed mapped to 2 added -> exactly 2 edges.
    assert len(res) == 2, f"expected 2 rename edges, got {len(res)}: {res}"

    # 1:1 mapping: no old name and no new name appears more than once.
    olds = [o for o, _, _ in res]
    news = [n for _, n, _ in res]
    assert len(olds) == len(set(olds)), f"old names not unique: {olds}"
    assert len(news) == len(set(news)), f"new names not unique: {news}"

    # Genuinely-new function survives: with one true rename and one new function,
    # only one of the new names is consumed as a rename, leaving the other in
    # `added` so its body is rendered downstream.
    with tempfile.TemporaryDirectory() as tmpdir:
        f = os.path.join(tmpdir, "m.py")
        with open(f, 'w') as fp:
            fp.write(
                "def keeper(value):\n"
                "    total = value + 1\n"
                "    return total\n"
            )
        _t, _m = read_smart(f, "sess2")

        # Rename `keeper` -> `holder` (identical body, similarity 1.0) AND add a
        # genuinely-new function `fresh` whose body overlaps but is not identical
        # (extra identifier `bonus`), so its similarity to `keeper` is < 1.0.
        # Greedy best-first must therefore claim the true keeper->holder pair and
        # leave `fresh` unclaimed.
        with open(f, 'w') as fp:
            fp.write(
                "def holder(value):\n"
                "    total = value + 1\n"
                "    return total\n"
                "def fresh(value):\n"
                "    bonus = value + 2\n"
                "    total = value + 1\n"
                "    return total + bonus\n"
            )
        text2, meta2 = read_smart(f, "sess2")

        renames = meta2["renamed"]
        renamed_new = {n for _, n, _ in renames}
        # Exactly one rename (greedy 1:1), the true keeper -> holder pair.
        assert len(renames) == 1, f"expected exactly 1 rename, got: {renames}"
        assert ("keeper", "holder") == renames[0][:2], f"wrong pairing: {renames}"
        # `fresh` must NOT be consumed as a rename target.
        assert "fresh" not in renamed_new, f"new function consumed as rename: {renames}"
        # `fresh` body must be rendered (full def with its body, not a bare stub).
        assert "def fresh(value):" in text2, text2
        assert "bonus = value + 2" in text2, text2


if __name__ == "__main__":
    run()
    run_greedy_one_to_one()
    print("pass")
