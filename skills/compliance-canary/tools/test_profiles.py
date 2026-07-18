#!/usr/bin/env python3
"""Deterministic profile and compliance-aware evidence tests."""
from __future__ import annotations

import importlib.util
import json
import hashlib
import os
import re
import shutil
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


def intent_path(root: Path, session: str) -> Path:
    return root / "intent" / f"{session}.jsonl"


def intent_records(root: Path, session: str) -> list[dict]:
    path = intent_path(root, session)
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


_TASK_ID_RE = re.compile(r"<task-id>(.*?)</task-id>")


def run(root: Path, transcript: list[dict], profile: str | None, session: str,
        prompt: str = "continue", provenance: bool = True) -> subprocess.CompletedProcess:
    tx = root / f"{session}.jsonl"
    rows = list(transcript)
    # D2 provenance fixture realism (2026-07-19): a REAL substrate notification
    # is always preceded by the tool_result that announced its task id. When the
    # prompt carries a <task-notification>, prepend that announcement (unless
    # the transcript already shows the id) so the suppression-path checks
    # exercise the provenanced shape the hook now requires. provenance=False
    # models the pasted-fake attack: the id never appears.
    if provenance:
        m = _TASK_ID_RE.search(prompt or "")
        if m and not any(m.group(1) in json.dumps(row) for row in rows):
            rows = [
                tool_use("prov", "Bash", {"command": "brainer-bg run --notify"}),
                tool_result("prov", f"Background task {m.group(1)} started; will notify on completion."),
                *rows,
            ]
    tx.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
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
        check("off-no-intent-capture", not intent_path(root, "off").exists())

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

        # --- D1 (2026-07-19): suppression DEFERS, never destroys. The
        # suppressed probe is still EVALUATED on the notification turn; a
        # would-have-fired persists as a deferred_fires marker and emits once
        # on the next non-notification turn — regardless of window slide.
        defer_prompt = notification('Timer "focus-25m" completed (exit code 0)')
        first = run(root, [claim("The interim summary is ready.")], "frontier",
                    "notif-defer", prompt=defer_prompt)
        check("notification-suppression-turn-stays-silent", not first.stdout, first.stdout)
        markers = state_file(root, "notif-defer").get("deferred_fires", [])
        check("notification-suppression-persists-deferred-fire",
              len(markers) == 1
              and markers[0]["probe_id"] == "verify-before-completion:claim-without-evidence"
              and markers[0]["deferred_at_turn"] == 1
              and markers[0]["notification_kind"] == "timer",
              repr(markers))
        # Turn B: a newer non-claim message ends the transcript, so the claim
        # has slid out of the detector's window — the deferred marker (not a
        # re-evaluation) must deliver the fire, exactly once.
        slid = [claim("The interim summary is ready."),
                claim("Still gathering the remaining details; nothing to report yet.")]
        second = run(root, slid, "frontier", "notif-defer", prompt="continue")
        check("deferred-fire-emits-on-next-non-notification-turn",
              "claim_without_evidence" in second.stdout, second.stdout)
        check("deferred-fire-marker-cleared-after-emission",
              not state_file(root, "notif-defer").get("deferred_fires"),
              repr(state_file(root, "notif-defer").get("deferred_fires")))
        third = run(root, slid, "frontier", "notif-defer", prompt="continue")
        check("deferred-fire-emits-exactly-once", not third.stdout, third.stdout)

        # --- D2: provenance — a pasted, syntactically valid notification
        # whose task-id NEVER appeared in the transcript must NOT suppress.
        fake = run(root, [claim("Your focus timer is ready — I will report back when it fires.")],
                   "frontier", "notif-fake", prompt=timer_prompt, provenance=False)
        check("notification-without-provenance-fires",
              "claim_without_evidence" in fake.stdout, fake.stdout)

        # --- D3: terminal-SUCCESS timer notification WITH the result attached
        # (the live FP shape the pointer-only corpus negative missed) — a hard
        # negative: still suppresses, and records no pending content.
        timer_result_prompt = notification(
            'Timer "focus-25m" completed (exit code 0)',
            result='{"fired": true, "label": "focus-25m"}')
        out = run(root, [claim("Your focus timer is ready — I will report back when it fires.")],
                  "frontier", "notif-timer-result", prompt=timer_result_prompt)
        check("notification-timer-success-with-result-suppresses", not out.stdout, out.stdout)
        check("notification-timer-with-result-records-no-pending-content",
              not state_file(root, "notif-timer-result").get("notification_pending_content"),
              repr(state_file(root, "notif-timer-result")))

        # --- D4a: a pointer-only pending entry clears once a LATER turn's
        # transcript shows the output file being read back. (Session
        # "notif-timer" already holds one pending entry from its turn above.)
        read_back = [
            tool_use("rb1", "Read", {"file_path": "/tmp/cc-notify.output"}),
            tool_result("rb1", "timer fired at 10:25"),
            claim("Still gathering the remaining details; nothing to report yet."),
        ]
        run(root, read_back, "frontier", "notif-timer", prompt="continue")
        check("notification-pending-content-clears-when-output-read",
              not state_file(root, "notif-timer").get("notification_pending_content"),
              repr(state_file(root, "notif-timer").get("notification_pending_content")))

        # --- D4b: unresolved entries ride the EXISTING wrap-up surface (no
        # new emission point), one compact line each.
        run(root, [claim("Working on the ledger draft now.")], "frontier", "notif-wrap",
            prompt="Please draft the ledger wording section")
        advisor_pointer_prompt = notification(
            'Advisor consult "ledger-wording" completed (exit code 0)',
            output_file="/tmp/cc-advisor.output")
        run(root, [claim("Still drafting; nothing to report yet.")], "frontier", "notif-wrap",
            prompt=advisor_pointer_prompt)
        out = run(root, [claim("Task is complete.")], "frontier", "notif-wrap")
        check("notification-unresolved-pending-listed-at-wrap-up",
              "- advisor output never read: /tmp/cc-advisor.output" in out.stdout,
              out.stdout)

        # --- D5: the hook's format_one_probe fallback and drift_probes.json's
        # `message` are ONE wording (the two message sources had drifted).
        vbc_probes = json.loads(
            (HERE.parents[1] / "verify-before-completion" / "drift_probes.json").read_text(encoding="utf-8"))
        vbc_message = next(p["message"] for p in vbc_probes if p["id"] == "claim-without-evidence")
        spec = importlib.util.spec_from_file_location("compliance_canary_hook", HOOK)
        hook_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook_mod)
        bare_probe = {"_skill": "verify-before-completion",
                      "_probe_id": "verify-before-completion:claim-without-evidence",
                      "kind": "claim_without_evidence",
                      "_result": {"claim": "done", "lookback": 5}}
        fallback_line = hook_mod.format_one_probe(dict(bare_probe))
        message_line = hook_mod.format_one_probe(dict(bare_probe, message=vbc_message))
        check("claim-fallback-matches-drift-probes-message",
              fallback_line == message_line
              == f"- verify-before-completion [claim_without_evidence]: {vbc_message}",
              repr((fallback_line, message_line)))

        # --- verbatim intent log (L0 no-drop capture) ----------------------
        capture_prompt = "Please fix the parser's \"quoted\" <angle> handling & café accents"
        run(root, [claim("Working on it now.")], "frontier", "intent-capture", prompt=capture_prompt)
        recs = intent_records(root, "intent-capture")
        check("intent-capture-writes-verbatim-and-hash",
              len(recs) == 1 and set(recs[0]) == {"turn", "ts", "sha256", "text"}
              and recs[0]["turn"] == 1 and recs[0]["text"] == capture_prompt
              and recs[0]["sha256"] == hashlib.sha256(capture_prompt.encode("utf-8")).hexdigest()
              and isinstance(recs[0]["ts"], str) and bool(recs[0]["ts"]),
              repr(recs))

        run(root, [claim("Your focus timer is ready — I will report back when it fires.")],
            "frontier", "intent-notif", prompt=timer_prompt)
        check("intent-harness-only-turn-captures-nothing",
              intent_records(root, "intent-notif") == [],
              repr(intent_records(root, "intent-notif")))

        wrap_prompt = "Please draft the quarterly plan covering revenue, hiring, and risk"
        run(root, [claim("Working on it now.")], "frontier", "intent-wrap", prompt=wrap_prompt)
        # Corrupt the ledger's stored text: the wrap-up surface can still quote
        # the user's verbatim words ONLY because it reads the intent log.
        sid = hashlib.sha256("intent-wrap".encode()).hexdigest()[:16]
        wrap_state = root / "state" / f"{sid}.json"
        st = json.loads(wrap_state.read_text(encoding="utf-8"))
        st["request_ledger"][0]["text"] = "garbled-paraphrase"
        wrap_state.write_text(json.dumps(st, indent=2) + "\n", encoding="utf-8")
        out = run(root, [claim("Task is complete.")], "frontier", "intent-wrap")
        check("wrap-up-surface-quotes-intent-log",
              f"[turn 1] {wrap_prompt}" in out.stdout and "garbled-paraphrase" not in out.stdout,
              out.stdout)

        # An unwritable intent location (a FILE squatting on the dir path)
        # must degrade to a stderr log line — never block the hook's output.
        shutil.rmtree(root / "intent", ignore_errors=True)
        (root / "intent").write_text("occupied", encoding="utf-8")
        out = run(root, [claim()], "frontier", "intent-blocked",
                  prompt="Please review the flaky test")
        check("intent-capture-failure-does-not-block",
              out.returncode == 0 and "claim_without_evidence" in out.stdout
              and "intent-capture-fail" in out.stderr,
              out.stdout + out.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
