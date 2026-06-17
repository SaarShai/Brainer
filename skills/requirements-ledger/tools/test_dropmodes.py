#!/usr/bin/env python3
"""Behavioral guard: a user request MUST NOT be silently dropped.

Drives the REAL compliance-canary hook across multi-turn transcripts that
reproduce the three ways agents drop work (the user's own words):

  A. "thinks it's complete"  — claims done after doing 1 of N asks
  B. "simply forgets"        — an early request never touched over many turns
  C. "misunderstands"        — does adjacent work, never answers the question

For each mode we assert the hook CATCHES the drop — surfaces the still-open
request and/or fires the closure gate — and that the request is never lost from
the hook's independent capture (the guarantee that does NOT depend on the agent
cooperating). A 4th case is the positive control: when the agent reconciles +
asks and the user closes, the nag clears (no false alarm — "works well", not
just "works").

Deterministic: no model, no network. Exit 0 = all modes caught.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
HOOK = REPO / "skills" / "compliance-canary" / "tools" / "hook.py"
REAL_PROBES = {
    "requirements-ledger": REPO / "skills" / "requirements-ledger" / "drift_probes.json",
    "verify-before-completion": REPO / "skills" / "verify-before-completion" / "drift_probes.json",
}

PASS = 0
FAIL = 0
FAILS: list[str] = []


def ok(name: str) -> None:
    global PASS
    PASS += 1
    print(f"  [PASS] {name}")


def no(name: str, detail: str = "") -> None:
    global FAIL
    FAIL += 1
    FAILS.append(name)
    print(f"  [FAIL] {name}{('  | ' + detail) if detail else ''}")


def _assistant(text: str) -> dict:
    return {"type": "assistant", "message": {"role": "assistant",
            "content": [{"type": "text", "text": text}]}}


def _state_file(state_dir: Path, sid: str) -> Path:
    h = hashlib.sha256(sid.encode("utf-8", "replace")).hexdigest()[:16]
    return state_dir / f"{h}.json"


class Session:
    """One canary session: shared state dir + skills root across turns."""

    def __init__(self, root: Path, sid: str, *, pulse: bool = False, extra_env: dict | None = None):
        self.sid = sid
        self.state_dir = root / "state" / sid
        self.skills_root = root / "skills"
        self.tx = root / f"tx_{sid}.jsonl"
        self.env = {
            **os.environ,
            "COMPLIANCE_CANARY_STATE_DIR": str(self.state_dir),
            "COMPLIANCE_CANARY_SKILLS_ROOT": str(self.skills_root),
        }
        if not pulse:
            self.env["COMPLIANCE_CANARY_PULSE_DISABLED"] = "1"
        if extra_env:
            self.env.update(extra_env)

    def turn(self, prompt: str, last_assistant: str | None = None,
             tool_uses: list[dict] | None = None) -> str:
        """Run one UserPromptSubmit. `last_assistant` is the agent's prior reply
        the hook will evaluate; `tool_uses` are appended as a tool_use turn."""
        events: list[dict] = []
        if last_assistant is not None:
            events.append(_assistant(last_assistant))
        for tu in (tool_uses or []):
            events.append({"type": "assistant", "message": {"role": "assistant",
                           "content": [{"type": "tool_use", "name": tu["name"],
                                        "input": tu.get("input", {})}]}})
        self.tx.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
        payload = json.dumps({"session_id": self.sid, "transcript_path": str(self.tx),
                              "hook_event_name": "UserPromptSubmit", "prompt": prompt})
        r = subprocess.run([sys.executable, str(HOOK)], input=payload,
                           capture_output=True, text=True, env=self.env)
        return r.stdout

    def state(self) -> dict:
        p = _state_file(self.state_dir, self.sid)
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}


def setup_skills(root: Path) -> None:
    sk = root / "skills"
    for name, src in REAL_PROBES.items():
        d = sk / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "drift_probes.json").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="reqledger-drop-") as td:
        root = Path(td)
        setup_skills(root)

        # ---- Mode A: "thinks it's complete" --------------------------------
        # User asks for THREE things in one message; agent does one and claims
        # done. The hook must re-surface the still-open request + fire the gate.
        print("[A] thinks-it's-complete: claims done after 1 of 3 asks")
        s = Session(root, "modeA")
        s.turn("add a --json flag to the CLI, update the README, and add a test for it")
        out = s.turn("thanks", last_assistant="All done — added the --json flag.")
        caught_gate = "completion_without_closure" in out
        caught_open = "still OPEN" in out and "json flag" in out
        if caught_gate and caught_open:
            ok("drop caught: gate fired + original 3-part request re-surfaced as open")
        else:
            no("mode A not caught", f"gate={caught_gate} open={caught_open} :: {out[:240]!r}")

        # ---- Mode B: "simply forgets" --------------------------------------
        # An early request, then 3 turns of other work that never touch it. The
        # hook's capture must retain it AND resurface it (pulse cadence = 4).
        print("[B] forgets: early request survives 3 turns of other work")
        s = Session(root, "modeB", pulse=True)  # default cadence 4
        s.turn("also rename the legacy foo() calls to bar() everywhere")
        s.turn("now optimize the parser", last_assistant="Optimizing the parser.")
        s.turn("check the logs too", last_assistant="Checked the logs.")
        out = s.turn("what's the status?", last_assistant="Looking into it.")
        st = s.state()
        retained = any("rename the legacy foo" in it.get("text", "") for it in st.get("request_ledger", []))
        resurfaced = ("rename the legacy foo" in out) or ("ledger_not_materialized" in out) \
            or ("still open" in out.lower())
        if retained and resurfaced:
            ok("forgotten request retained in capture AND resurfaced after 4 turns")
        else:
            no("mode B not caught", f"retained={retained} resurfaced={resurfaced} :: {out[:240]!r}")

        # ---- Mode C: "misunderstands" --------------------------------------
        # User asks a QUESTION + a task; agent does the task, never answers the
        # question, claims done. Gate must demand enumerating QUESTIONs; the
        # verbatim question must resurface.
        print("[C] misunderstands: does the task, never answers the question")
        s = Session(root, "modeC")
        s.turn("why is the build failing? also pin the numpy version")
        out = s.turn("ok", last_assistant="Done. Pinned numpy to 1.26.4.")
        names_question = "QUESTION" in out
        resurfaced_q = "build failing" in out
        if names_question and resurfaced_q:
            ok("unanswered question caught: gate names QUESTIONs + verbatim question re-surfaced")
        else:
            no("mode C not caught", f"names_question={names_question} resurfaced={resurfaced_q} :: {out[:240]!r}")

        # ---- Positive control: reconcile + ask + user closes => clean ------
        print("[D] positive control: reconcile + ask + user-close → no false nag, ledger empties")
        s = Session(root, "modeD")
        s.turn("add the --json flag, update the README, and add a test")
        out = s.turn(
            "perfect, that's everything — close it",
            last_assistant=("Reconciling: (1) --json flag added; (2) README updated; "
                            "(3) test added, tests pass. Ok to close?"))
        gate_silent = "completion_without_closure" not in out
        closed = "closed" in out.lower() and "ledger now empty" in out.lower()
        if gate_silent and closed:
            ok("good path: gate stayed silent (agent asked), user-close emptied the ledger")
        else:
            no("mode D positive control failed", f"gate_silent={gate_silent} closed={closed} :: {out[:240]!r}")

    print()
    total = PASS + FAIL
    if FAIL == 0:
        print(f"reqledger drop-mode guard: {PASS}/{total} PASS — no drop mode slips")
        return 0
    print(f"reqledger drop-mode guard: {PASS}/{total} — failures: {FAILS}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
