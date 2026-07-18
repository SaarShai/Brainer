#!/usr/bin/env python3
"""Deterministic profile and compliance-aware evidence tests."""
from __future__ import annotations

import json
import hashlib
import os
import subprocess
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
HOOK = HERE / "hook.py"


def event(role: str, blocks: list[dict]) -> dict:
    return {"type": role, "message": {"role": "assistant" if role == "assistant" else "user", "content": blocks}}


def tool_use(tid: str, name: str, inp: dict) -> dict:
    return event("assistant", [{"type": "tool_use", "id": tid, "name": name, "input": inp}])


def tool_result(tid: str, text: str, error: bool = False) -> dict:
    return event("user", [{"type": "tool_result", "tool_use_id": tid, "content": text, "is_error": error}])


def claim(text: str = "The tests pass; this is ready.") -> dict:
    return event("assistant", [{"type": "text", "text": text}])


def notification(summary: str, status: str = "completed", result: str | None = None,
                 output_file: str | None = "/tmp/cc-notify.output") -> str:
    """Harness-shaped <task-notification> UserPromptSubmit payload."""
    lines = ["<task-notification>", "<task-id>t-1</task-id>",
             "<tool-use-id>toolu_t1</tool-use-id>"]
    if output_file:
        lines.append(f"<output-file>{output_file}</output-file>")
    lines.append(f"<status>{status}</status>")
    lines.append(f"<summary>{summary}</summary>")
    if result is not None:
        lines.append(f"<result>{result}</result>")
    lines.append("</task-notification>")
    return "\n".join(lines)


def state_file(root: Path, session: str) -> dict:
    sid = hashlib.sha256(session.encode()).hexdigest()[:16]
    path = root / "state" / f"{sid}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def telemetry_records(root: Path, session: str) -> list[dict]:
    path = root / "telemetry.jsonl"
    if not path.is_file():
        return []
    sid = hashlib.sha256(session.encode()).hexdigest()[:16]
    return [row for row in (json.loads(line) for line in path.read_text().splitlines())
            if row.get("session_hash") == sid]


def run(root: Path, transcript: list[dict], profile: str | None, session: str,
        prompt: str = "continue") -> subprocess.CompletedProcess:
    tx = root / f"{session}.jsonl"
    tx.write_text("".join(json.dumps(row) + "\n" for row in transcript), encoding="utf-8")
    env = os.environ.copy()
    env.update({
        "COMPLIANCE_CANARY_STATE_DIR": str(root / "state"),
        "COMPLIANCE_CANARY_SKILLS_ROOT": str(root / "skills"),
        "COMPLIANCE_CANARY_TELEMETRY_PATH": str(root / "telemetry.jsonl"),
        "COMPLIANCE_CANARY_COOLDOWN": "0",
    })
    if profile is None:
        env.pop("COMPLIANCE_CANARY_PROFILE", None)
    else:
        env["COMPLIANCE_CANARY_PROFILE"] = profile
    payload = {"session_id": session, "transcript_path": str(tx), "prompt": prompt}
    return subprocess.run(["python3", str(HOOK)], input=json.dumps(payload), text=True,
                          capture_output=True, env=env, timeout=10)


def install_fixtures(root: Path) -> None:
    vbc = root / "skills" / "verify-before-completion"
    vbc.mkdir(parents=True)
    (vbc / "drift_probes.json").write_text(json.dumps([{
        "id": "claim-without-evidence",
        "kind": "claim_without_evidence",
        "claim_pattern": "(?i)\\b(pass|ready|done|fixed)\\b",
        "lookback_tool_uses": 6,
    }]), encoding="utf-8")
    noisy = root / "skills" / "noisy"
    noisy.mkdir(parents=True)
    (noisy / "drift_probes.json").write_text(json.dumps([{
        "id": "filler", "kind": "forbidden_regex", "pattern": "(?i)certainly"
    }]), encoding="utf-8")


def check(name: str, condition: bool, detail: str = "") -> None:
    if not condition:
        raise AssertionError(f"{name}: {detail}")
    print(f"PASS {name}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="cc-profile-") as tmp:
        root = Path(tmp)
        install_fixtures(root)

        off = run(root, [claim()], "off", "off")
        check("off-silent", off.returncode == 0 and not off.stdout, off.stderr)
        check("off-no-state-mutation", not (root / "state").exists())
        check("off-no-telemetry-mutation", not (root / "telemetry.jsonl").exists())

        no_evidence = run(root, [claim()], None, "default-frontier")
        check("default-is-frontier-and-fires", "claim_without_evidence" in no_evidence.stdout,
              no_evidence.stdout)

        fresh_success = [
            tool_use("m1", "Edit", {"file_path": "x.py", "old_string": "a", "new_string": "b"}),
            tool_result("m1", "updated"),
            tool_use("v1", "Bash", {"command": "pytest -q"}),
            tool_result("v1", "12 passed"),
            claim(),
        ]
        ok = run(root, fresh_success, "frontier", "fresh")
        check("successful-post-mutation-matching-evidence-suppresses", not ok.stdout, ok.stdout)

        check_script = [
            tool_use("m-check", "Edit", {"file_path": "x.py", "old_string": "a", "new_string": "b"}),
            tool_result("m-check", "updated"),
            tool_use("v-check", "Bash", {"command": "python3 check.py"}),
            tool_result("v-check", "PASS"), claim(),
        ]
        ok = run(root, check_script, "frontier", "check-script")
        check("executed-check-script-suppresses", not ok.stdout, ok.stdout)

        zero_failed = fresh_success[:-2] + [tool_result("v1", "12 passed, 0 failed"), claim()]
        ok = run(root, zero_failed, "frontier", "zero-failed")
        check("zero-failed-summary-is-success", not ok.stdout, ok.stdout)

        failed = fresh_success[:-3] + [
            tool_use("v2", "Bash", {"command": "pytest -q"}),
            tool_result("v2", "1 failed", True), claim(),
        ]
        out = run(root, failed, "frontier", "failed")
        check("failed-evidence-fires", "claim_without_evidence" in out.stdout, out.stdout)

        stale = [
            tool_use("v3", "Bash", {"command": "pytest -q"}), tool_result("v3", "12 passed"),
            tool_use("m3", "Edit", {"file_path": "x.py", "old_string": "a", "new_string": "b"}),
            tool_result("m3", "updated"), claim(),
        ]
        out = run(root, stale, "frontier", "stale")
        check("pre-mutation-evidence-fires", "claim_without_evidence" in out.stdout, out.stdout)

        wrong = [
            tool_use("v4", "Bash", {"command": "curl localhost:8000/healthz"}),
            tool_result("v4", "ok"), claim(),
        ]
        out = run(root, wrong, "frontier", "wrong")
        check("wrong-evidence-class-fires", "claim_without_evidence" in out.stdout, out.stdout)

        incidental = [
            tool_use("v5", "Bash", {"command": "echo status"}),
            tool_result("v5", "tests pass; server healthy; screenshot looks good"), claim(),
        ]
        out = run(root, incidental, "frontier", "incidental")
        check("incidental-result-keywords-do-not-create-evidence", "claim_without_evidence" in out.stdout,
              out.stdout)
        incidental_path = [
            tool_use("v6", "Bash", {"command": "cat test-results.txt"}),
            tool_result("v6", "12 passed"), claim(),
        ]
        out = run(root, incidental_path, "frontier", "incidental-path")
        check("incidental-command-path-does-not-create-test-evidence",
              "claim_without_evidence" in out.stdout, out.stdout)
        quoted_check = [
            tool_use("v7", "Bash", {"command": "echo python3 check.py"}),
            tool_result("v7", "python3 check.py"), claim(),
        ]
        out = run(root, quoted_check, "frontier", "quoted-check")
        check("mentioned-check-script-is-not-execution-evidence",
              "claim_without_evidence" in out.stdout, out.stdout)

        # Pending intent must exist before a genuine wrap-up. A single isolated
        # completion fixture is not a ledger test because there is no prior ask.
        first = run(root, [claim("Work is in progress.")], "frontier", "wrap-up",
                    prompt="Please implement feature X")
        check("pending-intent-capture-is-silent", not first.stdout, first.stdout)
        second = run(root, [claim("Task is complete.")], "frontier", "wrap-up")
        check("genuine-wrap-up-surfaces-pending-intent",
              "request(s) are still OPEN" in second.stdout, second.stdout)

        mixed = [claim("Certainly. The tests pass; this is ready.")]
        frontier = run(root, mixed, "frontier", "frontier-equivalence")
        shadow = run(root, mixed, "shadow", "shadow-equivalence")
        check("shadow-frontier-output-equivalence", shadow.stdout == frontier.stdout,
              f"frontier={frontier.stdout!r} shadow={shadow.stdout!r}")
        frontier_repeat = run(root, mixed, "frontier", "frontier-equivalence")
        shadow_repeat = run(root, mixed, "shadow", "shadow-equivalence")
        check("shadow-repeat-keeps-task-output-equivalent", shadow_repeat.stdout == frontier_repeat.stdout,
              shadow_repeat.stdout)
        records = [json.loads(line) for line in (root / "telemetry.jsonl").read_text().splitlines()]
        suppressed = [r for r in records if r["session_hash"] and r["probe_id"] == "noisy:filler"]
        check("shadow-logs-every-suppressed-repeat", len(suppressed) == 2 and
              all(not row["emitted"] for row in suppressed))
        check("telemetry-schema-redacted", all(set(r) == {
            "session_hash", "turn", "mechanism", "probe_id", "emitted",
            "injected_bytes", "content_hash"
        } for r in records))

        # --- notification evidence boundary (2026-07-18) -------------------
        timer_prompt = notification('Timer "focus-25m" completed (exit code 0)')
        out = run(root, [claim("Your focus timer is ready — I will report back when it fires.")],
                  "frontier", "notif-timer", prompt=timer_prompt)
        check("notification-timer-success-suppresses", not out.stdout, out.stdout)
        suppressed = [r for r in telemetry_records(root, "notif-timer")
                      if r["mechanism"] == "suppressed_notification"]
        check("notification-suppression-telemetry-logged",
              len(suppressed) == 1 and not suppressed[0]["emitted"]
              and suppressed[0]["probe_id"] == "verify-before-completion:claim-without-evidence",
              repr(suppressed))
        pending = state_file(root, "notif-timer").get("notification_pending_content", [])
        check("notification-pointer-only-records-pending-content",
              len(pending) == 1 and pending[0]["output_file"] == "/tmp/cc-notify.output"
              and pending[0]["turn"] == 1 and bool(pending[0]["recorded_iso"]),
              repr(pending))

        advisor_prompt = notification(
            'Advisor consult "ledger-wording" completed (exit code 0)',
            result='{"recommendation": "tighten the ledger wording"}')
        out = run(root, [claim("The background advisor consult is done.")],
                  "frontier", "notif-advisor", prompt=advisor_prompt)
        check("notification-advisor-success-with-result-suppresses", not out.stdout, out.stdout)
        check("notification-with-result-records-no-pending-content",
              not state_file(root, "notif-advisor").get("notification_pending_content"))

        failed_prompt = notification('Background command "python3 check.py" failed (exit code 1)',
                                     status="failed")
        out = run(root, [claim("The background re-index is done and everything is ready.")],
                  "frontier", "notif-failed", prompt=failed_prompt)
        check("notification-failed-job-still-fires",
              "claim_without_evidence" in out.stdout, out.stdout)

        subagent_prompt = notification(
            'Dynamic workflow "implement-feature" completed',
            result="Files moved into place; tests pass. DONE — READY FOR JUDGING.")
        out = run(root, [claim("The implementation subagent finished: files are moved and tests pass — this is done and ready.")],
                  "frontier", "notif-subagent", prompt=subagent_prompt)
        check("notification-subagent-worldstate-still-fires",
              "claim_without_evidence" in out.stdout, out.stdout)

        mixed_prompt = timer_prompt + "\nplease also review the draft"
        out = run(root, [claim("Your focus timer is ready — I will report back when it fires.")],
                  "frontier", "notif-mixed", prompt=mixed_prompt)
        check("notification-with-user-remainder-still-fires",
              "claim_without_evidence" in out.stdout, out.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
