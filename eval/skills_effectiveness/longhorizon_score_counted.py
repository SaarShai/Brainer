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
  All six counted scenarios script T01-T44 (44 turns) and each has TWO
  superseded lineage rows. ``compile_contract`` below mirrors the
  rehearsal function's logic (built from the same imported
  ``parse_scenario_md``) with those two assumptions generalized.
- ``build_raw_transcript`` closes over the module-level rehearsal ``RESULTS``
  directory as its write target, so calling it verbatim would write counted
  raw transcripts into the rehearsal results tree. ``build_raw_transcript``
  below is the same event-normalization loop (reusing the imported
  ``completed_item_event`` and ``normalize_usage`` primitives verbatim) with
  the output directory taken as a parameter instead.

Discovers the counted session directories (two arms per scenario in
SESSION_CONFIGS) under
eval/results/skills-effectiveness/longhorizon-main/<scenario>-<arm>/, scores
each that is complete (44/44 turns, all turn files present, all turns exit
0), and writes verdict-report.json next to them. If any configured session is
incomplete, no grader call is made and an INSUFFICIENT_DATA report is written
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
    "scenario-01": {
        "source": SCENARIOS_DIR / "scenario-01.md",
        "paths": {"plan": "dist/release-plan.json", "doc": "docs/operator.md"},
        "requirements": [
            ("S01-R01", ["dist/release-plan.json"]),
            ("S01-R02b", ["dist/release-plan.json", "docs/operator.md"]),
            ("S01-R03", ["dist/release-plan.json"]),
            ("S01-R04", ["dist/release-plan.json"]),
            ("S01-R05b", ["dist/release-plan.json"]),
            ("S01-R06", ["dist/release-plan.json", "docs/operator.md"]),
            ("S01-R07", ["dist/release-plan.json", "docs/operator.md"]),
        ],
        "lineage": [
            {"requirement_id": "S01-R02a", "status": "superseded", "superseded_by": "S01-R02b"},
            {"requirement_id": "S01-R05a", "status": "superseded", "superseded_by": "S01-R05b"},
        ],
        "decision_states": [
            {
                "key": "backend",
                "accepted_literals": ["streaming"],
                "abandoned_literals": ["classic"],
                "artifact_paths": ["dist/release-plan.json", "docs/operator.md"],
                "abandoned_value_setting_regexes": [r'"backend"\s*:\s*"classic"'],
                "existed_before_boundary": True,
            },
        ],
    },
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
    "scenario-03": {
        "source": SCENARIOS_DIR / "scenario-03.md",
        "paths": {"plan": "deploy/production.json", "doc": "docs/production.md", "decoy": "deploy/staging.json"},
        "requirements": [
            ("S03-R01", ["deploy/production.json"]),
            ("S03-R02b", ["deploy/production.json", "docs/production.md"]),
            ("S03-R03", ["deploy/production.json"]),
            ("S03-R04b", ["deploy/production.json"]),
            ("S03-R05", ["deploy/production.json"]),
            ("S03-R06", ["deploy/production.json", "docs/production.md"]),
            ("S03-R07", ["deploy/staging.json"]),
        ],
        "lineage": [
            {"requirement_id": "S03-R02a", "status": "superseded", "superseded_by": "S03-R02b"},
            {"requirement_id": "S03-R04a", "status": "superseded", "superseded_by": "S03-R04b"},
        ],
        "decision_states": [
            {
                "key": "port",
                "accepted_literals": ["8443"],
                "abandoned_literals": ["8080"],
                "artifact_paths": ["deploy/production.json", "docs/production.md"],
                "abandoned_value_setting_regexes": [r'"port"\s*:\s*8080'],
                "existed_before_boundary": True,
            },
        ],
        # Frozen decoy baseline recorded at fixture freeze (same philosophy as
        # LEGACY_ARCHIVE_HASHES); snapshot_scenario_03 refuses to guess when unset.
        "staging_baseline_sha256": None,
    },
    "scenario-04": {
        "source": SCENARIOS_DIR / "scenario-04.md",
        "paths": {"policy": "policy/access.json", "doc": "docs/access.md", "checksum": "policy/access.sha256"},
        "requirements": [
            ("S04-R01", ["policy/access.json"]),
            ("S04-R02b", ["policy/access.json"]),
            ("S04-R03b", ["policy/access.json", "docs/access.md", "policy/access.sha256"]),
            ("S04-R04", ["policy/access.json"]),
            ("S04-R05", ["policy/access.json", "docs/access.md"]),
            ("S04-R06", ["policy/access.json", "policy/access.sha256"]),
            ("S04-R07", ["policy/access.json", "docs/access.md", "policy/access.sha256"]),
        ],
        "lineage": [
            {"requirement_id": "S04-R02a", "status": "superseded", "superseded_by": "S04-R02b"},
            {"requirement_id": "S04-R03a", "status": "superseded", "superseded_by": "S04-R03b"},
        ],
        "decision_states": [
            {
                "key": "unknown_policy",
                "accepted_literals": ["reject"],
                "abandoned_literals": ["warn"],
                "artifact_paths": ["policy/access.json", "docs/access.md"],
                "abandoned_value_setting_regexes": [r'"unknown_policy"\s*:\s*"warn"'],
                "existed_before_boundary": True,
            },
        ],
    },
    "scenario-05": {
        "source": SCENARIOS_DIR / "scenario-05.md",
        "paths": {"manifest": "routes/manifest.json", "doc": "docs/routes.md", "env": ".env.example"},
        "requirements": [
            ("S05-R01b", ["routes/manifest.json"]),
            ("S05-R02b", ["routes/manifest.json"]),
            ("S05-R03", ["routes/manifest.json"]),
            ("S05-R04", ["routes/manifest.json"]),
            ("S05-R05", [".env.example"]),
            ("S05-R06", ["routes/manifest.json", "docs/routes.md"]),
            ("S05-R07", ["routes/manifest.json", "docs/routes.md", ".env.example"]),
        ],
        "lineage": [
            {"requirement_id": "S05-R01a", "status": "superseded", "superseded_by": "S05-R01b"},
            {"requirement_id": "S05-R02a", "status": "superseded", "superseded_by": "S05-R02b"},
        ],
        "decision_states": [
            {
                "key": "format",
                "accepted_literals": ["json"],
                "abandoned_literals": ["toml"],
                "artifact_paths": ["routes/manifest.json", "docs/routes.md"],
                "abandoned_value_setting_regexes": [r"manifest\.toml"],
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
    scripted-turn count fixed at 44 (T01-T44, per the six scenario-NN.md
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


def _values_for_key(node, wanted: str) -> list:
    """Value-returning analogue of longhorizon_gate.recursive_key_paths (which
    yields "$.path" strings; the S03-R05 answer-key predicate -- "recursively
    inspect .headers; exactly one case-sensitive X-Trace key" -- needs the
    matched values, not their paths)."""
    values = []
    if isinstance(node, dict):
        for key, child in node.items():
            if key == wanted:
                values.append(child)
            values.extend(_values_for_key(child, wanted))
    elif isinstance(node, list):
        for child in node:
            values.extend(_values_for_key(child, wanted))
    return values


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


def snapshot_scenario_01(config: dict, captured_after: int) -> dict:
    root = config["fixture"]
    plan_path = root / config["paths"]["plan"]
    doc_path = root / config["paths"]["doc"]
    plan_text = plan_path.read_text(encoding="utf-8")
    doc_text = doc_path.read_text(encoding="utf-8")
    plan = json.loads(plan_text)
    texts = {"dist/release-plan.json": plan_text, "docs/operator.md": doc_text}
    classic_matches = forbidden_matches(texts, ["classic"], include_iso=False)
    forbidden = forbidden_matches(texts, ["generated_at", "timestamp"])
    stages = plan.get("stages")
    dry_run = plan.get("dry_run")
    timeout = plan.get("timeout_seconds")
    doc_preview = "--preview" in doc_text
    doc_alias_only = bool(re.search(r"documentation[- ]only", doc_text, re.I))
    json_preview = re.search(r"preview", plan_text, re.I)
    checks = [
        ("S01-R01", isinstance(plan.get("schema_version"), int) and not isinstance(plan.get("schema_version"), bool) and plan.get("schema_version") == 3,
         {"type": type_name(plan.get("schema_version")), "value": plan.get("schema_version")}),
        ("S01-R02b", plan.get("backend") == "streaming" and not classic_matches,
         {"backend": plan.get("backend"), "backend_type": type_name(plan.get("backend")), "classic_matches": classic_matches}),
        ("S01-R03", stages == ["ingest", "normalize", "render", "publish"],
         {"type": type_name(stages), "value": stages}),
        ("S01-R04", dry_run is True,
         {"type": type_name(dry_run), "value": dry_run}),
        ("S01-R05b", isinstance(timeout, int) and not isinstance(timeout, bool) and timeout == 60,
         {"type": type_name(timeout), "value": timeout}),
        ("S01-R06", doc_preview and doc_alias_only and json_preview is None,
         {"doc_mentions_preview": doc_preview, "doc_marks_documentation_only": doc_alias_only,
          "json_preview_match": json_preview.group(0) if json_preview else None}),
        ("S01-R07", not forbidden,
         {"matches": forbidden}),
    ]
    return make_snapshot("scenario-01", config, captured_after, checks, [
        {"id": "unexpected-artifact", "expected_paths": sorted(texts)},
    ])


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


def snapshot_scenario_03(config: dict, captured_after: int) -> dict:
    root = config["fixture"]
    plan_path = root / config["paths"]["plan"]
    doc_path = root / config["paths"]["doc"]
    decoy_path = root / config["paths"]["decoy"]
    plan_text = plan_path.read_text(encoding="utf-8")
    doc_text = doc_path.read_text(encoding="utf-8")
    plan = json.loads(plan_text)
    texts = {"deploy/production.json": plan_text, "docs/production.md": doc_text,
             "deploy/staging.json": decoy_path.read_text(encoding="utf-8")}
    production_texts = {"deploy/production.json": plan_text, "docs/production.md": doc_text}
    baseline = config.get("staging_baseline_sha256")
    if not baseline:
        raise ValueError("scenario-03: staging decoy baseline sha256 is not registered")
    old_port_matches = forbidden_matches(production_texts, ["8080"], include_iso=False)
    environment = plan.get("environment")
    port = plan.get("port")
    tls = plan.get("tls")
    retries = plan.get("retries")
    headers = plan.get("headers")
    header_value = headers.get("X-Trace") if isinstance(headers, dict) else None
    xtrace_values = _values_for_key(headers, "X-Trace") if isinstance(headers, (dict, list)) else []
    doc_literals = None
    if (isinstance(environment, str) and isinstance(port, int) and not isinstance(port, bool)
            and isinstance(tls, bool) and isinstance(retries, int) and not isinstance(retries, bool)
            and isinstance(header_value, str)):
        doc_literals = [environment, str(port), "true" if tls else "false", str(retries), header_value]
    doc_values = doc_literals is not None and all(
        re.search(r"\b" + re.escape(literal) + r"\b", doc_text, re.I) for literal in doc_literals)
    decoy_sha256 = sha256(decoy_path)
    checks = [
        ("S03-R01", environment == "production",
         {"environment": environment, "environment_type": type_name(environment)}),
        ("S03-R02b", isinstance(port, int) and not isinstance(port, bool) and port == 8443 and not old_port_matches,
         {"type": type_name(port), "value": port, "old_port_matches": old_port_matches}),
        ("S03-R03", tls is True,
         {"type": type_name(tls), "value": tls}),
        ("S03-R04b", isinstance(retries, int) and not isinstance(retries, bool) and retries == 5,
         {"type": type_name(retries), "value": retries}),
        ("S03-R05", len(xtrace_values) == 1 and xtrace_values[0] == "off",
         {"type": type_name(headers), "value": headers, "xtrace_key_count": len(xtrace_values)}),
        ("S03-R06", "deploy/production.json" in doc_text and doc_values and "X-Trace" in doc_text,
         {"doc_names_production_path": "deploy/production.json" in doc_text,
          "expected_doc_literals": doc_literals, "doc_values_agree": bool(doc_values)}),
        ("S03-R07", decoy_sha256 == baseline,
         {"baseline_sha256": baseline, "final_sha256": decoy_sha256}),
    ]
    return make_snapshot("scenario-03", config, captured_after, checks, [
        {"id": "unexpected-artifact", "expected_paths": sorted(texts)},
    ])


def snapshot_scenario_04(config: dict, captured_after: int) -> dict:
    root = config["fixture"]
    policy_path = root / config["paths"]["policy"]
    doc_path = root / config["paths"]["doc"]
    checksum_path = root / config["paths"]["checksum"]
    policy_text = policy_path.read_text(encoding="utf-8")
    doc_text = doc_path.read_text(encoding="utf-8")
    checksum_text = checksum_path.read_text(encoding="utf-8")
    policy = json.loads(policy_text)
    texts = {"policy/access.json": policy_text, "docs/access.md": doc_text, "policy/access.sha256": checksum_text}
    warn_matches = [{"path": path, "match": match.group(0), "kind": "warn"}
                    for path, text in texts.items() for match in re.finditer(r"\bwarn\b", text, re.I)]
    forbidden = forbidden_matches(texts, ["generated_at", "timestamp"])
    rules = policy.get("rules")
    unknown_policy = policy.get("unknown_policy")
    allow_unknown = policy.get("allow_unknown")
    action_positions = []
    doc_rules = True
    if isinstance(rules, list) and rules and all(isinstance(rule, dict) for rule in rules):
        for rule in rules:
            action_match = re.search(r"\b" + re.escape(str(rule.get("action"))) + r"\b", doc_text, re.I)
            decision_match = re.search(r"\b" + re.escape(str(rule.get("decision"))) + r"\b", doc_text, re.I)
            if action_match is None or decision_match is None:
                doc_rules = False
                break
            action_positions.append(action_match.start())
    else:
        doc_rules = False
    doc_order = doc_rules and len(set(action_positions)) == len(action_positions) and action_positions == sorted(action_positions)
    doc_policy = isinstance(unknown_policy, str) and bool(re.search(r"\b" + re.escape(unknown_policy) + r"\b", doc_text, re.I))
    doc_boolean = isinstance(allow_unknown, bool) and bool(re.search(r"\btrue\b" if allow_unknown else r"\bfalse\b", doc_text, re.I))
    digest = sha256(policy_path)
    sidecar_trimmed = checksum_text[:-1] if checksum_text.endswith("\n") else checksum_text
    sidecar_format_ok = bool(re.fullmatch(r"[0-9a-f]{64}\n?", checksum_text))
    checks = [
        ("S04-R01", isinstance(policy.get("schema_version"), int) and not isinstance(policy.get("schema_version"), bool) and policy.get("schema_version") == 1,
         {"type": type_name(policy.get("schema_version")), "value": policy.get("schema_version")}),
        ("S04-R02b", rules == [{"action": "read", "decision": "allow"}, {"action": "write", "decision": "deny"}, {"action": "delete", "decision": "require_approval"}],
         {"type": type_name(rules), "value": rules}),
        ("S04-R03b", unknown_policy == "reject" and not warn_matches,
         {"unknown_policy": unknown_policy, "unknown_policy_type": type_name(unknown_policy), "warn_matches": warn_matches}),
        ("S04-R04", allow_unknown is False,
         {"type": type_name(allow_unknown), "value": allow_unknown}),
        ("S04-R05", doc_rules and doc_order and doc_policy and doc_boolean,
         {"doc_rule_literals_present": doc_rules, "doc_rule_order_positions": action_positions,
          "doc_unknown_policy_present": bool(doc_policy), "doc_allow_unknown_present": bool(doc_boolean)}),
        ("S04-R06", sidecar_trimmed == digest and sidecar_format_ok,
         {"computed_sha256": digest, "sidecar_trimmed": sidecar_trimmed, "sidecar_format_ok": sidecar_format_ok}),
        ("S04-R07", not forbidden,
         {"matches": forbidden}),
    ]
    return make_snapshot("scenario-04", config, captured_after, checks, [
        {"id": "unexpected-artifact", "expected_paths": sorted(texts)},
    ])


def snapshot_scenario_05(config: dict, captured_after: int) -> dict:
    root = config["fixture"]
    manifest_path = root / config["paths"]["manifest"]
    doc_path = root / config["paths"]["doc"]
    env_path = root / config["paths"]["env"]
    manifest_text = manifest_path.read_text(encoding="utf-8")
    doc_text = doc_path.read_text(encoding="utf-8")
    env_bytes = env_path.read_bytes()
    manifest = json.loads(manifest_text)
    texts = {"routes/manifest.json": manifest_text, "docs/routes.md": doc_text,
             ".env.example": env_bytes.decode("utf-8", errors="replace")}
    toml_files = sorted(path.relative_to(root).as_posix() for path in root.rglob("*")
                        if path.is_file() and path.suffix.lower() == ".toml")
    toml_matches = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if "toml" in relative.lower():
            toml_matches.append({"path": relative, "kind": "path"})
        if re.search(r"toml", path.read_text(encoding="utf-8", errors="replace"), re.I):
            toml_matches.append({"path": relative, "kind": "content"})
    routes = manifest.get("routes")
    timeout = manifest.get("timeout_seconds")
    auth_default = manifest.get("auth_default")
    path_positions = []
    doc_routes = True
    if isinstance(routes, list) and routes and all(isinstance(route, dict) for route in routes):
        for route in routes:
            path_match = re.search(re.escape(str(route.get("path"))), doc_text)
            access_match = re.search(r"\b" + re.escape(str(route.get("access"))) + r"\b", doc_text, re.I)
            if path_match is None or access_match is None:
                doc_routes = False
                break
            path_positions.append(path_match.start())
    else:
        doc_routes = False
    doc_order = doc_routes and len(set(path_positions)) == len(path_positions) and path_positions == sorted(path_positions)
    doc_timeout = isinstance(timeout, int) and not isinstance(timeout, bool) and bool(re.search(r"\b" + re.escape(str(timeout)) + r"\b", doc_text))
    doc_auth = isinstance(auth_default, bool) and bool(re.search(r"\btrue\b" if auth_default else r"\bfalse\b", doc_text, re.I))
    env_trimmed = env_bytes[:-1] if env_bytes.endswith(b"\n") else env_bytes
    checks = [
        ("S05-R01b", isinstance(manifest.get("schema_version"), int) and not isinstance(manifest.get("schema_version"), bool) and manifest.get("schema_version") == 1 and not toml_files,
         {"type": type_name(manifest.get("schema_version")), "value": manifest.get("schema_version"), "toml_files": toml_files}),
        ("S05-R02b", routes == [{"path": "/health", "access": "public"}, {"path": "/api", "access": "auth"},
                                {"path": "/admin", "access": "auth"}, {"path": "/metrics", "access": "public"}],
         {"type": type_name(routes), "value": routes}),
        ("S05-R03", isinstance(timeout, int) and not isinstance(timeout, bool) and timeout == 10,
         {"type": type_name(timeout), "value": timeout}),
        ("S05-R04", auth_default is True,
         {"type": type_name(auth_default), "value": auth_default}),
        ("S05-R05", env_trimmed == b"API_TOKEN=",
         {"byte_length": len(env_bytes), "trailing_newline": env_bytes.endswith(b"\n")}),
        ("S05-R06", "routes/manifest.json" in doc_text and not re.search(r"toml", doc_text, re.I) and doc_routes and doc_order and doc_timeout and doc_auth,
         {"doc_names_json_manifest": "routes/manifest.json" in doc_text,
          "doc_toml_free": not re.search(r"toml", doc_text, re.I),
          "doc_route_literals_present": doc_routes, "doc_route_order_positions": path_positions,
          "doc_timeout_present": bool(doc_timeout), "doc_auth_default_present": bool(doc_auth)}),
        ("S05-R07", not toml_matches,
         {"matches": toml_matches}),
    ]
    return make_snapshot("scenario-05", config, captured_after, checks, [
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
    "scenario-01": snapshot_scenario_01,
    "scenario-02": snapshot_scenario_02,
    "scenario-03": snapshot_scenario_03,
    "scenario-04": snapshot_scenario_04,
    "scenario-05": snapshot_scenario_05,
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
        configured = "/".join(f"{scenario_id}-{arm}" for scenario_id in sorted(SESSION_CONFIGS) for arm in ("off", "frontier"))
        report = {
            "schema_version": 1,
            "overall": "INSUFFICIENT_DATA",
            "session_status": {f"{s}-{a}": status for (s, a), status in statuses.items()},
            "incomplete_sessions": incomplete,
            "note": (
                f"Fewer than {len(SESSION_CONFIGS) * 2} counted session directories are complete "
                f"(need {EXPECTED_TURNS}/{EXPECTED_TURNS} turns, exit 0, in each of "
                f"{configured} under longhorizon-main/); no grader call was made "
                "and no verdict was computed. Decision-rule logic is unit-tested "
                "against a synthetic fixture in test_longhorizon_score_counted.py."
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
