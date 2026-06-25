#!/usr/bin/env python3
"""Idempotent hook-config merge for the learn-skill installer.

Extracted from install.sh (was two inline heredocs) so the JSON-mutating logic —
which edits the user's `.claude/settings.json` and `.codex/hooks.json` — has
regression coverage (test_install_merge.py) instead of being proven only by hand.

Both merges are IDEMPOTENT and NON-DESTRUCTIVE:
  * never overwrite a corrupt config (would silently erase the user's other hooks);
  * keep every non-learn-skill hook untouched;
  * a learn-skill hook on an event that is NOT the current command is pruned
    (stale wiring — e.g. an old Stop -> hook_session_end.sh, or a path change),
    so a re-install converges to exactly one learn-skill hook per event.

CLI (called by install.sh):
  hook_merge.py settings <settings.json> <end_cmd> <start_cmd>
  hook_merge.py codex    <hooks.json>    <end_cmd> <start_cmd>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _load_or_abort(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        # NEVER overwrite a corrupt config — that would silently erase the user's
        # other hooks/permissions. Abort; the human fixes it.
        sys.stderr.write(f"ABORT: {path} is not valid JSON ({e}).\n"
                         f"Fix or remove it, then re-run this installer.\n")
        sys.exit(1)


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _ensure_on_event(rules: list, cmd: str, *, prune_stale: bool) -> None:
    """Ensure exactly one matcher='*' rule on this event carries `cmd`.

    prune_stale=True (Codex): drop any learn-skill hook whose command != cmd
    (old wiring / path change), so re-install converges to one. Non-learn-skill
    hooks are always preserved. prune_stale=False (Claude SessionStart/End): the
    command paths are stable, so we only de-dup the exact same command."""
    if prune_stale:
        for rule in rules:
            rule["hooks"] = [h for h in rule.get("hooks", [])
                             if not ("learn-skill" in h.get("command", "")
                                     and h.get("command") != cmd)]
        # drop now-empty default rules, keep any rule with a non-default matcher
        rules[:] = [r for r in rules
                    if r.get("hooks") or r.get("matcher") not in (None, "*")]
    for rule in rules:
        if rule.get("matcher") not in (None, "*"):
            continue
        if any(h.get("type") == "command" and h.get("command") == cmd
               for h in rule.get("hooks", [])):
            return  # already present
    rules.append({"matcher": "*", "hooks": [{"type": "command", "command": cmd}]})


def merge(path: Path, end_cmd: str, start_cmd: str, end_event: str,
          start_event: str, *, prune_stale: bool) -> None:
    data = _load_or_abort(path)
    hooks = data.setdefault("hooks", {})
    for event, cmd in ((end_event, end_cmd), (start_event, start_cmd)):
        rules = hooks.setdefault(event, [])
        _ensure_on_event(rules, cmd, prune_stale=prune_stale)
    _write(path, data)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 4:
        sys.stderr.write("usage: hook_merge.py {settings|codex} <path> <end_cmd> <start_cmd>\n")
        return 2
    kind, path, end_cmd, start_cmd = argv
    if kind == "settings":   # Claude: SessionEnd + SessionStart, stable paths
        merge(Path(path), end_cmd, start_cmd, "SessionEnd", "SessionStart", prune_stale=False)
    elif kind == "codex":    # Codex: Stop + UserPromptSubmit, prune stale wiring
        merge(Path(path), end_cmd, start_cmd, "Stop", "UserPromptSubmit", prune_stale=True)
    else:
        sys.stderr.write(f"unknown kind: {kind!r}\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
