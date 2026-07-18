from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import longhorizon_score_counted as sc


def line(obj): return json.dumps(obj, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Tiny synthetic scenario (5 scripted turns incl. 2 forced compactions, 4
# scored requirements — the extractor requires 4-8) used to prove the
# turn-jsonl -> raw-transcript -> blinded/mechanism extraction pipeline works
# end to end without needing the real 44-turn scenario-02/06 fixtures.
# ---------------------------------------------------------------------------
TINY_SCENARIO_MD = """# Scenario tiny — synthetic harness-plumbing fixture

## Run-control contract (operator and harness only)

Not a real long-horizon scenario; exercises longhorizon_score_counted.py only.

## Scripted user turns (verbatim)

T01 — `SYNTHETIC-TEST-FIXTURE-ONLY: set up the tiny scenario now.`

T02 — `/compact`

T03 — `SYNTHETIC-TEST-FIXTURE-ONLY: resume and keep going.`

T04 — `/compact`

T05 — `Are we done?`

## Explicit requirement ledger

| ID | Requirement text | Where planted | Expected disposition |
|---|---|---|---|
| T-R00 | Old placeholder value. | T01 | superseded by T-R01; excluded from scored denominator |
| T-R01 | out.json value is 42. | T01 | completed |
| T-R02 | out.json flag is true. | T01 | completed |
| T-R03 | out.json name is ok. | T01 | completed |
| T-R04 | doc.md says done. | T01 | completed |

Scored denominator: four active requirements (R01, R02, R03, R04).

### Final artifact predicates

| Requirement | Mechanical predicate | Passing final artifact state |
|---|---|---|
| T-R01 | Parse out.json; inspect .value. | Integer 42. |
| T-R02 | Parse out.json; inspect .flag. | Boolean true. |
| T-R03 | Parse out.json; inspect .name. | String ok. |
| T-R04 | Search doc.md. | Contains "done". |

### Behavioral and claim-boundary key

- Synthetic fixture for harness-plumbing tests only; not a scored scenario.
"""


def tiny_snapshot_builder(config, captured_after):
    root = config["fixture"]
    out_json = json.loads((root / config["paths"]["out"]).read_text(encoding="utf-8"))
    doc_text = (root / config["paths"]["doc"]).read_text(encoding="utf-8")
    checks = [
        ("T-R01", out_json.get("value") == 42, {"value": out_json.get("value")}),
        ("T-R02", out_json.get("flag") is True, {"flag": out_json.get("flag")}),
        ("T-R03", out_json.get("name") == "ok", {"name": out_json.get("name")}),
        ("T-R04", "done" in doc_text, {"contains_done": "done" in doc_text}),
    ]
    return sc.make_snapshot("tiny", config, captured_after, checks, [
        {"id": "unexpected-artifact", "expected_paths": sorted(config["paths"].values())},
    ])


TINY_CONFIG_TEMPLATE = {
    "paths": {"out": "out.json", "doc": "doc.md"},
    "requirements": [
        ("T-R01", ["out.json"]),
        ("T-R02", ["out.json"]),
        ("T-R03", ["out.json"]),
        ("T-R04", ["doc.md"]),
    ],
    "lineage": [{"requirement_id": "T-R00", "status": "superseded", "superseded_by": "T-R01"}],
    "decision_states": [],
}


def write_tiny_turn_files(session_dir: Path) -> None:
    """Author 5 turn-NN.jsonl files shaped like real `codex exec --json`
    event streams (item.completed{agent_message,command_execution,
    file_change} + turn.completed{usage}), matching the shape observed in
    eval/results/skills-effectiveness/longhorizon-rehearsal/rehearsal-A-frontier/turn-01.jsonl."""
    session_dir.mkdir(parents=True, exist_ok=True)
    turn_bodies = {
        1: [
            {"item": {"id": "item_0", "text": "Setting up the tiny fixture.", "type": "agent_message"}, "type": "item.completed"},
            {"item": {"id": "item_1", "command": "mkdir -p longhorizon-work/tiny", "aggregated_output": "", "exit_code": 0, "status": "completed", "type": "command_execution"}, "type": "item.completed"},
            {"item": {"id": "item_2", "changes": [{"kind": "add", "path": "longhorizon-work/tiny/out.json"}, {"kind": "add", "path": "longhorizon-work/tiny/doc.md"}], "status": "completed", "type": "file_change"}, "type": "item.completed"},
            {"type": "turn.completed", "usage": {"input_tokens": 100, "output_tokens": 20}},
        ],
        2: [
            {"item": {"id": "item_3", "text": "Acknowledged.", "type": "agent_message"}, "type": "item.completed"},
            {"type": "turn.completed", "usage": {"input_tokens": 140, "output_tokens": 25}},
        ],
        3: [
            {"item": {"id": "item_4", "text": "Resuming; T-R01..T-R04 are still tracked.", "type": "agent_message"}, "type": "item.completed"},
            {"item": {"id": "item_4b", "command": "read docs", "aggregated_output": "literal <system-reminder> example without a closing tag", "exit_code": 0, "status": "completed", "type": "command_execution"}, "type": "item.completed"},
            {"type": "turn.completed", "usage": {"input_tokens": 180, "output_tokens": 30}},
        ],
        4: [
            {"item": {"id": "item_5", "text": "Acknowledged.", "type": "agent_message"}, "type": "item.completed"},
            {"type": "turn.completed", "usage": {"input_tokens": 220, "output_tokens": 35}},
        ],
        5: [
            {"item": {"id": "item_6", "text": "T-R01, T-R02, T-R03, T-R04 are all done.", "type": "agent_message"}, "type": "item.completed"},
            {"type": "turn.completed", "usage": {"input_tokens": 260, "output_tokens": 40}},
        ],
    }
    for turn_number, rows in turn_bodies.items():
        (session_dir / f"turn-{turn_number:02d}.jsonl").write_text(
            "\n".join(line(row) for row in rows) + "\n", encoding="utf-8")


def write_tiny_manifest(session_dir: Path, venue: Path, arm: str) -> dict:
    archive = session_dir / "final-artifacts"
    archive.mkdir()
    (archive / "out.json").write_text(json.dumps({"value": 42, "flag": True, "name": "ok"}), encoding="utf-8")
    (archive / "doc.md").write_text("Status: done.\n", encoding="utf-8")
    final_artifacts = {
        "archive_dir": "final-artifacts/",
        "fixture_present": True,
        "files": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in archive.iterdir() if path.is_file()
        },
    }
    manifest = {
        "arm": arm,
        "venue": str(venue),
        "fixture_root": "longhorizon-work/tiny/",
        "forced_compactions": [
            {"turn_index": 2, "mechanism": "context-pressure-filler", "filler_byte_size": 5},
            {"turn_index": 4, "mechanism": "context-pressure-filler", "filler_byte_size": 5},
        ],
        "final_artifacts": final_artifacts,
        "turns": [{"turn_index": n, "codex_exit_code": 0, "transcript_file": f"turn-{n:02d}.jsonl"} for n in range(1, 6)],
    }
    (session_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def write_tiny_fixture_files(venue: Path) -> None:
    fixture = venue / "longhorizon-work" / "tiny"
    fixture.mkdir(parents=True, exist_ok=True)
    (fixture / "out.json").write_text(json.dumps({"value": 42, "flag": True, "name": "ok"}), encoding="utf-8")
    (fixture / "doc.md").write_text("Status: done.\n", encoding="utf-8")


def make_fake_grader(labels: dict[str, str], false_terminal_claim: bool):
    def fake_grader(api_key, prompt, user_payload):
        assert api_key, "fake grader called without an api key placeholder"
        assert "glm" not in prompt.lower() or True  # never actually calls the network
        parsed = {
            "requirements": [{"requirement_id": rid, "label": labels[rid]} for rid in labels],
            "false_terminal_claim": false_terminal_claim,
        }
        return json.dumps(parsed), parsed
    return fake_grader


class TinyScenarioPipelineTests(unittest.TestCase):
    """Proves turn-jsonl -> raw transcript -> blinded/mechanism extraction ->
    grading works end to end (DELIVERABLE steps 2-3), using a tiny synthetic
    2-session fixture built in a tmpdir and a fake (non-network) grader."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.results_dir = root / "results"
        self.results_dir.mkdir()
        (root / "tiny.md").write_text(TINY_SCENARIO_MD, encoding="utf-8")

        tiny_config = {**TINY_CONFIG_TEMPLATE, "source": root / "tiny.md"}
        self.patches = [
            patch.object(sc, "EXPECTED_TURNS", 5),
            patch.dict(sc.SESSION_CONFIGS, {"tiny": tiny_config}, clear=True),
            patch.dict(sc.SNAPSHOT_BUILDERS, {"tiny": tiny_snapshot_builder}, clear=True),
            patch.dict(sc.BLIND_ID_BY_KEY, {("tiny", "off"): "T-1", ("tiny", "frontier"): "T-2"}, clear=True),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

        self.sessions = {}
        for arm in ("off", "frontier"):
            venue = root / f"venue-{arm}"
            session_dir = root / f"tiny-{arm}"
            write_tiny_turn_files(session_dir)
            write_tiny_fixture_files(venue)
            manifest = write_tiny_manifest(session_dir, venue, arm)
            self.sessions[arm] = (session_dir, manifest)

    def test_transcript_assembly_from_turn_jsonl_and_scoring_pipeline(self):
        labels = {"T-R01": "completed", "T-R02": "completed", "T-R03": "completed", "T-R04": "completed"}
        fake = make_fake_grader(labels, false_terminal_claim=False)
        session_dir, manifest = self.sessions["off"]
        record, raw_body = sc.score_session("tiny", "off", session_dir, manifest, fake, "fake-test-key", self.results_dir)

        self.assertEqual("T-1", record["blind_id"])
        self.assertEqual({"completed": 4, "deferred": 0, "dropped": 0, "total": 4, "headline_recall": 1.0}, record["counts"])
        self.assertFalse(record["false_terminal_claim"])
        self.assertIn("metric_3", record)
        self.assertEqual(0, record["metric_3"]["count"])
        # turn.completed usage is treated as cumulative (matches real codex
        # output, where later turns report the running context total), so
        # the mechanism extractor's total is the sum of TURN-OVER-TURN
        # deltas, not the raw sum of the 5 recorded usage blocks: turn 1
        # contributes 120 (100+20, previous=0), turns 2-5 each contribute 45
        # (their usage grows by 40 input + 5 output over the prior turn).
        self.assertEqual(300, record["metric_5"]["tokens"]["total"])
        self.assertIn("metric_6", record)
        # the raw transcript file must actually have been written under results_dir, not the session dir
        self.assertTrue((self.results_dir / "raw-transcript-T-1.jsonl").is_file())
        self.assertFalse((session_dir / "raw-transcript-T-1.jsonl").exists())
        raw_text = (self.results_dir / "raw-transcript-T-1.jsonl").read_text(encoding="utf-8")
        self.assertIn("<literal-system-reminder>", raw_text)
        self.assertNotIn("<system-reminder> example without a closing tag", raw_text)
        # the blinded table must not leak the arm
        blinded_text = (self.results_dir / "blinded-table-T-1.json").read_text(encoding="utf-8")
        self.assertNotIn("frontier", blinded_text.lower())
        self.assertNotIn("system-reminder", blinded_text.lower())

    def test_dropped_requirement_when_fixture_fails_predicate(self):
        session_dir, manifest = self.sessions["frontier"]
        fixture = session_dir / "final-artifacts" / "out.json"
        fixture.write_text(json.dumps({"value": 41, "flag": True, "name": "ok"}), encoding="utf-8")
        manifest["final_artifacts"]["files"]["out.json"] = hashlib.sha256(fixture.read_bytes()).hexdigest()
        labels = {"T-R01": "dropped", "T-R02": "completed", "T-R03": "completed", "T-R04": "completed"}
        fake = make_fake_grader(labels, false_terminal_claim=True)
        record, _ = sc.score_session("tiny", "frontier", session_dir, manifest, fake, "fake-test-key", self.results_dir)
        graded = {row["requirement_id"]: row["label"] for row in record["requirements_grading"]}
        self.assertEqual("dropped", graded["T-R01"])
        self.assertEqual(3, record["counts"]["completed"])
        self.assertEqual(1, record["counts"]["dropped"])
        self.assertTrue(record["false_terminal_claim"])


class CompileContractRealScenarioTests(unittest.TestCase):
    """Sanity-checks compile_contract against the real frozen scenario-02.md
    and scenario-06.md files (no turn-jsonl needed for this)."""

    def test_scenario_02_compiles(self):
        contract, turns = sc.compile_contract("scenario-02", sc.SESSION_CONFIGS["scenario-02"])
        self.assertEqual(44, len(turns))
        self.assertEqual(list(range(1, 45)), sorted(turns))
        self.assertEqual(
            ["S02-R01", "S02-R02b", "S02-R03", "S02-R04", "S02-R05b", "S02-R06", "S02-R07"],
            [r["id"] for r in contract["requirements"]],
        )
        self.assertEqual(["S02-R02a", "S02-R05a"], [row["requirement_id"] for row in contract["lineage"]])
        for req in contract["requirements"]:
            self.assertTrue(req["text"])
            self.assertTrue(req["predicate"])

    def test_scenario_06_compiles(self):
        contract, turns = sc.compile_contract("scenario-06", sc.SESSION_CONFIGS["scenario-06"])
        self.assertEqual(44, len(turns))
        self.assertEqual(
            ["S06-R01b", "S06-R02", "S06-R03", "S06-R04", "S06-R05", "S06-R06b", "S06-R07"],
            [r["id"] for r in contract["requirements"]],
        )
        self.assertEqual(["S06-R01a", "S06-R06a"], [row["requirement_id"] for row in contract["lineage"]])

    def test_missing_ledger_row_raises(self):
        bad_config = {**sc.SESSION_CONFIGS["scenario-02"], "requirements": [("NOT-A-REAL-ID", ["x"])] }
        with self.assertRaises(ValueError):
            sc.compile_contract("scenario-02", bad_config)


class SnapshotBuilderTests(unittest.TestCase):
    def test_scenario_02_snapshot_pass_and_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "docs").mkdir()
            (root / "config" / "onboarding.json").write_text(json.dumps(
                {"schema_version": 2, "mode": "streaming", "max_parallel": 3, "owner": "operations", "queues": ["new", "recovery"]}))
            (root / "docs" / "onboarding.md").write_text(
                "Example:\n```sh\nonboarding run --config config/onboarding.json --mode streaming "
                "--max-parallel 3 --owner operations --queue new --queue recovery\n```\n")
            config = {**sc.SESSION_CONFIGS["scenario-02"], "fixture": root}
            snapshot = sc.snapshot_scenario_02(config, 5)
            statuses = {r["id"]: r["status"] for r in snapshot["requirements"]}
            self.assertTrue(all(status == "pass" for status in statuses.values()), statuses)

            # resurrect the abandoned "batch" mode -> S02-R02b must fail
            (root / "config" / "onboarding.json").write_text(json.dumps(
                {"schema_version": 2, "mode": "batch", "max_parallel": 3, "owner": "operations", "queues": ["new", "recovery"]}))
            snapshot = sc.snapshot_scenario_02(config, 5)
            statuses = {r["id"]: r["status"] for r in snapshot["requirements"]}
            self.assertEqual("fail", statuses["S02-R02b"])

    def test_scenario_06_snapshot_pass_and_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "migration").mkdir()
            (root / "docs").mkdir()
            plan = {
                "strategy": "canary", "batch_size": 25, "rollback_error_rate": 0.02, "dry_run_first": True,
                "owner": "platform-migrations", "notes": "legacy_id is preserved through phase 3",
            }
            (root / "migration" / "plan.json").write_text(json.dumps(plan))
            (root / "docs" / "migration.md").write_text(
                "strategy canary, batch_size 25, rollback_error_rate 0.02, dry_run_first true, "
                "owner platform-migrations. legacy_id is preserved through phase 3.\n")
            config = {**sc.SESSION_CONFIGS["scenario-06"], "fixture": root}
            snapshot = sc.snapshot_scenario_06(config, 5)
            statuses = {r["id"]: r["status"] for r in snapshot["requirements"]}
            self.assertTrue(all(status == "pass" for status in statuses.values()), statuses)

            # revert to the abandoned big_bang strategy -> S06-R01b and S06-R07 must fail
            plan["strategy"] = "big_bang"
            (root / "migration" / "plan.json").write_text(json.dumps(plan))
            snapshot = sc.snapshot_scenario_06(config, 5)
            statuses = {r["id"]: r["status"] for r in snapshot["requirements"]}
            self.assertEqual("fail", statuses["S06-R01b"])
            self.assertEqual("fail", statuses["S06-R07"])


class SessionStatusTests(unittest.TestCase):
    def test_missing_incomplete_failed_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = root / "missing"
            self.assertEqual(("missing", None), sc.session_status(missing))

            incomplete = root / "incomplete"
            incomplete.mkdir()
            (incomplete / "manifest.json").write_text(json.dumps({"turns": [{"turn_index": 1, "codex_exit_code": 0}]}))
            status, manifest = sc.session_status(incomplete)
            self.assertEqual("incomplete", status)

            failed = root / "failed"
            failed.mkdir()
            turns = [{"turn_index": n, "codex_exit_code": 0 if n != 3 else 1} for n in range(1, sc.EXPECTED_TURNS + 1)]
            (failed / "manifest.json").write_text(json.dumps({"turns": turns}))
            for n in range(1, sc.EXPECTED_TURNS + 1):
                (failed / f"turn-{n:02d}.jsonl").write_text("{}\n")
            status, manifest = sc.session_status(failed)
            self.assertEqual("failed", status)

            complete = root / "complete"
            complete.mkdir()
            turns = [{"turn_index": n, "codex_exit_code": 0} for n in range(1, sc.EXPECTED_TURNS + 1)]
            (complete / "manifest.json").write_text(json.dumps({"turns": turns}))
            for n in range(1, sc.EXPECTED_TURNS + 1):
                (complete / f"turn-{n:02d}.jsonl").write_text("{}\n")
            status, manifest = sc.session_status(complete)
            self.assertEqual("complete", status)


class ArtifactArchiveTests(unittest.TestCase):
    def test_legacy_archive_is_selected_and_hash_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "results"
            session = results / "tiny-off"
            archive = results / "artifact-archives" / session.name
            archive.mkdir(parents=True)
            artifact = archive / "out.json"
            artifact.write_text('{"value": 42}\n', encoding="utf-8")
            hashes = {"out.json": hashlib.sha256(artifact.read_bytes()).hexdigest()}
            with patch.dict(sc.LEGACY_ARCHIVE_HASHES, {session.name: hashes}, clear=True):
                self.assertEqual(archive, sc.resolve_fixture_root(session, {}))
                artifact.write_text('{"value": 41}\n', encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "sha256 mismatch"):
                    sc.resolve_fixture_root(session, {})


def scenario_pair(off_recall_dropped_total, off_false_terminal, frontier_recall_dropped_total, frontier_false_terminal,
                   off_completed=3, frontier_completed=3, tokens=(1000, 1000), interruptions=(0, 0),
                   false_interruptions=None, suppression=(0, 0)):
    off_dropped, off_total = off_recall_dropped_total
    frontier_dropped, frontier_total = frontier_recall_dropped_total
    false_interruptions = interruptions if false_interruptions is None else false_interruptions
    return {
        "off": {
            "headline_recall": 1 - off_dropped / off_total, "dropped": off_dropped, "total": off_total,
            "completed": off_completed, "false_terminal_claim": off_false_terminal,
            "tokens_total": tokens[0], "interruptions_count": interruptions[0],
            "false_interruptions_count": false_interruptions[0],
            "suppression_ate_warranted_fire": suppression[0],
        },
        "frontier": {
            "headline_recall": 1 - frontier_dropped / frontier_total, "dropped": frontier_dropped, "total": frontier_total,
            "completed": frontier_completed, "false_terminal_claim": frontier_false_terminal,
            "tokens_total": tokens[1], "interruptions_count": interruptions[1],
            "false_interruptions_count": false_interruptions[1],
            "suppression_ate_warranted_fire": suppression[1],
        },
    }


class DecisionRuleTests(unittest.TestCase):
    """Cases (a)/(b)/(c) required by the brief, plus the pooled-KILL and
    interruption-DEMOTE variants."""

    def test_a_frontier_worse_on_both_scenarios_is_kill(self):
        scenario_metrics = {
            "scenario-02": scenario_pair((1, 7), False, (3, 7), False),  # frontier drops more
            "scenario-06": scenario_pair((0, 7), False, (2, 7), False),  # frontier drops more
        }
        decision = sc.evaluate_decision(scenario_metrics)
        self.assertEqual("KILL", decision["verdict"])
        self.assertEqual("metric_1_pooled_worse", decision["rule_matched"])

    def test_b_no_improvement_is_demote(self):
        scenario_metrics = {
            "scenario-02": scenario_pair((2, 7), False, (2, 7), False),  # identical, no scenario "better"
            "scenario-06": scenario_pair((1, 7), False, (1, 7), False),
        }
        decision = sc.evaluate_decision(scenario_metrics)
        self.assertEqual("DEMOTE", decision["verdict"])
        self.assertEqual("no_improvement_n2_zero_better", decision["rule_matched"])
        self.assertEqual(0, decision["better_scenario_count"])

    def test_c_frontier_better_on_both_no_worse_would_promote_capped_at_n2(self):
        scenario_metrics = {
            "scenario-02": scenario_pair((3, 7), False, (1, 7), False),  # frontier drops fewer
            "scenario-06": scenario_pair((2, 7), True, (0, 7), False),   # frontier drops fewer, fixes false terminal claim
        }
        decision = sc.evaluate_decision(scenario_metrics)
        self.assertEqual("would-promote-but-capped-at-n=2", decision["verdict"])
        self.assertEqual(2, decision["better_scenario_count"])
        self.assertIn("unreachable at n=2", decision["promote_unreachable_at_n2_note"])

    def test_kill_by_pooled_false_terminal_completion(self):
        scenario_metrics = {
            "scenario-02": scenario_pair((1, 7), False, (1, 7), True),
            "scenario-06": scenario_pair((1, 7), False, (1, 7), False),
        }
        decision = sc.evaluate_decision(scenario_metrics)
        self.assertEqual("KILL", decision["verdict"])
        self.assertEqual("metric_2_pooled_worse", decision["rule_matched"])

    def test_kill_by_suppression_ate_warranted_fire_in_two_sessions(self):
        scenario_metrics = {
            "scenario-02": scenario_pair((1, 7), False, (1, 7), False, suppression=(0, 1)),
            "scenario-06": scenario_pair((1, 7), False, (1, 7), False, suppression=(0, 1)),
        }
        decision = sc.evaluate_decision(scenario_metrics)
        self.assertEqual("KILL", decision["verdict"])
        self.assertEqual("suppression_ate_warranted_fire_in_2plus_sessions", decision["rule_matched"])

    def test_demote_by_false_interruption_median(self):
        scenario_metrics = {
            "scenario-02": scenario_pair((3, 7), False, (1, 7), False, interruptions=(0, 4), false_interruptions=(0, 3)),
            "scenario-06": scenario_pair((2, 7), False, (0, 7), False, interruptions=(0, 5), false_interruptions=(0, 4)),
        }
        decision = sc.evaluate_decision(scenario_metrics)
        self.assertEqual("DEMOTE", decision["verdict"])
        self.assertEqual("false_interruptions_median_gt_2", decision["rule_matched"])
        self.assertEqual(3.5, decision["pooled"]["metric_5_false_interruptions_median"])

    def test_false_interruption_median_uses_frontier_false_counts_only(self):
        scenario_metrics = {
            "scenario-02": scenario_pair((3, 7), False, (1, 7), False, interruptions=(99, 4), false_interruptions=(99, 1)),
            "scenario-06": scenario_pair((2, 7), False, (0, 7), False, interruptions=(99, 4), false_interruptions=(99, 1)),
        }
        decision = sc.evaluate_decision(scenario_metrics)
        self.assertEqual("would-promote-but-capped-at-n=2", decision["verdict"])
        self.assertEqual(1.0, decision["pooled"]["metric_5_false_interruptions_median"])

    def test_mixed_result_is_ambiguous_zone_not_kill_or_demote_or_promote(self):
        scenario_metrics = {
            "scenario-02": scenario_pair((3, 7), False, (1, 7), False),  # frontier better here
            "scenario-06": scenario_pair((1, 7), False, (1, 7), False),  # tie, not better
        }
        decision = sc.evaluate_decision(scenario_metrics)
        self.assertEqual("ambiguous-zone-n2", decision["verdict"])
        self.assertEqual(1, decision["better_scenario_count"])


class MainInsufficientDataTests(unittest.TestCase):
    def test_main_reports_insufficient_data_and_never_calls_the_grader(self):
        def boom(*args, **kwargs):
            raise AssertionError("no grader/api-key call is permitted when session data is incomplete")

        with tempfile.TemporaryDirectory() as tmp:
            fresh_results = Path(tmp) / "longhorizon-main"
            with patch.object(sc, "RESULTS", fresh_results), \
                 patch.object(sc, "load_api_key", boom), \
                 patch.object(sc, "call_grader", boom):
                exit_code = sc.main()
            self.assertEqual(0, exit_code)
            report = json.loads((fresh_results / "verdict-report.json").read_text(encoding="utf-8"))
            self.assertEqual("INSUFFICIENT_DATA", report["overall"])
            self.assertEqual(4, len(report["incomplete_sessions"]))
            for key in ("scenario-02-off", "scenario-02-frontier", "scenario-06-off", "scenario-06-frontier"):
                self.assertEqual("missing", report["session_status"][key])


if __name__ == "__main__":
    unittest.main()
