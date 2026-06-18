#!/usr/bin/env python3
"""Smoke tests for output_filter.py — runnable standalone with no pytest dep."""
from __future__ import annotations

import json
import os
import sys
import subprocess
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from output_filter import ANSI, archive_event, filter_text, load_rules, rewind  # noqa: E402

ESC = "\x1b"
_OUTPUT_FILTER = Path(__file__).parent / "output_filter.py"


def assert_strips(seq: str, msg: str = "") -> None:
    out = ANSI.sub("", seq)
    assert out == "", f"expected empty after ANSI strip: {msg}\n  in ={seq!r}\n  out={out!r}"


def test_strips_csi_color_codes() -> None:
    # Standard SGR / CSI sequences the old regex already handled — must keep working.
    assert_strips(ESC + "[32m", "SGR color")
    assert_strips(ESC + "[0m", "SGR reset")
    assert_strips(ESC + "[2J", "clear screen")


def test_strips_private_mode_csi() -> None:
    # `?`-prefixed private-mode CSI (cursor hide/show) — ubiquitous in spinners.
    # The old regex r"\x1b\[[0-9;]*[A-Za-z]" missed the '?' param byte and leaked ESC.
    assert_strips(ESC + "[?25l", "cursor hide")
    assert_strips(ESC + "[?25h", "cursor show")


def test_strips_osc_sequence() -> None:
    # OSC set-title terminated by BEL — old regex left the whole thing as a leak.
    assert_strips(ESC + "]0;t\x07", "OSC set-title (BEL-terminated)")


def test_strips_single_char_escape() -> None:
    # Two-byte escape (no CSI bracket), e.g. ESC M reverse-index.
    assert_strips(ESC + "M", "single-char escape ESC M")


def test_no_raw_esc_leaks_and_error_preserved() -> None:
    # End-to-end: a spinner-style line (private-mode CSI + color) followed by an
    # error line. No raw ESC may survive, and the error line must be preserved
    # verbatim (keep-guard runs post-sub).
    raw = ESC + "[?25l" + ESC + "[32mBuilding..." + ESC + "[0m\nERROR: build failed\n"
    out, _ = filter_text(raw, rules=load_rules(None))
    assert ESC not in out, f"raw ESC leaked into cleaned output: {out!r}"
    assert "ERROR: build failed" in out, f"error line dropped: {out!r}"
    assert "Building..." in out, f"content corrupted: {out!r}"


def test_search_content_filter_keeps_diversity_and_errors() -> None:
    raw = "\n".join(
        f"src/file{i % 12}.py:{i}: match {i}" for i in range(120)
    ) + "\nERROR: important failure\n"
    out, stats = filter_text(raw, rules=load_rules(None), content_type="search")
    assert stats["content_type"] == "search", stats
    assert "search-summary" in stats["transforms"], stats
    assert len(out.splitlines()) < len(raw.splitlines()), "search output should shrink"
    assert "src/file0.py:0: match 0" in out, "first hit lost"
    assert "src/file11.py:119: match 119" in out, "last hit lost"
    assert "ERROR: important failure" in out, "error signal lost"


def test_log_content_filter_preserves_signal_lines() -> None:
    raw = "\n".join(
        [f"progress chunk {i}" for i in range(180)]
        + ["WARNING: retrying slow test", "FAILED tests/test_api.py::test_auth"]
        + [f"tail progress {i}" for i in range(120)]
    )
    out, stats = filter_text(raw, rules=load_rules(None), content_type="log")
    assert stats["content_type"] == "log", stats
    assert "log-summary" in stats["transforms"], stats
    assert len(out.splitlines()) < len(raw.splitlines()), "log output should shrink"
    assert "WARNING: retrying slow test" in out, "warning line lost"
    assert "FAILED tests/test_api.py::test_auth" in out, "failure line lost"


def test_diff_content_filter_preserves_headers_and_changes() -> None:
    raw = "\n".join(
        ["diff --git a/app.py b/app.py", "index abc..def 100644", "--- a/app.py", "+++ b/app.py", "@@ -1,320 +1,320 @@"]
        + [f" context {i}" for i in range(330)]
        + ["-old line", "+new line"]
    )
    out, stats = filter_text(raw, rules=load_rules(None), content_type="diff")
    assert stats["content_type"] == "diff", stats
    assert "diff-hunks" in stats["transforms"], stats
    assert "diff --git a/app.py b/app.py" in out, "diff header lost"
    assert "@@ -1,320 +1,320 @@" in out, "hunk header lost"
    assert "-old line" in out and "+new line" in out, "changed lines lost"
    assert " context 42" not in out, "large context block should be omitted"


def test_archive_rewind_roundtrip_and_grep() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        raw = "alpha\nbeta ERROR\nbeta ok\n"
        record = archive_event(root, raw, "alpha\n", {"raw_lines": 3, "filtered_lines": 1, "raw_tokens_est": 6}, "s1")
        assert rewind(root, record["id"]) == raw
        assert rewind(root, record["id"], grep="ERROR") == "beta ERROR\n"
        assert record["raw_tokens_est"] == 6


def test_rewind_rejects_tampered_raw_path_escape() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        outside = root / "outside.txt"
        outside.write_text("do not read me\n", encoding="utf-8")
        index = root / ".brainer" / "output-filter" / "index.jsonl"
        index.parent.mkdir(parents=True)
        index.write_text(
            json.dumps({"id": "evil", "raw_path": "../../outside.txt"}) + "\n",
            encoding="utf-8",
        )
        try:
            rewind(root, "evil")
        except SystemExit as exc:
            msg = str(exc)
            assert "unsafe output-filter raw_path" in msg, msg
        else:
            raise AssertionError("tampered raw_path escape was accepted")


def test_cli_noisy_content_types_preserve_signal_and_rewind_roundtrip() -> None:
    search_raw = "\n".join(
        f"src/file{i % 50}.py:{i}: match {i}" for i in range(140)
    ) + "\nERROR: search failed late\n"
    log_raw = (
        ESC + "[?25l" + "\n".join(f"progress {i} 99%" for i in range(180))
        + "\nWARNING: retrying flaky shard\nFAILED tests/test_api.py::test_auth\n"
        + "\n".join(f"tail {i}" for i in range(120))
        + ESC + "[?25h\n"
    )
    diff_raw = "\n".join(
        ["diff --git a/app.py b/app.py", "index abc..def 100644", "--- a/app.py", "+++ b/app.py", "@@ -1,340 +1,340 @@"]
        + [f" context {i}" for i in range(340)]
        + ["-old important line", "+new important line"]
    ) + "\n"
    cases = [
        ("search", search_raw, ["ERROR: search failed late", "src/file0.py:0: match 0"]),
        ("log", log_raw, ["WARNING: retrying flaky shard", "FAILED tests/test_api.py::test_auth"]),
        ("diff", diff_raw, ["diff --git a/app.py b/app.py", "-old important line", "+new important line"]),
    ]
    for content_type, raw, signals in cases:
        with tempfile.TemporaryDirectory() as td:
            env = {**os.environ, "TOKEN_ECONOMY_SESSION_ID": f"stress-{content_type}"}
            filtered = subprocess.run(
                [sys.executable, str(_OUTPUT_FILTER), "--repo", td, "filter", "--content-type", content_type, "--show-marker"],
                input=raw,
                text=True,
                capture_output=True,
                check=True,
                env=env,
            )
            for signal in signals:
                assert signal in filtered.stdout, (content_type, signal, filtered.stdout)
            recovered = subprocess.run(
                [sys.executable, str(_OUTPUT_FILTER), "--repo", td, "rewind", "last"],
                text=True,
                capture_output=True,
                check=True,
            )
            assert recovered.stdout == raw, content_type


def test_cli_show_marker_is_opt_in() -> None:
    raw = "\n".join(f"src/file{i % 3}.py:{i}: match {i}" for i in range(120)) + "\n"
    with tempfile.TemporaryDirectory() as td:
        base = [sys.executable, str(_OUTPUT_FILTER), "--repo", td, "filter", "--content-type", "search"]
        plain = subprocess.run(base, input=raw, text=True, capture_output=True, check=True)
        marked = subprocess.run([*base, "--show-marker"], input=raw, text=True, capture_output=True, check=True)
    assert "raw archived id=" not in plain.stdout, plain.stdout
    assert "raw archived id=" in marked.stdout, marked.stdout


def main() -> int:
    tests = [
        test_strips_csi_color_codes,
        test_strips_private_mode_csi,
        test_strips_osc_sequence,
        test_strips_single_char_escape,
        test_no_raw_esc_leaks_and_error_preserved,
        test_search_content_filter_keeps_diversity_and_errors,
        test_log_content_filter_preserves_signal_lines,
        test_diff_content_filter_preserves_headers_and_changes,
        test_archive_rewind_roundtrip_and_grep,
        test_rewind_rejects_tampered_raw_path_escape,
        test_cli_noisy_content_types_preserve_signal_and_rewind_roundtrip,
        test_cli_show_marker_is_opt_in,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ok  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {t.__name__}: {e}")
    if failed:
        print(f"\n{failed}/{len(tests)} failed")
        return 1
    print(f"\nall {len(tests)} passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
