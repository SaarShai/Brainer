#!/usr/bin/env python3
"""Execute the frozen trigger corpus through the current canary hook.

Frontier expectations are mechanism-specific: verification and genuine wrap-up
may emit; correction and error-loop cases remain semantic positives but are
expected silent because frontier intentionally suppresses those mechanisms.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from cases import trigger_cases

REPO = Path(__file__).resolve().parents[2]
HOOK = REPO / "skills" / "compliance-canary" / "tools" / "hook.py"
PROBE_RE = re.compile(r"(?m)^-\s+([\w-]+)\s*\[([\w-]+)\]:")


def event(role: str, blocks: list[dict]) -> dict:
    return {"type": role, "message": {"role": role, "content": blocks}}


def use(tid: str, name: str, inp: dict) -> dict:
    return event("assistant", [{"type": "tool_use", "id": tid, "name": name, "input": inp}])


def result(tid: str, content: str, error: bool = False) -> dict:
    return event("user", [{"type": "tool_result", "tool_use_id": tid,
                            "content": content, "is_error": error}])


def text(content: str) -> dict:
    return event("assistant", [{"type": "text", "text": content}])


def transcript_for(case: dict) -> list[dict]:
    if case["kind"] == "verification":
        claim = text("The tests pass; this is ready.")
        variant = case["evidence_variant"]
        mutation = [use("m", "Edit", {"file_path": "task.py", "old_string": "0", "new_string": "1"}),
                    result("m", "updated")]
        if variant == "none":
            return mutation + [claim]
        if variant == "failed":
            return mutation + [use("v", "Bash", {"command": "python3 check.py"}),
                               result("v", "1 failed", True), claim]
        if variant == "stale":
            return [use("v", "Bash", {"command": "python3 check.py"}), result("v", "12 passed")] + mutation + [claim]
        if variant == "wrong-class":
            return mutation + [use("v", "Bash", {"command": "curl localhost/healthz"}), result("v", "ok"), claim]
        return mutation + [use("v", "Bash", {"command": "echo status"}),
                           result("v", "tests pass; screenshot looks good"), claim]
    if case["kind"] == "correction":
        return [text("Using port 443."), event("user", [{"type": "text", "text": case["prompt"]}])]
    if case["kind"] == "error_loop":
        return [use(str(i), "Bash", {"command": "false"}) if j == 0 else result(str(i), "failed", True)
                for i in range(3) for j in range(2)]
    if case["kind"] == "already_compliant":
        return [use("m", "Edit", {"file_path": "task.py"}), result("m", "updated"),
                use("v", "Bash", {"command": "python3 check.py"}), result("v", "12 passed"),
                text("The targeted check passes after the edit; continuing with the requested summary.")]
    if case["kind"] == "wrap_up":
        return [text("All done. The task is complete.")]
    return [text("I will answer the user's informational request without claiming completion.")]


def invoke(root: Path, case: dict, profile: str, *, prompt: str | None = None) -> subprocess.CompletedProcess:
    root.mkdir(parents=True, exist_ok=True)
    tx = root / f"{case['id']}.jsonl"
    tx.write_text("".join(json.dumps(row) + "\n" for row in transcript_for(case)))
    env = {**os.environ, "COMPLIANCE_CANARY_PROFILE": profile,
           "COMPLIANCE_CANARY_STATE_DIR": str(root / "state"),
           "COMPLIANCE_CANARY_SKILLS_ROOT": str(REPO / "skills"),
           "COMPLIANCE_CANARY_TELEMETRY_PATH": str(root / "telemetry.jsonl"),
           "COMPLIANCE_CANARY_COOLDOWN": "0"}
    payload = {"session_id": f"trigger-{case['id']}", "transcript_path": str(tx),
               "hook_event_name": "UserPromptSubmit", "prompt": prompt or case["prompt"]}
    return subprocess.run(["python3", str(HOOK)], input=json.dumps(payload), text=True,
                          capture_output=True, env=env, timeout=15)


def run_case(root: Path, case: dict, profile: str) -> dict:
    telemetry = root / "telemetry.jsonl"
    before_lines = len(telemetry.read_text().splitlines()) if telemetry.is_file() else 0
    if case["kind"] == "wrap_up":
        invoke(root, case, profile, prompt=f"Please complete deliverable {case['id']} before stopping.")
    proc = invoke(root, case, profile)
    encoded = proc.stdout.encode()
    probes = sorted({f"{a}:{b}" for a, b in PROBE_RE.findall(proc.stdout)})
    any_emitted = bool(proc.stdout.strip())
    if case["mechanism"] == "verification":
        mechanism_fired = "claim_without_evidence" in proc.stdout
    elif case["mechanism"] == "pending-intent-wrap":
        mechanism_fired = "compliance-canary ledger" in proc.stdout and "still OPEN" in proc.stdout
    else:
        mechanism_fired = any_emitted
    expected = case["profile_expect"][profile] == "fire"
    new_telemetry = []
    if telemetry.is_file():
        for line in telemetry.read_text().splitlines()[before_lines:]:
            try:
                new_telemetry.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    suppressed = sorted({r.get("probe_id") for r in new_telemetry if not r.get("emitted") and r.get("probe_id")})
    return {"id": case["id"], "kind": case["kind"], "mechanism": case["mechanism"],
            "expected": expected, "fired": mechanism_fired if expected else any_emitted,
            "any_emitted": any_emitted, "mechanism_fired": mechanism_fired,
            "suppressed_probe_ids": suppressed,
            "returncode": proc.returncode, "stdout_utf8_bytes": len(encoded),
            "stdout_sha256": hashlib.sha256(encoded).hexdigest(), "probe_ids": probes}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", choices=["frontier", "shadow", "legacy", "off"], default="frontier")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    corpus = trigger_cases()[:args.limit]
    with tempfile.TemporaryDirectory(prefix="brainer-trigger-gate-") as tmp:
        root = Path(tmp)
        rows = []
        for case in corpus:
            row = run_case(root / args.profile, case, args.profile)
            if args.profile == "shadow":
                reference = run_case(root / "frontier-reference", case, "frontier")
                row["frontier_output_identical"] = row["stdout_sha256"] == reference["stdout_sha256"]
            rows.append(row)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    return 0 if all(row["returncode"] == 0 for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
