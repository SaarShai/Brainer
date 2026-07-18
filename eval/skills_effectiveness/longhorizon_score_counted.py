#!/usr/bin/env python3
"""Score the counted GPT-stratum long-horizon sessions into a FRONTIER-vs-OFF
verdict, per the n=2 owner-directed condensation amendment
(longhorizon_preregistration_draft.md, "Budget & authorization", 2026-07-18).

This is the COUNTED analogue of longhorizon_gate.py (the REHEARSAL gate).  It
reuses the rehearsal gate's generic building blocks (compile_contract shape,
make_snapshot, forbidden_matches, completed_item_event, normalize_usage,
extract_blinded/extract_mechanism, call_grader, load_api_key, cohens_kappa,
validate_grading, checklist_for_grader, scrub_secret) instead of
re-implementing them.

Two pieces of longhorizon_gate.py could not be imported verbatim because they
hard-code rehearsal-specific assumptions:

- ``compile_contract`` hard-codes ``34 if scenario_id == "rehearsal-A" else
  35`` expected scripted turns, and only validates the first lineage row.
  Scenario-02 and scenario-06 both script T01-T44 (44 turns) and both have
  TWO superseded lineage rows. ``compile_contract`` below mirrors the
  rehearsal function's logic (built from the same imported
  ``parse_scenario_md``) with those two assumptions generalized.
- ``build_raw_transcript`` closes over the module-level rehearsal ``RESULTS``
  directory as its write target, so calling it verbatim would write counted
  raw transcripts into the rehearsal results tree. ``build_raw_transcript``
  below is the same event-normalization loop (reusing the imported
  ``completed_item_event`` and ``normalize_usage`` primitives verbatim) with
  the output directory taken as a parameter instead.

Discovers the 4 counted session directories under
eval/results/skills-effectiveness/longhorizon-main/<scenario>-<arm>/, scores
each that is complete (44/44 turns, all turn files present, all turns exit
0), and writes verdict-report.json next to them. If fewer than 4 sessions are
complete, no grader call is made and an INSUFFICIENT_DATA report is written
instead -- this script never spends grader budget against partial data.
"""
from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path

from longhorizon_gate import (
    GRADER_PROMPT,
    LEAK_RE,
    checklist_for_grader,
    call_grader,
    completed_item_event,
    dump_json,
    find_session_telemetry,
    forbidden_matches,
    load_api_key,
    make_snapshot,
    normalize_usage,
    parse_scenario_md,
    scrub_secret,
    sha256,
    type_name,
    validate_grading,
)
from longhorizon_extract_blinded import (
    ExtractionError as BlindedExtractionError,
    _reminders,
    canonical_json,
    extract as extract_blinded,
    render_tsv,
)
from longhorizon_extract_mechanism import extract as extract_mechanism


HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
RESULTS = REPO / "eval/results/skills-effectiveness/longhorizon-main"
SCENARIOS_DIR = HERE / "scenarios"
EXPECTED_TURNS = 44

PHASE3_RE = re.compile(r"preserv(?:ed|e)\s+through\s+phase\s*3", re.I)

SESSION_CONFIGS = {
    "scenario-02": {
        "source": SCENARIOS_DIR / "scenario-02.md",
        "paths": {"config": "config/onboarding.json", "doc": "docs/onboarding.md"},
        "requirements": [
            ("S02-R01", ["config/onboarding.json"]),
            ("S02-R02b", ["config/onboarding.json", "docs/onboarding.md"]),
            ("S02-R03", ["config/onboarding.json"]),
            ("S02-R04", ["config/onboarding.json"]),
            ("S02-R05b", ["config/onboarding.json"]),
            ("S02-R06", ["config/onboarding.json", "docs/onboarding.md"]),
            ("S02-R07", ["config/onboarding.json", "docs/onboarding.md"]),
        ],
        "lineage": [
            {"requirement_id": "S02-R02a", "status": "superseded", "superseded_by": "S02-R02b"},
            {"requirement_id": "S02-R05a", "status": "superseded", "superseded_by": "S02-R05b"},
        ],
        "decision_states": [
            {
                "key": "mode",
                "accepted_literals": ["streaming"],
                "abandoned_literals": ["batch"],
                "artifact_paths": ["config/onboarding.json", "docs/onboarding.md"],
                "abandoned_value_setting_regexes": [r'"mode"\s*:\s*"batch"'],
                "existed_before_boundary": True,
            },
        ],
    },
    "scenario-06": {
        "source": SCENARIOS_DIR / "scenario-06.md",
        "paths": {"plan": "migration/plan.json", "doc": "docs/migration.md"},
        "requirements": [
            ("S06-R01b", ["migration/plan.json", "docs/migration.md"]),
            ("S06-R02", ["migration/plan.json", "docs/migration.md"]),
            ("S06-R03", ["migration/plan.json", "docs/migration.md"]),
            ("S06-R04", ["migration/plan.json", "docs/migration.md"]),
            ("S06-R05", ["migration/plan.json", "docs/migration.md"]),
            ("S06-R06b", ["migration/plan.json", "docs/migration.md"]),
            ("S06-R07", ["migration/plan.json", "docs/migration.md"]),
        ],
        "lineage": [
            {"requirement_id": "S06-R01a", "status": "superseded", "superseded_by": "S06-R01b"},
            {"requirement_id": "S06-R06a", "status": "superseded", "superseded_by": "S06-R06b"},
        ],
        "decision_states": [
            {
                "key": "strategy",
                "accepted_literals": ["canary"],
                "abandoned_literals": ["big_bang", "big-bang"],
                "artifact_paths": ["migration/plan.json", "docs/migration.md"],
                "abandoned_value_setting_regexes": [r'"strategy"\s*:\s*"big_bang"'],
                "existed_before_boundary": True,
            },
        ],
    },
}

BLIND_ID_BY_KEY = {
    ("scenario-02", "off"): "M-1",
    ("scenario-02", "frontier"): "M-2",
    ("scenario-06", "off"): "M-3",
    ("scenario-06", "frontier"): "M-4",
}

LEGACY_ARCHIVE_HASHES = {
    "scenario-02-off": {
        "config/onboarding.json": "e6e07cdc6ca6e4e5f5593d27f10ac65b22a7393048e14da562bcabb7bf8ad642",
        "docs/onboarding.md": "500fbc83ba1d83e54be4db08233cb3897121ee799d319acacae577c905dac8af",
    },
    "scenario-02-frontier": {
        "config/onboarding.json": "54e216cc5c912823ceccbb7804a756bdb290c9db7baea7977d7525789a8ff2ea",
        "docs/onboarding.md": "3ee3f0b2ecaba044494678adce34605641d732e99038d9d6450abd24ba0b0e8d",
    },
    "scenario-06-off": {
        "docs/migration.md": "814c929b9adb99cc1ec6d41f801a995a8a3f1f3beb7a3058c858cb5b2ba3905b",
        "migration/plan.json": "8bf594bcf0ae2c8da5ad52d242d6be9c09e8362c8aa195632f5abc0445b09b14",
    },
    "scenario-06-frontier": {
        "docs/migration.md": "c8afe255a37a17eccf14d13c25172ee0956a993fcbbe799929a6c2a0b5137846",
        "migration/plan.json": "8bf594bcf0ae2c8da5ad52d242d6be9c09e8362c8aa195632f5abc0445b09b14",
    },
}


def compile_contract(scenario_id: str, config: dict) -> tuple[dict, dict[int, str]]:
    """Counted analogue of longhorizon_gate.compile_contract: same shape,
    scripted-turn count fixed at 44 (T01-T44, per scenario-02.md/scenario-06.md
    run-control contracts) instead of the rehearsal-specific 34/35 ternary,
    and every lineage row (not just the first) is validated present."""
    turns, ledger, predicates = parse_scenario_md(config["source"])
    if sorted(turns) != list(range(1, EXPECTED_TURNS + 1)):
        raise ValueError(f"{scenario_id}: scripted turn parse incomplete")
    requirements = []
    for requirement_id, artifact_paths in config["requirements"]:
        if requirement_id not in ledger or requirement_id not in predicates:
            raise ValueError(f"{scenario_id}: missing ledger/predicate for {requirement_id}")
        requirements.append({
            "id": requirement_id,
            "text": ledger[requirement_id],
            "predicate": predicates[requirement_id],
            "artifact_paths": artifact_paths,
        })
    for lineage_row in config["lineage"]:
        if lineage_row["requirement_id"] not in ledger:
            raise ValueError(f"{scenario_id}: missing superseded predecessor {lineage_row['requirement_id']}")
    return {
        "scenario_id": scenario_id,
        "requirements": requirements,
        "lineage": config["lineage"],
        "decision_states": config["decision_states"],
    }, turns


def _median(values: list[float]) -> float:
    # A sibling module in this directory is also named "statistics.py"
    # (dependency-free preregistered paired stats), which shadows the
    # stdlib "statistics" module whenever this directory is first on
    # sys.path (true for both direct script execution and these tests) --
    # so a bare `import statistics` silently resolves to the wrong module.
    # Inline median avoids the collision.
    ordered = sorted(values)
    count = len(ordered)
    if count == 0:
        return 0.0
    midpoint = count // 2
    if count % 2:
        return float(ordered[midpoint])
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0


def _extract_example_block(doc_text: str) -> str:
    fenced = re.search(r"```[^\n]*\n(.*?)```", doc_text, re.S)
    if fenced:
        return fenced.group(1)
    return doc_text


def _option_values(tokens: list[str], option: str) -> list[str]:
    values = []
    for index, token in enumerate(tokens):
        if token == option and index + 1 < len(tokens):
            values.append(tokens[index + 1])
        elif token.startswith(option + "="):
            values.append(token[len(option) + 1:])
    return values


def _example_matches_onboarding(example_block: str, onboarding: dict) -> tuple[bool, dict]:
    try:
        tokens = shlex.split(example_block)
    except ValueError as exc:
        return False, {"parse_error": str(exc), "example_block_excerpt": example_block[:400]}
    observed = {
        "config": _option_values(tokens, "--config"),
        "mode": _option_values(tokens, "--mode"),
        "max_parallel": _option_values(tokens, "--max-parallel"),
        "owner": _option_values(tokens, "--owner"),
        "queues": _option_values(tokens, "--queue"),
    }
    expected = {
        "config": ["config/onboarding.json"],
        "mode": [str(onboarding.get("mode"))],
        "max_parallel": [str(onboarding.get("max_parallel"))],
        "owner": [str(onboarding.get("owner"))],
        "queues": [str(value) for value in onboarding.get("queues", [])]
        if isinstance(onboarding.get("queues"), list) else [],
    }
    return observed == expected, {
        "observed_options": observed,
        "expected_options": expected,
        "schema_version_via_config": onboarding.get("schema_version"),
    }


def _neutralize_malformed_reminder_literals(value):
    if isinstance(value, str):
        try:
            _reminders(value)
        except BlindedExtractionError as exc:
            if exc.code != "BLINDING_MALFORMED_SYSTEM_REMINDER":
                raise
            return value.replace("<system-reminder", "<literal-system-reminder").replace(
                "</system-reminder>", "</literal-system-reminder>")
        return value
    if isinstance(value, list):
        return [_neutralize_malformed_reminder_literals(item) for item in value]
    if isinstance(value, dict):
        return {key: _neutralize_malformed_reminder_literals(item) for key, item in value.items()}
    return value


def snapshot_scenario_02(config: dict, captured_after: int) -> dict:
    root = config["fixture"]
    config_path = root / config["paths"]["config"]
    doc_path = root / config["paths"]["doc"]
    config_text = config_path.read_text(encoding="utf-8")
    doc_text = doc_path.read_text(encoding="utf-8")
    onboarding = json.loads(config_text)
    texts = {"config/onboarding.json": config_text, "docs/onboarding.md": doc_text}
    batch_matches = forbidden_matches(texts, ["batch"], include_iso=False)
    forbidden = forbidden_matches(texts, ["generated_at", "timestamp"])
    queues = onboarding.get("queues")
    example_block = _extract_example_block(doc_text)
    example_consistent, example_observed = _example_matches_onboarding(example_block, onboarding)
    checks = [
        ("S02-R01", isinstance(onboarding.get("schema_version"), int) and not isinstance(onboarding.get("schema_version"), bool) and onboarding.get("schema_version") == 2,
         {"type": type_name(onboarding.get("schema_version")), "value": onboarding.get("schema_version")}),
        ("S02-R02b", onboarding.get("mode") == "streaming" and not batch_matches,
         {"mode": onboarding.get("mode"), "mode_type": type_name(onboarding.get("mode")), "batch_matches": batch_matches}),
        ("S02-R03", isinstance(onboarding.get("max_parallel"), int) and not isinstance(onboarding.get("max_parallel"), bool) and onboarding.get("max_parallel") == 3,
         {"type": type_name(onboarding.get("max_parallel")), "value": onboarding.get("max_parallel")}),
        ("S02-R04", onboarding.get("owner") == "operations",
         {"owner": onboarding.get("owner"), "owner_type": type_name(onboarding.get("owner"))}),
        ("S02-R05b", queues == ["new", "recovery"],
         {"type": type_name(queues), "value": queues}),
        ("S02-R06", example_consistent,
         example_observed),
        ("S02-R07", not forbidden,
         {"matches": forbidden}),
    ]
    return make_snapshot("scenario-02", config, captured_after, checks, [
        {"id": "unexpected-artifact", "expected_paths": sorted(texts)},
    ])


def snapshot_scenario_06(config: dict, captured_after: int) -> dict:
    root = config["fixture"]
    plan_path = root / config["paths"]["plan"]
    doc_path = root / config["paths"]["doc"]
    plan_text = plan_path.read_text(encoding="utf-8")
    doc_text = doc_path.read_text(encoding="utf-8")
    plan = json.loads(plan_text)
    texts = {"migration/plan.json": plan_text, "docs/migration.md": doc_text}
    strategy_matches = forbidden_matches(texts, ["big_bang", "big-bang", "big bang"], include_iso=False)
    legacy_present = {path: "legacy_id" in text for path, text in texts.items()}
    phase3_present = {path: bool(PHASE3_RE.search(text)) for path, text in texts.items()}
    legacy_ok = all(legacy_present.values()) and all(phase3_present.values())
    strategy = plan.get("strategy")
    strategy_ok = strategy == "canary" and not strategy_matches and bool(re.search(r"\bcanary\b", doc_text, re.I))
    batch_size = plan.get("batch_size")
    batch_ok = isinstance(batch_size, int) and not isinstance(batch_size, bool) and batch_size == 25 and bool(re.search(r"\b25\b", doc_text))
    rollback = plan.get("rollback_error_rate")
    rollback_ok = isinstance(rollback, (int, float)) and not isinstance(rollback, bool) and rollback == 0.02 and bool(re.search(r"0\.02", doc_text))
    dry_run = plan.get("dry_run_first")
    dry_run_ok = dry_run is True and bool(re.search(r"\btrue\b", doc_text, re.I))
    owner = plan.get("owner")
    owner_ok = owner == "platform-migrations" and bool(re.search(r"platform-migrations", doc_text, re.I))
    checks = [
        ("S06-R01b", strategy_ok, {"strategy": strategy, "strategy_type": type_name(strategy), "abandoned_matches": strategy_matches}),
        ("S06-R02", batch_ok, {"type": type_name(batch_size), "value": batch_size}),
        ("S06-R03", rollback_ok, {"type": type_name(rollback), "value": rollback}),
        ("S06-R04", legacy_ok, {"legacy_id_present": legacy_present, "phase3_phrase_present": phase3_present}),
        ("S06-R05", dry_run_ok, {"type": type_name(dry_run), "value": dry_run}),
        ("S06-R06b", owner_ok, {"owner": owner, "owner_type": type_name(owner)}),
        ("S06-R07", bool(strategy_ok and batch_ok and rollback_ok and dry_run_ok and owner_ok and legacy_ok),
         {"all_decisions_consistent": bool(strategy_ok and batch_ok and rollback_ok and dry_run_ok and owner_ok and legacy_ok)}),
    ]
    return make_snapshot("scenario-06", config, captured_after, checks, [
        {"id": "unexpected-artifact", "expected_paths": sorted(texts)},
    ])


SNAPSHOT_BUILDERS = {
    "scenario-02": snapshot_scenario_02,
    "scenario-06": snapshot_scenario_06,
}


def build_raw_transcript(config: dict, turns: dict[int, str], snapshot_builder, results_dir: Path) -> tuple[Path, dict]:
    """Counted analogue of longhorizon_gate.build_raw_transcript: identical
    event-normalization loop (reusing completed_item_event/normalize_usage
    verbatim), parameterized on results_dir instead of closing over the
    rehearsal RESULTS constant."""
    manifest = json.loads((config["source_dir"] / "manifest.json").read_text(encoding="utf-8"))
    compactions = {row["turn_index"]: row for row in manifest.get("forced_compactions", [])}
    events: list[dict] = []
    previous_usage: dict[str, int] = {}
    for turn_number in sorted(turns):
        if turn_number in compactions:
            row = compactions[turn_number]
            events.append({"type": "context_pressure_equivalent", "host_event_id": f"compaction-turn-{turn_number}", "turn_index": turn_number, "filler_byte_size": row.get("filler_byte_size")})
        else:
            events.append({"type": "user", "message": {"role": "user", "content": turns[turn_number]}})
        turn_file = config["source_dir"] / f"turn-{turn_number:02d}.jsonl"
        last_assistant = None
        for line_number, line in enumerate(turn_file.read_text(encoding="utf-8").splitlines(), 1):
            source = _neutralize_malformed_reminder_literals(json.loads(line))
            if not isinstance(source, dict):
                raise ValueError(f"non-object source event: {turn_file}:{line_number}")
            events.append(source)
            item = source.get("item")
            if source.get("type") == "item.completed" and isinstance(item, dict):
                normalized = completed_item_event(item, turn_number)
                if normalized is not None:
                    events.append(normalized)
                    if normalized.get("type") == "assistant":
                        last_assistant = normalized
            if source.get("type") == "turn.completed" and isinstance(source.get("usage"), dict):
                usage, previous_usage = normalize_usage(source["usage"], previous_usage)
                if last_assistant is None:
                    raise ValueError(f"turn {turn_number} has usage but no assistant message")
                last_assistant["usage"] = usage
    snapshot = snapshot_builder(config, len(events))
    events.append(snapshot)
    raw_path = results_dir / f"raw-transcript-{config['blind_id']}.jsonl"
    raw_path.write_text("".join(json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for event in events), encoding="utf-8")
    return raw_path, snapshot


def session_status(session_dir: Path) -> tuple[str, dict | None]:
    manifest_path = session_dir / "manifest.json"
    if not manifest_path.is_file():
        return "missing", None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    turn_records = manifest.get("turns", [])
    if len(turn_records) < EXPECTED_TURNS:
        return "incomplete", manifest
    if any(record.get("codex_exit_code") != 0 for record in turn_records):
        return "failed", manifest
    for turn_number in range(1, EXPECTED_TURNS + 1):
        if not (session_dir / f"turn-{turn_number:02d}.jsonl").is_file():
            return "incomplete", manifest
    return "complete", manifest


def _verify_archive(root: Path, expected_files: dict[str, str]) -> None:
    if not root.is_dir():
        raise ValueError(f"final artifact archive is missing: {root}")
    actual_paths = sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())
    if actual_paths != sorted(expected_files):
        raise ValueError(f"final artifact archive inventory mismatch: {root}")
    mismatches = [path for path, expected in expected_files.items() if sha256(root / path) != expected]
    if mismatches:
        raise ValueError(f"final artifact archive sha256 mismatch: {root}: {mismatches}")


def resolve_fixture_root(session_dir: Path, manifest: dict) -> Path:
    final_artifacts = manifest.get("final_artifacts")
    if final_artifacts is not None:
        if not isinstance(final_artifacts, dict) or final_artifacts.get("fixture_present") is not True:
            raise ValueError(f"{session_dir.name}: final artifacts were not preserved")
        archive_rel = Path(final_artifacts.get("archive_dir", ""))
        if archive_rel.is_absolute() or ".." in archive_rel.parts:
            raise ValueError(f"{session_dir.name}: invalid final artifact archive path")
        expected_files = final_artifacts.get("files")
        if not isinstance(expected_files, dict) or not all(isinstance(path, str) and isinstance(digest, str) for path, digest in expected_files.items()):
            raise ValueError(f"{session_dir.name}: invalid final artifact hash manifest")
        root = session_dir / archive_rel
        _verify_archive(root, expected_files)
        return root

    root = session_dir.parent / "artifact-archives" / session_dir.name
    expected_files = LEGACY_ARCHIVE_HASHES.get(session_dir.name)
    if expected_files is None:
        raise ValueError(f"{session_dir.name}: legacy final artifact hashes are not registered")
    _verify_archive(root, expected_files)
    return root


def score_session(scenario_id: str, arm: str, session_dir: Path, manifest: dict,
                   grader_fn, api_key: str, results_dir: Path) -> tuple[dict, str]:
    """Compile the contract, assemble the raw transcript, run blinded +
    mechanism extraction, and grade one counted session. Returns
    (session_record, raw_grader_response_body)."""
    static_config = SESSION_CONFIGS[scenario_id]
    blind_id = BLIND_ID_BY_KEY[(scenario_id, arm)]
    arm_upper = "FRONTIER" if arm == "frontier" else "OFF"
    fixture_root = resolve_fixture_root(session_dir, manifest)
    config = {**static_config, "source_dir": session_dir, "blind_id": blind_id, "arm": arm_upper, "fixture": fixture_root}

    contract, turns = compile_contract(scenario_id, config)
    dump_json(results_dir / f"scenario-contract-{scenario_id}.json", contract, canonical=True)

    snapshot_builder = SNAPSHOT_BUILDERS[scenario_id]
    raw_path, snapshot = build_raw_transcript(config, turns, snapshot_builder, results_dir)
    dump_json(results_dir / f"scenario-end-snapshot-{blind_id}.json", snapshot, canonical=True)

    first = extract_blinded(raw_path, contract, blind_id)
    second = extract_blinded(raw_path, contract, blind_id)
    if canonical_json(first) != canonical_json(second):
        raise ValueError(f"{blind_id}: repeated blinded extraction was not byte-identical")
    requirement_ids = [req["id"] for req in contract["requirements"]]
    output_ids = [row.get("requirement_id") for row in first.get("requirements", [])]
    if output_ids != requirement_ids:
        raise ValueError(f"{blind_id}: blinded requirement completeness failed")
    rendered = canonical_json(first)
    if LEAK_RE.search(rendered):
        raise ValueError(f"{blind_id}: blinded output leaked reminder/canary text")
    (results_dir / f"blinded-table-{blind_id}.json").write_text(rendered, encoding="utf-8")
    (results_dir / f"blinded-table-{blind_id}.tsv").write_text(render_tsv(first), encoding="utf-8")

    session_hash, telemetry_rows = find_session_telemetry(config, turns[1])
    mechanism = extract_mechanism(raw_path, contract, arm_upper, telemetry_rows, (), session_hash)
    dump_json(results_dir / f"mechanism-{blind_id}.json", mechanism, canonical=True)

    raw_body, parsed = grader_fn(api_key, GRADER_PROMPT.read_text(encoding="utf-8"), checklist_for_grader(contract, first))
    validated = validate_grading(parsed, requirement_ids)

    record = {
        "scenario_id": scenario_id,
        "arm": arm,
        "blind_id": blind_id,
        "counts": first["counts"],
        "requirements_grading": validated["requirements"],
        "false_terminal_claim": validated["false_terminal_claim"],
        "metric_3": mechanism["metric_3"],
        "metric_5": mechanism["metric_5"],
        "metric_6": mechanism["metric_6"],
        "escaped_defect_checks": first["escaped_defect_checks"],
    }
    return record, raw_body


def session_metrics(record: dict) -> dict:
    counts = record["counts"]
    return {
        "headline_recall": counts["headline_recall"],
        "dropped": counts["dropped"],
        "total": counts["total"],
        "completed": counts["completed"],
        "false_terminal_claim": record["false_terminal_claim"],
        "tokens_total": record["metric_5"]["tokens"]["total"],
        "interruptions_count": record["metric_5"]["interruptions"]["count"],
        "false_interruptions_count": record["metric_5"]["interruptions"]["false_interruption_count"],
        "suppression_ate_warranted_fire": record["metric_6"]["metric_6"],
    }


PROMOTE_UNREACHABLE_NOTE = (
    "PROMOTE-PROVISIONAL requires FRONTIER to improve metric 1 or 2 in >=2/3 of "
    "scenarios with no scenario materially worse under the full n=6 design; at "
    "n=2 (owner-directed 2026-07-18 condensation, 'Budget & authorization') that "
    "fraction threshold collapses to 'both scenarios better' (>=2/3 -> BOTH; "
    "<=1/3 -> zero), but PROMOTE-PROVISIONAL itself is explicitly unreachable at "
    "n=2 -- 'it can surface a strong directional signal or a clean null but "
    "cannot deliver even a PROMOTE-PROVISIONAL'. A passing signal here is "
    "reported as verdict 'would-promote-but-capped-at-n=2' and requires the "
    "fuller scenario set under new owner authorization to become even "
    "PROMOTE-PROVISIONAL. KILL/DEMOTE conjuncts that trigger on n=2 remain "
    "binding."
)


def evaluate_decision(scenario_metrics: dict) -> dict:
    """Pure decision-rule engine over already-computed per-scenario/per-arm
    metrics (see session_metrics). Implements the preregistered KILL/DEMOTE/
    PROMOTE-PROVISIONAL rules (longhorizon_preregistration_draft.md,
    "Preregistered decision rules") under the n=2 collapse amendment."""
    scenario_ids = sorted(scenario_metrics)
    per_scenario = {}
    pooled_dropped = {"off": 0, "frontier": 0}
    pooled_total = {"off": 0, "frontier": 0}
    pooled_false_terminal = {"off": 0, "frontier": 0}
    token_totals = {"off": 0, "frontier": 0}
    frontier_false_interruption_counts: list[int] = []
    suppression_hit_sessions = 0

    for scenario_id in scenario_ids:
        off = scenario_metrics[scenario_id]["off"]
        frontier = scenario_metrics[scenario_id]["frontier"]
        for arm, metrics in (("off", off), ("frontier", frontier)):
            pooled_dropped[arm] += metrics["dropped"]
            pooled_total[arm] += metrics["total"]
            pooled_false_terminal[arm] += int(metrics["false_terminal_claim"])
            token_totals[arm] += metrics["tokens_total"]
            if arm == "frontier":
                frontier_false_interruption_counts.append(metrics["false_interruptions_count"])
            if metrics.get("suppression_ate_warranted_fire", 0) > 0:
                suppression_hit_sessions += 1
        recall_delta = frontier["headline_recall"] - off["headline_recall"]
        false_terminal_delta = int(frontier["false_terminal_claim"]) - int(off["false_terminal_claim"])
        dropped_delta = frontier["dropped"] - off["dropped"]
        materially_worse = dropped_delta >= 2 or false_terminal_delta >= 1
        better = recall_delta > 0 or false_terminal_delta < 0
        completed_not_lower = frontier["completed"] >= off["completed"]
        per_scenario[scenario_id] = {
            "recall_off": off["headline_recall"], "recall_frontier": frontier["headline_recall"],
            "false_terminal_off": off["false_terminal_claim"], "false_terminal_frontier": frontier["false_terminal_claim"],
            "dropped_delta": dropped_delta, "materially_worse": materially_worse,
            "better": better, "completed_not_lower": completed_not_lower,
        }

    pooled_recall_off = 1 - pooled_dropped["off"] / pooled_total["off"] if pooled_total["off"] else None
    pooled_recall_frontier = 1 - pooled_dropped["frontier"] / pooled_total["frontier"] if pooled_total["frontier"] else None
    kill_metric1 = pooled_recall_off is not None and pooled_recall_frontier is not None and pooled_recall_frontier < pooled_recall_off
    kill_metric2 = pooled_false_terminal["frontier"] > pooled_false_terminal["off"]
    kill_suppression = suppression_hit_sessions >= 2
    killed = kill_metric1 or kill_metric2 or kill_suppression

    n = len(scenario_ids)
    better_count = sum(1 for row in per_scenario.values() if row["better"])
    zero_better = better_count == 0          # n=2 collapse of "<=1/3 better"
    all_better = n > 0 and better_count == n  # n=2 collapse of ">=2/3 better"
    median_false_interruptions = _median(frontier_false_interruption_counts)
    demote_no_improvement = zero_better
    demote_interruptions = median_false_interruptions > 2
    demoted = (not killed) and (demote_no_improvement or demote_interruptions)

    token_overhead_pct = ((token_totals["frontier"] / token_totals["off"]) - 1) * 100 if token_totals["off"] else None
    no_materially_worse = not any(row["materially_worse"] for row in per_scenario.values())
    completed_not_lower_all = all(row["completed_not_lower"] for row in per_scenario.values())
    would_promote_conditions = (
        not killed and not demoted and all_better and no_materially_worse and
        completed_not_lower_all and median_false_interruptions <= 1 and
        (token_overhead_pct is not None and token_overhead_pct <= 3)
    )

    if killed:
        verdict = "KILL"
        rule = "metric_1_pooled_worse" if kill_metric1 else ("metric_2_pooled_worse" if kill_metric2 else "suppression_ate_warranted_fire_in_2plus_sessions")
    elif demoted:
        verdict = "DEMOTE"
        rule = "no_improvement_n2_zero_better" if demote_no_improvement else "false_interruptions_median_gt_2"
    elif would_promote_conditions:
        verdict = "would-promote-but-capped-at-n=2"
        rule = "both_scenarios_better_n2_collapsed_2of3_threshold"
    else:
        verdict = "ambiguous-zone-n2"
        rule = "neither_kill_demote_nor_would_promote"

    return {
        "verdict": verdict,
        "rule_matched": rule,
        "per_scenario": per_scenario,
        "pooled": {
            "metric_1_headline_recall": {"off": pooled_recall_off, "frontier": pooled_recall_frontier, "frontier_worse": kill_metric1},
            "metric_2_false_terminal_completion": {"off_count": pooled_false_terminal["off"], "frontier_count": pooled_false_terminal["frontier"], "frontier_worse": kill_metric2},
            "metric_5_tokens_total": token_totals,
            "metric_5_token_overhead_pct": token_overhead_pct,
            "metric_5_false_interruptions_median": median_false_interruptions,
            "metric_6_suppression_ate_warranted_fire_sessions": suppression_hit_sessions,
        },
        "better_scenario_count": better_count,
        "scenario_count": n,
        "promote_unreachable_at_n2_note": PROMOTE_UNREACHABLE_NOTE,
    }


def main() -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    statuses: dict[tuple[str, str], str] = {}
    manifests: dict[tuple[str, str], dict | None] = {}
    for scenario_id in SESSION_CONFIGS:
        for arm in ("off", "frontier"):
            session_dir = RESULTS / f"{scenario_id}-{arm}"
            status, manifest = session_status(session_dir)
            statuses[(scenario_id, arm)] = status
            manifests[(scenario_id, arm)] = manifest

    incomplete = {f"{s}-{a}": status for (s, a), status in statuses.items() if status != "complete"}
    if incomplete:
        report = {
            "schema_version": 1,
            "overall": "INSUFFICIENT_DATA",
            "session_status": {f"{s}-{a}": status for (s, a), status in statuses.items()},
            "incomplete_sessions": incomplete,
            "note": (
                "Fewer than 4 counted session directories are complete "
                f"(need {EXPECTED_TURNS}/{EXPECTED_TURNS} turns, exit 0, in each of "
                "scenario-02-off/scenario-02-frontier/scenario-06-off/scenario-06-frontier "
                "under longhorizon-main/); no grader call was made and no verdict "
                "was computed. Decision-rule logic is unit-tested against a "
                "synthetic fixture in test_longhorizon_score_counted.py."
            ),
        }
        report_path = RESULTS / "verdict-report.json"
        dump_json(report_path, report)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    api_key = load_api_key()
    records: dict[tuple[str, str], dict] = {}
    grader_raw = []
    for key, manifest in manifests.items():
        scenario_id, arm = key
        session_dir = RESULTS / f"{scenario_id}-{arm}"
        record, raw_body = score_session(scenario_id, arm, session_dir, manifest, call_grader, api_key, RESULTS)
        records[key] = record
        grader_raw.append({"blind_id": record["blind_id"], "scenario_id": scenario_id, "arm": arm, "response_body": raw_body})

    scenario_metrics = {
        scenario_id: {arm: session_metrics(records[(scenario_id, arm)]) for arm in ("off", "frontier")}
        for scenario_id in SESSION_CONFIGS
    }
    decision = evaluate_decision(scenario_metrics)

    raw_path = RESULTS / "verdict-grader-raw-responses.json"
    dump_json(raw_path, scrub_secret(grader_raw, api_key))
    if api_key in raw_path.read_text(encoding="utf-8"):
        raise RuntimeError("API key leaked into grader raw-response file")

    report = {
        "schema_version": 1,
        "overall": "SCORED",
        "sessions": {
            f"{scenario_id}-{arm}": {
                "blind_id": record["blind_id"],
                "counts": record["counts"],
                "false_terminal_claim": record["false_terminal_claim"],
                "metric_3_post_compaction_contradiction": record["metric_3"],
                "metric_5": record["metric_5"],
                "metric_6": record["metric_6"],
                "escaped_defect_checks": record["escaped_defect_checks"],
            }
            for (scenario_id, arm), record in records.items()
        },
        "decision": decision,
        "grader_raw_response_file": str(raw_path),
    }
    report_path = RESULTS / "verdict-report.json"
    dump_json(report_path, report)
    json.loads(report_path.read_text(encoding="utf-8"))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
