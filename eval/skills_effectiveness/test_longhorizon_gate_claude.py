"""Tests for longhorizon_gate_claude.py using a tiny SYNTHETIC 35-turn
rehearsal-shaped scenario (built entirely in a tmpdir) instead of the real
rehearsal-A/B fixtures, and a fake (non-network) grader function -- no paid
API call and no real ``claude`` invocation is made anywhere in this file.

The real SCENARIO_KEYS dict (rehearsal-A/rehearsal-B) is replaced via
patch.dict for the duration of each test, mirroring the pattern
test_longhorizon_score_counted.py uses against longhorizon_score_counted's
SESSION_CONFIGS/SNAPSHOT_BUILDERS for the codex host.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import longhorizon_gate as gate
import longhorizon_gate_claude as gc


def line(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def synthetic_scenario_md(prefix: str) -> str:
    """35 scripted turns (T01..T35); T34 is the organic 'Are we done?'
    boundary the blinded extractor requires. Two of the interior turns will
    be marked as forced compactions via manifest.json (not via /compact
    literal text -- compaction is manifest-driven for the claude host)."""
    lines = [f"# Synthetic {prefix} scenario -- harness-plumbing test fixture only", ""]
    for n in range(1, 35):
        lines.append(f"T{n:02d} — `{prefix} scripted turn {n}`")
    lines.append(f"T35 — `Are we done?`")
    lines.append("")
    lines.append("## Explicit requirement ledger")
    lines.append("")
    lines.append("| ID | Requirement text | Where planted | Expected disposition |")
    lines.append("|---|---|---|---|")
    lines.append(f"| {prefix}-R00 | Old placeholder value. | T01 | superseded by {prefix}-R01 |")
    for i in range(1, 5):
        lines.append(f"| {prefix}-R0{i} | Requirement {i} text. | T01 | completed |")
    lines.append("")
    lines.append("Scored denominator: four active requirements.")
    lines.append("")
    lines.append("### Final artifact predicates")
    lines.append("")
    lines.append("| Requirement | Mechanical predicate | Passing final artifact state |")
    lines.append("|---|---|---|")
    for i in range(1, 5):
        lines.append(f"| {prefix}-R0{i} | Parse out.json field f{i}. | Value {i}. |")
    lines.append("")
    return "\n".join(lines) + "\n"


def synthetic_snapshot_builder(config: dict, captured_after: int) -> dict:
    root = config["fixture"]
    out = json.loads((root / config["paths"]["out"]).read_text(encoding="utf-8"))
    checks = [
        (f"{config['prefix']}-R01", out.get("f1") == 1, {"f1": out.get("f1")}),
        (f"{config['prefix']}-R02", out.get("f2") == 2, {"f2": out.get("f2")}),
        (f"{config['prefix']}-R03", out.get("f3") == 3, {"f3": out.get("f3")}),
        (f"{config['prefix']}-R04", out.get("f4") == 4, {"f4": out.get("f4")}),
    ]
    scenario_id = config["scenario_id"]
    requirements = []
    artifact_paths_by_id = dict(config["requirements"])
    for requirement_id, passed, observed in checks:
        requirements.append({
            "id": requirement_id,
            "predicate_id": requirement_id + "-final",
            "status": "pass" if passed else "fail",
            "observed": observed,
            "artifact_paths": artifact_paths_by_id[requirement_id],
        })
    return {
        "type": "scenario_end_snapshot",
        "scenario_id": scenario_id,
        "captured_after_raw_event": captured_after,
        "requirements": requirements,
        "escaped_defect_checks": [],
    }


def make_snapshot_builder(prefix: str, scenario_id: str):
    def builder(config, captured_after):
        return synthetic_snapshot_builder({**config, "prefix": prefix, "scenario_id": scenario_id}, captured_after)
    return builder


def write_turn_files(session_dir: Path, terminal_text: str) -> None:
    session_dir.mkdir(parents=True, exist_ok=True)
    for n in range(1, 35):
        rows = [{"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": f"working on turn {n}"}]}}]
        (session_dir / f"turn-{n:02d}.jsonl").write_text("\n".join(line(r) for r in rows) + "\n", encoding="utf-8")
    # T35's turn-35.jsonl carries the terminal assistant response following
    # the organic "Are we done?" scripted user event the converter emits.
    (session_dir / "turn-35.jsonl").write_text(
        line({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": terminal_text}]}}) + "\n",
        encoding="utf-8",
    )


def write_manifest(session_dir: Path, venue: Path, arm: str, fixture_root: str, compaction_turns: tuple[int, int]) -> None:
    manifest = {
        "schema_version": 1,
        "arm": arm,
        "venue": str(venue),
        "fixture_root": fixture_root,
        "forced_compactions": [
            {"turn_index": compaction_turns[0], "mechanism": "claude-native-compact"},
            {"turn_index": compaction_turns[1], "mechanism": "claude-native-compact"},
        ],
        "turns": [{"turn_index": n, "codex_exit_code": 0, "transcript_file": f"turn-{n:02d}.jsonl"} for n in range(1, 36)],
    }
    (session_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def write_fixture(venue: Path, fixture_root: str, values: dict) -> None:
    fixture = venue / fixture_root
    fixture.mkdir(parents=True, exist_ok=True)
    (fixture / "out.json").write_text(json.dumps(values), encoding="utf-8")


def make_fake_grader(labels: dict[str, str]):
    """Returns only the labels whose requirement_id appears in this call's
    checklist payload, so the fake grader answers per-scenario like a real
    one would (the real run_gate calls it once per scenario per pass)."""
    def fake_grader(api_key, prompt, user_payload):
        assert api_key
        relevant = [rid for rid in labels if rid in user_payload]
        parsed = {
            "requirements": [{"requirement_id": rid, "label": labels[rid]} for rid in relevant],
            "false_terminal_claim": False,
        }
        return json.dumps(parsed), parsed
    return fake_grader


class RunGateClaudeSyntheticTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.stratum_dir = self.root / "stratum"
        self.stratum_dir.mkdir()

        scenario_a_md = self.root / "synth-a.md"
        scenario_b_md = self.root / "synth-b.md"
        scenario_a_md.write_text(synthetic_scenario_md("SA"), encoding="utf-8")
        scenario_b_md.write_text(synthetic_scenario_md("SB"), encoding="utf-8")

        self.synthetic_keys = {
            "synth-A": {
                "source": scenario_a_md,
                "session_subdir": "synth-A-frontier",
                "blind_id": "S-1",
                "arm": "FRONTIER",
                "paths": {"out": "out.json"},
                "requirements": [(f"SA-R0{i}", ["out.json"]) for i in range(1, 5)],
                "lineage": [{"requirement_id": "SA-R00", "status": "superseded", "superseded_by": "SA-R01"}],
                "decision_states": [],
                "snapshot_builder": make_snapshot_builder("SA", "synth-A"),
            },
            "synth-B": {
                "source": scenario_b_md,
                "session_subdir": "synth-B-off",
                "blind_id": "S-2",
                "arm": "OFF",
                "paths": {"out": "out.json"},
                "requirements": [(f"SB-R0{i}", ["out.json"]) for i in range(1, 5)],
                "lineage": [{"requirement_id": "SB-R00", "status": "superseded", "superseded_by": "SB-R01"}],
                "decision_states": [],
                "snapshot_builder": make_snapshot_builder("SB", "synth-B"),
            },
        }

        for key, config in self.synthetic_keys.items():
            venue = self.root / f"venue-{key}"
            session_dir = self.stratum_dir / config["session_subdir"]
            prefix = "SA" if key == "synth-A" else "SB"
            terminal_text = f"{prefix}-R01, {prefix}-R02, {prefix}-R03, {prefix}-R04 are all done."
            write_turn_files(session_dir, terminal_text)
            write_manifest(session_dir, venue, config["arm"].lower(), "fixture/", (5, 20))
            write_fixture(venue, "fixture", {"f1": 1, "f2": 2, "f3": 3, "f4": 4})

        # Hermetic: point the imported longhorizon_gate module's telemetry
        # paths at nonexistent tmpdir locations so tests never read the
        # real PROMPTER canary state / telemetry off this machine.
        self.patches = [
            patch.dict(gc.SCENARIO_KEYS, self.synthetic_keys, clear=True),
            patch.object(gate, "CANARY_STATE", self.root / "no-canary-state"),
            patch.object(gate, "TELEMETRY", self.root / "no-telemetry.jsonl"),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_run_gate_end_to_end_all_components_pass(self):
        labels = {}
        for prefix in ("SA", "SB"):
            for i in range(1, 5):
                labels[f"{prefix}-R0{i}"] = "completed"
        fake_grader = make_fake_grader(labels)
        report = gc.run_gate(self.stratum_dir, grader_fn=fake_grader, api_key_loader=lambda: "fake-test-key")

        self.assertEqual("PASS", report["overall"])
        self.assertEqual("PASS", report["components"]["blinded_extraction_A"]["status"])
        self.assertEqual("PASS", report["components"]["blinded_extraction_B"]["status"])
        self.assertEqual("PASS", report["components"]["mechanism_extraction"]["status"])
        self.assertEqual("PASS", report["components"]["compactions"]["status"])
        self.assertEqual("PASS", report["components"]["grader_kappa"]["status"])
        self.assertEqual(1.0, report["components"]["grader_kappa"]["kappa"])

        counts = report["components"]["blinded_extraction_A"]["counts"]
        self.assertEqual(4, counts["completed"])
        self.assertEqual(1.0, counts["headline_recall"])

        report_path = self.stratum_dir / "gate-report.json"
        self.assertTrue(report_path.is_file())
        on_disk = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report, on_disk)

        blinded_text = (self.stratum_dir / "blinded-table-S-1.json").read_text(encoding="utf-8")
        self.assertNotIn("frontier", blinded_text.lower())
        self.assertNotIn("system-reminder", blinded_text.lower())

        raw_responses = (self.stratum_dir / "grader-raw-responses.json").read_text(encoding="utf-8")
        self.assertNotIn("fake-test-key", raw_responses)

    def test_compactions_component_fails_when_mechanism_is_wrong(self):
        # Overwrite synth-A's manifest with a codex-style filler-byte
        # mechanism instead of claude-native-compact.
        session_dir = self.stratum_dir / "synth-A-frontier"
        manifest = json.loads((session_dir / "manifest.json").read_text(encoding="utf-8"))
        manifest["forced_compactions"] = [
            {"turn_index": 5, "mechanism": "context-pressure-filler", "filler_byte_size": 200000},
            {"turn_index": 20, "mechanism": "claude-native-compact"},
        ]
        (session_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        labels = {}
        for prefix in ("SA", "SB"):
            for i in range(1, 5):
                labels[f"{prefix}-R0{i}"] = "completed"
        fake_grader = make_fake_grader(labels)
        report = gc.run_gate(self.stratum_dir, grader_fn=fake_grader, api_key_loader=lambda: "fake-test-key")

        self.assertEqual("FAIL", report["components"]["compactions"]["status"])
        self.assertFalse(report["components"]["compactions"]["sessions"]["synth-A"]["valid"])
        self.assertTrue(report["components"]["compactions"]["sessions"]["synth-B"]["valid"])
        self.assertEqual("FAIL", report["overall"])

    def test_blinded_extraction_component_still_passes_but_reports_the_dropped_requirement(self):
        # blinded_extraction's component status reflects mechanical
        # extraction success, not whether every requirement was satisfied --
        # the dropped requirement shows up in "counts", and overall PASS/FAIL
        # is a PASS-if-all-components-PASS rollup, not a requirement-level
        # gate. This test documents that distinction so it isn't mistaken
        # for a bug later.
        write_fixture(self.root / "venue-synth-A", "fixture", {"f1": 999, "f2": 2, "f3": 3, "f4": 4})
        labels = {}
        for prefix in ("SA", "SB"):
            for i in range(1, 5):
                labels[f"{prefix}-R0{i}"] = "completed"
        fake_grader = make_fake_grader(labels)
        report = gc.run_gate(self.stratum_dir, grader_fn=fake_grader, api_key_loader=lambda: "fake-test-key")

        self.assertEqual("PASS", report["components"]["blinded_extraction_A"]["status"])
        counts = report["components"]["blinded_extraction_A"]["counts"]
        self.assertEqual(3, counts["completed"])
        self.assertEqual(1, counts["dropped"])
        self.assertEqual("PASS", report["overall"])

    def test_grader_failure_marks_overall_fail_without_crashing(self):
        def broken_grader(api_key, prompt, user_payload):
            raise RuntimeError("simulated grader outage")

        report = gc.run_gate(self.stratum_dir, grader_fn=broken_grader, api_key_loader=lambda: "fake-test-key")
        self.assertEqual("FAIL", report["components"]["grader_kappa"]["status"])
        self.assertIn("simulated grader outage", report["components"]["grader_kappa"]["error"])
        self.assertEqual("FAIL", report["overall"])


if __name__ == "__main__":
    unittest.main()
