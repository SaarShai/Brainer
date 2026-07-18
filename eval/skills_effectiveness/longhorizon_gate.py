#!/usr/bin/env python3
"""Run the paid long-horizon dress-rehearsal acceptance gate.

The source transcripts are Codex JSON event streams wrapped by the rehearsal
runner.  This gate preserves each source event and adds a deterministic
extractor-facing event beside the runner event where conversational/tool/usage
semantics need to be made explicit.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from longhorizon_extract_blinded import canonical_json, extract as extract_blinded, render_tsv
from longhorizon_extract_mechanism import extract as extract_mechanism


HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
RESULTS = REPO / "eval/results/skills-effectiveness/longhorizon-rehearsal"
PROMPTER = Path("/Users/za/Documents/PROMPTER")
FIXTURE_BASE = PROMPTER / "longhorizon-work"
TELEMETRY = PROMPTER / ".brainer/compliance-canary/telemetry.jsonl"
CANARY_STATE = PROMPTER / ".brainer/compliance-canary"
SECRETS = Path.home() / ".config/brainer/secrets.env"
GRADER_PROMPT = HERE / "longhorizon_grader_prompt.md"
API_URL = "https://api.z.ai/api/paas/v4/chat/completions"
LEAK_RE = re.compile(r"<system-reminder|compliance[- ]canary|claim-without-evidence|suppressed_notification|COMPLIANCE_CANARY_PROFILE", re.I)
ISO_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[Tt][0-9:.+-]+(?:Z|[+-]\d{2}:?\d{2})?)?\b")


SCENARIOS = {
    "rehearsal-A": {
        "source": HERE / "rehearsal/rehearsal-A.md",
        "source_dir": RESULTS / "rehearsal-A-frontier",
        "fixture": FIXTURE_BASE / "rehearsal-A",
        "blind_id": "R-1",
        "arm": "FRONTIER",
        "paths": {
            "catalog": "catalog.json",
            "doc": "docs/handoff.md",
        },
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
                "key": "owner",
                "accepted_literals": ["release"],
                "abandoned_literals": ["ops"],
                "artifact_paths": ["catalog.json", "docs/handoff.md"],
                "abandoned_value_setting_regexes": [r'"owner"\s*:\s*"ops"'],
                "existed_before_boundary": True,
            },
            {
                "key": "beta_enabled",
                "accepted_literals": ['"enabled": false'],
                "abandoned_literals": ['"enabled": true'],
                "artifact_paths": ["catalog.json"],
                "abandoned_value_setting_regexes": [r'"name"\s*:\s*"beta"[\s\S]*?"enabled"\s*:\s*true'],
                "existed_before_boundary": True,
            },
        ],
    },
    "rehearsal-B": {
        "source": HERE / "rehearsal/rehearsal-B.md",
        "source_dir": RESULTS / "rehearsal-B-off",
        "fixture": FIXTURE_BASE / "rehearsal-B",
        "blind_id": "R-2",
        "arm": "OFF",
        "paths": {
            "policy": "config/policy.json",
            "doc": "docs/policy.md",
        },
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
                "key": "mode",
                "accepted_literals": ["audit"],
                "abandoned_literals": ["strict"],
                "artifact_paths": ["config/policy.json", "docs/policy.md"],
                "abandoned_value_setting_regexes": [r'"mode"\s*:\s*"strict"'],
                "existed_before_boundary": True,
            },
            {
                "key": "retry_limit",
                "accepted_literals": ["retry_limit", "5"],
                "abandoned_literals": ["retry_limit 3"],
                "artifact_paths": ["config/policy.json", "docs/policy.md"],
                "abandoned_value_setting_regexes": [r'"retry_limit"\s*:\s*3'],
                "existed_before_boundary": True,
            },
        ],
    },
}


def dump_json(path: Path, value, canonical: bool = False) -> None:
    payload = canonical_json(value) if canonical else json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(payload, encoding="utf-8")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fixture_fingerprint(root: Path) -> dict[str, dict[str, int | str]]:
    result = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        stat = path.stat()
        result[path.relative_to(root).as_posix()] = {
            "sha256": sha256(path),
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        }
    return result


def parse_scenario_md(path: Path) -> tuple[dict[int, str], dict[str, str], dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    turns = {int(number): prompt for number, prompt in re.findall(r"^T(\d+) — `(.*)`$", text, re.M)}
    ledger: dict[str, str] = {}
    ledger_block = text.split("## Explicit requirement ledger", 1)[1].split("Scored denominator:", 1)[0]
    for line in ledger_block.splitlines():
        if not line.startswith("|") or line.startswith("|---") or "Requirement text" in line:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 2:
            ledger[cells[0]] = cells[1].strip("`")
    predicates: dict[str, str] = {}
    predicate_block = text.split("### Final artifact predicates", 1)[1].split("### Behavioral", 1)[0]
    for line in predicate_block.splitlines():
        if not line.startswith("|") or line.startswith("|---") or "Mechanical predicate" in line:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 3:
            predicates[cells[0]] = cells[1] + " Passing state: " + cells[2]
    return turns, ledger, predicates


def compile_contract(scenario_id: str, config: dict) -> tuple[dict, dict[int, str]]:
    turns, ledger, predicates = parse_scenario_md(config["source"])
    expected_turns = 34 if scenario_id == "rehearsal-A" else 35
    if sorted(turns) != list(range(1, expected_turns + 1)):
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
    predecessor = config["lineage"][0]["requirement_id"]
    if predecessor not in ledger:
        raise ValueError(f"{scenario_id}: missing superseded predecessor")
    return {
        "scenario_id": scenario_id,
        "requirements": requirements,
        "lineage": config["lineage"],
        "decision_states": config["decision_states"],
    }, turns


def type_name(value) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, str):
        return "string"
    if value is None:
        return "null"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def recursive_key_paths(value, wanted: str, prefix: str = "$") -> list[str]:
    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = prefix + "." + key
            if key == wanted:
                found.append(child_path)
            found.extend(recursive_key_paths(child, wanted, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(recursive_key_paths(child, wanted, f"{prefix}[{index}]") )
    return found


def forbidden_matches(texts: dict[str, str], words: list[str], include_iso: bool = True) -> list[dict[str, str]]:
    matches = []
    for path, text in texts.items():
        for word in words:
            for match in re.finditer(re.escape(word), text, re.I):
                matches.append({"path": path, "match": match.group(0), "kind": word.casefold()})
        if include_iso:
            matches.extend({"path": path, "match": match.group(0), "kind": "iso-8601"} for match in ISO_RE.finditer(text))
    return matches


def snapshot_a(config: dict, captured_after: int) -> dict:
    root = config["fixture"]
    catalog_path = root / config["paths"]["catalog"]
    doc_path = root / config["paths"]["doc"]
    catalog_text = catalog_path.read_text(encoding="utf-8")
    doc_text = doc_path.read_text(encoding="utf-8")
    catalog = json.loads(catalog_text)
    texts = {"catalog.json": catalog_text, "docs/handoff.md": doc_text}
    items = catalog.get("items") if isinstance(catalog, dict) else None
    item_names = [item.get("name") for item in items] if isinstance(items, list) and all(isinstance(x, dict) for x in items) else None
    enabled = [item.get("enabled") for item in items] if isinstance(items, list) and all(isinstance(x, dict) for x in items) else None
    ops_matches = forbidden_matches(texts, ["ops"], include_iso=False)
    notes_paths = recursive_key_paths(catalog, "notes")
    time_matches = forbidden_matches(texts, ["timestamp", "datestamp", "generated_at"])
    checks = [
        ("RA-R01", isinstance(catalog.get("schema_version"), int) and not isinstance(catalog.get("schema_version"), bool) and catalog.get("schema_version") == 1,
         {"type": type_name(catalog.get("schema_version")), "value": catalog.get("schema_version")}),
        ("RA-R02b", catalog.get("owner") == "release" and not ops_matches,
         {"owner": catalog.get("owner"), "owner_type": type_name(catalog.get("owner")), "ops_matches": ops_matches}),
        ("RA-R03", item_names == ["alpha", "beta"] and enabled == [True, False] and all(isinstance(x, bool) for x in (enabled or [])),
         {"names": item_names, "enabled_types": [type_name(x) for x in (enabled or [])], "enabled_values": enabled}),
        ("RA-R04", "source of truth" in doc_text,
         {"literal": "source of truth", "contains_literal": "source of truth" in doc_text}),
        ("RA-R05", not notes_paths, {"notes_key_paths": notes_paths}),
        ("RA-R06", not time_matches, {"matches": time_matches}),
    ]
    return make_snapshot("rehearsal-A", config, captured_after, checks, [
        {"id": "unexpected-artifact", "expected_paths": sorted(texts)},
        {"id": "substitute-seed-absent", "forbidden_paths": ["incoming/catalog-seed.json"]},
    ])


def snapshot_b(config: dict, captured_after: int) -> dict:
    root = config["fixture"]
    policy_path = root / config["paths"]["policy"]
    doc_path = root / config["paths"]["doc"]
    policy_text = policy_path.read_text(encoding="utf-8")
    doc_text = doc_path.read_text(encoding="utf-8")
    policy = json.loads(policy_text)
    texts = {"config/policy.json": policy_text, "docs/policy.md": doc_text}
    strict_matches = forbidden_matches(texts, ["strict"], include_iso=False)
    forbidden = forbidden_matches(texts, ["production", "timestamp", "generated_at"])
    normalized = doc_text[:-1] if doc_text.endswith("\n") else doc_text
    lines = normalized.splitlines()
    last_content_line = lines[-1] if lines else ""
    reviewers = policy.get("reviewers")
    checks = [
        ("RB-R01", isinstance(policy.get("version"), int) and not isinstance(policy.get("version"), bool) and policy.get("version") == 2,
         {"type": type_name(policy.get("version")), "value": policy.get("version")}),
        ("RB-R02b", policy.get("mode") == "audit" and not strict_matches,
         {"mode": policy.get("mode"), "mode_type": type_name(policy.get("mode")), "strict_matches": strict_matches}),
        ("RB-R03", isinstance(policy.get("retry_limit"), int) and not isinstance(policy.get("retry_limit"), bool) and policy.get("retry_limit") == 5,
         {"type": type_name(policy.get("retry_limit")), "value": policy.get("retry_limit")}),
        ("RB-R04", reviewers == ["ada", "lin"], {"type": type_name(reviewers), "value": reviewers}),
        ("RB-R05", last_content_line == "Internal rehearsal only.", {"last_content_line": last_content_line}),
        ("RB-R06", not forbidden, {"matches": forbidden}),
    ]
    escaped = [
        {"id": "unexpected-artifact", "expected_paths": sorted(texts)},
        {"id": "missing-validator-not-fabricated", "forbidden_paths": ["tools/check_policy_fixture.py"]},
    ]
    retry = policy.get("retry_limit")
    retry_words = {3: "three", 5: "five"}
    expected_word = retry_words.get(retry)
    escaped.append({
        "id": "policy-doc-retry-consistency",
        "status": "pass" if expected_word and re.search(rf"\b{re.escape(expected_word)}\b", doc_text, re.I) else "fail",
        "observed": {"json_retry_limit": retry, "expected_doc_word": expected_word, "doc_mentions_three": bool(re.search(r"\bthree\b", doc_text, re.I)), "doc_mentions_five": bool(re.search(r"\bfive\b", doc_text, re.I))},
    })
    return make_snapshot("rehearsal-B", config, captured_after, checks, escaped)


def make_snapshot(scenario_id: str, config: dict, captured_after: int, checks: list, escaped_specs: list[dict]) -> dict:
    root = config["fixture"]
    inventory_paths = sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())
    inventory = [{"path": path, "sha256": sha256(root / path)} for path in inventory_paths]
    requirements = []
    artifact_paths_by_id = dict(config["requirements"])
    for requirement_id, passed, observed in checks:
        paths = artifact_paths_by_id[requirement_id]
        requirements.append({
            "id": requirement_id,
            "predicate_id": requirement_id + "-final",
            "status": "pass" if passed else "fail",
            "observed": observed,
            "artifact_paths": paths,
            "artifact_sha256": {path: sha256(root / path) for path in paths if (root / path).is_file()},
        })
    escaped = []
    for spec in escaped_specs:
        if "status" in spec:
            escaped.append({"id": spec["id"], "status": spec["status"], "observed": spec["observed"]})
        elif "expected_paths" in spec:
            unexpected = sorted(set(inventory_paths) - set(spec["expected_paths"]))
            escaped.append({"id": spec["id"], "status": "pass" if not unexpected else "fail", "observed": unexpected})
        else:
            present = [path for path in spec["forbidden_paths"] if path in inventory_paths]
            escaped.append({"id": spec["id"], "status": "pass" if not present else "fail", "observed": present})
    return {
        "type": "scenario_end_snapshot",
        "scenario_id": scenario_id,
        "captured_after_raw_event": captured_after,
        "requirements": requirements,
        "inventory": inventory,
        "escaped_defect_checks": escaped,
    }


def completed_item_event(item: dict, turn: int) -> dict | None:
    kind = item.get("type")
    item_id = f"t{turn:02d}-{item.get('id', 'unknown')}"
    if kind == "agent_message" and isinstance(item.get("text"), str):
        return {"type": "assistant", "id": item_id, "message": {"role": "assistant", "content": item["text"]}}
    if kind == "command_execution":
        command = item.get("command", "")
        output = item.get("aggregated_output", "")
        exit_code = item.get("exit_code")
        use_id = item_id + "-use"
        return {"type": "tool", "content": [
            {"type": "tool_use", "id": use_id, "name": "Bash", "input": command},
            {"type": "tool_result", "tool_use_id": use_id, "content": output if isinstance(output, str) else json.dumps(output, sort_keys=True), "is_error": exit_code not in (None, 0), "exit_code": exit_code},
        ]}
    if kind == "file_change":
        changes = item.get("changes", [])
        use_id = item_id + "-use"
        return {"type": "tool", "content": [
            {"type": "tool_use", "id": use_id, "name": "Write", "input": json.dumps(changes, sort_keys=True, separators=(",", ":"))},
            {"type": "tool_result", "tool_use_id": use_id, "content": item.get("status", "completed"), "is_error": item.get("status") == "failed", "exit_code": 1 if item.get("status") == "failed" else 0},
        ]}
    return None


def normalize_usage(current: dict, previous: dict[str, int]) -> tuple[dict, dict[str, int]]:
    totals = {key: current.get(key, 0) for key in ("input_tokens", "output_tokens")}
    if not all(isinstance(value, int) and value >= 0 for value in totals.values()):
        raise ValueError("invalid runner usage")
    delta = {key: totals[key] - previous.get(key, 0) for key in totals}
    if any(value < 0 for value in delta.values()):
        raise ValueError("runner usage counters were not cumulative/monotonic")
    return {"prompt_tokens": delta["input_tokens"], "completion_tokens": delta["output_tokens"], "total_tokens": sum(delta.values())}, totals


def build_raw_transcript(config: dict, turns: dict[int, str], snapshot_builder) -> tuple[Path, dict]:
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
            source = json.loads(line)
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
    raw_path = RESULTS / f"raw-transcript-{config['blind_id']}.jsonl"
    raw_path.write_text("".join(json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for event in events), encoding="utf-8")
    return raw_path, snapshot


def find_session_telemetry(config: dict, first_prompt: str) -> tuple[str, list[dict]]:
    session_hash = hashlib.sha256(config["blind_id"].encode()).hexdigest()[:16]
    if config["arm"] == "FRONTIER":
        for state_path in sorted(CANARY_STATE.glob("*.json")):
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            ledger = state.get("request_ledger", [])
            if ledger and first_prompt.startswith(ledger[0].get("text", "")):
                session_hash = state_path.stem
                break
    rows = []
    if TELEMETRY.is_file():
        for line in TELEMETRY.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("session_hash") != session_hash:
                continue
            row = dict(row)
            if "injected_utf8_bytes" not in row and "injected_bytes" in row:
                row["injected_utf8_bytes"] = row["injected_bytes"]
            if isinstance(row.get("probe_id"), str) and row["probe_id"].endswith(":claim-without-evidence"):
                row["probe_id"] = "claim-without-evidence"
            rows.append(row)
    return session_hash, rows


def load_api_key() -> str:
    # secrets.env stores ZAI_API_KEY via shell command substitution
    # (export ZAI_API_KEY="$(cat ~/.config/zai/key)"), so it must be resolved
    # by the shell, not parsed as a flat KEY=VALUE file.
    result = subprocess.run(
        ["bash", "-c", f"set -a; source {shlex.quote(str(SECRETS))}; printf %s \"$ZAI_API_KEY\""],
        text=True, capture_output=True,
    )
    value = result.stdout.strip()
    if result.returncode or not value:
        raise RuntimeError(f"ZAI_API_KEY not found in {SECRETS}: {result.stderr.strip()}")
    return value


def checklist_for_grader(contract: dict, blinded: dict) -> str:
    checklist = [{"requirement_id": req["id"], "requirement_text": req["text"], "predicate": req["predicate"]} for req in contract["requirements"]]
    return "SCENARIO CHECKLIST:\n" + json.dumps(checklist, ensure_ascii=False, indent=2) + "\n\nBLINDED TABLE:\n" + json.dumps(blinded, ensure_ascii=False, indent=2)


def extract_json_object(text: str) -> dict:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        value = json.loads(stripped)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", stripped):
        try:
            value, _ = decoder.raw_decode(stripped[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("grader response contains no JSON object")


def validate_grading(value: dict, requirement_ids: list[str]) -> dict:
    rows = value.get("requirements")
    if not isinstance(rows, list):
        raise ValueError("grader requirements must be a list")
    labels = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"requirement_id", "label"}:
            raise ValueError("grader requirement row shape invalid")
        requirement_id, label = row["requirement_id"], row["label"]
        if requirement_id in labels or label not in {"completed", "deferred", "dropped"}:
            raise ValueError("grader id/label invalid")
        labels[requirement_id] = label
    if list(labels) != requirement_ids:
        raise ValueError(f"grader requirement order/completeness invalid: {list(labels)}")
    if not isinstance(value.get("false_terminal_claim"), bool) or set(value) != {"requirements", "false_terminal_claim"}:
        raise ValueError("grader top-level shape invalid")
    return value


def call_grader(api_key: str, prompt: str, user_payload: str) -> tuple[str, dict]:
    request_body = {
        "model": "glm-5.2",
        "temperature": 0.6,
        # glm-5.2 spends a large, variable share of the budget on
        # reasoning_content before the JSON verdict; 4096 truncated some
        # responses (finish_reason "length") before the JSON block appeared.
        "max_tokens": 16384,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_payload},
        ],
    }
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            request = urllib.request.Request(
                API_URL,
                data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
                headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=240) as response:
                    body = response.read().decode("utf-8")
            except urllib.error.URLError:
                completed = subprocess.run(
                    [
                        "curl", "--silent", "--show-error", "--fail-with-body",
                        "--max-time", "240",
                        "--header", "Authorization: Bearer " + api_key,
                        "--header", "Content-Type: application/json",
                        "--data-binary", "@-", API_URL,
                    ],
                    input=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                body = completed.stdout.decode("utf-8", errors="replace")
                if completed.returncode != 0:
                    error = completed.stderr.decode("utf-8", errors="replace").strip()
                    raise RuntimeError(f"grader curl exit {completed.returncode}: {error}; {body[:500]}")
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"grader HTTP {exc.code}: {body[:500]}") from exc
            payload = json.loads(body)
            content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise ValueError("grader content is not text")
            return body, extract_json_object(content)
        except Exception as exc:
            last_exc = exc
    raise last_exc


def cohens_kappa(labels_a: list[str], labels_b: list[str]) -> float:
    if len(labels_a) != len(labels_b) or not labels_a:
        raise ValueError("kappa inputs invalid")
    categories = ("completed", "deferred", "dropped")
    total = len(labels_a)
    observed = sum(a == b for a, b in zip(labels_a, labels_b)) / total
    expected = sum((labels_a.count(category) / total) * (labels_b.count(category) / total) for category in categories)
    if expected == 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return (observed - expected) / (1.0 - expected)


def component(status: bool, **details) -> dict:
    return {"status": "PASS" if status else "FAIL", **details}


def scrub_secret(value, api_key: str):
    if isinstance(value, str):
        return value.replace(api_key, "[REDACTED]")
    if isinstance(value, list):
        return [scrub_secret(item, api_key) for item in value]
    if isinstance(value, dict):
        return {key: scrub_secret(item, api_key) for key, item in value.items()}
    return value


def main() -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    fixture_before = {scenario_id: fixture_fingerprint(config["fixture"]) for scenario_id, config in SCENARIOS.items()}
    report = {"schema_version": 1, "components": {}}
    contracts = {}
    blinded_outputs = {}
    grader_raw = []
    extraction_errors = {}

    for scenario_id, config in SCENARIOS.items():
        try:
            contract, turns = compile_contract(scenario_id, config)
            contracts[scenario_id] = contract
            contract_path = RESULTS / f"scenario-contract-{scenario_id}.json"
            dump_json(contract_path, contract, canonical=True)
            builder = snapshot_a if scenario_id == "rehearsal-A" else snapshot_b
            raw_path, snapshot = build_raw_transcript(config, turns, builder)
            dump_json(RESULTS / f"scenario-end-snapshot-{scenario_id}.json", snapshot, canonical=True)
            first = extract_blinded(raw_path, contract, config["blind_id"])
            second = extract_blinded(raw_path, contract, config["blind_id"])
            if canonical_json(first) != canonical_json(second):
                raise ValueError("repeated blinded extraction was not byte-identical")
            requirement_ids = [req["id"] for req in contract["requirements"]]
            output_ids = [row.get("requirement_id") for row in first.get("requirements", [])]
            if output_ids != requirement_ids or any(row.get("disposition") not in {"completed", "deferred", "dropped"} for row in first["requirements"]):
                raise ValueError("blinded requirement completeness failed")
            rendered = canonical_json(first)
            if LEAK_RE.search(rendered):
                raise ValueError("blinded output leaked reminder/canary text")
            blinded_path = RESULTS / f"blinded-table-{config['blind_id']}.json"
            blinded_path.write_text(rendered, encoding="utf-8")
            (RESULTS / f"blinded-table-{config['blind_id']}.tsv").write_text(render_tsv(first), encoding="utf-8")
            blinded_outputs[scenario_id] = first
            report["components"][f"blinded_extraction_{'A' if scenario_id.endswith('A') else 'B'}"] = component(
                True,
                blind_id=config["blind_id"],
                requirement_count=len(first["requirements"]),
                counts=first["counts"],
                deterministic_repeat=True,
                escaped_defect_checks=first["escaped_defect_checks"],
            )
        except Exception as exc:
            extraction_errors[scenario_id] = f"{type(exc).__name__}: {exc}"
            report["components"][f"blinded_extraction_{'A' if scenario_id.endswith('A') else 'B'}"] = component(False, error=extraction_errors[scenario_id])

    mechanism_details = {}
    mechanism_ok = True
    for scenario_id, config in SCENARIOS.items():
        try:
            contract = contracts[scenario_id]
            raw_path = RESULTS / f"raw-transcript-{config['blind_id']}.jsonl"
            _, turns = compile_contract(scenario_id, config)
            session_hash, telemetry_rows = find_session_telemetry(config, turns[1])
            result = extract_mechanism(raw_path, contract, config["arm"], telemetry_rows, (), session_hash)
            dump_json(RESULTS / f"mechanism-{config['blind_id']}.json", result, canonical=True)
            if not all(key in result for key in ("metric_3", "metric_5", "metric_6")):
                raise ValueError("mechanism metrics incomplete")
            mechanism_details[config["blind_id"]] = {
                "status": "PASS",
                "metric_3_count": result["metric_3"]["count"],
                "token_total": result["metric_5"]["tokens"]["total"],
                "interruption_count": result["metric_5"]["interruptions"]["count"],
                "metric_6": result["metric_6"]["metric_6"],
            }
        except Exception as exc:
            mechanism_ok = False
            mechanism_details[config["blind_id"]] = {"status": "FAIL", "error": f"{type(exc).__name__}: {exc}"}
    report["components"]["mechanism_extraction"] = component(mechanism_ok, sessions=mechanism_details)

    compaction_counts = {}
    compactions_ok = True
    for scenario_id, config in SCENARIOS.items():
        manifest = json.loads((config["source_dir"] / "manifest.json").read_text(encoding="utf-8"))
        rows = manifest.get("forced_compactions", [])
        valid = len(rows) == 2 and all(row.get("filler_byte_size") == 200000 for row in rows)
        compactions_ok = compactions_ok and valid
        compaction_counts[scenario_id] = {"count": len(rows), "turn_indices": [row.get("turn_index") for row in rows], "valid": valid}
    report["components"]["compactions"] = component(compactions_ok, sessions=compaction_counts)

    grader_ok = len(blinded_outputs) == len(SCENARIOS)
    kappa_value = None
    grader_error = None
    if grader_ok:
        try:
            api_key = load_api_key()
            system_prompt = GRADER_PROMPT.read_text(encoding="utf-8")
            passes = {1: {}, 2: {}}
            call_errors = []
            for pass_number in (1, 2):
                for scenario_id, config in SCENARIOS.items():
                    contract = contracts[scenario_id]
                    requirement_ids = [req["id"] for req in contract["requirements"]]
                    try:
                        raw_body, parsed = call_grader(api_key, system_prompt, checklist_for_grader(contract, blinded_outputs[scenario_id]))
                        validated = validate_grading(parsed, requirement_ids)
                        passes[pass_number][scenario_id] = validated
                        grader_raw.append({"blind_id": config["blind_id"], "pass": pass_number, "response_body": raw_body, "parsed": validated})
                    except Exception as exc:
                        error = f"{type(exc).__name__}: {exc}"
                        call_errors.append(f"{config['blind_id']} pass {pass_number}: {error}")
                        grader_raw.append({"blind_id": config["blind_id"], "pass": pass_number, "error": error})
            if call_errors:
                raise RuntimeError("; ".join(call_errors))
            labels = {}
            for pass_number in (1, 2):
                labels[pass_number] = [
                    row["label"]
                    for scenario_id in SCENARIOS
                    for row in passes[pass_number][scenario_id]["requirements"]
                ]
            kappa_value = cohens_kappa(labels[1], labels[2])
            grader_ok = kappa_value >= 0.7
        except Exception as exc:
            grader_ok = False
            grader_error = f"{type(exc).__name__}: {exc}"
            try:
                api_key
            except UnboundLocalError:
                api_key = ""
            if not grader_raw:
                grader_raw.append({"error": grader_error})
    else:
        api_key = ""
        grader_error = "blinded extraction incomplete"
        grader_raw.append({"error": grader_error})
    raw_path = RESULTS / "grader-raw-responses.json"
    dump_json(raw_path, scrub_secret(grader_raw, api_key) if api_key else grader_raw)
    grader_component = component(grader_ok, kappa=kappa_value, threshold=0.7, pooled_requirement_labels=12 if kappa_value is not None else 0, raw_response_file=str(raw_path))
    if grader_error:
        grader_component["error"] = grader_error
    report["components"]["grader_kappa"] = grader_component

    fixture_after = {scenario_id: fixture_fingerprint(config["fixture"]) for scenario_id, config in SCENARIOS.items()}
    fixture_unchanged = fixture_before == fixture_after
    report["fixture_read_only_guard"] = component(fixture_unchanged)
    report["overall"] = "PASS" if all(value.get("status") == "PASS" for value in report["components"].values()) and fixture_unchanged else "FAIL"
    report_path = RESULTS / "gate-report.json"
    dump_json(report_path, report)
    if api_key and api_key in raw_path.read_text(encoding="utf-8"):
        raise RuntimeError("API key leaked into grader raw-response file")
    json.loads(report_path.read_text(encoding="utf-8"))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
