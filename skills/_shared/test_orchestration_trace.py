#!/usr/bin/env python3
"""Tests for orchestration_trace.py — plain-python (no pytest dep), runnable
standalone. Shape mirrors test_model_roster.py: a list of test_* functions, a
main() that runs them and returns the failure count (exit 0 == all pass).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import orchestration_trace as ot  # noqa: E402


def test_record_lane_event_appends_one_json_line():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lanes.jsonl"
        ok = ot.record_lane_event(str(path), {"role": "verifier", "lane": "gpt", "ok": True})
        rows = path.read_text(encoding="utf-8").splitlines()
        return ok is True and len(rows) == 1 and json.loads(rows[0])["lane"] == "gpt"


def test_record_lane_event_creates_parent_dirs():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "nested" / "deeper" / "lanes.jsonl"
        ok = ot.record_lane_event(str(path), {"role": "advisor", "lane": "glm", "ok": False})
        return ok is True and path.exists()


def test_record_lane_event_appends_not_overwrites():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lanes.jsonl"
        ot.record_lane_event(str(path), {"lane": "gpt", "ok": True})
        ot.record_lane_event(str(path), {"lane": "gemini", "ok": True})
        rows = path.read_text(encoding="utf-8").splitlines()
        return len(rows) == 2 and json.loads(rows[0])["lane"] == "gpt" and json.loads(rows[1])["lane"] == "gemini"


def test_record_lane_event_carries_telemetry_fields():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lanes.jsonl"
        event = {"role": "verifier", "lane": "gpt", "vendor": "GPT via OpenRouter", "ok": True,
                 "usage": {"prompt_tokens": 12, "completion_tokens": 34}, "latency_ms": 456.7,
                 "served_model": "openai/gpt-5.4-mini"}
        ot.record_lane_event(str(path), event)
        row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
        return (row["usage"] == {"prompt_tokens": 12, "completion_tokens": 34}
                and row["latency_ms"] == 456.7 and row["served_model"] == "openai/gpt-5.4-mini")


def test_record_lane_event_never_raises_on_unwritable_path():
    # Point at a path whose parent cannot be created (a FILE in the way, not a
    # dir) — mkdir(parents=True) must fail, and record_lane_event must swallow
    # it and return False rather than propagate.
    with tempfile.TemporaryDirectory() as td:
        blocker = Path(td) / "not_a_dir"
        blocker.write_text("i am a file, not a directory", encoding="utf-8")
        bad_path = blocker / "sub" / "lanes.jsonl"
        ok = ot.record_lane_event(str(bad_path), {"lane": "gpt", "ok": True})
        return ok is False


def test_record_lane_event_default_path_is_dot_brainer_trace():
    return ot.DEFAULT_TRACE_PATH.parts[-3:] == (".brainer", "trace", "lanes.jsonl")


def test_record_lane_event_redacts_task_digest():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lanes.jsonl"
        ot.record_lane_event(str(path), {"lane": "gpt", "ok": True,
                                         "task_digest": "key=sk-proj-abcdef0123456789abcdef"})
        row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
        return "sk-proj-abcdef" not in (row["task_digest"] or "") and "[REDACTED]" in row["task_digest"]


def test_record_lane_event_drops_entirely_when_redactor_missing():
    # 2026-07-05 T2 fix: with no redactor available there is no way to
    # guarantee a clean line, so the event must be dropped ENTIRELY (return
    # False, nothing written) rather than blanking string values — a partial
    # scrub (e.g. keys/coerced values still raw) would still be a leak.
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lanes.jsonl"
        orig = ot._redact_secrets
        ot._redact_secrets = None
        try:
            ok = ot.record_lane_event(str(path), {"lane": "gpt", "ok": True, "task_digest": "some raw task text"})
        finally:
            ot._redact_secrets = orig
        return ok is False and not path.exists()


def test_record_lane_event_redacts_secrets_in_extra_and_nested_usage_fields():
    # 2026-07-05 cross-vendor review (T1): only task_digest was redacted before;
    # a secret in ANY other field (a top-level extra field, or nested inside
    # usage) must be scrubbed too, not written verbatim.
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lanes.jsonl"
        ot.record_lane_event(str(path), {
            "role": "builder",
            "extra": "ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            "usage": {"note": "sk-ant-SECRETSECRET"},
        })
        raw = path.read_text(encoding="utf-8")
        row = json.loads(raw.splitlines()[0])
        return ("ghp_AAAA" not in raw and "sk-ant-SECRET" not in raw
                and row["extra"] == "[REDACTED]"
                and row["usage"]["note"] == "[REDACTED]")


def test_record_lane_event_redacts_secrets_in_list_items():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lanes.jsonl"
        ot.record_lane_event(str(path), {
            "lane": "gpt", "ok": True,
            "notes": ["fine", "sk-proj-abcdef0123456789abcdef"],
        })
        raw = path.read_text(encoding="utf-8")
        row = json.loads(raw.splitlines()[0])
        return ("sk-proj-abcdef" not in raw and row["notes"] == ["fine", "[REDACTED]"])


def test_record_lane_event_non_string_values_pass_through_unchanged():
    # int token counts / None / bool must NOT be stringified or dropped by the
    # new recursive redaction — only string leaves are touched.
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lanes.jsonl"
        ot.record_lane_event(str(path), {
            "lane": "gpt", "ok": True,
            "usage": {"prompt_tokens": 12, "completion_tokens": 34, "cached": None},
            "latency_ms": 456.7,
        })
        row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
        return (row["usage"] == {"prompt_tokens": 12, "completion_tokens": 34, "cached": None}
                and row["latency_ms"] == 456.7 and row["ok"] is True)


def test_record_lane_event_nothing_written_when_redactor_missing_even_with_dict_key_secret():
    # Extending the drop-entirely fail-closed test: with the redactor
    # unavailable, a secret sitting in a DICT KEY (which the old structure-walk
    # never scrubbed even when the redactor WAS available) must also result in
    # nothing being written at all — the whole event is refused, not partially
    # blanked.
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lanes.jsonl"
        orig = ot._redact_secrets
        ot._redact_secrets = None
        try:
            ok = ot.record_lane_event(str(path), {
                "lane": "gpt", "ok": True,
                "extra": "some raw text that must not be written verbatim",
                "usage": {"note": "also raw"},
                "sk-ant-SECRETSECRETSECRET": "x",
            })
        finally:
            ot._redact_secrets = orig
        return ok is False and not path.exists()


def test_record_lane_event_nonserializable_set_is_stored_coerced_not_dropped():
    # 2026-07-05 review: a non-JSON-serializable value (a set) must not make
    # json.dumps raise inside the try — it must be coerced (via default=str)
    # and the event still gets written, rather than silently dropping it.
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lanes.jsonl"
        ok = ot.record_lane_event(str(path), {"lane": "gpt", "ok": False, "tags": {1, 2, 3}})
        rows = path.read_text(encoding="utf-8").splitlines()
        if not (ok is True and len(rows) == 1):
            return False
        row = json.loads(rows[0])
        return isinstance(row["tags"], str) and row["tags"] in ("{1, 2, 3}", "{1, 3, 2}", "{2, 1, 3}",
                                                                  "{2, 3, 1}", "{3, 1, 2}", "{3, 2, 1}")


def test_record_lane_event_nonserializable_bytes_is_stored_coerced_not_dropped():
    # bytes are DECODED (not repr-ed) so a token inside keeps its exact
    # characters for the regex — the 2026-07-05 3rd-pass 5c fix. A plain
    # ascii payload therefore stores as "hello", not "b'hello'".
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lanes.jsonl"
        ok = ot.record_lane_event(str(path), {"lane": "gemini", "ok": True, "raw": b"hello"})
        rows = path.read_text(encoding="utf-8").splitlines()
        row = json.loads(rows[0]) if rows else {}
        return ok is True and len(rows) == 1 and row["raw"] == "hello"


def test_record_lane_event_redacts_secret_with_embedded_quote_and_newline():
    # 2026-07-05 3rd-pass 5a leak repro: a secret containing a `"` or newline
    # survived JSON escaping (`\"`, `\n`) in a serialize-then-redact design, so
    # the token pattern no longer anchored. Redacting the RAW string leaf BEFORE
    # serialization means the quote/newline is a clean token boundary and the
    # secret-shaped prefix is scrubbed.
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lanes.jsonl"
        ok = ot.record_lane_event(str(path), {
            "lane": "gpt", "ok": True,
            "q": 'sk-proj-AAAAAAAAAAAAAAAAAAAA"tail',
            "nl": "sk-proj-BBBBBBBBBBBBBBBBBBBB\nmore",
        })
        raw = path.read_text(encoding="utf-8")
        return (ok is True and "sk-proj-AAAA" not in raw and "sk-proj-BBBB" not in raw
                and "[REDACTED]" in raw)


def test_record_lane_event_redacts_secret_with_non_ascii_char():
    # 2026-07-05 3rd-pass 5b leak repro: ensure_ascii=True turned a non-ASCII
    # secret byte into `\uXXXX`, which the regex missed. The walk redacts the
    # raw string (non-ASCII char is a token boundary), and the final dump uses
    # ensure_ascii=False so nothing is re-hidden.
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lanes.jsonl"
        ok = ot.record_lane_event(str(path), {
            "lane": "gpt", "ok": True,
            "s": "sk-proj-AAAAAAAAAAAAAAAAé-BBBB",
        })
        raw = path.read_text(encoding="utf-8")
        return (ok is True and "sk-proj-AAAA" not in raw
                and "\\u" not in raw and "[REDACTED]" in raw)


def test_record_lane_event_redacts_word_char_prefixed_and_suffixed_tokens():
    # 2026-07-05 4th-pass HIGH finding: leading \b in the standalone-token
    # regexes silently refused a match when a word char preceded the token
    # (`key_sk-proj-...` — `_` is a word char, no boundary), and trailing \b
    # failed for families whose class lacks `_` (`ghp_..._tail`) or has a fixed
    # count that cannot backtrack (`AKIA...x`). Anchors removed — all three
    # shapes must now redact.
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lanes.jsonl"
        ok = ot.record_lane_event(str(path), {
            "lane": "gpt", "ok": True,
            "prefixed": "key_sk-proj-AAAAAAAAAAAAAAAAAAAA",
            "suffixed": "ghp_BBBBBBBBBBBBBBBBBBBBBBBB_tail",
            "akid": "key_AKIAAAAAAAAAAAAAAAAAx",
            "pat": "key_github_pat_CCCCCCCCCCCCCCCCCCCCCC",
        })
        raw = path.read_text(encoding="utf-8")
        return (ok is True
                and "sk-proj-AAAA" not in raw
                and "ghp_BBBB" not in raw
                and "AKIAAAAA" not in raw
                and "github_pat_CCCC" not in raw
                and "[REDACTED]" in raw)


def test_record_lane_event_redacts_token_inside_bytes_via_decode():
    # 2026-07-05 3rd-pass 5c: bytes are decoded (not repr-ed) so a real token
    # inside them keeps its exact character sequence and is matched — a
    # repr(b"...") backslash artifact would otherwise dodge the pattern.
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lanes.jsonl"
        ok = ot.record_lane_event(str(path), {
            "lane": "gpt", "ok": True,
            "raw": b"ghp_EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE",
        })
        raw = path.read_text(encoding="utf-8")
        return ok is True and "ghp_EEEE" not in raw and "[REDACTED]" in raw


def test_record_lane_event_nonserializable_custom_object_never_raises():
    # An object whose __str__ itself raises must never propagate out of
    # record_lane_event — the absolute never-raise contract. The coerce-and-
    # redact walk guards the str() call, so the bad field is stored as a
    # placeholder and the rest of the event is still written (better than
    # dropping the whole row for one odd field).
    class _Evil:
        def __str__(self):
            raise RuntimeError("str() itself blows up")

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lanes.jsonl"
        ok = ot.record_lane_event(str(path), {"lane": "gpt", "ok": False, "evil": _Evil()})
        raw = path.read_text(encoding="utf-8") if path.exists() else ""
        return ok is True and "[UNSERIALIZABLE]" in raw and '"lane": "gpt"' in raw


def test_record_lane_event_redacts_secret_in_dict_key():
    # 2026-07-05 T1 leak repro: the old structure-walker never scrubbed dict
    # KEYS, only values — a secret used as a key was written verbatim.
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lanes.jsonl"
        ot.record_lane_event(str(path), {"sk-ant-SECRETSECRETSECRET": "x", "lane": "gpt"})
        raw = path.read_text(encoding="utf-8")
        return "sk-ant-" not in raw


def test_record_lane_event_redacts_coerced_object_and_bytes_values():
    # 2026-07-05 T2 leak repro: a value survives the (pre-serialization)
    # redaction step unchanged because it isn't a string yet, then
    # json.dumps(default=str) stringifies it AFTER the scrub ran — bypassing
    # redaction entirely for bytes / objects whose __str__ returns a secret.
    # The final-string-pass fix scrubs AFTER coercion, so this must be caught.
    class _SecretObj:
        def __str__(self):
            return "sk-ant-OBJECTSECRET"

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lanes.jsonl"
        ok = ot.record_lane_event(str(path), {
            "obj": _SecretObj(),
            "raw": b"ghp_DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD",
        })
        raw = path.read_text(encoding="utf-8") if Path(path).exists() else ""
        return ok is True and "sk-ant-" not in raw and "ghp_" not in raw


def test_record_lane_event_redacts_nested_list_and_tuple_secrets():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lanes.jsonl"
        ot.record_lane_event(str(path), {
            "lane": "gpt", "ok": True,
            "nested": {"inner": ["sk-proj-abcdef0123456789abcdef", "fine"]},
            "as_tuple": ("ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "ok"),
        })
        raw = path.read_text(encoding="utf-8")
        return ("sk-proj-abcdef" not in raw and "ghp_AAAA" not in raw
                and "[REDACTED]" in raw)


def test_record_lane_event_circular_ref_never_raises():
    # A circular reference is broken by the id-based `seen` set (emits
    # [CIRCULAR]) rather than making json.dumps raise — the event is still
    # written with other fields intact, and nothing propagates.
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lanes.jsonl"
        event: dict[str, Any] = {"lane": "gpt", "ok": True}
        event["self"] = event
        ok = ot.record_lane_event(str(path), event)
        raw = path.read_text(encoding="utf-8") if path.exists() else ""
        return ok is True and "[CIRCULAR]" in raw and '"lane": "gpt"' in raw


def test_record_lane_event_str_raises_never_propagates():
    # __str__ raising is caught by the coercion guard → stored as a placeholder,
    # event still written, exception never propagates.
    class _Evil:
        def __str__(self):
            raise RuntimeError("str() itself blows up")

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lanes.jsonl"
        ok = ot.record_lane_event(str(path), {"lane": "gpt", "ok": False, "evil": _Evil()})
        raw = path.read_text(encoding="utf-8") if path.exists() else ""
        return ok is True and "[UNSERIALIZABLE]" in raw


def test_record_lane_event_10mb_string_never_raises():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lanes.jsonl"
        big = "x" * (10 * 1024 * 1024)
        ok = ot.record_lane_event(str(path), {"lane": "gpt", "ok": True, "blob": big})
        return ok is True and path.exists()


def test_record_lane_event_none_path_uses_default():
    # Never actually write to the real repo root from a test: redirect the
    # module-level default and confirm None resolves to *some* default path,
    # not a crash, without touching the real .brainer/trace.
    orig_default = ot.DEFAULT_TRACE_PATH
    with tempfile.TemporaryDirectory() as td:
        ot.DEFAULT_TRACE_PATH = Path(td) / ".brainer" / "trace" / "lanes.jsonl"
        try:
            ok = ot.record_lane_event(None, {"lane": "gpt", "ok": True})
            return ok is True and ot.DEFAULT_TRACE_PATH.exists()
        finally:
            ot.DEFAULT_TRACE_PATH = orig_default


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]


def main() -> int:
    failures = 0
    for t in TESTS:
        try:
            ok = t()
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"ERROR {t.__name__}: {e}")
        if ok:
            print(f"PASS {t.__name__}")
        else:
            failures += 1
            print(f"FAIL {t.__name__}")
    total = len(TESTS)
    print(f"\n{total - failures}/{total} passed")
    return failures


if __name__ == "__main__":
    sys.exit(main())
