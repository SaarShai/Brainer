"""Regression tests for config.py + code_map.py bugs fixed 2026-06-14.

config.py:
  - An empty scalar value was coerced to [] ("key: " → []), so float([]) crashed
    load_config and bool([]) silently flipped bool defaults. Empty now means
    "absent" → typed default.
  - A scalar given for a list-typed key ("external_adapters: foo") was returned
    as a bare str, so iterating it yielded characters. Now coerced to a list.
  - A malformed float ("refresh_threshold: high") crashed; now falls to default.

code_map.py:
  - IMPORT_RE's `[\w.,\s{}*]` class spanned across `{ } from`, capturing ES6
    import specifiers as junk ("{ Foo } from ") and dropping the real module.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
import code_map  # noqa: E402


def _cfg(text):
    d = Path(tempfile.mkdtemp())
    (d / ".git").mkdir()
    (d / "brainer.yaml").write_text(text)
    return config.load_config(d)


def test_empty_scalar_falls_to_default():
    c = _cfg("refresh_threshold:\noutput_filter_archive:\n")
    assert c.refresh_threshold == 0.20, "empty refresh_threshold should default, not crash"
    assert c.output_filter_archive is True, "empty bool should keep default True, not bool([])"


def test_scalar_for_list_key_wrapped():
    c = _cfg("external_adapters: foo\n")
    assert c.external_adapters == ["foo"], "scalar list-key must wrap to [v], not a bare str"


def test_block_and_inline_lists_still_work():
    assert _cfg("external_adapters:\n  - a\n  - b\n").external_adapters == ["a", "b"]
    assert _cfg("external_adapters: [x, y]\n").external_adapters == ["x", "y"]


def test_malformed_float_falls_to_default():
    assert _cfg("refresh_threshold: high\n").refresh_threshold == 0.20


def test_es6_imports_not_garbled():
    js = ("import { Foo } from './foo';\n"
          "import Bar from \"./bar\";\n"
          "const z = require('./z');\n"
          "import './side';\n")
    imports, _ = code_map.parse_regex_symbols(js, "javascript")
    assert imports == ["./bar", "./foo", "./side", "./z"], f"garbled imports: {imports}"


def test_python_imports_intact():
    py = "import os\nfrom pathlib import Path\n"
    imports, _ = code_map.parse_python(py)
    assert "os" in imports and "pathlib" in imports


def run():
    test_empty_scalar_falls_to_default()
    test_scalar_for_list_key_wrapped()
    test_block_and_inline_lists_still_work()
    test_malformed_float_falls_to_default()
    test_es6_imports_not_garbled()
    test_python_imports_intact()


if __name__ == "__main__":
    run()
    print("pass")
