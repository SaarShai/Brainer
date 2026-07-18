from __future__ import annotations

import json
import unittest

import longhorizon_extract_blinded as blinded
import longhorizon_extract_mechanism as mechanism


CONTRACT = {
    "scenario_id": "scenario-01",
    "requirements": [
        {"id": "S01-R01", "text": "one", "artifact_paths": ["dist/a.json"]},
        {"id": "S01-R02", "text": "two", "artifact_paths": ["dist/a.json"]},
        {"id": "S01-R03", "text": "three", "artifact_paths": ["docs/a.md"]},
        {"id": "S01-R04", "text": "four", "artifact_paths": []},
    ],
    "lineage": [{"requirement_id": "S01-R00", "status": "superseded", "superseded_by": "S01-R01"}],
    "session_hash": "session-x",
}


def line(obj): return json.dumps(obj, ensure_ascii=False)


def transcript(reminder=""):
    rows = [
        {"message": {"role": "user", "content": "Make artifacts."}},
        {"message": {"role": "assistant", "content": [{"type": "tool_use", "id": "u1", "name": "Bash", "input": "check dist/a.json"}]}},
        {"message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "u1", "content": "OK exit 0"}]}},
        {"message": {"role": "user", "content": "Organic " + reminder + " request"}},
        {"message": {"role": "user", "content": "Are we done?"}},
        {"message": {"role": "assistant", "content": "- S01-R02: deferred because tool access is unavailable\nS01-R01 done."}},
        {"type": "scenario_end_snapshot", "scenario_id": "scenario-01", "requirements": [
            {"id": "S01-R01", "status": "pass", "observed": {"value": 1}},
            {"id": "S01-R02", "status": "fail", "observed": {}},
            {"id": "S01-R03", "status": "fail", "observed": {}},
            {"id": "S01-R04", "status": "pass", "observed": {}},
        ], "escaped_defect_checks": [{"id": "extra", "status": "pass", "observed": []}]},
    ]
    return "\n".join(line(x) for x in rows) + "\n"


class BlindedExtractorTests(unittest.TestCase):
    def test_frontier_and_off_shapes_are_indistinguishable_and_reminders_leak_nothing(self):
        frontier = transcript("<system-reminder profile='x'>COMPLIANCE_CANARY_PROFILE FRONTIER</system-reminder>")
        off = transcript("")
        a = blinded.extract(frontier, CONTRACT, "opaque")
        b = blinded.extract(off, CONTRACT, "opaque")
        self.assertEqual(a, b)
        self.assertNotIn("system-reminder", blinded.canonical_json(a).casefold())
        self.assertNotIn("frontier", blinded.canonical_json(a).casefold())

    def test_completed_deferred_dropped_and_conflict(self):
        result = blinded.extract(transcript(), CONTRACT, "opaque")
        self.assertEqual(["completed", "deferred", "dropped", "completed"], [x["disposition"] for x in result["requirements"]])
        self.assertEqual({"completed": 2, "deferred": 1, "dropped": 1, "total": 4, "headline_recall": .75}, result["counts"])
        self.assertTrue(result["requirements"][3]["terminal_disposition_conflict"] is False)

    def test_nested_and_malformed_reminders(self):
        self.assertEqual("before  after", blinded._reminders("before <system-reminder>x <system-reminder>y</system-reminder> z</system-reminder> after"))
        self.assertEqual("ab", blinded._reminders("a<system-reminder x='y'/>b"))
        with self.assertRaisesRegex(blinded.ExtractionError, "BLINDING_MALFORMED_SYSTEM_REMINDER"):
            blinded._reminders("x</system-reminder>")
        with self.assertRaisesRegex(blinded.ExtractionError, "BLINDING_MALFORMED_SYSTEM_REMINDER"):
            blinded._reminders("<system-reminder>x")

    def test_hook_event_and_empty_text_block_are_removed(self):
        raw = "\n".join([line({"type": "hook_output", "content": "secret"}), line({"message": {"role": "user", "content": "<system-reminder>x</system-reminder>"}})])
        events = blinded.parse_transcript(raw)
        self.assertEqual([], events)


class MechanismExtractorTests(unittest.TestCase):
    def test_known_counts(self):
        rows = [
            {"message": {"role": "user", "content": "start"}},
            {"message": {"role": "assistant", "id": "a1", "content": "working", "usage": {"input_tokens": 10, "cache_creation_input_tokens": 2, "cache_read_input_tokens": 1, "output_tokens": 3}}},
            {"type": "compact_boundary", "host_event_id": "c1"},
            {"message": {"role": "user", "content": "recover"}},
            {"message": {"role": "assistant", "id": "a2", "content": "fine", "usage": {"prompt_tokens": 7, "completion_tokens": 5, "total_tokens": 12}}},
            {"type": "compact_boundary", "host_event_id": "c2"},
            {"message": {"role": "user", "content": "Are we done?"}},
            {"message": {"role": "assistant", "id": "a3", "content": "done", "usage": {"input_tokens": 1, "output_tokens": 1}}},
            {"type": "scenario_end_snapshot", "scenario_id": "scenario-01"},
        ]
        telemetry = [{"session_hash": "session-x", "turn": 4, "emitted": True, "injected_utf8_bytes": 9, "probe_id": "new-probe"}, {"session_hash": "session-x", "turn": 4, "mechanism": "suppressed_notification", "emitted": False, "probe_id": "claim-without-evidence"}]
        result = mechanism.extract("\n".join(line(x) for x in rows), CONTRACT, "FRONTIER", telemetry)
        self.assertEqual(30, result["metric_5"]["tokens"]["total"])
        self.assertEqual(1, result["metric_5"]["interruptions"]["count"])
        self.assertEqual(1, result["metric_5"]["interruptions"]["false_interruption_count"])
        self.assertEqual(1, result["metric_6"]["total_suppressions"])
        self.assertEqual(1, result["metric_6"]["counts"]["fire_deferred"])
        self.assertEqual(0, result["metric_3"]["count"])

    def test_off_telemetry_is_violation(self):
        raw = "\n".join(line(x) for x in [{"type": "compact_boundary", "host_event_id": "a"}, {"type": "compact_boundary", "host_event_id": "b"}, {"type": "scenario_end_snapshot", "scenario_id": "scenario-01"}])
        with self.assertRaisesRegex(mechanism.ExtractionError, "OFF_MUTATION_VIOLATION"):
            mechanism.extract(raw, CONTRACT, "OFF", [{"session_hash": "session-x", "turn": 1, "emitted": True, "injected_utf8_bytes": 1}])


if __name__ == "__main__": unittest.main()
