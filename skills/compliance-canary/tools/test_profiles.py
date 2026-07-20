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
import sys
import tempfile
import time
import types
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
                 output_file: str | None = "/tmp/cc-notify.output",
                 task_id: str = "task-t1") -> str:
    """Harness-shaped <task-notification> UserPromptSubmit payload. task_id
    defaults to a realistic >=6-char substrate id (F1 entropy floor: shorter
    ids fail provenance open by design)."""
    lines = ["<task-notification>", f"<task-id>{task_id}</task-id>",
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


def visible_ledger_path(root: Path, session: str) -> Path:
    sid = hashlib.sha256(session.encode()).hexdigest()[:16]
    return root / "ledger" / f"{sid}.md"


_TASK_ID_RE = re.compile(r"<task-id>(.*?)</task-id>")


def run(root: Path, transcript: list[dict], profile: str | None, session: str | None,
        prompt: str = "continue", provenance: bool = True,
        extra_env: dict | None = None) -> subprocess.CompletedProcess:
    tx = root / f"{session if session is not None else 'anon'}.jsonl"
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
        # Pin the project anchor to the isolated fixture root so a host
        # repo's real armed task-retrospective current.json can't arm the
        # correction ledger under an "unarmed" test (live farey-hecke
        # failure, 2026-07-20). extra_env below can still override.
        "CLAUDE_PROJECT_DIR": str(root),
    })
    if profile is None:
        env.pop("COMPLIANCE_CANARY_PROFILE", None)
    else:
        env["COMPLIANCE_CANARY_PROFILE"] = profile
    if extra_env:
        env.update(extra_env)
    payload = {"transcript_path": str(tx), "prompt": prompt}
    if session is not None:
        payload["session_id"] = session
    return subprocess.run(["python3", str(HOOK)], input=json.dumps(payload), text=True,
                          capture_output=True, env=env, timeout=10)


def install_fixtures(root: Path) -> None:
    # Named "compliance-canary" (not "verify-before-completion") because the
    # 2026-07-19 rehome moved the real claim-without-evidence probe there;
    # FRONTIER_VERIFY_PROBE_IDS now gates on "compliance-canary:claim-without-evidence".
    cc = root / "skills" / "compliance-canary"
    cc.mkdir(parents=True)
    (cc / "drift_probes.json").write_text(json.dumps([{
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
        check("off-no-visible-ledger", not visible_ledger_path(root, "off").exists())

        no_evidence = run(root, [claim()], None, "default-frontier")
        check("default-is-frontier-and-fires",
              no_evidence.stdout.count("[claim_without_evidence]:") == 1,
              no_evidence.stdout)
        visible = visible_ledger_path(root, "default-frontier")
        check("default-materializes-visible-ledger", visible.is_file(), str(visible))
        check("visible-ledger-captures-prompt",
              "(r1-" in visible.read_text(encoding="utf-8")
              and "continue" in visible.read_text(encoding="utf-8"),
              visible.read_text(encoding="utf-8"))
        check("visible-ledger-does-not-claim-task-status",
              "Captured does not mean unfinished" in visible.read_text(encoding="utf-8")
              and "not a task-status claim" in visible.read_text(encoding="utf-8"),
              visible.read_text(encoding="utf-8"))
        run(root, [claim()], None, "default-frontier", prompt="record the second request")
        visible_text = visible.read_text(encoding="utf-8")
        check("visible-ledger-appends-across-turns",
              visible_text.count("source=compliance-canary") == 2
              and "record the second request" in visible_text, visible_text)

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
        check("failed-evidence-fires", out.stdout.count("[claim_without_evidence]:") == 1,
              out.stdout)

        stale = [
            tool_use("v3", "Bash", {"command": "pytest -q"}), tool_result("v3", "12 passed"),
            tool_use("m3", "Edit", {"file_path": "x.py", "old_string": "a", "new_string": "b"}),
            tool_result("m3", "updated"), claim(),
        ]
        out = run(root, stale, "frontier", "stale")
        check("pre-mutation-evidence-fires", out.stdout.count("[claim_without_evidence]:") == 1,
              out.stdout)

        wrong = [
            tool_use("v4", "Bash", {"command": "curl localhost:8000/healthz"}),
            tool_result("v4", "ok"), claim(),
        ]
        out = run(root, wrong, "frontier", "wrong")
        check("wrong-evidence-class-fires", out.stdout.count("[claim_without_evidence]:") == 1,
              out.stdout)

        incidental = [
            tool_use("v5", "Bash", {"command": "echo status"}),
            tool_result("v5", "tests pass; server healthy; screenshot looks good"), claim(),
        ]
        out = run(root, incidental, "frontier", "incidental")
        check("incidental-result-keywords-do-not-create-evidence",
              out.stdout.count("[claim_without_evidence]:") == 1,
              out.stdout)
        incidental_path = [
            tool_use("v6", "Bash", {"command": "cat test-results.txt"}),
            tool_result("v6", "12 passed"), claim(),
        ]
        out = run(root, incidental_path, "frontier", "incidental-path")
        check("incidental-command-path-does-not-create-test-evidence",
              out.stdout.count("[claim_without_evidence]:") == 1,
              out.stdout)
        quoted_check = [
            tool_use("v7", "Bash", {"command": "echo python3 check.py"}),
            tool_result("v7", "python3 check.py"), claim(),
        ]
        out = run(root, quoted_check, "frontier", "quoted-check")
        check("mentioned-check-script-is-not-execution-evidence",
              out.stdout.count("[claim_without_evidence]:") == 1,
              out.stdout)

        # Pending intent must exist before a genuine wrap-up. A single isolated
        # completion fixture is not a ledger test because there is no prior ask.
        first = run(root, [claim("Work is in progress.")], "frontier", "wrap-up",
                    prompt="Please implement feature X")
        check("pending-intent-capture-is-silent", not first.stdout, first.stdout)
        second = run(root, [claim("Task is complete.")], "frontier", "wrap-up")
        check("genuine-wrap-up-surfaces-pending-intent",
              second.stdout.count("request(s) are still OPEN") == 1, second.stdout)

        # legacy/shadow are retired (2026-07-19): PROFILES = {frontier, off}.
        # A stale COMPLIANCE_CANARY_PROFILE=legacy/shadow must fail-safe
        # normalize to frontier (never crash, never silently no-op) — assert
        # byte-identical output to a genuine frontier run, plus the stderr
        # warning active_profile() logs on the fallback.
        mixed = [claim("Certainly. The tests pass; this is ready.")]
        legacy_value = run(root, mixed, "legacy", "legacy-normalizes")
        frontier_again = run(root, mixed, "frontier", "frontier-normalizes")
        check("legacy-profile-value-normalizes-to-frontier-output",
              legacy_value.stdout == frontier_again.stdout,
              f"legacy={legacy_value.stdout!r} frontier={frontier_again.stdout!r}")
        check("legacy-profile-value-logs-unknown-profile-fallback-warning",
              "unknown-profile value='legacy'" in legacy_value.stderr
              and "using frontier" in legacy_value.stderr,
              legacy_value.stderr)
        shadow_value = run(root, mixed, "shadow", "shadow-normalizes")
        check("shadow-profile-value-normalizes-to-frontier-output",
              shadow_value.stdout == frontier_again.stdout,
              f"shadow={shadow_value.stdout!r} frontier={frontier_again.stdout!r}")

        records = [json.loads(line) for line in (root / "telemetry.jsonl").read_text().splitlines()]
        check("telemetry-schema-redacted", all(set(r) == {
            "session_hash", "turn", "mechanism", "probe_id", "emitted",
            "injected_bytes", "content_hash"
        } for r in records), repr(records[:3]))

        # --- probe-ID migration alias (MINOR 1): a configured OLD id
        # `verify-before-completion:<name>` (pre-2026-07-19 rehome) still
        # selects the rehomed `compliance-canary:<name>` probe, with a
        # one-line stderr warning naming the rename; an unrecognized id is
        # unchanged (selects nothing, no crash, no warning).
        alias_claim = [
            tool_use("al1", "Bash", {"command": "echo status"}),
            tool_result("al1", "nothing relevant"),
            claim("all done"),
        ]
        aliased = run(root, alias_claim, "frontier", "probe-id-alias", extra_env={
            "COMPLIANCE_CANARY_PROBE_IDS": "verify-before-completion:claim-without-evidence"})
        check("probe-id-alias-selects-rehomed-probe",
              aliased.stdout.count("[claim_without_evidence]:") == 1, aliased.stdout)
        check("probe-id-alias-warns-on-stderr",
              "probe-id-renamed: 'verify-before-completion:claim-without-evidence' -> "
              "'compliance-canary:claim-without-evidence'" in aliased.stderr,
              aliased.stderr)
        unknown = run(root, alias_claim, "frontier", "probe-id-unknown", extra_env={
            "COMPLIANCE_CANARY_PROBE_IDS": "nonexistent-skill:some-id"})
        check("probe-id-unknown-id-selects-nothing-silently-no-warning",
              not unknown.stdout and "probe-id-renamed" not in unknown.stderr,
              (unknown.stdout, unknown.stderr))

        # --- Mechanism 4: correction ledger rehomed into frontier (2026-07-19,
        # LEARNING_CONTRACT §2) — ARMED-ONLY (2026-07-20 policy fix): an
        # earlier unconditional reading regressed the frozen 862-case frontier
        # trigger-gate corpus (FP=175, precision 65.2%). Armed (env var here;
        # test.sh's [34q] covers the task-retrospective current.json signal),
        # a correction-shaped prompt fires user_correction and opens a
        # closeout-blocking OPEN item; a banked write_gate.py call (command
        # position + a PASSED execution-evidence tool_result) resolves it and
        # stops surfacing.
        correction_skill = root / "skills" / "corrections"
        correction_skill.mkdir(parents=True)
        (correction_skill / "drift_probes.json").write_text(json.dumps([{
            "id": "uc", "kind": "user_correction",
            "pattern": r"(?i)(?:^\s*no[,. ]|i said\b)",
            "message": "harvest the correction",
        }]), encoding="utf-8")
        armed_env = {"COMPLIANCE_CANARY_CORRECTION_LEDGER": "1"}
        opened = run(root, [claim("ok, using tabs")], "frontier", "correction-rehome",
                    prompt="no, I said use spaces not tabs", extra_env=armed_env)
        check("frontier-correction-ledger-opens-on-fired-user-correction",
              "correction(s) still OPEN" in opened.stdout and "§2" in opened.stdout,
              opened.stdout)
        bank_tx = [
            tool_use("bank1", "Bash", {
                "command": "python3 skills/write-gate/tools/write_gate.py score --json --text x"}),
            tool_result("bank1", '{"verdict": "PASSED: ok"}'),
            claim("banked the lesson"),
        ]
        banked = run(root, bank_tx, "frontier", "correction-rehome", prompt="go ahead",
                    extra_env=armed_env)
        check("frontier-correction-ledger-resolves-on-banked-write-gate-call",
              "resolved 1 correction" in banked.stdout and "still OPEN" not in banked.stdout,
              banked.stdout)
        quiet = run(root, [claim("continuing")], "frontier", "correction-rehome", prompt="next",
                   extra_env=armed_env)
        check("frontier-correction-ledger-stays-quiet-once-resolved",
              "correction ledger" not in quiet.stdout, quiet.stdout)

        # --- ARMED-only boundary (2026-07-20): unarmed is fully inert — the
        # user_correction probe still opens nothing and the ledger's state
        # key is never written, even though the SAME probe fixture (sk
        # "corrections") is discovered on every run.
        unarmed = run(root, [claim("ok, using tabs")], "frontier", "correction-unarmed",
                     prompt="no, I said use spaces not tabs")
        check("unarmed-correction-ledger-stays-silent", not unarmed.stdout, unarmed.stdout)
        check("unarmed-correction-ledger-writes-no-state-key",
              "correction_ledger" not in state_file(root, "correction-unarmed"),
              repr(state_file(root, "correction-unarmed")))

        # --- ARMED context-safe matching (2026-07-20 reviewer fix) ---------
        # The raw user_correction regex matched inside quoted/fenced text
        # (2026-07-17 adversarial review: 250/400 false injections on this
        # exact class). Import the frozen corpus's exact hard-negative case
        # texts (eval/skills_effectiveness/cases.py) and run the REAL,
        # tightened task-retrospective/wiki-memory patterns armed, over both
        # the hard negatives (must stay silent) and a set of genuine
        # correction-shaped prompts (must open the ledger).
        _cases_path = HERE.parent.parent.parent / "eval" / "skills_effectiveness" / "cases.py"
        _cases_spec = importlib.util.spec_from_file_location("cc_test_cases", _cases_path)
        _cases_mod = importlib.util.module_from_spec(_cases_spec)
        _cases_spec.loader.exec_module(_cases_mod)

        for _skill_name in ("task-retrospective", "wiki-memory"):
            _src = HERE.parent.parent / _skill_name / "drift_probes.json"
            _dst_dir = root / "skills" / _skill_name
            _dst_dir.mkdir(parents=True, exist_ok=True)
            (_dst_dir / "drift_probes.json").write_text(
                _src.read_text(encoding="utf-8"), encoding="utf-8")

        armed_ctx_env = {"COMPLIANCE_CANARY_CORRECTION_LEDGER": "1"}
        HARD_NEGATIVE_KINDS = ("bare_again", "quoted_article", "code_fence")
        armed_fp = 0
        armed_neg_total = 0
        for kind in HARD_NEGATIVE_KINDS:
            for i in range(5):
                prompt = _cases_mod._NEG[kind].format(i=i)
                armed_neg_total += 1
                out = run(root, [claim("noted")], "frontier", f"ctxsafe-neg-{kind}-{i}",
                          prompt=prompt, extra_env=armed_ctx_env)
                fired_ledger = "correction(s) still OPEN" in out.stdout
                if fired_ledger:
                    armed_fp += 1
                check(f"armed-hard-negative-{kind}-{i}-ledger-silent",
                      not fired_ledger, out.stdout)
        print(f"INFO armed-hard-negative-false-positive-count={armed_fp}/{armed_neg_total}")

        genuine_corrections = [
            "No, use tabs instead of spaces.",
            "That's wrong, the port should be 8443.",
            "You were wrong about that.",
            "You didn't actually run the tests.",
            "You just assumed the config was fine.",
            "This is the second time you've made this mistake.",
            "You keep making this mistake.",
            "Every time I ask, you skip the check.",
            "I told you to use spaces, not tabs.",
            "Stop doing that.",
            "Nope, that's not right.",
            "Don't use tabs here.",
        ]
        armed_tp = 0
        for i, prompt in enumerate(genuine_corrections):
            out = run(root, [claim("ok, noted")], "frontier", f"ctxsafe-pos-{i}",
                      prompt=prompt, extra_env=armed_ctx_env)
            fired_ledger = "correction(s) still OPEN" in out.stdout and "§2" in out.stdout
            if fired_ledger:
                armed_tp += 1
            check(f"armed-genuine-correction-{i}-ledger-opens", fired_ledger, out.stdout)
        check("armed-genuine-corrections-at-least-ten", len(genuine_corrections) >= 10,
              len(genuine_corrections))
        print(f"INFO armed-genuine-correction-true-positive-count={armed_tp}/{len(genuine_corrections)}")

        # "run it again" must NOT match armed; the tightened pattern dropped
        # the bare `again` alternative entirely (2026-07-20).
        again_out = run(root, [claim("ok, noted")], "frontier", "ctxsafe-run-again",
                        prompt="run it again", extra_env=armed_ctx_env)
        check("armed-run-it-again-stays-silent",
              "correction(s) still OPEN" not in again_out.stdout, again_out.stdout)

        # --- notification evidence boundary (2026-07-18) -------------------
        timer_prompt = notification('Timer "focus-25m" completed (exit code 0)')
        out = run(root, [claim("Your focus timer is ready — I will report back when it fires.")],
                  "frontier", "notif-timer", prompt=timer_prompt)
        check("notification-timer-success-suppresses", not out.stdout, out.stdout)
        suppressed = [r for r in telemetry_records(root, "notif-timer")
                      if r["mechanism"] == "suppressed_notification"]
        check("notification-suppression-telemetry-logged",
              len(suppressed) == 1 and not suppressed[0]["emitted"]
              and suppressed[0]["probe_id"] == "compliance-canary:claim-without-evidence",
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
              out.stdout.count("[claim_without_evidence]:") == 1, out.stdout)

        subagent_prompt = notification(
            'Dynamic workflow "implement-feature" completed',
            result="Files moved into place; tests pass. DONE — READY FOR JUDGING.")
        out = run(root, [claim("The implementation subagent finished: files are moved and tests pass — this is done and ready.")],
                  "frontier", "notif-subagent", prompt=subagent_prompt)
        check("notification-subagent-worldstate-still-fires",
              out.stdout.count("[claim_without_evidence]:") == 1, out.stdout)

        mixed_prompt = timer_prompt + "\nplease also review the draft"
        out = run(root, [claim("Your focus timer is ready — I will report back when it fires.")],
                  "frontier", "notif-mixed", prompt=mixed_prompt)
        check("notification-with-user-remainder-still-fires",
              out.stdout.count("[claim_without_evidence]:") == 1, out.stdout)

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
              and markers[0]["probe_id"] == "compliance-canary:claim-without-evidence"
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
              second.stdout.count("[claim_without_evidence]:") == 1, second.stdout)
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
              fake.stdout.count("[claim_without_evidence]:") == 1, fake.stdout)

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

        # F9: the paired read may have scrolled beyond the 400-line detector
        # tail. Full-file reconciliation must still find it and stay silent.
        early_pointer_prompt = notification(
            'Timer "early-read" completed (exit code 0)',
            output_file="/tmp/cc-early-read.output", task_id="early-read-001")
        run(root, [claim("Still gathering the remaining details; nothing to report yet.")],
            "frontier", "notif-earlyread", prompt=early_pointer_prompt)
        early_read = [
            tool_use("rb-early", "Read", {"file_path": "/tmp/cc-early-read.output"}),
            tool_result("rb-early", "timer fired at 10:25"),
            *[claim(f"Working note {j}: still exploring the draft.") for j in range(450)],
        ]
        out = run(root, early_read, "frontier", "notif-earlyread", prompt="continue")
        check("notification-pending-content-clears-when-read-beyond-tail",
              not out.stdout
              and not state_file(root, "notif-earlyread").get("notification_pending_content"),
              out.stdout + repr(state_file(root, "notif-earlyread").get(
                  "notification_pending_content")))

        # R3-2: a successful non-read command/result pair that merely echoes
        # the full path is not read evidence and must leave the marker armed.
        echoed_pointer_prompt = notification(
            'Timer "echoed-path" completed (exit code 0)',
            output_file="/tmp/cc-echoed-path.output", task_id="echoed-path-001")
        run(root, [claim("Still gathering the remaining details; nothing to report yet.")],
            "frontier", "notif-echoed-path", prompt=echoed_pointer_prompt)
        echoed_path = [
            tool_use("not-read", "Bash", {
                "command": "printf '%s\\n' /tmp/cc-echoed-path.output"}),
            tool_result("not-read", "/tmp/cc-echoed-path.output"),
            claim("Task is complete."),
        ]
        out = run(root, echoed_path, "frontier", "notif-echoed-path", prompt="continue")
        check("notification-non-read-path-result-does-not-clear",
              out.stdout.count(
                  "- timer output never read: /tmp/cc-echoed-path.output") == 1,
              out.stdout)

        # --- D4b: the existing must-fire no-read control remains armed:
        # unresolved entries ride the EXISTING wrap-up surface (no new
        # emission point), one compact line each.
        run(root, [claim("Working on the ledger draft now.")], "frontier", "notif-wrap",
            prompt="Please draft the ledger wording section")
        advisor_pointer_prompt = notification(
            'Advisor consult "ledger-wording" completed (exit code 0)',
            output_file="/tmp/cc-advisor.output")
        run(root, [claim("Still drafting; nothing to report yet.")], "frontier", "notif-wrap",
            prompt=advisor_pointer_prompt)
        out = run(root, [claim("Task is complete.")], "frontier", "notif-wrap")
        check("notification-unresolved-pending-listed-at-wrap-up",
              out.stdout.count("- advisor output never read: /tmp/cc-advisor.output") == 1,
              out.stdout)

        # --- D5: the hook's format_one_probe fallback and drift_probes.json's
        # `message` are ONE wording (the two message sources had drifted).
        # Sourced from the REAL shipped skills/compliance-canary/drift_probes.json
        # (rehomed 2026-07-19 from verify-before-completion; skill remains, but
        # the probe file and its qualified id are now canary-owned).
        cc_probes = json.loads(
            (HERE.parents[1] / "compliance-canary" / "drift_probes.json").read_text(encoding="utf-8"))
        cc_message = next(p["message"] for p in cc_probes if p["id"] == "claim-without-evidence")
        spec = importlib.util.spec_from_file_location("compliance_canary_hook", HOOK)
        hook_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook_mod)
        bare_probe = {"_skill": "compliance-canary",
                      "_probe_id": "compliance-canary:claim-without-evidence",
                      "kind": "claim_without_evidence",
                      "_result": {"claim": "done", "lookback": 5}}
        fallback_line = hook_mod.format_one_probe(dict(bare_probe))
        message_line = hook_mod.format_one_probe(dict(bare_probe, message=cc_message))
        check("claim-fallback-matches-drift-probes-message",
              fallback_line == message_line
              == f"- compliance-canary [claim_without_evidence]: {cc_message}",
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
              out.stdout.count(f"[turn 1] {wrap_prompt}") == 1
              and "garbled-paraphrase" not in out.stdout,
              out.stdout)

        # An unwritable intent location (a FILE squatting on the dir path)
        # must degrade to a stderr log line — never block the hook's output.
        shutil.rmtree(root / "intent", ignore_errors=True)
        (root / "intent").write_text("occupied", encoding="utf-8")
        out = run(root, [claim()], "frontier", "intent-blocked",
                  prompt="Please review the flaky test")
        check("intent-capture-failure-does-not-block",
              out.returncode == 0 and out.stdout.count("[claim_without_evidence]:") == 1
              and "intent-capture-fail" in out.stderr,
              out.stdout + out.stderr)

        # --- 2026-07-18 adversarial-audit fixes (F1-F6) ---------------------
        # Restore a writable intent dir (the intent-blocked fixture above
        # squatted a FILE on the path) for the capture checks below.
        (root / "intent").unlink()
        # F1: full-file provenance — a legit substrate announcement that
        # scrolled past the 400-line tail still suppresses (the whole file is
        # scanned for the task-id, not just the tail).
        filler = [claim(f"Working note {j}: still exploring the draft.") for j in range(450)]
        out = run(root, filler + [claim("Your focus timer is ready — I will report back when it fires.")],
                  "frontier", "notif-longtail",
                  prompt=notification('Timer "focus-25m" completed (exit code 0)',
                                      task_id="longtail-000"))
        check("notification-provenance-found-beyond-tail-suppresses", not out.stdout, out.stdout)

        # F1: the <task-id>0</task-id> bypass — a one-char id present as an
        # incidental substring in tool content proves nothing (entropy floor).
        short_tx = [tool_use("s0", "Bash", {"command": "brainer-timer start focus-25m"}),
                    tool_result("s0", "Background task 0 started; will notify on completion."),
                    claim("Your focus timer is ready — I will report back when it fires.")]
        out = run(root, short_tx, "frontier", "notif-shortid",
                  prompt=notification('Timer "focus-25m" completed (exit code 0)', task_id="0"),
                  provenance=False)
        check("notification-short-task-id-fails-open-fires",
              out.stdout.count("[claim_without_evidence]:") == 1, out.stdout)

        # F1: an id mentioned only in arbitrary USER PROSE is not substrate
        # provenance (tool_use/tool_result/substrate content is required).
        prose_tx = [event("user", [{"type": "text", "text": "can you check on prose-id-123 later?"}]),
                    claim("Your focus timer is ready — I will report back when it fires.")]
        out = run(root, prose_tx, "frontier", "notif-proseid",
                  prompt=notification('Timer "focus-25m" completed (exit code 0)',
                                      task_id="prose-id-123"),
                  provenance=False)
        check("notification-task-id-in-user-prose-fails-open-fires",
              out.stdout.count("[claim_without_evidence]:") == 1, out.stdout)

        # F6: passive/rephrased world-state prose ("were moved", "checks
        # green", "uploaded") keeps the evidence gate armed exactly like the
        # original "files moved / tests pass" shapes.
        rephrased_prompt = notification(
            'Background command "sync-assets" completed (exit code 0)',
            result="Files were moved into place; checks green; artifacts uploaded.",
            task_id="ws-0001")
        out = run(root, [claim("The sync finished: files are moved and checks green — this is ready.")],
                  "frontier", "notif-ws-rephrased", prompt=rephrased_prompt)
        check("notification-worldstate-rephrased-still-fires",
              out.stdout.count("[claim_without_evidence]:") == 1, out.stdout)

        # F2: a notification FLOOD cannot destroy a fire — the second
        # qualifying notification while a marker is pending emits it anyway.
        first = run(root, [claim("The interim summary is ready.")], "frontier", "notif-flood",
                    prompt=notification('Timer "one" completed (exit code 0)', task_id="flood-aa"))
        check("notification-flood-first-turn-stays-silent", not first.stdout, first.stdout)
        second = run(root, [claim("The interim summary is ready."),
                            claim("Still gathering the remaining details; nothing to report yet.")],
                     "frontier", "notif-flood",
                     prompt=notification('Timer "two" completed (exit code 0)', task_id="flood-bb"))
        check("notification-flood-second-notification-emits-deferred",
              second.stdout.count("[claim_without_evidence]:") == 1, second.stdout)
        check("notification-flood-markers-cleared-after-forced-emission",
              not state_file(root, "notif-flood").get("deferred_fires"),
              repr(state_file(root, "notif-flood").get("deferred_fires")))

        # F2: the agent verified in the meantime — the stale marker drops
        # silently instead of nagging (emission-time freshness re-check).
        # ("tests pass" → the claim's evidence class is test/build, matching
        # the later check.py run; "checks pass" would classify otherwise.)
        first = run(root, [claim("The interim summary is ready and the tests pass.")],
                    "frontier", "notif-stale",
                    prompt=notification('Timer "focus-25m" completed (exit code 0)', task_id="stale-01"))
        check("notification-stale-defer-turn-stays-silent", not first.stdout, first.stdout)
        verified_tx = [tool_use("prov", "Bash", {"command": "brainer-timer start focus-25m"}),
                       tool_result("prov", "Background task stale-01 started; will notify on completion."),
                       claim("The interim summary is ready and the tests pass."),
                       tool_use("vs", "Bash", {"command": "python3 check.py"}),
                       tool_result("vs", "12 passed"),
                       claim("The fresh check came back green; continuing.")]
        second = run(root, verified_tx, "frontier", "notif-stale", prompt="continue")
        check("stale-deferred-marker-drops-silently-after-verification",
              not second.stdout, second.stdout)
        check("stale-deferred-marker-cleared",
              not state_file(root, "notif-stale").get("deferred_fires"),
              repr(state_file(root, "notif-stale").get("deferred_fires")))
        third = run(root, verified_tx, "frontier", "notif-stale", prompt="continue")
        check("stale-marker-drop-is-final", not third.stdout, third.stdout)

        # F3: DESTRUCTION does not clear a pending entry (rm on the output
        # file), and a FAILED read does not clear either.
        run(root, [claim("Your focus timer is set; I will report back when it fires.")],
            "frontier", "notif-rm",
            prompt=notification('Timer "focus-25m" completed (exit code 0)', task_id="rm-0001",
                                output_file="/tmp/cc-rm/rm-0001.output"))
        check("notification-rm-session-records-pending",
              len(state_file(root, "notif-rm").get("notification_pending_content", [])) == 1,
              repr(state_file(root, "notif-rm")))
        rm_tx = [tool_use("rm1", "Bash", {"command": "rm -f /tmp/cc-rm/rm-0001.output"}),
                 tool_result("rm1", ""),
                 tool_use("er1", "Read", {"file_path": "/tmp/cc-rm/rm-0001.output"}),
                 tool_result("er1", "No such file or directory", True),
                 claim("Still gathering the remaining details; nothing to report yet.")]
        run(root, rm_tx, "frontier", "notif-rm", prompt="continue")
        check("notification-pending-content-survives-deletion-and-error",
              len(state_file(root, "notif-rm").get("notification_pending_content", [])) == 1,
              repr(state_file(root, "notif-rm").get("notification_pending_content")))

        # F3 (audit round 1): mv (rename) and an Edit-overwrite are NOT reads
        # — neither reconciles the entry.
        run(root, [claim("Your focus timer is set; I will report back when it fires.")],
            "frontier", "notif-mv",
            prompt=notification('Timer "focus-25m" completed (exit code 0)', task_id="mv-0001",
                                output_file="/tmp/cc-mv/mv-0001.output"))
        mv_tx = [tool_use("mv1", "Bash", {"command": "mv /tmp/cc-mv/mv-0001.output /tmp/cc-mv/archived.output"}),
                 tool_result("mv1", ""),
                 tool_use("ed1", "Edit", {"file_path": "/tmp/cc-mv/mv-0001.output",
                                          "old_string": "a", "new_string": "b"}),
                 tool_result("ed1", "updated"),
                 claim("Still gathering the remaining details; nothing to report yet.")]
        run(root, mv_tx, "frontier", "notif-mv", prompt="continue")
        check("notification-pending-content-survives-mv-and-edit",
              len(state_file(root, "notif-mv").get("notification_pending_content", [])) == 1,
              repr(state_file(root, "notif-mv").get("notification_pending_content")))

        # F3: a bare basename with NO parent-dir anchor does not clear…
        run(root, [claim("Your focus timer is set; I will report back when it fires.")],
            "frontier", "notif-basename",
            prompt=notification('Timer "focus-25m" completed (exit code 0)', task_id="base-01",
                                output_file="/tmp/cc-base/base-01.output"))
        base_tx = [tool_use("rb", "Bash", {"command": "cat base-01.output"}),
                   tool_result("rb", "contents"),
                   claim("Still gathering the remaining details; nothing to report yet.")]
        run(root, base_tx, "frontier", "notif-basename", prompt="continue")
        check("notification-bare-basename-does-not-clear",
              len(state_file(root, "notif-basename").get("notification_pending_content", [])) == 1,
              repr(state_file(root, "notif-basename").get("notification_pending_content")))

        # F3: …but a genuine `cd <dir> && cat <file>` relative read DOES.
        run(root, [claim("Your focus timer is set; I will report back when it fires.")],
            "frontier", "notif-relread",
            prompt=notification('Timer "focus-25m" completed (exit code 0)', task_id="rel-001",
                                output_file="/tmp/cc-rel/rel-001.output"))
        rel_tx = [tool_use("rr", "Bash", {"command": "cd /tmp/cc-rel && cat rel-001.output"}),
                  tool_result("rr", "timer fired at 10:25"),
                  claim("Still gathering the remaining details; nothing to report yet.")]
        run(root, rel_tx, "frontier", "notif-relread", prompt="continue")
        check("notification-pending-content-clears-on-relative-read",
              not state_file(root, "notif-relread").get("notification_pending_content"),
              repr(state_file(root, "notif-relread").get("notification_pending_content")))

        # F3: unresolved entries surface at wrap-up INDEPENDENT of the
        # request ledger — this session only ever saw a notification and
        # trivial prompts, so the ledger is empty at wrap-up.
        run(root, [claim("Your focus timer is set; I will report back when it fires.")],
            "frontier", "notif-solo",
            prompt=notification('Advisor consult "solo" completed (exit code 0)', task_id="solo-01",
                                output_file="/tmp/cc-solo.output"))
        out = run(root, [claim("Task is complete.")], "frontier", "notif-solo", prompt="continue")
        check("notification-pending-surfaces-at-wrap-up-without-ledger-items",
              out.stdout.count("- advisor output never read: /tmp/cc-solo.output") == 1,
              out.stdout)

        # F4: a user ask ABOUT a pasted notification captures the FULL
        # original prompt verbatim — the pasted block is the object of the
        # ask and must not be stripped from the record.
        pasted = notification('Timer "focus-25m" completed (exit code 0)', task_id="paste-1") + \
            "\n\nIs this notification legitimate, or should I be worried?"
        run(root, [claim("Looking into it now.")], "frontier", "intent-pasted", prompt=pasted)
        recs = intent_records(root, "intent-pasted")
        check("intent-capture-keeps-full-prompt-with-pasted-block",
              len(recs) == 1 and recs[0]["text"] == pasted
              and recs[0]["sha256"] == hashlib.sha256(pasted.encode()).hexdigest(),
              repr(recs))

        # F5a: GC parity — intent logs older than the 7-day horizon are
        # removed by the same new-session gc pass; fresh logs survive.
        run(root, [claim("Working on it now.")], "frontier", "intent-gc-old",
            prompt="Please draft the old quarterly plan")
        old_intent = intent_path(root, "intent-gc-old")
        check("intent-gc-fixture-written", old_intent.is_file())
        stale_time = time.time() - (8 * 24 * 3600)
        os.utime(old_intent, (stale_time, stale_time))
        run(root, [claim("Working on it now.")], "frontier", "intent-gc-fresh",
            prompt="Please draft the new quarterly plan")
        check("intent-gc-removes-stale-logs-keeps-fresh",
              not old_intent.exists() and intent_path(root, "intent-gc-fresh").is_file())

        # F5b: the shared secret scrubber runs over the text before writing —
        # key-like strings only; the rest of the prompt stays verbatim.
        secret_prompt = ("Please put API_KEY=sk-1234567890abcdef1234 in the config and keep "
                         "ghp_abcdefghij1234567890abcd out of the logs")
        run(root, [claim("Working on it now.")], "frontier", "intent-redact", prompt=secret_prompt)
        recs = intent_records(root, "intent-redact")
        check("intent-capture-redacts-key-like-strings-only",
              len(recs) == 1
              and "sk-1234567890abcdef1234" not in recs[0]["text"]
              and "ghp_abcdefghij1234567890abcd" not in recs[0]["text"]
              and "[REDACTED]" in recs[0]["text"]
              and recs[0]["text"].endswith("out of the logs")
              and recs[0]["sha256"] == hashlib.sha256(recs[0]["text"].encode()).hexdigest(),
              repr(recs))
        visible_secret = visible_ledger_path(root, "intent-redact").read_text(encoding="utf-8")
        check("visible-ledger-redacts-key-like-strings",
              "sk-1234567890abcdef1234" not in visible_secret
              and "ghp_abcdefghij1234567890abcd" not in visible_secret
              and "[REDACTED]" in visible_secret, visible_secret)

        # R2-3: verbatim means verbatim — the persisted record keeps the
        # prompt's exact whitespace (capture_intent's own .strip() is gone).
        quoted_ws = ("\n\n" + notification('Timer "focus-25m" completed (exit code 0)',
                                          task_id="ws-ver01") + "\n\nIs this real?  \n")
        run(root, [claim("Looking into it now.")], "frontier", "intent-ws", prompt=quoted_ws)
        recs = intent_records(root, "intent-ws")
        check("intent-capture-preserves-exact-whitespace",
              len(recs) == 1 and recs[0]["text"] == quoted_ws
              and recs[0]["sha256"] == hashlib.sha256(quoted_ws.encode()).hexdigest(),
              repr(recs))

        # R2-2: a FAILING redactor must never fall back to raw text — the
        # record degrades to "[REDACTION-FAILED]" + the ORIGINAL text's
        # hash (integrity anchor kept, secret bytes never persisted).
        broken = types.ModuleType("audit_redact")

        def _boom(_text):
            raise RuntimeError("scrubber exploded")

        broken.redact_secrets = _boom
        old_env = os.environ.get("COMPLIANCE_CANARY_STATE_DIR")
        os.environ["COMPLIANCE_CANARY_STATE_DIR"] = str(root / "state")
        old_mod = sys.modules.get("audit_redact")
        sys.modules["audit_redact"] = broken
        raw_secret = "  Please keep sk-1234567890abcdef1234 safe  "
        try:
            ok = hook_mod.capture_intent("intent-redact-broken", 1, raw_secret)
        finally:
            if old_mod is None:
                sys.modules.pop("audit_redact", None)
            else:
                sys.modules["audit_redact"] = old_mod
            if old_env is None:
                os.environ.pop("COMPLIANCE_CANARY_STATE_DIR", None)
            else:
                os.environ["COMPLIANCE_CANARY_STATE_DIR"] = old_env
        recs = intent_records(root, "intent-redact-broken")
        check("intent-redaction-failure-stores-placeholder-never-raw",
              ok and len(recs) == 1 and recs[0]["text"] == "[REDACTION-FAILED]"
              and "sk-1234567890abcdef1234" not in json.dumps(recs)
              and recs[0]["sha256"] == hashlib.sha256(raw_secret.encode()).hexdigest(),
              repr(recs))

        # F5d: a payload WITHOUT session_id writes a timestamped fallback —
        # never a shared unknown.jsonl.
        out = run(root, [claim("Working on it now.")], "frontier", None,
                  prompt="Please draft the anonymous thing")
        fallbacks = list((root / "intent").glob("unknown-*.jsonl"))
        check("intent-missing-session-id-uses-timestamped-fallback",
              out.returncode == 0 and len(fallbacks) == 1
              and not (root / "intent" / "unknown.jsonl").exists(),
              repr((out.returncode, fallbacks, out.stderr)))

        # F1: a >=6-char but ZERO-ENTROPY id fails open even when the
        # substrate-style announcement IS present in tool content (the
        # run() helper prepends it) — all-same-char / trivial-sequence ids
        # collide with incidental substrings and prove nothing.
        for bad_id in ("000000", "123456"):
            out = run(root, [claim("Your focus timer is ready — I will report back when it fires.")],
                      "frontier", f"notif-entropy-{bad_id}",
                      prompt=notification('Timer "focus-25m" completed (exit code 0)',
                                          task_id=bad_id))
            check(f"notification-low-entropy-id-{bad_id}-fails-open-fires",
                  out.stdout.count("[claim_without_evidence]:") == 1, out.stdout)

        # F5c: COMPLIANCE_CANARY_DISABLED=1 suppresses intent capture like
        # every other mechanism — while the request LEDGER still records the
        # ask (standing user directive: the ledger stays ahead of the valve).
        disabled_prompt = "Please draft the disabled-valve plan"
        out = run(root, [claim("Working on it now.")], "frontier", "intent-disabled",
                  prompt=disabled_prompt,
                  extra_env={"COMPLIANCE_CANARY_DISABLED": "1"})
        check("intent-capture-suppressed-when-disabled",
              out.returncode == 0 and not out.stdout
              and not intent_path(root, "intent-disabled").exists(),
              repr((out.returncode, out.stdout, out.stderr)))
        check("request-ledger-still-records-when-disabled",
              len(state_file(root, "intent-disabled").get("request_ledger", [])) == 1,
              repr(state_file(root, "intent-disabled")))
        check("visible-ledger-still-records-when-disabled",
              disabled_prompt in visible_ledger_path(root, "intent-disabled").read_text(encoding="utf-8"),
              str(visible_ledger_path(root, "intent-disabled")))
        out = run(root, [claim("Working on it now.")], "frontier", "intent-disabled-resume",
                  prompt="Please draft the resumed plan")
        check("intent-capture-resumes-after-disabled",
              len(intent_records(root, "intent-disabled-resume")) == 1,
              repr(intent_records(root, "intent-disabled-resume")))

        # F6: an interpreter-mediated file write IS a mutation — a check run
        # BEFORE `python3 -c "open(...,'w')..."` is stale evidence, exactly
        # like a check run before an Edit.
        pywrite = [
            tool_use("v8", "Bash", {"command": "pytest -q"}),
            tool_result("v8", "12 passed"),
            tool_use("m8", "Bash", {"command": "python3 -c \"open('x.py','w').write('print(1)')\""}),
            tool_result("m8", ""),
            claim(),
        ]
        out = run(root, pywrite, "frontier", "py-oneliner-write")
        check("python-one-liner-write-makes-prior-evidence-stale-fires",
              out.stdout.count("[claim_without_evidence]:") == 1, out.stdout)
        pyprint = [
            tool_use("v9", "Bash", {"command": "pytest -q"}),
            tool_result("v9", "12 passed"),
            tool_use("m9", "Bash", {"command": "python3 -c \"print('hi')\""}),
            tool_result("m9", "hi"),
            claim(),
        ]
        out = run(root, pyprint, "frontier", "py-oneliner-print")
        check("python-one-liner-print-is-not-a-mutation-stays-silent",
              not out.stdout, out.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
