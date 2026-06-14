from __future__ import annotations

"""Simulation eval: plant KNOWN contradictions + synthesis clusters into synthetic
wikis and measure the detectors against the ground truth. Converts spot-checks
into measured recall/precision and guards against regression.

Run: python3 skills/wiki-memory/tools/test_sim_eval.py
"""

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from wiki import WikiStore  # noqa: E402


def _page(root: Path, rel: str, title: str, tags: str, body: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    fm = (f"---\nschema_version: 2\ntitle: {title}\ntype: concept\ndomain: tools\n"
          f"tier: semantic\nconfidence: 0.6\ncreated: 2026-01-01\nupdated: 2026-01-01\n"
          f"verified: 2026-01-01\nsources: [x.md]\ntags: {tags}\n---\n")
    p.write_text(fm + f"\n# {title}\n\n{body}\n", encoding="utf-8")


class TestContradictionSim(unittest.TestCase):
    """Plant K real contradictions + K agreeing (non-contradiction) same-subject
    pairs; measure recall (planted caught) and precision (no spurious flags)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "wiki"
        self.root.mkdir(parents=True)
        _page(self.root, "index.md", "I", "[]", "x")
        _page(self.root, "log.md", "L", "[]", "x")
        self.planted = set()
        # topically-DISTINCT plants (a real wiki's contradictions are on different
        # subjects; templated near-identical pages would cross-contaminate every
        # same-subject test and explode the candidate set).
        # 4 numeric contradictions: distinct subject, distinct keyword, diverging number
        numeric = [
            ("cache", "Cache eviction interval {n}ms in the hot read path here."),
            ("queue", "Worker queue depth {n} items per shard in this design."),
            ("retry", "Request retry count {n} attempts before the call fails."),
            ("budget", "Per-call token budget {n} tokens for a single request."),
        ]
        for i, (tag, tmpl) in enumerate(numeric):
            _page(self.root, f"concepts/num{i}a.md", f"{tag.title()} A", f"[{tag}]", tmpl.format(n=300 + i * 100))
            _page(self.root, f"concepts/num{i}b.md", f"{tag.title()} B", f"[{tag}]", tmpl.format(n=100 + i * 10))
            self.planted.add(frozenset({f"concepts/num{i}a", f"concepts/num{i}b"}))
        # 4 polarity contradictions: distinct subject, negation flip / antonym
        polarity = [
            ("idem", "The retry policy is idempotent across redelivery by design here.",
                     "The retry policy is not idempotent across redelivery by design here."),
            ("cachep", "The read cache layer is enabled for every lookup in this mode.",
                       "The read cache layer is disabled for every lookup in this mode."),
            ("jobs", "Background ledger jobs run synchronous within the request here.",
                     "Background ledger jobs run asynchronous within the request here."),
            ("block", "Writes to the append ledger are blocking on every commit here.",
                      "Writes to the append ledger are nonblocking on every commit here."),
        ]
        for i, (tag, a, b) in enumerate(polarity):
            _page(self.root, f"concepts/pol{i}a.md", f"Pol {tag} A", f"[{tag}]", a)
            _page(self.root, f"concepts/pol{i}b.md", f"Pol {tag} B", f"[{tag}]", b)
            self.planted.add(frozenset({f"concepts/pol{i}a", f"concepts/pol{i}b"}))
        # 4 AGREEING same-subject pairs (must NOT be flagged)
        agree = [
            ("sess", "Session cache holds 256 entries for each connected user here."),
            ("idx", "The search index rebuilds 175 pages on every commit in this repo."),
            ("warm", "Model keep-alive stays warm for 2 hours after the last call here."),
            ("halff", "Decay half-life is 405 days for confidence aging in this tool."),
        ]
        for i, (tag, body) in enumerate(agree):
            _page(self.root, f"concepts/ok{i}a.md", f"Ok {tag} A", f"[{tag}]", body)
            _page(self.root, f"concepts/ok{i}b.md", f"Ok {tag} B", f"[{tag}]", body)

    def tearDown(self):
        self.tmp.cleanup()

    def test_recall_and_precision(self):
        rep = WikiStore(self.root).contradict_scan(k=200)  # high k: measure true recall, not the display cap
        found = {frozenset({c["a"], c["b"]}) for c in rep["candidates"]}
        caught = self.planted & found
        recall = len(caught) / len(self.planted)
        spurious = found - self.planted
        precision = len(self.planted & found) / len(found) if found else 1.0
        self.assertGreaterEqual(recall, 0.9, f"recall {recall:.2f}; missed {self.planted - found}")
        self.assertGreaterEqual(precision, 0.8, f"precision {precision:.2f}; spurious {spurious}")


class TestSynthesisSim(unittest.TestCase):
    """Plant K synthesis clusters (>=2 shared tags) + isolated pages; measure that
    every planted cluster is surfaced and no isolated page is clustered."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "wiki"
        self.root.mkdir(parents=True)
        _page(self.root, "index.md", "I", "[]", "x")
        _page(self.root, "log.md", "L", "[]", "x")
        self.clusters = []
        for g in range(3):
            tags = f"[grp{g}, theme{g}]"
            members = set()
            for m in range(3):
                pid = f"concepts/c{g}_{m}"
                _page(self.root, pid + ".md", f"C{g}{m}", tags, f"cluster {g} member {m} body text here.")
                members.add(pid)
            self.clusters.append(members)
        for i in range(3):
            _page(self.root, f"concepts/iso{i}.md", f"Iso{i}", f"[unique{i}]", "alone here.")

    def tearDown(self):
        self.tmp.cleanup()

    def test_all_clusters_surfaced_no_isolated(self):
        rep = WikiStore(self.root).synth_candidates()
        found = [set(c["members"]) for c in rep["candidates"] + rep["already_synthesized"]]
        for planted in self.clusters:
            self.assertTrue(any(planted <= f for f in found), f"cluster not surfaced: {planted}")
        clustered = set().union(*found) if found else set()
        for i in range(3):
            self.assertNotIn(f"concepts/iso{i}", clustered)


class TestStageInferenceSim(unittest.TestCase):
    """Plant pages with a clear dominant epistemic klass and measure maturity's
    page-level stage inference (observation/hypothesis/rule) against the truth —
    the aggregate accuracy nothing else covers (claim_grade gold is per-claim)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "wiki"
        self.root.mkdir(parents=True)
        _page(self.root, "index.md", "I", "[]", "x")
        _page(self.root, "log.md", "L", "[]", "x")
        self.truth = {}
        data = ("Latency measured 113ms on the hot path. The build took 4.2s today. "
                "12 tests passed with no failures here. Indexed 175 pages on 2026-01-02.")
        rule = ("Always retrieve before reasoning here. Never promote via reuse alone. "
                "Do not rewrite raw pages ever. Prefer updates over creates in this repo.")
        judg = ("This might be the root cause here. It probably stems from cold load. "
                "It seems likely under concurrency. The design feels cleaner this way.")
        for i in range(3):
            _page(self.root, f"concepts/d{i}.md", f"D{i}", f"[d{i}]", data)
            self.truth[f"concepts/d{i}"] = "observation"
            _page(self.root, f"concepts/r{i}.md", f"R{i}", f"[r{i}]", rule)
            self.truth[f"concepts/r{i}"] = "rule"
            _page(self.root, f"concepts/h{i}.md", f"H{i}", f"[h{i}]", judg)
            self.truth[f"concepts/h{i}"] = "hypothesis"

    def tearDown(self):
        self.tmp.cleanup()

    def test_stage_inference_accuracy(self):
        # re-derive each page's inferred stage the way maturity() does, via the
        # public claim_audit klass mix, and compare to planted truth.
        import claim_grade as _cg
        st = WikiStore(self.root)
        correct = 0
        for p in st._knowledge_pages(include_raw=False):
            if p.id not in self.truth:
                continue
            h = _cg.grade_text(p.body)["klass_histogram"]
            data, direc, judg = h["data"], h["directive"], h["judgment"]
            if direc > 0 and direc >= data and direc >= judg:
                stage = "rule"
            elif judg > data:
                stage = "hypothesis"
            elif data > 0:
                stage = "observation"
            else:
                stage = "mixed"
            correct += (stage == self.truth[p.id])
        acc = correct / len(self.truth)
        self.assertGreaterEqual(acc, 0.88, f"stage inference accuracy {acc:.2f} ({correct}/{len(self.truth)})")


if __name__ == "__main__":
    unittest.main(verbosity=2)
