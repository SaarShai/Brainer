#!/usr/bin/env python3
"""Give an equivalent host hook precedence over Brainer's plugin hook.

Claude loads project hooks and native-plugin hooks independently.  When both
point at the same installed Brainer handler, executing both doubles every side
effect.  This router is the plugin-side boundary: it suppresses only when the
active project or user settings configure the exact expected executable. Any
uncertainty fails open to the packaged plugin handler.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def active_project(raw: bytes, env: dict[str, str] | None = None,
                   process_cwd: Path | None = None) -> Path:
    """Resolve project root: payload cwd, then CLAUDE_PROJECT_DIR, then cwd."""
    environment = os.environ if env is None else env
    cwd = Path.cwd() if process_cwd is None else process_cwd
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = {}
    if isinstance(payload, dict):
        value = payload.get("cwd")
        if isinstance(value, str) and value.strip():
            candidate = Path(value).expanduser()
            return candidate if candidate.is_absolute() else cwd / candidate
    value = environment.get("CLAUDE_PROJECT_DIR", "").strip()
    if value:
        candidate = Path(value).expanduser()
        return candidate if candidate.is_absolute() else cwd / candidate
    return cwd


def _handler_tokens(handler: dict) -> list[str]:
    command = handler.get("command")
    if not isinstance(command, str) or not command.strip():
        return []
    args = handler.get("args")
    if isinstance(args, list):
        return [command, *(str(value) for value in args)]
    try:
        return shlex.split(command)
    except ValueError:
        return []


def _resolve_command_token(token: str, project: Path) -> Path | None:
    prefixes = (
        "${CLAUDE_PROJECT_DIR:-$PWD}",
        "${CLAUDE_PROJECT_DIR}",
        "$CLAUDE_PROJECT_DIR",
        "${PWD}",
        "$PWD",
    )
    value = token
    for prefix in prefixes:
        if value == prefix or value.startswith(prefix + "/"):
            value = str(project) + value[len(prefix):]
            break
    if not value or value.startswith("-") or "$" in value:
        return None
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = project / candidate
    try:
        return candidate.resolve()
    except OSError:
        return None


def _invokes_target(handler: dict, project: Path, target: Path) -> bool:
    if handler.get("type", "command") != "command":
        return False
    tokens = _handler_tokens(handler)
    if not tokens:
        return False
    resolved = [_resolve_command_token(token, project) for token in tokens]
    if resolved[0] == target:
        return True
    launcher = Path(tokens[0]).name
    return launcher in {"bash", "sh"} and target in resolved[1:]


def has_equivalent_host_hook(project: Path, event: str, project_handler: str,
                             user_settings: Path | None = None) -> bool:
    """True only for an unconditional, exact, executable host hook.

    settings.local.json is included because Claude merges it into the active
    project hook surface; ignoring it would still double a locally configured
    handler.  A malformed settings file is ignored, which fails open to the
    plugin rather than risking a dropped lifecycle event.
    """
    target = (project / project_handler).resolve()
    if not target.is_file() or not os.access(target, os.X_OK):
        return False
    configs: list[dict] = []
    settings_paths = [
        project / ".claude" / "settings.json",
        project / ".claude" / "settings.local.json",
        user_settings or Path.home() / ".claude" / "settings.json",
    ]
    for path in settings_paths:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        configs.append(data)
    for data in configs:
        hooks = data.get("hooks")
        if not isinstance(hooks, dict):
            continue
        groups = hooks.get(event)
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, dict):
                continue
            # Conditional groups can be inactive for this payload. Suppressing
            # the plugin merely because their executable exists could drop an
            # event, so only match-all groups receive structural precedence.
            if group.get("matcher") not in (None, "", "*"):
                continue
            handlers = group.get("hooks")
            if not isinstance(handlers, list):
                continue
            if any(isinstance(handler, dict)
                   and _invokes_target(handler, project, target)
                   for handler in handlers):
                return True
    return False


def route(raw: bytes, event: str, project_handler: str,
          plugin_handler: Path, env: dict[str, str] | None = None,
          process_cwd: Path | None = None,
          user_settings: Path | None = None) -> int:
    project = active_project(raw, env=env, process_cwd=process_cwd)
    try:
        if has_equivalent_host_hook(
                project, event, project_handler, user_settings=user_settings):
            return 0
    except Exception:
        pass  # Fail open: an uncertain project check must not drop the event.
    try:
        handler_cwd = project if project.is_dir() else None
        child_env = os.environ.copy()
        if env is not None:
            child_env.update(env)
        if handler_cwd is not None:
            child_env["CLAUDE_PROJECT_DIR"] = str(project)
        return subprocess.run(
            ["bash", str(plugin_handler)], input=raw, cwd=handler_cwd,
            env=child_env).returncode
    except OSError as exc:
        print(f"brainer plugin hook fallback failed: {exc}", file=sys.stderr)
        return 0


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: project_hook_precedence.py EVENT PROJECT_HANDLER PLUGIN_HANDLER",
              file=sys.stderr)
        return 0
    event, project_handler, plugin_handler = sys.argv[1:]
    raw = sys.stdin.buffer.read()
    return route(raw, event, project_handler, PLUGIN_ROOT / plugin_handler)


if __name__ == "__main__":
    raise SystemExit(main())
