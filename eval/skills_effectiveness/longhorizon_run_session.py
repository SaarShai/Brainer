"""Run one scripted long-horizon Codex rehearsal or experiment session."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

TURN_RE = re.compile(r"^T(\d{2})\s+—\s+`(.*)`$")
FIXTURE_RE = re.compile(r"`(longhorizon-work/([^/`]+)/)`")
PROFILE_BY_ARM = {"frontier": "frontier", "off": "off"}
FILLER_BYTES = 200_000
FILLER_UNIT = b"neutral rehearsal context filler; no instructions or facts.\n"
FILLER_INSTRUCTION = (
    "Host context-pressure equivalent. The neutral payload below carries no "
    "task facts or instructions. Acknowledge receipt in one line only.\n\n"
)


@dataclass(frozen=True)
class RunnerResult:
    exit_code: int
    session_id: str | None = None


def parse_scripted_turns(path: Path) -> list[tuple[int, str]]:
    """Parse consecutive TNN em-dash/backtick turns from a scenario Markdown."""
    turns = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = TURN_RE.fullmatch(line)
        if match:
            turns.append((int(match.group(1)), match.group(2)))
    expected = list(range(1, len(turns) + 1))
    observed = [index for index, _ in turns]
    if not turns or observed != expected:
        raise ValueError(f"scenario turns must be consecutive from T01: {observed}")
    return turns


def arm_profile(arm: str) -> str:
    try:
        return PROFILE_BY_ARM[arm]
    except KeyError as exc:
        raise ValueError(f"unsupported arm: {arm}") from exc


def pressure_prompt() -> tuple[str, int]:
    payload = (FILLER_UNIT * (FILLER_BYTES // len(FILLER_UNIT) + 1))[:FILLER_BYTES]
    assert len(payload) == FILLER_BYTES
    return FILLER_INSTRUCTION + payload.decode("ascii"), len(payload)


def fixture_relative_path(scenario_path: Path) -> Path:
    text = scenario_path.read_text(encoding="utf-8")
    match = FIXTURE_RE.search(text)
    if not match:
        raise ValueError("scenario does not declare a longhorizon-work fixture root")
    relative = Path(match.group(1))
    if relative.parts != ("longhorizon-work", match.group(2)):
        raise ValueError(f"unsafe fixture root: {relative}")
    if match.group(2) != scenario_path.stem:
        raise ValueError("fixture root name must match the scenario filename")
    return relative


def _session_id(value: object) -> str | None:
    if isinstance(value, dict):
        for key in ("thread_id", "session_id", "conversation_id"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate
        for candidate in value.values():
            found = _session_id(candidate)
            if found:
                return found
    elif isinstance(value, list):
        for candidate in value:
            found = _session_id(candidate)
            if found:
                return found
    return None


def subprocess_runner(command: list[str], env: dict[str, str], output_path: Path) -> RunnerResult:
    """Run Codex while preserving both output streams as valid JSONL records."""
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        bufsize=1, env=env,
    )
    lock = threading.Lock()
    observed_session = []

    def consume(stream, stream_name, sink):
        for line in iter(stream.readline, ""):
            raw = line.rstrip("\r\n")
            if stream_name == "stdout":
                try:
                    record = json.loads(raw)
                except json.JSONDecodeError:
                    record = {"type": "runner_stdout", "text": raw}
                found = _session_id(record)
                if found:
                    observed_session.append(found)
            else:
                record = {"type": "runner_stderr", "text": raw}
            with lock:
                sink.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
                sink.flush()
        stream.close()

    with output_path.open("w", encoding="utf-8") as sink:
        threads = [
            threading.Thread(target=consume, args=(process.stdout, "stdout", sink)),
            threading.Thread(target=consume, args=(process.stderr, "stderr", sink)),
        ]
        for thread in threads:
            thread.start()
        exit_code = process.wait()
        for thread in threads:
            thread.join()
    return RunnerResult(exit_code, observed_session[0] if observed_session else None)


def codex_version() -> str:
    result = subprocess.run(["codex", "--version"], text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f"codex --version failed: {result.stderr.strip()}")
    return result.stdout.strip()


def git_state(venue: Path) -> str:
    result = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all"], cwd=venue,
        text=True, capture_output=True,
    )
    if result.returncode:
        raise RuntimeError(f"cannot record venue git state: {result.stderr.strip()}")
    return result.stdout


def _write_manifest(path: Path, manifest: dict) -> None:
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _command(venue: Path, text: str, session_id: str | None) -> list[str]:
    # PROMPTER's .codex/hooks.json has no persisted trust entry; without this
    # flag the canary UserPromptSubmit hook silently never runs under exec.
    # Passed in BOTH arms so the command surface is arm-identical.
    base = ["codex", "exec", "--cd", str(venue), "--dangerously-bypass-hook-trust"]
    if session_id is None:
        return base + ["--json", text]
    return base + ["resume", session_id, "--json", text]


def run_session(
        scenario: Path, arm: str, venue: Path, out_dir: Path,
        resume_from: int = 1,
        runner: Callable[[list[str], dict[str, str], Path], RunnerResult] = subprocess_runner,
        version_getter: Callable[[], str] = codex_version,
        git_state_getter: Callable[[Path], str] = git_state) -> dict:
    scenario = scenario.resolve()
    venue = venue.resolve()
    out_dir = out_dir.resolve()
    turns = parse_scripted_turns(scenario)
    if resume_from < 1 or resume_from > len(turns):
        raise ValueError(f"--resume-from must be between 1 and {len(turns)}")
    profile = arm_profile(arm)
    fixture_relative = fixture_relative_path(scenario)
    fixture = venue / fixture_relative
    if not fixture.resolve().is_relative_to(venue):
        raise ValueError(f"fixture root escapes venue: {fixture}")
    manifest_path = out_dir / "manifest.json"
    out_dir.mkdir(parents=True, exist_ok=True)

    if resume_from == 1:
        if manifest_path.exists():
            raise FileExistsError(f"refusing to overwrite existing manifest: {manifest_path}")
        before = git_state_getter(venue)
        if fixture.exists():
            shutil.rmtree(fixture)
        after = git_state_getter(venue)
        manifest = {
            "schema_version": 1,
            "scenario": str(scenario),
            "scenario_sha256": hashlib.sha256(scenario.read_bytes()).hexdigest(),
            "arm": arm,
            "venue": str(venue),
            "fixture_root": fixture_relative.as_posix() + "/",
            "fixture_reset": True,
            "venue_git_state_before_reset": before,
            "venue_git_state_after_reset": after,
            "environment": {
                "COMPLIANCE_CANARY_PROFILE": profile,
                "codex_version": version_getter(),
                "started_at_utc": datetime.now(timezone.utc).isoformat(),
            },
            "forced_compactions": [],
            "turns": [],
        }
        _write_manifest(manifest_path, manifest)
        session_id = None
    else:
        if not manifest_path.exists():
            raise FileNotFoundError("--resume-from requires an existing manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected = (str(scenario), arm, str(venue), profile)
        observed = (
            manifest.get("scenario"), manifest.get("arm"), manifest.get("venue"),
            manifest.get("environment", {}).get("COMPLIANCE_CANARY_PROFILE"),
        )
        if observed != expected:
            raise ValueError("resume arguments do not match the existing manifest")
        previous = [record for record in manifest["turns"] if record["turn_index"] == resume_from - 1]
        if len(previous) != 1 or previous[0]["codex_exit_code"] != 0:
            raise ValueError("resume requires a successful immediately preceding turn")
        session_id = previous[0].get("session_id")
        if not session_id:
            raise ValueError("resume manifest has no session id")
        manifest["turns"] = [record for record in manifest["turns"] if record["turn_index"] < resume_from]
        manifest["forced_compactions"] = [
            record for record in manifest["forced_compactions"]
            if record["turn_index"] < resume_from
        ]
        _write_manifest(manifest_path, manifest)

    env = {**os.environ, "COMPLIANCE_CANARY_PROFILE": profile}
    for turn_index, scripted_text in turns[resume_from - 1:]:
        sent_text = scripted_text
        if scripted_text == "/compact":
            sent_text, byte_size = pressure_prompt()
            manifest["forced_compactions"].append({
                "turn_index": turn_index,
                "mechanism": "context-pressure-filler",
                "filler_byte_size": byte_size,
            })
        output_path = out_dir / f"turn-{turn_index:02d}.jsonl"
        started = time.monotonic()
        result = runner(_command(venue, sent_text, session_id), env, output_path)
        elapsed = time.monotonic() - started
        if session_id is None:
            session_id = result.session_id
        elif result.session_id and result.session_id != session_id:
            raise RuntimeError("Codex returned a different session id while resuming")
        record = {
            "turn_index": turn_index,
            "sent_text_sha256": hashlib.sha256(sent_text.encode("utf-8")).hexdigest(),
            "codex_exit_code": result.exit_code,
            "wall_time_seconds": round(elapsed, 6),
            "session_id": session_id,
            "transcript_file": output_path.name,
        }
        manifest["turns"].append(record)
        _write_manifest(manifest_path, manifest)
        if result.exit_code:
            raise RuntimeError(f"Codex turn {turn_index:02d} failed with exit code {result.exit_code}")
        if session_id is None:
            raise RuntimeError("Codex turn 01 did not emit a session id")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True, type=Path)
    parser.add_argument("--arm", required=True, choices=sorted(PROFILE_BY_ARM))
    parser.add_argument("--venue", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--resume-from", type=int, default=1)
    args = parser.parse_args()
    run_session(args.scenario, args.arm, args.venue, args.out_dir, args.resume_from)


if __name__ == "__main__":
    main()
