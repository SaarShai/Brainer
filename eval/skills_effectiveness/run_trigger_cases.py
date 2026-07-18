#!/usr/bin/env python3
"""Execute the frozen trigger corpus through the current canary hook.

Frontier expectations are mechanism-specific: verification and genuine wrap-up
may emit; correction and error-loop cases remain semantic positives but are
expected silent because frontier intentionally suppresses those mechanisms.
Notification cases (2026-07-18) expect frontier/shadow silent on terminal-
SUCCESS self-contained job notifications and firing on failed jobs and on
forwarded implementation-subagent world-state claims. Hardening cases
(2026-07-19, lane A2): neg-n3 adds the result-ATTACHED timer hard negative
(the live FP shape); pos-p3 must fire on an unprovenanced (pasted)
notification whose task-id never appears in the transcript; pos-d1 is a
TWO-TURN deferred-fire sequence — turn A carries an unverified claim plus a
qualifying provenanced notification (frontier/shadow must NOT emit;
suppression defers), turn B is a plain non-notification turn whose transcript
has slid the claim out of the message window (frontier/shadow MUST emit
exactly once via the persisted deferred_fire marker; legacy keeps its
pre-boundary behavior and fires immediately at turn A).
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


_TASK_ID_RE = re.compile(r"<task-id>(.*?)</task-id>")


def _prompt_task_id(prompt: str) -> str:
    m = _TASK_ID_RE.search(prompt or "")
    return m.group(1) if m else ""


def _provenance_events(task_id: str) -> list[dict]:
    """The substrate announcement a REAL background-task notification is
    always preceded by: the tool_result naming its task id (D2 provenance).
    The command/result carry no verification-evidence class, so the paired
    claim stays unverified."""
    return [use("bg", "Bash", {"command": "brainer-timer start focus-25m"}),
            result("bg", f"Background task {task_id} started; will notify on completion.")]


def transcript_for(case: dict, turn: str = "a") -> list[dict]:
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
    # Notification-boundary cases: the case PROMPT carries the harness
    # <task-notification>; the transcript ends on an assistant message whose
    # claim word would trip claim_without_evidence unless the notification
    # evidence boundary suppresses it (neg-n1/neg-n2/neg-n3) — and keeps
    # tripping it where the boundary must stay armed (pos-p1 failed job,
    # pos-p2 forwarded implementation-subagent world-state claim, pos-p3
    # pasted/unprovenanced notification). Suppression-path kinds (n1/n2/n3)
    # include the substrate's task-id announcement EARLIER in the transcript —
    # the D2 provenance anchor a real notification always has; pos-p3
    # deliberately omits it (the pasted-fake attack).
    if case["kind"] in {"notification_timer_success", "notification_timer_result"}:
        return _provenance_events(_prompt_task_id(case["prompt"])) + [
            text("Your 25-minute focus timer is ready — I will report back when it fires.")]
    if case["kind"] == "notification_advisor_success":
        return _provenance_events(_prompt_task_id(case["prompt"])) + [
            text("The background advisor consult is done; I will fold its recommendation into the draft.")]
    if case["kind"] == "notification_unprovenanced":
        return [text("Your 25-minute focus timer is ready — I will report back when it fires.")]
    if case["kind"] == "notification_deferred_fire":
        base = _provenance_events(_prompt_task_id(case["prompt"])) + [
            text("The focus timer is set and the interim summary is ready.")]
        if turn == "b":
            # The claim has slid out of the detector's recent-message window:
            # only the persisted deferred_fire marker can deliver the fire.
            return base + [text("Still gathering the remaining details; nothing to report yet.")]
        return base
    if case["kind"] == "notification_failed_claim":
        return [text("The background re-index is done and everything is ready.")]
    if case["kind"] == "notification_subagent_forwarded":
        return [text("The implementation subagent finished: files are moved and tests pass — this is done and ready.")]
    return [text("I will answer the user's informational request without claiming completion.")]


def invoke(root: Path, case: dict, profile: str, *, prompt: str | None = None,
           turn: str = "a") -> subprocess.CompletedProcess:
    root.mkdir(parents=True, exist_ok=True)
    tx = root / f"{case['id']}.{turn}.jsonl"
    tx.write_text("".join(json.dumps(row) + "\n" for row in transcript_for(case, turn)))
    env = {**os.environ, "COMPLIANCE_CANARY_PROFILE": profile,
           "COMPLIANCE_CANARY_STATE_DIR": str(root / "state"),
           "COMPLIANCE_CANARY_SKILLS_ROOT": str(REPO / "skills"),
           "COMPLIANCE_CANARY_TELEMETRY_PATH": str(root / "telemetry.jsonl"),
           "COMPLIANCE_CANARY_COOLDOWN": "0"}
    payload = {"session_id": f"trigger-{case['id']}", "transcript_path": str(tx),
               "hook_event_name": "UserPromptSubmit",
               "prompt": prompt or (case["prompt"] if turn == "a"
                                    else case.get("prompt_b", "continue"))}
    return subprocess.run(["python3", str(HOOK)], input=json.dumps(payload), text=True,
                          capture_output=True, env=env, timeout=15)


def _run_deferred_case(root: Path, case: dict, profile: str,
                       telemetry: Path, before_lines: int) -> dict:
    """Two-turn D1 sequence. Turn A: unverified claim + qualifying provenanced
    notification — frontier/shadow must stay silent (suppression DEFERS the
    fire). Turn B: non-notification prompt, claim slid out of the message
    window — frontier/shadow must emit exactly once via the persisted
    deferred_fire marker. legacy has no notification boundary: its correct
    behavior is the IMMEDIATE fire at turn A. `fired` folds the sequence into
    the gate's binary shape: for an expected-fire profile it is the
    profile-correct composite; for an expected-silent profile it is any
    emission on either turn."""
    proc_a = invoke(root, case, profile, turn="a")
    proc_b = invoke(root, case, profile, turn="b")
    turn_a_any = bool(proc_a.stdout.strip())
    turn_b_any = bool(proc_b.stdout.strip())
    turn_a_mech = "claim_without_evidence" in proc_a.stdout
    turn_b_mech = "claim_without_evidence" in proc_b.stdout
    expected = case["profile_expect"][profile] == "fire"
    mechanism_fired = turn_a_mech if profile == "legacy" else (not turn_a_any) and turn_b_mech
    any_emitted = turn_a_any or turn_b_any
    encoded = proc_a.stdout.encode() + b"\x00" + proc_b.stdout.encode()
    probes = sorted({f"{a}:{b}" for a, b in
                     PROBE_RE.findall(proc_a.stdout + proc_b.stdout)})
    new_telemetry = []
    if telemetry.is_file():
        for line in telemetry.read_text().splitlines()[before_lines:]:
            try:
                new_telemetry.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    suppressed = sorted({r.get("probe_id") for r in new_telemetry
                         if not r.get("emitted") and r.get("probe_id")})
    return {"id": case["id"], "kind": case["kind"], "mechanism": case["mechanism"],
            "expected": expected,
            "fired": mechanism_fired if expected else any_emitted,
            "any_emitted": any_emitted, "mechanism_fired": mechanism_fired,
            "turn_a_any_emitted": turn_a_any, "turn_b_any_emitted": turn_b_any,
            "turn_a_mechanism_fired": turn_a_mech,
            "turn_b_mechanism_fired": turn_b_mech,
            "suppressed_probe_ids": suppressed,
            "returncode": proc_a.returncode or proc_b.returncode,
            "stdout_utf8_bytes": len(encoded),
            "stdout_sha256": hashlib.sha256(encoded).hexdigest(), "probe_ids": probes}


def run_case(root: Path, case: dict, profile: str) -> dict:
    telemetry = root / "telemetry.jsonl"
    before_lines = len(telemetry.read_text().splitlines()) if telemetry.is_file() else 0
    if case["kind"] == "wrap_up":
        invoke(root, case, profile, prompt=f"Please complete deliverable {case['id']} before stopping.")
    if case["kind"] == "notification_deferred_fire":
        return _run_deferred_case(root, case, profile, telemetry, before_lines)
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
