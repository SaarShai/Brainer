"""Tests for the OKF-interop + quality-scan additions to wiki.py.

Covers: export-okf serializer (+ frontmatter remap, wikilink rewrite, per-dir
index.md, fence-immunity), okf_conformance, the `resource:` field lint/audit,
the `[[?stub]]` forward-ref hatch + --fail-on-error gate, contradict-scan
(detection), novelty (redundancy_index), and claim-ground.

Run:
  python3 skills/wiki-memory/tools/test_okf.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from wiki import (  # noqa: E402
    WikiStore,
    okf_frontmatter,
    okf_scalar,
    redundancy_index,
    parse_frontmatter,
)

WIKI_PY = HERE / "wiki.py"


def _v2(title: str, *, type_: str = "concept", updated: str = "2026-01-02",
        extra: dict[str, str] | None = None, body: str = "") -> str:
    fm = {
        "schema_version": "2", "title": title, "type": type_, "domain": "tools",
        "tier": "semantic", "confidence": "0.7", "created": "2026-01-01",
        "updated": updated, "verified": "2026-01-02", "sources": "[a.md]",
        "supersedes": "[]", "superseded-by": "[]", "tags": "[t]",
    }
    if extra:
        fm.update(extra)
    lines = ["---"] + [f"{k}: {v}" for k, v in fm.items()] + ["---", ""]
    return "\n".join(lines) + body


def _write(root: Path, rel: str, content: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


class TestOkfHelpers(unittest.TestCase):
    def test_okf_scalar_quoting(self):
        self.assertEqual(okf_scalar("concept"), "concept")          # bare token
        self.assertEqual(okf_scalar("2026-01-02"), "2026-01-02")    # date bare
        self.assertEqual(okf_scalar("[a, b]"), "[a, b]")            # clean flow list passthrough
        self.assertEqual(okf_scalar("a: b with space"), '"a: b with space"')  # quoted
        # legacy v1 `related: [[x]], [[y]]` is NOT valid YAML flow -> must quote
        self.assertTrue(okf_scalar("[[concepts/x]], [[raw/y]]").startswith('"'))
        # flow list with a colon-space or comment marker is unsafe -> quote
        self.assertTrue(okf_scalar("[a: b]").startswith('"'))

    def test_okf_frontmatter_order_and_preserve(self):
        fm = {"schema_version": "2", "type": "concept", "title": "My Page",
              "tags": "[x, y]", "domain": "tools"}
        out = okf_frontmatter(fm)
        # type first (recommended order), custom keys preserved after
        self.assertTrue(out.startswith("---\ntype: concept\n"))
        self.assertIn('title: "My Page"', out)
        self.assertIn("schema_version: 2", out)
        self.assertIn("domain: tools", out)

    def test_redundancy_index_bounds(self):
        # all prose words echo the heading -> near-zero novelty
        echo = redundancy_index("Orders", "# Orders\norders orders orders", set())
        # prose words absent from heading/echo -> high novelty
        novel = redundancy_index("Orders", "# Orders\nfreight customs tariff invoice", set())
        self.assertLess(echo, novel)
        self.assertGreaterEqual(novel, 0.5)


class TestExportOkf(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "wiki"
        self.root.mkdir(parents=True)
        _write(self.root, "concepts/alpha.md",
               _v2("Alpha Title", updated="2026-03-04",
                   body="\n# Alpha Title\n\nFirst sentence preview here.\n\n"
                        "See [[beta]] and [[concepts/alpha|myself]].\n"))
        _write(self.root, "concepts/beta.md", _v2("Beta", body="\n# Beta\n\nBeta preview.\n"))
        # legacy v1 page with a nested-bracket `related:` value (real-corpus shape
        # that broke PyYAML round-trip before the okf_scalar fix)
        _write(self.root, "concepts/legacy.md",
               "---\ntitle: Legacy\ntype: concept\nrelated: [[concepts/alpha]], [[concepts/beta]]\n"
               "---\n# Legacy\n\nLegacy preview.\n")
        # A page whose BODY documents the schema inside a yaml fence (rec K):
        _write(self.root, "concepts/fenced.md",
               _v2("Fenced", type_="concept",
                   body="\n# Fenced\n\nExample frontmatter:\n\n```yaml\ntype: x|y|z\n```\n"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_export_is_conformant_and_remaps_frontmatter(self):
        store = WikiStore(self.root)
        out = Path(self.tmp.name) / "bundle"
        res = store.export_okf(out)
        self.assertTrue(res["conformant"], res["violations"])
        self.assertEqual(res["violations"], [])
        self.assertGreaterEqual(res["concepts"], 3)

        fm, body = parse_frontmatter((out / "concepts/alpha.md").read_text())
        self.assertEqual(fm["type"], "concept")
        self.assertEqual(fm["title"], "Alpha Title")          # from body H1 (J)
        self.assertTrue(fm["description"].startswith("First sentence"))  # preview (J)
        self.assertEqual(fm["timestamp"], "2026-03-04")       # from updated (J)
        self.assertEqual(fm["schema_version"], "2")           # governance key preserved
        # wikilink -> OKF bundle-relative markdown link
        self.assertIn("[Beta](/concepts/beta.md)", body)
        self.assertIn("[myself](/concepts/alpha.md)", body)
        self.assertNotIn("[[", body)

    def test_fence_immunity_K(self):
        store = WikiStore(self.root)
        out = Path(self.tmp.name) / "bundle"
        store.export_okf(out)
        fm, _ = parse_frontmatter((out / "concepts/fenced.md").read_text())
        # the fenced ```yaml type: x|y|z``` must NOT become the concept type
        self.assertEqual(fm["type"], "concept")

    def test_root_index_has_okf_version_and_subdir(self):
        store = WikiStore(self.root)
        out = Path(self.tmp.name) / "bundle"
        store.export_okf(out)
        root_idx = (out / "index.md").read_text()
        self.assertIn('okf_version: "0.1"', root_idx)
        self.assertIn("(concepts/)", root_idx)
        concepts_idx = (out / "concepts/index.md").read_text()
        self.assertIn("(alpha.md)", concepts_idx)
        self.assertIn("(beta.md)", concepts_idx)

    def test_exported_frontmatter_parses_under_real_yaml(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed")
        store = WikiStore(self.root)
        out = Path(self.tmp.name) / "bundle"
        store.export_okf(out)
        bad = []
        for f in out.rglob("*.md"):
            text = f.read_text()
            if not text.startswith("---"):
                continue
            block = text.split("---", 2)[1]
            try:
                d = yaml.safe_load(block)
                if not isinstance(d, dict):
                    bad.append((f.name, "non-dict"))
            except yaml.YAMLError as e:
                bad.append((f.name, str(e)[:60]))
        self.assertEqual(bad, [], f"invalid YAML in exported frontmatter: {bad}")

    def test_conformance_detects_violation(self):
        store = WikiStore(self.root)
        out = Path(self.tmp.name) / "bundle"
        store.export_okf(out)
        # inject a non-conformant concept (frontmatter present, empty type)
        _write(out, "concepts/bad.md", "---\ntype:\ntitle: Bad\n---\n# Bad\n")
        rep = store.okf_conformance(out)
        self.assertFalse(rep["conformant"])
        self.assertTrue(any(v["code"] == "missing_type" for v in rep["violations"]))


class TestResourceField(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "wiki"
        self.root.mkdir(parents=True)
        _write(self.root, "index.md", "# Index\n")
        _write(self.root, "log.md", "# Log\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_broken_resource_strict_error(self):
        _write(self.root, "concepts/r.md",
               _v2("R", extra={"resource": "skills/nope/GONE.md"}, body="\n# R\n\nx [[index]]\n"))
        rep = WikiStore(self.root).lint_pages(strict=True)
        codes = {e["code"] for e in rep["errors"]}
        self.assertIn("broken_resource", codes)

    def test_existing_resource_ok(self):
        _write(self.root, "concepts/r2.md",
               _v2("R2", extra={"resource": "concepts/r2.md"}, body="\n# R2\n\nx [[index]]\n"))
        rep = WikiStore(self.root).lint_pages(strict=True)
        self.assertNotIn("broken_resource", {e["code"] for e in rep["errors"]})

    def test_url_resource_not_path_checked(self):
        _write(self.root, "concepts/r3.md",
               _v2("R3", extra={"resource": "https://example.com/x"}, body="\n# R3\n\nx [[index]]\n"))
        rep = WikiStore(self.root).lint_pages(strict=True)
        self.assertNotIn("broken_resource", {e["code"] for e in rep["errors"]})

    def test_audit_refs_surfaces_rotted_sources_path(self):
        _write(self.root, "concepts/s.md",
               _v2("S", extra={"sources": "[projects/ghost/README.md]"}, body="\n# S\n\nprose only\n"))
        rep = WikiStore(self.root).audit_refs(code_root=self.root)
        drifted = {d["id"]: d for d in rep["drifted"]}
        self.assertIn("concepts/s", drifted)
        self.assertIn("projects/ghost/README.md", drifted["concepts/s"]["missing_refs"])


class TestStubLinkAndGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "wiki"
        self.root.mkdir(parents=True)
        _write(self.root, "index.md", "# Index\n")
        _write(self.root, "log.md", "# Log\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_stub_link_is_advisory_not_error(self):
        _write(self.root, "concepts/fwd.md",
               _v2("Fwd", body="\n# Fwd\n\npoints at [[?not-written-yet]] and [[index]]\n"))
        rep = WikiStore(self.root).lint_pages(strict=True)
        self.assertTrue(any(s["to"] == "?not-written-yet" for s in rep["stub_links"]))
        self.assertFalse(any(b["to"] == "?not-written-yet" for b in rep["broken_links"]))
        self.assertNotIn("broken_link", {e["code"] for e in rep["errors"]})

    def test_real_broken_link_still_errors_on_v2(self):
        _write(self.root, "concepts/bad.md",
               _v2("Bad", body="\n# Bad\n\npoints at [[truly-gone]] and [[index]]\n"))
        rep = WikiStore(self.root).lint_pages(strict=True)
        self.assertTrue(any(b["to"] == "truly-gone" for b in rep["broken_links"]))
        self.assertIn("broken_link", {e["code"] for e in rep["errors"]})

    def test_typed_edge_stub_still_strict(self):
        # a `?`-prefixed target inside supersedes is a dangling typed edge -> error
        _write(self.root, "concepts/sup.md",
               _v2("Sup", extra={"superseded-by": "[[?ghost]]"}, body="\n# Sup\n\nx [[index]]\n"))
        rep = WikiStore(self.root).lint_pages(strict=True)
        self.assertIn("broken_supersession", {e["code"] for e in rep["errors"]})

    def test_fail_on_error_exit_codes(self):
        # v2 page with a real broken link -> errors -> exit 1
        _write(self.root, "concepts/bad.md",
               _v2("Bad", body="\n# Bad\n\n[[truly-gone]]\n"))
        r = subprocess.run([sys.executable, str(WIKI_PY), "--root", str(self.root),
                            "lint", "--strict", "--fail-on-error"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_fail_on_error_clean_wiki_exit_zero(self):
        # legacy v1-only page (no schema_version, not all 4 v2 keys) -> no strict errors
        _write(self.root, "concepts/legacy.md", "---\ntitle: Legacy\n---\n# Legacy\n\nplain\n")
        r = subprocess.run([sys.executable, str(WIKI_PY), "--root", str(self.root),
                            "lint", "--strict", "--fail-on-error"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class TestContradictScan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "wiki"
        self.root.mkdir(parents=True)
        _write(self.root, "index.md", "# Index\n")
        _write(self.root, "log.md", "# Log\n")

    def tearDown(self):
        self.tmp.cleanup()

    def _decay_pair(self, a_extra=None, b_extra=None):
        _write(self.root, "concepts/decay-a.md",
               _v2("Decay halflife", extra=a_extra,
                   body="\n# Decay halflife\n\nDefault halflife 405 days governs confidence aging.\n"))
        _write(self.root, "concepts/decay-b.md",
               _v2("Decay halflife", extra=b_extra,
                   body="\n# Decay halflife\n\nDefault halflife 200 days governs confidence aging.\n"))

    def test_detects_numeric_divergence(self):
        self._decay_pair()
        rep = WikiStore(self.root).contradict_scan()
        self.assertEqual(rep["candidate_count"], 1, rep)
        cand = rep["candidates"][0]
        keys = {s["key"] for s in cand["numeric_divergence"]}
        self.assertIn("halflife", keys)

    def test_declared_edge_suppresses_candidate(self):
        self._decay_pair(a_extra={"contradicts": "[[concepts/decay-b]]"},
                         b_extra={"contradicts": "[[concepts/decay-a]]"})
        rep = WikiStore(self.root).contradict_scan()
        self.assertEqual(rep["candidate_count"], 0, rep)

    def test_unrelated_pages_not_flagged(self):
        _write(self.root, "concepts/x.md",
               _v2("Alpha widget", extra={"tags": "[alpha]"},
                   body="\n# Alpha widget\n\nWidget count 5 here.\n"))
        _write(self.root, "concepts/y.md",
               _v2("Beta gadget", extra={"tags": "[beta]"},
                   body="\n# Beta gadget\n\nGadget count 9 here.\n"))
        rep = WikiStore(self.root).contradict_scan()
        self.assertEqual(rep["candidate_count"], 0, rep)


class TestNoveltyAndClaimGround(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "wiki"
        self.root.mkdir(parents=True)
        _write(self.root, "index.md", "# Index\n")
        _write(self.root, "log.md", "# Log\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_novelty_flags_echo_page(self):
        # body restates its headings + a fenced schema with the same tokens
        _write(self.root, "concepts/echo.md",
               _v2("Orders columns",
                   body="\n# Orders columns\n\n## Orders columns\n\norders columns\n\n"
                        "```\norders columns orders columns\n```\n"))
        _write(self.root, "concepts/rich.md",
               _v2("Freight",
                   body="\n# Freight\n\nManifest reconciliation across customs brokers and "
                        "intermodal carriers prevents demurrage penalties on transshipment.\n"))
        rep = WikiStore(self.root).novelty(threshold=0.5)
        flagged = {s["page"] for s in rep["low_novelty"]}
        self.assertIn("concepts/echo", flagged)
        self.assertNotIn("concepts/rich", flagged)

    def test_claim_ground_flags_missing_artifact(self):
        code = Path(self.tmp.name) / "code"
        (code / "src").mkdir(parents=True)
        (code / "src" / "real.py").write_text("x=1\n", encoding="utf-8")
        _write(self.root, "concepts/claims.md",
               _v2("Claims",
                   body="\n# Claims\n\nThe loader lives in src/real.py and parses input. "
                        "The writer is in src/gone.py now.\n"))
        rep = WikiStore(self.root).claim_ground("concepts/claims", code_root=code)
        self.assertEqual(rep["claims_total"], 2, rep)
        self.assertEqual(rep["claims_with_missing_artifact"], 1, rep)
        missing = [c for c in rep["claims"] if c["missing_refs"]][0]
        self.assertIn("src/gone.py", missing["missing_refs"])


class TestClaimAudit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "wiki"
        self.root.mkdir(parents=True)
        _write(self.root, "index.md", "# Index\n")
        _write(self.root, "log.md", "# Log\n")
        # judgment-heavy (opinion) concept page -> should flag (>=4 claims, each >=5 words)
        _write(self.root, "concepts/opinion.md",
               _v2("Opinion heavy", type_="concept",
                   body="\n# Opinion heavy\n\nThe new API design is much cleaner overall. "
                        "The updated layout feels far nicer to use. "
                        "It is more elegant than the previous version. "
                        "The old structure was considerably uglier than this.\n"))
        # data-heavy page -> should NOT flag
        _write(self.root, "concepts/data.md",
               _v2("Data heavy", type_="concept",
                   body="\n# Data heavy\n\nLatency measured 113ms on the regex path. "
                        "12 tests passed with no failures recorded. The cold build took 4.2s. "
                        "Indexed 175 pages on 2026-06-14 here.\n"))
        # decision page that is judgment-led -> exempt from flag
        _write(self.root, "queries/decision.md",
               _v2("Decision page", type_="decision",
                   body="\n# Decision page\n\nThe new approach feels much cleaner overall. "
                        "It seems clearly nicer to work with. "
                        "The design is more elegant than before. "
                        "This reads considerably better than the old one.\n"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_flags_judgment_heavy_weak_evidence(self):
        rep = WikiStore(self.root).claim_audit()
        flagged = {f["id"] for f in rep["flagged"]}
        self.assertIn("concepts/opinion", flagged)

    def test_data_heavy_not_flagged(self):
        rep = WikiStore(self.root).claim_audit()
        flagged = {f["id"] for f in rep["flagged"]}
        self.assertNotIn("concepts/data", flagged)
        row = next((r for r in rep["rows"] if r["id"] == "concepts/data"), None)
        self.assertIsNotNone(row)
        self.assertGreater(row["data"], row["judgment"])

    def test_decision_type_exempt(self):
        # a judgment-led page typed `decision` is not flagged (decisions are
        # expected to be directive/judgment-led, not evidence-led)
        rep = WikiStore(self.root).claim_audit()
        self.assertNotIn("queries/decision", {f["id"] for f in rep["flagged"]})

    def test_report_only_no_writes(self):
        before = sorted(p.name for p in self.root.rglob("*.md"))
        WikiStore(self.root).claim_audit()
        after = sorted(p.name for p in self.root.rglob("*.md"))
        self.assertEqual(before, after)  # report-only: mutates nothing


class TestSynthCandidates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "wiki"
        self.root.mkdir(parents=True)
        _write(self.root, "index.md", "# Index\n")
        _write(self.root, "log.md", "# Log\n")
        # group 1: 3 same-subject pages sharing 2 tags, no interlinks -> candidate
        for x in "abc":
            _write(self.root, f"concepts/g1{x}.md",
                   _v2(f"G1{x}", extra={"tags": "[alpha, beta]"}, body=f"\n# G1{x}\n\nbody {x}\n"))
        # group 2: hub links the other two (+shared tags) -> already-synthesized
        _write(self.root, "concepts/g2hub.md",
               _v2("G2 hub", extra={"tags": "[gamma, delta]"},
                   body="\n# G2 hub\n\noverview [[concepts/g2a]] [[concepts/g2b]]\n"))
        for x in "ab":
            _write(self.root, f"concepts/g2{x}.md",
                   _v2(f"G2{x}", extra={"tags": "[gamma, delta]"}, body=f"\n# G2{x}\n\nbody {x}\n"))
        # isolated page (unique tag) -> not clustered
        _write(self.root, "concepts/iso.md",
               _v2("Iso", extra={"tags": "[zeta]"}, body="\n# Iso\n\nalone\n"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_surfaces_same_subject_cluster(self):
        rep = WikiStore(self.root).synth_candidates()
        cand_members = [set(c["members"]) for c in rep["candidates"]]
        self.assertIn({"concepts/g1a", "concepts/g1b", "concepts/g1c"}, cand_members)

    def test_detects_existing_synthesis_parent(self):
        rep = WikiStore(self.root).synth_candidates()
        synthd = {c["likely_existing_parent"] for c in rep["already_synthesized"]}
        self.assertIn("concepts/g2hub", synthd)

    def test_isolated_page_not_clustered(self):
        rep = WikiStore(self.root).synth_candidates()
        allmembers = set()
        for c in rep["candidates"] + rep["already_synthesized"]:
            allmembers |= set(c["members"])
        self.assertNotIn("concepts/iso", allmembers)

    def test_report_only_no_writes(self):
        before = sorted(p.name for p in self.root.rglob("*.md"))
        WikiStore(self.root).synth_candidates()
        self.assertEqual(before, sorted(p.name for p in self.root.rglob("*.md")))


if __name__ == "__main__":
    unittest.main()
