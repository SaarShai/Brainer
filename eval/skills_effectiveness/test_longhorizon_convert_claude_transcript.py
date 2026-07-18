"""Tests for longhorizon_convert_claude_transcript.py.

Uses SYNTHETIC fixture transcripts only -- never invokes the real ``claude``
CLI or makes any paid API call. Fixture event shapes are modeled on the
observed claude stream-json line types documented in the converter's own
module docstring (assistant/user/result/system events under
``claude -p --output-format stream-json --verbose``).
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

try:
    from .longhorizon_convert_claude_transcript import (
        compacted_turns, convert_session_events, read_manifest, write_raw_transcript,
    )
    from .longhorizon_extract_blinded import parse_transcript
except ImportError:
    from longhorizon_convert_claude_transcript import (
        compacted_turns, convert_session_events, read_manifest, write_raw_transcript,
    )
    from longhorizon_extract_blinded import parse_transcript


def line(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def write_manifest(session_dir: Path, forced_compactions: list[dict]) -> dict:
    manifest = {
        "schema_version": 1,
        "arm": "frontier",
        "venue": "/fake/venue",
        "fixture_root": "longhorizon-work/sample/",
        "forced_compactions": forced_compactions,
        "turns": [],
    }
    (session_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


class ReadManifestAndCompactedTurnsTests(unittest.TestCase):
    def test_read_manifest_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp)
            manifest = write_manifest(session_dir, [{"turn_index": 3, "mechanism": "claude-native-compact"}])
            self.assertEqual(manifest, read_manifest(session_dir))

    def test_compacted_turns_only_counts_claude_native_mechanism(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp)
            write_manifest(session_dir, [
                {"turn_index": 3, "mechanism": "claude-native-compact"},
                {"turn_index": 5, "mechanism": "context-pressure-filler"},
            ])
            manifest = read_manifest(session_dir)
            self.assertEqual({3}, compacted_turns(manifest))


class ConvertSessionEventsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.session_dir = Path(self.tmp.name)

    def _write_turn(self, turn_number: int, rows: list[dict]) -> None:
        (self.session_dir / f"turn-{turn_number:02d}.jsonl").write_text(
            "\n".join(line(r) for r in rows) + "\n", encoding="utf-8"
        )

    def test_ordinary_turn_prepends_scripted_user_event_and_preserves_source_lines(self):
        write_manifest(self.session_dir, [])
        self._write_turn(1, [
            {"type": "system", "subtype": "init", "tools": ["Bash"], "mcp_servers": [], "session_id": "s1"},
            {
                "type": "assistant",
                "message": {
                    "model": "claude-x",
                    "role": "assistant",
                    "content": [{"type": "text", "text": "hello"}],
                    "usage": {"input_tokens": 10, "cache_creation_input_tokens": 0,
                              "cache_read_input_tokens": 0, "output_tokens": 5},
                },
                "session_id": "s1",
            },
            {"type": "result", "subtype": "success", "is_error": False, "result": "hello",
             "usage": {"input_tokens": 10, "output_tokens": 5}, "total_cost_usd": 0.001, "session_id": "s1"},
        ])
        events = convert_session_events(self.session_dir, {1: "say exactly: hello"})

        self.assertEqual(4, len(events))
        self.assertEqual(
            {"type": "user", "message": {"role": "user", "content": "say exactly: hello"}},
            events[0],
        )
        self.assertEqual("system", events[1]["type"])
        self.assertEqual("assistant", events[2]["type"])
        self.assertEqual("hello", events[2]["message"]["content"][0]["text"])
        self.assertEqual("result", events[3]["type"])
        # Claude-native events are appended verbatim -- no synthetic wrapper
        # "type":"tool" event is fabricated alongside them.
        self.assertNotIn("tool", [e["type"] for e in events])

    def test_forced_compaction_turn_emits_marker_instead_of_scripted_text(self):
        write_manifest(self.session_dir, [{"turn_index": 2, "mechanism": "claude-native-compact"}])
        self._write_turn(1, [{"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "ok"}]}}])
        self._write_turn(2, [{"type": "result", "subtype": "success", "is_error": False, "result": "compacted"}])
        events = convert_session_events(self.session_dir, {1: "do the thing", 2: "/compact"})

        marker = events[2]
        self.assertEqual(
            {
                "type": "context_pressure_equivalent",
                "host_event_id": "compaction-turn-2",
                "turn_index": 2,
                "mechanism": "claude-native-compact",
            },
            marker,
        )
        # The literal "/compact" scripted text is NOT sent as a user event
        # for a forced-compaction turn.
        self.assertNotIn({"type": "user", "message": {"role": "user", "content": "/compact"}}, events)

    def test_tool_use_and_tool_result_blocks_pass_through_in_anthropic_block_shape(self):
        write_manifest(self.session_dir, [])
        self._write_turn(1, [
            {
                "type": "assistant",
                "message": {"role": "assistant", "content": [
                    {"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": {"command": "echo hi"}},
                ]},
            },
            {
                "type": "user",
                "message": {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_1", "content": "hi\n", "is_error": False},
                ]},
                "tool_use_result": {"stdout": "hi\n"},
            },
        ])
        events = convert_session_events(self.session_dir, {1: "run echo hi"})
        tool_use_block = events[1]["message"]["content"][0]
        tool_result_block = events[2]["message"]["content"][0]
        self.assertEqual("tool_use", tool_use_block["type"])
        self.assertEqual("Bash", tool_use_block["name"])
        self.assertEqual("tool_result", tool_result_block["type"])
        self.assertEqual("toolu_1", tool_result_block["tool_use_id"])

    def test_multiple_turns_are_emitted_in_ascending_turn_order_regardless_of_dict_order(self):
        write_manifest(self.session_dir, [])
        self._write_turn(1, [{"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "one"}]}}])
        self._write_turn(2, [{"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "two"}]}}])
        # dict insertion order deliberately reversed
        events = convert_session_events(self.session_dir, {2: "second", 1: "first"})
        user_events = [e for e in events if e["type"] == "user"]
        self.assertEqual(["first", "second"], [e["message"]["content"] for e in user_events])

    def test_malformed_source_line_raises_value_error(self):
        write_manifest(self.session_dir, [])
        (self.session_dir / "turn-01.jsonl").write_text("not json\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "non-JSON source line"):
            convert_session_events(self.session_dir, {1: "x"})

    def test_non_object_source_line_raises_value_error(self):
        write_manifest(self.session_dir, [])
        (self.session_dir / "turn-01.jsonl").write_text("[1, 2, 3]\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "non-object source event"):
            convert_session_events(self.session_dir, {1: "x"})

    def test_blank_lines_in_turn_file_are_skipped(self):
        write_manifest(self.session_dir, [])
        (self.session_dir / "turn-01.jsonl").write_text(
            line({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "x"}]}}) + "\n\n\n",
            encoding="utf-8",
        )
        events = convert_session_events(self.session_dir, {1: "x"})
        self.assertEqual(2, len(events))  # scripted user event + the one assistant event


class WriteRawTranscriptTests(unittest.TestCase):
    def test_writes_one_canonical_json_line_per_event_and_is_readable_by_frozen_extractor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events = [
                {"type": "user", "message": {"role": "user", "content": "hello"}},
                {
                    "type": "assistant",
                    "message": {"role": "assistant", "content": [{"type": "text", "text": "hi there, all done"}]},
                },
            ]
            out_path = write_raw_transcript(events, root / "raw.jsonl")
            lines = out_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(2, len(lines))
            for raw_line in lines:
                json.loads(raw_line)  # must be valid, single-line JSON
            # The frozen blinded extractor's own transcript parser must be
            # able to consume the file this converter writes, unmodified.
            parsed = parse_transcript(out_path, blind=True)
            self.assertEqual(2, len(parsed))
            self.assertEqual("user", parsed[0]["event"]["type"])
            self.assertEqual("assistant", parsed[1]["event"]["type"])


if __name__ == "__main__":
    unittest.main()
