"""Regression tests for three bugs fixed 2026-06-14:

  BUG1  render_diff silently dropped a changed/added class (parent) whenever one
        of its members also changed — class-level changes (base class, decorator,
        leading class constant, a new class's signature) never reached the
        rendered diff. Now the parent is emitted HEADER-ONLY.
  BUG2  rename_detect decoded bodies with strict utf-8; a single non-utf-8 byte
        raised UnicodeDecodeError, which render_diff's broad except swallowed —
        silently disabling rename detection for the whole file.
  BUG3  ignore_comments stripped comments with a string-unaware regex, so a `//`
        or `#` inside a string literal collapsed genuinely-different bodies to
        the same hash, hiding real changes. Now uses tree-sitter comment nodes.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from semdiff import core


def test_classlevel_change_surfaced():
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "m.py"
        f.write_text("class C(Base1):\n    LIMIT = 10\n    def m(self):\n        return 1\n")
        prev = core.snapshot_full(f)
        f.write_text("class C(Base2):\n    LIMIT = 99\n    def m(self):\n        return 2\n")
        rendered, meta = core.render_diff(f, prev)
        # member change still shown
        assert "return 2" in rendered, "member body change hidden"
        # class-level changes must NOT be silently dropped
        assert "Base2" in rendered, "changed base class hidden (BUG1)"
        assert "LIMIT = 99" in rendered, "changed class constant hidden (BUG1)"


def test_new_class_signature_surfaced():
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "n.py"
        f.write_text("x = 1\n")
        prev = core.snapshot_full(f)
        f.write_text("x = 1\nclass Brand(NewBase):\n    def a(self):\n        return 1\n")
        rendered, _ = core.render_diff(f, prev)
        assert "class Brand(NewBase)" in rendered, "brand-new class header dropped (BUG1)"


def test_rename_survives_non_utf8():
    from semdiff.rename_detect import detect_renames
    body = b"def x():\n    return shared_helper(value)  # \xff note\n"
    res = detect_renames({"old": "h1"}, {"new": "h2"}, {"old": body}, {"new": body})
    assert res and res[0][0] == "old" and res[0][1] == "new", "rename lost on non-utf8 body (BUG2)"


def test_ignore_comments_is_string_aware():
    src1 = b'def u():\n    return "http://example.com/v1"\n'
    src2 = b'def u():\n    return "http://example.com/v2"\n'
    h1 = {n.name: n.hash for n in core.extract_nodes(src1, "python", ignore_comments=True)}
    h2 = {n.name: n.hash for n in core.extract_nodes(src2, "python", ignore_comments=True)}
    assert h1["u"] != h2["u"], "string change hidden under ignore_comments (BUG3)"
    # a genuine comment-only change is STILL ignored
    src3 = b'def u():\n    return "http://example.com/v1"  # changed comment\n'
    h3 = {n.name: n.hash for n in core.extract_nodes(src3, "python", ignore_comments=True)}
    assert h1["u"] == h3["u"], "comment-only change no longer ignored (BUG3 regression)"


def run():
    test_classlevel_change_surfaced()
    test_new_class_signature_surfaced()
    test_rename_survives_non_utf8()
    test_ignore_comments_is_string_aware()


if __name__ == "__main__":
    run()
    print("pass")
