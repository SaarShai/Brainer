#!/usr/bin/env python3
"""Smoke tests for output_filter.py — runnable standalone with no pytest dep."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from output_filter import ANSI, filter_text, load_rules  # noqa: E402

ESC = "\x1b"


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


def main() -> int:
    tests = [
        test_strips_csi_color_codes,
        test_strips_private_mode_csi,
        test_strips_osc_sequence,
        test_strips_single_char_escape,
        test_no_raw_esc_leaks_and_error_preserved,
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
