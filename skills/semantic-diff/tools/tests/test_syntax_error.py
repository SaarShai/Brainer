import hashlib
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from semdiff import core, read_smart
from semdiff.cache import SessionCache


def _v2_cache_record(path, nodes):
    return {
        "__semdiff_cache_version__": 2,
        "source_hash": hashlib.sha256(path.read_bytes()).hexdigest(),
        "syntax_error": False,
        "nodes": nodes,
    }


def _assert_invalid_nested_node_entry(make_entry):
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        f = root / "module.py"
        cache = root / "cache"
        f.write_text("def stable():\n    return 1\n")
        valid_entry = core.snapshot_full(f)["stable"]
        malformed = _v2_cache_record(f, {"stable": make_entry(valid_entry)})
        SessionCache("sess", cache_dir=cache).set(str(f.resolve()), malformed)

        text2, meta2 = read_smart(f, "sess", cache_dir=cache)
        assert meta2["mode"] == "full", meta2
        assert meta2["reason"] == "invalid-cache-schema", meta2
        assert meta2["error"] is False, meta2
        assert text2 == f.read_text(), "invalid cache fallback must return full current source"
        upgraded = SessionCache("sess", cache_dir=cache).get(str(f.resolve()))
        upgraded_entry = upgraded["nodes"]["stable"]
        assert isinstance(upgraded_entry["hash"], str), upgraded
        assert isinstance(upgraded_entry["body"], str), upgraded


def test_unsupported_language_always_returns_full_without_parser_loading():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        cache = root / "cache"
        original_get_parser = core.get_parser
        parser_cache_before = dict(core._PARSER_CACHE)

        def fail_if_parser_loaded(lang):
            raise AssertionError(f"unsupported file attempted parser loading: {lang!r}")

        core.get_parser = fail_if_parser_loaded
        try:
            for filename in ("notes.md", "notes.txt", "README"):
                path = root / filename
                first = b"first read: \xff\n"
                second = b"second read: \xfe\n"
                path.write_bytes(first)

                text1, meta1 = read_smart(path, filename, cache_dir=cache)
                assert text1 == first.decode("utf-8", "replace")
                assert meta1["mode"] == "full", meta1
                assert meta1["reason"] == "unsupported-language", meta1

                path.write_bytes(second)
                text2, meta2 = read_smart(path, filename, cache_dir=cache)
                assert text2 == second.decode("utf-8", "replace")
                assert meta2["mode"] == "full", meta2
                assert meta2["reason"] == "unsupported-language", meta2
        finally:
            core.get_parser = original_get_parser

        assert core._PARSER_CACHE == parser_cache_before
        assert not cache.exists(), "unsupported reads must not create session cache state"


def test_syntax_error_falls_back_to_full_file():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        f = root / "bad.py"
        cache = root / "cache"
        f.write_text("def ok():\n    return 1\n")
        _text1, meta1 = read_smart(f, "sess", cache_dir=cache)
        assert meta1["mode"] == "full"

        f.write_text("def broken(\n    return 1\n")
        text2, meta2 = read_smart(f, "sess", cache_dir=cache)
        assert meta2["mode"] == "full", meta2
        assert meta2["reason"] == "syntax-error", meta2
        assert meta2["error"] is True, meta2
        assert text2 == f.read_text(), "syntax fallback must return the full changed file"


def test_byte_change_with_empty_ast_delta_falls_back_to_full_file():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        f = root / "module.py"
        cache = root / "cache"
        f.write_text("SETTING = 1\n")
        _text1, meta1 = read_smart(f, "sess", cache_dir=cache)
        assert meta1["mode"] == "full"

        f.write_text("SETTING = 2\n")
        text2, meta2 = read_smart(f, "sess", cache_dir=cache)
        assert meta2["mode"] == "full", meta2
        assert meta2["reason"] == "bytes-changed-without-ast-delta", meta2
        assert meta2["error"] is False, meta2
        assert text2 == f.read_text(), "empty AST delta fallback must return the full changed file"


def test_legacy_v1_cache_reread_falls_back_and_upgrades():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        f = root / "module.py"
        cache = root / "cache"
        f.write_text("SETTING = 1\n")
        legacy_snapshot = core.snapshot_full(f)
        SessionCache("sess", cache_dir=cache).set(str(f.resolve()), legacy_snapshot)

        f.write_text("SETTING = 2\n")
        text2, meta2 = read_smart(f, "sess", cache_dir=cache)
        assert meta2["mode"] == "full", meta2
        assert meta2["reason"] == "legacy-cache-migration", meta2
        assert meta2["error"] is False, meta2
        assert "source hash" in meta2["warning"].lower(), meta2
        assert text2 == f.read_text(), "migration fallback must expose the full current source"

        upgraded = SessionCache("sess", cache_dir=cache).get(str(f.resolve()))
        assert upgraded["__semdiff_cache_version__"] == 2, upgraded
        _text3, meta3 = read_smart(f, "sess", cache_dir=cache)
        assert meta3["mode"] == "diff", meta3
        assert not meta3["added"] and not meta3["changed"], meta3


def test_previous_syntax_error_cache_recovery_returns_full():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        f = root / "recover.py"
        cache = root / "cache"
        f.write_text("def broken(\n    return 1\n")
        _text1, meta1 = read_smart(f, "sess", cache_dir=cache)
        assert meta1["reason"] == "syntax-error", meta1
        assert meta1["error"] is True, meta1

        f.write_text("def recovered():\n    return 1\n")
        text2, meta2 = read_smart(f, "sess", cache_dir=cache)
        assert meta2["mode"] == "full", meta2
        assert meta2["reason"] == "syntax-error-recovery", meta2
        assert meta2["error"] is False, meta2
        assert text2 == f.read_text(), "syntax recovery must return the full current source"


def test_malformed_v2_cache_nodes_null_falls_back_and_upgrades():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        f = root / "module.py"
        cache = root / "cache"
        f.write_text("SETTING = 2\n")
        malformed = {
            "__semdiff_cache_version__": 2,
            "source_hash": "stale-but-string-shaped",
            "syntax_error": False,
            "nodes": None,
        }
        SessionCache("sess", cache_dir=cache).set(str(f.resolve()), malformed)

        text2, meta2 = read_smart(f, "sess", cache_dir=cache)
        assert meta2["mode"] == "full", meta2
        assert meta2["reason"] == "invalid-cache-schema", meta2
        assert meta2["error"] is False, meta2
        assert text2 == f.read_text(), "invalid cache fallback must return full current source"
        upgraded = SessionCache("sess", cache_dir=cache).get(str(f.resolve()))
        assert isinstance(upgraded["nodes"], dict), upgraded


def test_malformed_v2_cache_empty_node_entry_falls_back():
    _assert_invalid_nested_node_entry(lambda _valid: {})


def test_malformed_v2_cache_list_node_entry_falls_back():
    _assert_invalid_nested_node_entry(lambda _valid: [])


def test_malformed_v2_cache_missing_hash_falls_back():
    _assert_invalid_nested_node_entry(
        lambda valid: {"body": valid["body"]}
    )


def test_malformed_v2_cache_missing_body_falls_back():
    _assert_invalid_nested_node_entry(
        lambda valid: {"hash": valid["hash"]}
    )


def test_malformed_v2_cache_non_string_hash_falls_back():
    _assert_invalid_nested_node_entry(
        lambda valid: {"hash": 17, "body": valid["body"]}
    )


def test_malformed_v2_cache_non_string_body_falls_back():
    _assert_invalid_nested_node_entry(
        lambda valid: {"hash": valid["hash"], "body": None}
    )


def test_valid_v2_cache_nested_node_schema_reaches_diff():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        f = root / "module.py"
        cache = root / "cache"
        f.write_text("def stable():\n    return 1\n")
        valid = _v2_cache_record(f, core.snapshot_full(f))
        SessionCache("sess", cache_dir=cache).set(str(f.resolve()), valid)

        _text2, meta2 = read_smart(f, "sess", cache_dir=cache)
        assert meta2["mode"] == "diff", meta2
        assert not meta2["added"] and not meta2["changed"], meta2


def test_valid_v2_cache_empty_nodes_mapping_reaches_diff():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        f = root / "module.py"
        cache = root / "cache"
        f.write_text("SETTING = 2\n")
        valid = _v2_cache_record(f, {})
        SessionCache("sess", cache_dir=cache).set(str(f.resolve()), valid)

        _text2, meta2 = read_smart(f, "sess", cache_dir=cache)
        assert meta2["mode"] == "diff", meta2
        assert not meta2["added"] and not meta2["changed"], meta2


def run():
    test_unsupported_language_always_returns_full_without_parser_loading()
    test_syntax_error_falls_back_to_full_file()
    test_byte_change_with_empty_ast_delta_falls_back_to_full_file()
    test_legacy_v1_cache_reread_falls_back_and_upgrades()
    test_previous_syntax_error_cache_recovery_returns_full()
    test_malformed_v2_cache_nodes_null_falls_back_and_upgrades()
    test_malformed_v2_cache_empty_node_entry_falls_back()
    test_malformed_v2_cache_list_node_entry_falls_back()
    test_malformed_v2_cache_missing_hash_falls_back()
    test_malformed_v2_cache_missing_body_falls_back()
    test_malformed_v2_cache_non_string_hash_falls_back()
    test_malformed_v2_cache_non_string_body_falls_back()
    test_valid_v2_cache_nested_node_schema_reaches_diff()
    test_valid_v2_cache_empty_nodes_mapping_reaches_diff()


if __name__ == "__main__":
    run()
    print("pass")
