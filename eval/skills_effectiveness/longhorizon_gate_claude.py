#!/usr/bin/env python3
"""Thin rehearsal-gate runner for a CLAUDE-host long-horizon stratum
(e.g. Fable-5 / Kimi-K3), analogous to ``longhorizon_gate.py`` but consuming
sessions produced by ``longhorizon_run_session_claude.py`` instead of the
codex runner.

Expects ``--stratum-dir`` to contain ``rehearsal-A-frontier/`` and
``rehearsal-B-off/`` session directories (manifest.json + turn-NN.jsonl each),
matching the naming ``longhorizon_gate.SCENARIOS`` already uses for the codex
rehearsal. Converts each session with
``longhorizon_convert_claude_transcript.convert_session_events``, then reuses
``longhorizon_gate``'s imported pieces verbatim: ``compile_contract`` (the
rehearsal-specific 34/35-scripted-turn contract compiler -- reusable as-is
per the scenario markdown being identical between hosts), ``snapshot_a`` /
``snapshot_b``, ``extract_blinded``, ``extract_mechanism``, ``call_grader``,
``cohens_kappa``, ``scrub_secret``, ``load_api_key``, ``checklist_for_grader``,
``validate_grading``, ``dump_json``, ``LEAK_RE``, ``find_session_telemetry``.

Produces ``<stratum-dir>/gate-report.json`` with the same component structure
as the codex gate: ``blinded_extraction_A``/``blinded_extraction_B``,
``grader_kappa``, ``compactions``, ``mechanism_extraction``, ``overall``.

Compactions component here counts manifest ``forced_compactions`` entries
whose mechanism is ``"claude-native-compact"`` (see
``longhorizon_convert_claude_transcript``'s docstring for why claude has no
``filler_byte_size`` equivalent) -- valid iff there are exactly 2 such entries,
with NO ``filler_byte_size`` requirement (unlike the codex gate's
``compactions`` component).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from longhorizon_gate import (
    GRADER_PROMPT,
    LEAK_RE,
    call_grader,
    checklist_for_grader,
    cohens_kappa,
    compile_contract,
    component,
    dump_json,
    find_session_telemetry,
    load_api_key,
    scrub_secret,
    snapshot_a,
    snapshot_b,
    validate_grading,
)
from longhorizon_extract_blinded import canonical_json, extract as extract_blinded, render_tsv
from longhorizon_extract_mechanism import extract as extract_mechanism
from longhorizon_convert_claude_transcript import convert_session_events, write_raw_transcript

HERE = Path(__file__).resolve().parent

SCENARIO_KEYS = {
    "rehearsal-A": {
        "source": HERE / "rehearsal/rehearsal-A.md",
        "session_subdir": "rehearsal-A-frontier",
        "blind_id": "R-1",
        "arm": "FRONTIER",
        "paths": {"catalog": "catalog.json", "doc": "docs/handoff.md"},
        "requirements": [
            ("RA-R01", ["catalog.json"]),
            ("RA-R02b", ["catalog.json", "docs/handoff.md"]),
            ("RA-R03", ["catalog.json"]),
            ("RA-R04", ["docs/handoff.md"]),
            ("RA-R05", ["catalog.json"]),
            ("RA-R06", ["catalog.json", "docs/handoff.md"]),
        ],
        "lineage": [{"requirement_id": "RA-R02a", "status": "superseded", "superseded_by": "RA-R02b"}],
        "decision_states": [
            {
                "key": "owner", "accepted_literals": ["release"], "abandoned_literals": ["ops"],
                "artifact_paths": ["catalog.json", "docs/handoff.md"],
                "abandoned_value_setting_regexes": [r'"owner"\s*:\s*"ops"'], "existed_before_boundary": True,
            },
            {
                "key": "beta_enabled", "accepted_literals": ['"enabled": false'], "abandoned_literals": ['"enabled": true'],
                "artifact_paths": ["catalog.json"],
                "abandoned_value_setting_regexes": [r'"name"\s*:\s*"beta"[\s\S]*?"enabled"\s*:\s*true'],
                "existed_before_boundary": True,
            },
        ],
        "snapshot_builder": snapshot_a,
    },
    "rehearsal-B": {
        "source": HERE / "rehearsal/rehearsal-B.md",
        "session_subdir": "rehearsal-B-off",
        "blind_id": "R-2",
        "arm": "OFF",
        "paths": {"policy": "config/policy.json", "doc": "docs/policy.md"},
        "requirements": [
            ("RB-R01", ["config/policy.json"]),
            ("RB-R02b", ["config/policy.json", "docs/policy.md"]),
            ("RB-R03", ["config/policy.json"]),
            ("RB-R04", ["config/policy.json"]),
            ("RB-R05", ["docs/policy.md"]),
            ("RB-R06", ["config/policy.json", "docs/policy.md"]),
        ],
        "lineage": [{"requirement_id": "RB-R02a", "status": "superseded", "superseded_by": "RB-R02b"}],
        "decision_states": [
            {
                "key": "mode", "accepted_literals": ["audit"], "abandoned_literals": ["strict"],
                "artifact_paths": ["config/policy.json", "docs/policy.md"],
                "abandoned_value_setting_regexes": [r'"mode"\s*:\s*"strict"'], "existed_before_boundary": True,
            },
            {
                "key": "retry_limit", "accepted_literals": ["retry_limit", "5"], "abandoned_literals": ["retry_limit 3"],
                "artifact_paths": ["config/policy.json", "docs/policy.md"],
                "abandoned_value_setting_regexes": [r'"retry_limit"\s*:\s*3'], "existed_before_boundary": True,
            },
        ],
        "snapshot_builder": snapshot_b,
    },
}


def run_gate(stratum_dir: Path, grader_fn=call_grader, api_key_loader=load_api_key) -> dict:
    stratum_dir = stratum_dir.resolve()
    report = {"schema_version": 1, "components": {}}
    contracts: dict[str, dict] = {}
    turns_by_scenario: dict[str, dict[int, str]] = {}
    session_dirs: dict[str, Path] = {}
    blinded_outputs: dict[str, dict] = {}
    extraction_errors: dict[str, str] = {}

    for scenario_id, static_config in SCENARIO_KEYS.items():
        session_dir = stratum_dir / static_config["session_subdir"]
        session_dirs[scenario_id] = session_dir
        try:
            contract, turns = compile_contract(scenario_id, static_config)
            contracts[scenario_id] = contract
            turns_by_scenario[scenario_id] = turns
            dump_json(stratum_dir / f"scenario-contract-{scenario_id}.json", contract, canonical=True)

            manifest = json.loads((session_dir / "manifest.json").read_text(encoding="utf-8"))
            fixture_root = Path(manifest["venue"]) / manifest["fixture_root"]
            config = {**static_config, "fixture": fixture_root}

            events = convert_session_events(session_dir, turns)
            snapshot = static_config["snapshot_builder"](config, len(events))
            events.append(snapshot)
            raw_path = stratum_dir / f"raw-transcript-{static_config['blind_id']}.jsonl"
            write_raw_transcript(events, raw_path)
            dump_json(stratum_dir / f"scenario-end-snapshot-{scenario_id}.json", snapshot, canonical=True)

            first = extract_blinded(raw_path, contract, static_config["blind_id"])
            second = extract_blinded(raw_path, contract, static_config["blind_id"])
            if canonical_json(first) != canonical_json(second):
                raise ValueError("repeated blinded extraction was not byte-identical")
            requirement_ids = [req["id"] for req in contract["requirements"]]
            output_ids = [row.get("requirement_id") for row in first.get("requirements", [])]
            if output_ids != requirement_ids or any(row.get("disposition") not in {"completed", "deferred", "dropped"} for row in first["requirements"]):
                raise ValueError("blinded requirement completeness failed")
            rendered = canonical_json(first)
            if LEAK_RE.search(rendered):
                raise ValueError("blinded output leaked reminder/canary text")
            (stratum_dir / f"blinded-table-{static_config['blind_id']}.json").write_text(rendered, encoding="utf-8")
            (stratum_dir / f"blinded-table-{static_config['blind_id']}.tsv").write_text(render_tsv(first), encoding="utf-8")
            blinded_outputs[scenario_id] = first
            report["components"][f"blinded_extraction_{'A' if scenario_id.endswith('A') else 'B'}"] = component(
                True, blind_id=static_config["blind_id"], requirement_count=len(first["requirements"]),
                counts=first["counts"], deterministic_repeat=True, escaped_defect_checks=first["escaped_defect_checks"],
            )
        except Exception as exc:
            extraction_errors[scenario_id] = f"{type(exc).__name__}: {exc}"
            report["components"][f"blinded_extraction_{'A' if scenario_id.endswith('A') else 'B'}"] = component(False, error=extraction_errors[scenario_id])

    mechanism_details = {}
    mechanism_ok = True
    for scenario_id, static_config in SCENARIO_KEYS.items():
        try:
            contract = contracts[scenario_id]
            raw_path = stratum_dir / f"raw-transcript-{static_config['blind_id']}.jsonl"
            turns = turns_by_scenario[scenario_id]
            config = {**static_config, "arm": static_config["arm"]}
            session_hash, telemetry_rows = find_session_telemetry(config, turns[1])
            result = extract_mechanism(raw_path, contract, static_config["arm"], telemetry_rows, (), session_hash)
            dump_json(stratum_dir / f"mechanism-{static_config['blind_id']}.json", result, canonical=True)
            if not all(key in result for key in ("metric_3", "metric_5", "metric_6")):
                raise ValueError("mechanism metrics incomplete")
            mechanism_details[static_config["blind_id"]] = {
                "status": "PASS", "metric_3_count": result["metric_3"]["count"],
                "token_total": result["metric_5"]["tokens"]["total"],
                "interruption_count": result["metric_5"]["interruptions"]["count"],
                "metric_6": result["metric_6"]["metric_6"],
            }
        except Exception as exc:
            mechanism_ok = False
            mechanism_details[static_config["blind_id"]] = {"status": "FAIL", "error": f"{type(exc).__name__}: {exc}"}
    report["components"]["mechanism_extraction"] = component(mechanism_ok, sessions=mechanism_details)

    compaction_counts = {}
    compactions_ok = True
    for scenario_id, static_config in SCENARIO_KEYS.items():
        session_dir = session_dirs[scenario_id]
        manifest = json.loads((session_dir / "manifest.json").read_text(encoding="utf-8"))
        rows = manifest.get("forced_compactions", [])
        valid = len(rows) == 2 and all(row.get("mechanism") == "claude-native-compact" for row in rows)
        compactions_ok = compactions_ok and valid
        compaction_counts[scenario_id] = {"count": len(rows), "turn_indices": [row.get("turn_index") for row in rows], "valid": valid}
    report["components"]["compactions"] = component(compactions_ok, sessions=compaction_counts)

    grader_ok = len(blinded_outputs) == len(SCENARIO_KEYS)
    kappa_value = None
    grader_error = None
    grader_raw = []
    api_key = ""
    if grader_ok:
        try:
            api_key = api_key_loader()
            system_prompt = GRADER_PROMPT.read_text(encoding="utf-8")
            passes = {1: {}, 2: {}}
            call_errors = []
            for pass_number in (1, 2):
                for scenario_id, static_config in SCENARIO_KEYS.items():
                    contract = contracts[scenario_id]
                    requirement_ids = [req["id"] for req in contract["requirements"]]
                    try:
                        raw_body, parsed = grader_fn(api_key, system_prompt, checklist_for_grader(contract, blinded_outputs[scenario_id]))
                        validated = validate_grading(parsed, requirement_ids)
                        passes[pass_number][scenario_id] = validated
                        grader_raw.append({"blind_id": static_config["blind_id"], "pass": pass_number, "response_body": raw_body, "parsed": validated})
                    except Exception as exc:
                        error = f"{type(exc).__name__}: {exc}"
                        call_errors.append(f"{static_config['blind_id']} pass {pass_number}: {error}")
                        grader_raw.append({"blind_id": static_config["blind_id"], "pass": pass_number, "error": error})
            if call_errors:
                raise RuntimeError("; ".join(call_errors))
            labels = {
                pass_number: [row["label"] for scenario_id in SCENARIO_KEYS for row in passes[pass_number][scenario_id]["requirements"]]
                for pass_number in (1, 2)
            }
            kappa_value = cohens_kappa(labels[1], labels[2])
            grader_ok = kappa_value >= 0.7
        except Exception as exc:
            grader_ok = False
            grader_error = f"{type(exc).__name__}: {exc}"
            if not grader_raw:
                grader_raw.append({"error": grader_error})
    else:
        grader_error = "blinded extraction incomplete"
        grader_raw.append({"error": grader_error})

    raw_path = stratum_dir / "grader-raw-responses.json"
    dump_json(raw_path, scrub_secret(grader_raw, api_key) if api_key else grader_raw)
    grader_component = component(grader_ok, kappa=kappa_value, threshold=0.7, pooled_requirement_labels=12 if kappa_value is not None else 0, raw_response_file=str(raw_path))
    if grader_error:
        grader_component["error"] = grader_error
    report["components"]["grader_kappa"] = grader_component

    report["overall"] = "PASS" if all(value.get("status") == "PASS" for value in report["components"].values()) else "FAIL"
    report_path = stratum_dir / "gate-report.json"
    dump_json(report_path, report)
    if api_key and api_key in raw_path.read_text(encoding="utf-8"):
        raise RuntimeError("API key leaked into grader raw-response file")
    json.loads(report_path.read_text(encoding="utf-8"))
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stratum-dir", required=True, type=Path)
    args = parser.parse_args()
    args.stratum_dir.mkdir(parents=True, exist_ok=True)
    report = run_gate(args.stratum_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
