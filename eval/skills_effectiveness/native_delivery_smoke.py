#!/usr/bin/env python3
"""Four-run carrier-free native skill-delivery feasibility smoke.

This is not an outcome evaluation. It asks one narrower question before paid
paired work: can each host activate a project skill natively, and does an OFF
fixture avoid the treatment-only nonce, under a bounded no-egress setup?
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable

LANES = ("codex-default", "claude-opus")
ARMS = ("FRONTIER", "OFF")
PROMPTS = {
    "codex-default": "Use $eval-native-marker and follow its instructions exactly. Do not use tools.",
    "claude-opus": "/eval-native-marker",
}
TRIPWIRE = "BRAINER_NATIVE_SMOKE_TRIPWIRE_DO_NOT_REPEAT"
SAFE_ENV_KEYS = {"PATH", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TMPDIR", "SHELL", "USER", "LOGNAME"}
SECRET_MARKERS = ("TOKEN", "SECRET", "PASSWORD", "API_KEY", "PRIVATE_KEY", "CREDENTIAL")


def host_auth_env() -> dict[str, str]:
    """Expose host auth stores to the CLI without forwarding API-key env vars."""
    env = {key: os.environ[key] for key in SAFE_ENV_KEYS if key in os.environ}
    env["HOME"] = str(Path.home())
    unsafe = [key for key in env if any(marker in key.upper() for marker in SECRET_MARKERS)]
    if unsafe:
        raise RuntimeError(f"unsafe environment keys: {unsafe}")
    return env


def prepare_fixture(lane: str, arm: str, marker: str) -> tuple[Path, Path | None]:
    root = Path(tempfile.mkdtemp(prefix="brainer-native-smoke-"))
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, env=host_auth_env())
    (root / ".eval-secret-tripwire").write_text(TRIPWIRE + "\n")
    (root / "README.md").write_text("# Isolated native skill activation fixture\n")
    if arm == "OFF":
        return root, None
    base = root / (".codex/skills" if lane == "codex-default" else ".claude/skills") / "eval-native-marker"
    base.mkdir(parents=True)
    (base / "SKILL.md").write_text(
        "---\n"
        "name: eval-native-marker\n"
        "description: Emit a private fixture nonce when explicitly requested.\n"
        "disable-model-invocation: false\n"
        "---\n\n"
        f"Respond with exactly `{marker}` and nothing else. Do not use tools.\n"
    )
    return root, base / "SKILL.md"


def build_command(lane: str, root: Path) -> list[str]:
    if lane == "codex-default":
        return [
            "codex", "exec", "--ephemeral", "--ignore-user-config", "--ignore-rules",
            "-s", "read-only", "-c", "sandbox_workspace_write.network_access=false",
            "-c", "shell_environment_policy.inherit=none",
            "-C", str(root), "--json", PROMPTS[lane],
        ]
    if lane == "claude-opus":
        return [
            "claude", "-p", "--no-session-persistence", "--model", "opus",
            "--tools", "Skill", "--no-chrome", "--strict-mcp-config",
            "--mcp-config", '{"mcpServers":{}}', "--setting-sources", "project",
            "--max-budget-usd", "1.00", "--output-format", "json", PROMPTS[lane],
        ]
    raise ValueError(f"unknown lane: {lane}")


def _version(binary: str, env: dict[str, str]) -> str:
    try:
        proc = subprocess.run([binary, "--version"], text=True, capture_output=True,
                              timeout=15, env=env)
        return (proc.stdout or proc.stderr).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return f"unavailable:{type(exc).__name__}"


def _failure_kind(returncode: int, stdout: str, stderr: str) -> str | None:
    if returncode == 0:
        return None
    text = (stdout + "\n" + stderr).lower()
    if "auth" in text or "login" in text or "credential" in text:
        return "authentication"
    if "rate limit" in text or "overloaded" in text:
        return "provider-capacity"
    if "network" in text or "connect" in text:
        return "transport"
    return "nonzero-exit"


def _tool_calls(text: str) -> int:
    """Count host-reported tool records without retaining response content."""
    records = []
    for line in text.splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    if not records:
        try:
            records = [json.loads(text)]
        except json.JSONDecodeError:
            return 0

    count = 0
    stack = list(records)
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            kind = str(value.get("type", "")).lower()
            if any(token in kind for token in ("tool_use", "tool_call", "command_execution", "mcp_call")):
                count += 1
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
    return count


def execute_one(lane: str, arm: str, marker: str, timeout: int = 240,
                runner: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> dict:
    root, skill_path = prepare_fixture(lane, arm, marker)
    started = time.monotonic()
    try:
        cmd = build_command(lane, root)
        try:
            proc = runner(cmd, cwd=root, text=True, capture_output=True, timeout=timeout,
                          env=host_auth_env())
            stdout, stderr = proc.stdout or "", proc.stderr or ""
            marker_observed = marker in stdout
            tripwire_leaked = TRIPWIRE in stdout or TRIPWIRE in stderr
            tool_calls = _tool_calls(stdout)
            valid = proc.returncode == 0 and not tripwire_leaked and tool_calls == 0 and (
                marker_observed if arm == "FRONTIER" else not marker_observed)
            return {
                "lane": lane,
                "arm": arm,
                "returncode": proc.returncode,
                "valid": valid,
                "marker_observed": marker_observed,
                "tripwire_leaked": tripwire_leaked,
                "tool_calls_observed": tool_calls,
                "failure_kind": _failure_kind(proc.returncode, stdout, stderr),
                "wall_seconds": time.monotonic() - started,
                "native_skill_path": str(skill_path.relative_to(root)) if skill_path else None,
                "carrier_used": False,
                "prompt_sha256": hashlib.sha256(PROMPTS[lane].encode()).hexdigest(),
                "stdout_sha256": hashlib.sha256(stdout.encode()).hexdigest(),
                "stderr_sha256": hashlib.sha256(stderr.encode()).hexdigest(),
                "stdout_bytes": len(stdout.encode()),
                "stderr_bytes": len(stderr.encode()),
            }
        except subprocess.TimeoutExpired:
            return {"lane": lane, "arm": arm, "valid": False, "marker_observed": False,
                    "tripwire_leaked": False, "failure_kind": "timeout",
                    "wall_seconds": time.monotonic() - started,
                    "native_skill_path": str(skill_path.relative_to(root)) if skill_path else None,
                    "carrier_used": False,
                    "prompt_sha256": hashlib.sha256(PROMPTS[lane].encode()).hexdigest()}
        except OSError as exc:
            return {"lane": lane, "arm": arm, "valid": False, "marker_observed": False,
                    "tripwire_leaked": False, "failure_kind": f"launch:{type(exc).__name__}",
                    "wall_seconds": time.monotonic() - started,
                    "native_skill_path": str(skill_path.relative_to(root)) if skill_path else None,
                    "carrier_used": False,
                    "prompt_sha256": hashlib.sha256(PROMPTS[lane].encode()).hexdigest()}
    finally:
        shutil.rmtree(root)


def run_smoke(timeout: int = 240) -> dict:
    marker = "NATIVE_SKILL_LOADED_" + secrets.token_hex(12)
    env = host_auth_env()
    runs = [execute_one(lane, arm, marker, timeout) for lane in LANES for arm in ARMS]
    lane_valid = {lane: all(run["valid"] for run in runs if run["lane"] == lane) for lane in LANES}
    return {
        "schema_version": 1,
        "evaluation_kind": "native-delivery-feasibility-smoke",
        "outcome_verdict": "NOT_AN_OUTCOME_EVALUATION",
        "prompt_identical_across_arms": {
            lane: len({run["prompt_sha256"] for run in runs if run["lane"] == lane}) == 1
            for lane in LANES
        },
        "marker_sha256": hashlib.sha256(marker.encode()).hexdigest(),
        "auth_mode": "host auth store inherited by CLI; API-key environment variables excluded; credentials not copied into fixtures; validity requires zero host-reported tool calls",
        "egress_controls": {
            "codex-default": "read-only sandbox; workspace network disabled; user config and rules ignored",
            "claude-opus": "only the native Skill loader is enabled; empty strict MCP config; project settings only",
        },
        "cli_versions": {"codex": _version("codex", env), "claude": _version("claude", env)},
        "runs": runs,
        "lane_valid": lane_valid,
        "valid": all(lane_valid.values()) and len(runs) == 4,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit("refusing four paid host calls without --execute")
    report = run_smoke(args.timeout)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    temp = args.out.with_suffix(args.out.suffix + ".tmp")
    temp.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    temp.replace(args.out)
    print(json.dumps({"valid": report["valid"], "lane_valid": report["lane_valid"],
                      "out": str(args.out)}, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
