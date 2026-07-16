#!/usr/bin/env python3
"""Run and machine-score the frozen weakest-executor transfer case.

Stdlib only. The case rubric is never included in the executor prompt. Inputs
are hashed before dispatch; raw prompt/stdout/stderr and their hashes are kept
in the result so a cold reviewer can reconstruct the run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
DEFAULT_CASE = HERE / "weakest-executor-case-v1.json"
DEFAULT_SKILL = HERE.parent / "SKILL.md"
DEFAULT_OUTPUT = HERE / "2026-07-16-gemma4-26b-mlx.json"
DEFAULT_MODEL = "gemma4:26b-mlx"
_DIGEST_RE = re.compile(r"^(?:sha256:)?([0-9a-f]{64})$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_text_bytes(text: str) -> bytes:
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def normalize_digest(value: Any) -> str:
    match = _DIGEST_RE.fullmatch(value) if isinstance(value, str) else None
    if not match:
        raise ValueError("digest must be 64 lowercase hex characters, optionally prefixed by sha256:")
    return "sha256:" + match.group(1)


def get_model_metadata(model: str, host: str = "http://127.0.0.1:11434") -> dict[str, Any]:
    request = urllib.request.Request(host.rstrip("/") + "/api/tags")
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.load(response)
    matches = [item for item in payload.get("models", [])
               if item.get("name") == model or item.get("model") == model]
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one local Ollama model named {model!r}, found {len(matches)}")
    item = matches[0]
    try:
        digest = normalize_digest(item.get("digest"))
    except ValueError as exc:
        raise RuntimeError(f"Ollama returned no full sha256 digest for {model!r}: {exc}") from exc
    return {
        "name": model,
        "digest": digest,
        "size_bytes": item.get("size"),
        "modified_at": item.get("modified_at"),
    }


def extract_json_object(raw: str) -> dict[str, Any]:
    """Parse direct, fenced, quoted, or preamble-prefixed model JSON."""
    text = raw.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()
    for _ in range(2):
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            break
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            text = value.strip()
            continue
        raise ValueError(f"model JSON must be an object, got {type(value).__name__}")
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("model stdout contains no parseable JSON object")


def get_path(value: Any, dotted: str) -> Any:
    current = value
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _string_set(value: Any) -> set[str] | None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None
    return set(value)


def evaluate_criterion(response: dict[str, Any], criterion: dict[str, Any]) -> tuple[bool, str, Any]:
    kind = criterion["type"]
    if kind == "distinct":
        paths = criterion["paths"]
        values = [get_path(response, path) for path in paths]
        passed = (all(isinstance(value, str) and value.strip() for value in values)
                  and len(set(values)) == len(values))
        return passed, f"values={values!r}", values

    actual = get_path(response, criterion["path"])
    if kind == "equals":
        passed = actual == criterion["expected"]
        reason = f"expected={criterion['expected']!r}; actual={actual!r}"
    elif kind in {"contains_all", "exact_set"}:
        actual_set = _string_set(actual)
        expected_set = set(criterion["expected"])
        passed = (actual_set is not None and
                  (expected_set <= actual_set if kind == "contains_all" else expected_set == actual_set))
        reason = f"expected_{kind}={sorted(expected_set)!r}; actual={actual!r}"
    elif kind == "nonempty_string":
        passed = isinstance(actual, str) and bool(actual.strip())
        reason = f"actual={actual!r}"
    elif kind == "true":
        passed = actual is True
        reason = f"expected=True; actual={actual!r}"
    elif kind == "bounded_positive_int":
        maximum = criterion["maximum"]
        passed = type(actual) is int and 1 <= actual <= maximum
        reason = f"expected integer in [1,{maximum}]; actual={actual!r}"
    else:
        raise ValueError(f"unsupported criterion type: {kind}")
    return passed, reason, actual


def score_response(case: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    results = []
    for criterion in case["rubric"]["criteria"]:
        passed, reason, actual = evaluate_criterion(response, criterion)
        results.append({
            "id": criterion["id"],
            "required": criterion.get("required", True),
            "pass": passed,
            "reason": reason,
            "actual": actual,
        })
    blocking = [item["id"] for item in results if item["required"] and not item["pass"]]
    return {
        "criteria_total": len(results),
        "criteria_passed": sum(1 for item in results if item["pass"]),
        "all_required_passed": not blocking,
        "blocking_criteria": blocking,
        "criteria": results,
    }


def promotion_eligible(process_exit: int | None, parse_error: str | None,
                       scoring: dict[str, Any] | None) -> bool:
    return (process_exit == 0 and parse_error is None and scoring is not None
            and scoring.get("all_required_passed") is True)


def build_prompt(case: dict[str, Any], skill_text: str) -> str:
    public_case = {
        "case_id": case["case_id"],
        "scenario": case["scenario"],
        "response_contract": case["response_contract"],
    }
    return (
        "You are the weakest intended executor in a fresh, stateless evaluation.\n"
        "Apply the policy below to the transfer case. The hidden rubric is not provided.\n"
        "Return exactly one JSON object matching the public response contract.\n\n"
        "POLICY\n------\n" + skill_text.rstrip() +
        "\n\nTRANSFER CASE\n-------------\n" +
        json.dumps(public_case, indent=2, ensure_ascii=False) + "\n"
    )


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    os.replace(temp, path)


def run(case_path: Path, skill_path: Path, output_path: Path, model: str,
        timeout_seconds: int) -> dict[str, Any]:
    case = json.loads(case_path.read_text())
    skill_text = skill_path.read_text()
    prompt = build_prompt(case, skill_text)
    model_meta = get_model_metadata(model)
    ollama = shutil.which("ollama")
    if not ollama:
        raise RuntimeError("ollama executable not found")
    command = [
        str(Path(ollama).resolve()), "run", model, "--format", "json",
        "--hidethinking", "--think=false", "--nowordwrap", "--keepalive", "0",
    ]
    version = subprocess.run(
        [str(Path(ollama).resolve()), "--version"], text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10,
    ).stdout.strip()

    frozen_at = utc_now()
    frozen_inputs = {
        "frozen_at": frozen_at,
        "case_path": str(case_path),
        "case_hash_algorithm": "canonical-json-sort-keys-compact-utf8-v1",
        "case_hash": sha256(canonical_json_bytes(case)),
        "skill_path": str(skill_path),
        "skill_hash_algorithm": "utf8-normalized-lf-v1",
        "skill_hash": sha256(canonical_text_bytes(skill_text)),
    }

    env = os.environ.copy()
    env["OLLAMA_NOHISTORY"] = "1"
    started_at = utc_now()
    started = time.monotonic()
    timed_out = False
    try:
        completed = subprocess.run(
            command, input=prompt, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=timeout_seconds, env=env,
        )
        process_exit = completed.returncode
        raw_stdout = completed.stdout
        raw_stderr = completed.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        process_exit = 124
        raw_stdout = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        raw_stderr = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
    duration_ms = round((time.monotonic() - started) * 1000)
    finished_at = utc_now()

    parsed_response = None
    parse_error = None
    scoring = None
    try:
        parsed_response = extract_json_object(raw_stdout)
        scoring = score_response(case, parsed_response)
    except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        parse_error = f"{type(exc).__name__}: {exc}"

    eligible = promotion_eligible(process_exit, parse_error, scoring)
    result = {
        "schema_version": 2,
        "case_id": case["case_id"],
        "run": {
            "executor": model,
            "executor_tier": case["executor_tier"],
            "transport": "local Ollama CLI",
            "egress": False,
            "fresh_context": True,
            "fresh_context_mechanism": "one-shot subprocess with OLLAMA_NOHISTORY=1 and prompt on stdin",
            "model": model_meta,
            "ollama_version": version,
            "command_argv": command,
            "command_shell": shlex.join(command) + " <PROMPT_ON_STDIN>",
            "timeout_seconds": timeout_seconds,
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_ms": duration_ms,
            "process_exit": process_exit,
            "timed_out": timed_out,
        },
        "frozen_inputs": frozen_inputs,
        "io_evidence": {
            "raw_prompt": prompt,
            "prompt_hash": sha256(prompt.encode("utf-8")),
            "raw_stdout": raw_stdout,
            "stdout_hash": sha256(raw_stdout.encode("utf-8")),
            "raw_stderr": raw_stderr,
            "stderr_hash": sha256(raw_stderr.encode("utf-8")),
        },
        "parsed_response": parsed_response,
        "parse_error": parse_error,
        "scoring": scoring,
        "verdict": "promotion_gate_passed" if eligible else "not_promotion_eligible",
        "promotion_eligible": eligible,
        "promotion_action": (
            "none; evidence may be presented for human review, but this runner never changes skill status"
            if eligible else
            "none; retain proposed and disabled status"
        ),
    }
    write_json_atomic(output_path, result)
    return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", type=Path, default=DEFAULT_CASE)
    parser.add_argument("--skill", type=Path, default=DEFAULT_SKILL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args(argv)
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    try:
        result = run(args.case, args.skill, args.output, args.model, args.timeout_seconds)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    scoring = result.get("scoring") or {}
    print(json.dumps({
        "output": str(args.output),
        "verdict": result["verdict"],
        "promotion_eligible": result["promotion_eligible"],
        "criteria_passed": scoring.get("criteria_passed", 0),
        "criteria_total": scoring.get("criteria_total", 0),
        "blocking_criteria": scoring.get("blocking_criteria", []),
    }, indent=2))
    return 0 if result["promotion_eligible"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
