#!/usr/bin/env python3
"""loop-breaker PreToolUse hook.

Reads Claude Code's PreToolUse payload from stdin, tracks consecutive-identical
tool calls per session, and emits an `additionalContext` signal when the
threshold is hit. Optionally escalates to `permissionDecision: deny`.

Payload shape (Claude Code PreToolUse):
  {
    "session_id": "...",
    "hook_event_name": "PreToolUse",
    "tool_name": "Bash",
    "tool_input": { ... },
    ...
  }

Output (stdout, one JSON object, only when threshold hit):
  {
    "hookSpecificOutput": {
      "hookEventName": "PreToolUse",
      "additionalContext": "<replan signal>",
      // optional, with LOOP_BREAKER_HARD_BLOCK=1 past threshold:
      "permissionDecision": "deny",
      "permissionDecisionReason": "<same signal>"
    }
  }

Contract: always exit 0. The hook must never stall the agent on its own bugs.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path


THRESHOLD_DEFAULT = 5
PREVIEW_MAX = 200
GC_AGE_SECONDS = 7 * 24 * 3600   # delete state files older than 7 days
GC_SCAN_MAX = 500                # bound the scandir cost


def log_err(msg: str) -> None:
    ts = time.strftime("%FT%TZ", time.gmtime())
    sys.stderr.write(f"{ts} loop-breaker: {msg}\n")


SIG_STRIP_KEYS = {"description"}  # model-generated free-text labels that vary per call


def signature_input(tool_input: object) -> object:
    """Project tool_input down to fields that meaningfully define the action.
    Drops `description` (model-generated label, varies per call) and any
    leading-underscore internal fields. Other tool-specific drift sources
    (e.g. a future `_callId`) get caught by the underscore rule."""
    if isinstance(tool_input, dict):
        return {
            k: v for k, v in tool_input.items()
            if k not in SIG_STRIP_KEYS and not k.startswith("_")
        }
    return tool_input


def canonical_signature(tool_name: str, tool_input: object) -> str:
    projected = signature_input(tool_input)
    try:
        canon = json.dumps(projected, sort_keys=True, separators=(",", ":"), default=str)
    except Exception:
        canon = repr(projected)
    digest = hashlib.sha256(canon.encode("utf-8", errors="replace")).hexdigest()
    return f"{tool_name}::{digest}"


def preview(tool_name: str, tool_input: object) -> str:
    try:
        if isinstance(tool_input, dict):
            if tool_name == "Bash" and "command" in tool_input:
                raw = str(tool_input.get("command", ""))
            elif "file_path" in tool_input:
                raw = f"{tool_input.get('file_path', '')}"
                extras = {k: v for k, v in tool_input.items() if k != "file_path"}
                if extras:
                    raw += f" {json.dumps(extras, default=str)[:120]}"
            else:
                raw = json.dumps(tool_input, default=str)
        else:
            raw = str(tool_input)
    except Exception:
        raw = repr(tool_input)
    raw = raw.replace("\n", " ⏎ ")
    return raw[:PREVIEW_MAX] + ("…" if len(raw) > PREVIEW_MAX else "")


def state_dir() -> Path:
    override = os.environ.get("LOOP_BREAKER_STATE_DIR")
    if override:
        return Path(override)
    # Anchor to the project dir Claude Code reports — process cwd is NOT stable
    # across tool calls (the agent can `cd` mid-session), and a relative state
    # path would silently fragment the per-session counter across multiple
    # directories. CLAUDE_PROJECT_DIR is set by Claude Code for every hook
    # invocation. Fall back to cwd if it's missing (other hosts / tests).
    project = os.environ.get("CLAUDE_PROJECT_DIR")
    base = Path(project) if project else Path.cwd()
    return base / ".token-economy" / "loop-breaker"


def state_path(session_id: str) -> Path:
    # H6 fix: 8-char truncation caused collisions when distinct sessions shared
    # the same prefix (e.g. two UUIDs starting "a3f0c1d2…"), making one session
    # overwrite another's state under the same flock. Hash the full session_id
    # so the filename stays short and filesystem-safe while distinct inputs
    # remain distinct. (SHA-256 truncated to 16 hex chars: ~2^64 namespace —
    # collisions are astronomically unlikely for the per-host session count.)
    sid = session_id or "unknown"
    sid_hash = hashlib.sha256(sid.encode("utf-8", errors="replace")).hexdigest()[:16]
    return state_dir() / f"{sid_hash}.json"


def gc_old_state(dir_path: Path, now: float) -> int:
    """Delete state + lock files older than GC_AGE_SECONDS. Returns count removed.
    Bounded by GC_SCAN_MAX; on any error logs and returns the count so far."""
    if not dir_path.is_dir():
        return 0
    removed = 0
    try:
        with os.scandir(dir_path) as it:
            for i, entry in enumerate(it):
                if i >= GC_SCAN_MAX:
                    break
                if not entry.is_file():
                    continue
                name = entry.name
                if not (name.endswith(".json") or name.endswith(".json.lock")):
                    continue
                try:
                    if now - entry.stat().st_mtime > GC_AGE_SECONDS:
                        os.unlink(entry.path)
                        removed += 1
                except OSError:
                    pass
    except OSError as e:
        log_err(f"gc-scandir-fail dir={dir_path} err={e!r}")
    return removed


@contextmanager
def state_lock(path: Path):
    """Hold an exclusive flock over a sibling lockfile during read+update+write.
    Parallel PreToolUse hooks for parallel tool calls would otherwise race.
    On platforms without fcntl (Windows), or if locking fails, falls through
    unlocked — better to under-count than to crash the hook.

    L5 fix: previously `open(lock_path, "a+")` would silently fall through
    unlocked if the directory was read-only or otherwise unwritable (e.g. when
    the wider state dir was relocated to a read-only mount). Now we explicitly
    catch PermissionError / OSError from mkdir + open, log a stderr warning so
    operators can see it, and *then* fall through unlocked. The hook still
    yields (and main() continues to load/save best-effort) because the
    reliability contract requires exit 0 on every input."""
    lock_path = path.with_suffix(path.suffix + ".lock")
    fh = None
    try:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except (PermissionError, OSError) as e:
            log_err(f"lock-mkdir-fail dir={path.parent} err={e!r} — proceeding unlocked")
            yield
            return
        try:
            fh = open(lock_path, "a+")
        except (PermissionError, OSError) as e:
            log_err(f"lock-open-fail path={lock_path} err={e!r} — proceeding unlocked")
            yield
            return
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        except (OSError, AttributeError) as e:
            log_err(f"lock-skip path={lock_path} err={e!r}")
        yield
    except Exception as e:
        # Last-resort guard: never let a lock-layer bug crash the hook.
        log_err(f"lock-unexpected path={lock_path} err={e!r}")
        yield
    finally:
        if fh is not None:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                fh.close()
            except Exception:
                pass


def load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception as e:
        log_err(f"state-read-fail path={path} err={e!r}")
        return {}


def save_state(path: Path, state: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    except Exception as e:
        log_err(f"state-write-fail path={path} err={e!r}")


def build_signal(tool_name: str, prev: str, count: int, threshold: int) -> str:
    return (
        f"⚠️ loop-breaker: the same tool call has now happened {count}× in a row "
        f"(threshold {threshold}).\n"
        f"  tool: {tool_name}\n"
        f"  args (truncated): {prev}\n"
        f"Stop. This is the pattern that burns the most tokens in long sessions. "
        f"Before calling this again, briefly:\n"
        f"  1. State the last error verbatim (don't paraphrase).\n"
        f"  2. Name a *different* hypothesis for the failure.\n"
        f"  3. Pick a different next step — a different tool, different args, "
        f"or ask the user.\n"
        f"If the repetition was intentional (polling, batch retry), say so once "
        f"and you won't see this again unless the count climbs further."
    )


def build_deny_reason(tool_name: str, count: int) -> str:
    """H7 fix: `permissionDecisionReason` should be a single concise line.
    Multi-paragraph text rendered there gets truncated or displayed poorly in
    Claude Code's permission UI. Keep the long-form replan text in
    `additionalContext`; the reason is a one-line summary the user/agent sees
    in the deny notification."""
    return (
        f"loop-breaker: {count}× identical {tool_name} call — "
        f"change approach (see additionalContext)"
    )


def resolve_threshold() -> int:
    """M3 fix: explicit validation of LOOP_BREAKER_THRESHOLD with stderr warnings.
    Previously: `max(2, int(env))` silently clamped THRESHOLD=1 to 2, and any
    ValueError (empty string, whitespace, non-numeric) was swallowed by a bare
    `except ValueError: pass`. Now: empty / whitespace / non-numeric falls back
    to the default with a stderr warning; explicit clamping of values <2 is
    also warned. Behavioral contract preserved — test.sh case [2] still expects
    `THRESHOLD=1` to behave as 2 — only the warning is new."""
    raw = os.environ.get("LOOP_BREAKER_THRESHOLD")
    if raw is None:
        return THRESHOLD_DEFAULT
    s = raw.strip()
    if not s:
        log_err(f"threshold-empty: LOOP_BREAKER_THRESHOLD={raw!r} → using default {THRESHOLD_DEFAULT}")
        return THRESHOLD_DEFAULT
    try:
        n = int(s)
    except ValueError:
        log_err(f"threshold-invalid: LOOP_BREAKER_THRESHOLD={raw!r} (not an integer) → using default {THRESHOLD_DEFAULT}")
        return THRESHOLD_DEFAULT
    if n < 2:
        log_err(f"threshold-clamped: LOOP_BREAKER_THRESHOLD={n} too low (min 2) → clamped to 2")
        return 2
    return n


def main() -> int:
    threshold = resolve_threshold()

    hard_block = os.environ.get("LOOP_BREAKER_HARD_BLOCK") == "1"
    allowlist_raw = os.environ.get("LOOP_BREAKER_ALLOWLIST_TOOLS", "")
    allowlist = {t.strip() for t in allowlist_raw.split(",") if t.strip()}

    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        log_err(f"json-decode-fail: {e}")
        return 0

    tool_name = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input")
    session_id = payload.get("session_id") or "unknown"

    if not tool_name:
        return 0
    if tool_name in allowlist:
        return 0

    sig = canonical_signature(tool_name, tool_input)
    path = state_path(session_id)
    is_new_session = not path.exists()

    with state_lock(path):
        state = load_state(path)
        now_iso = time.strftime("%FT%TZ", time.gmtime())
        if state.get("last_signature") == sig:
            count = int(state.get("consecutive_count", 1)) + 1
        else:
            count = 1
            state["first_seen_iso"] = now_iso

        state.update({
            "last_signature": sig,
            "last_tool_name": tool_name,
            "last_tool_input_preview": preview(tool_name, tool_input),
            "consecutive_count": count,
            "last_seen_iso": now_iso,
        })
        save_state(path, state)

    if is_new_session:
        gc_old_state(path.parent, time.time())

    # Two independent paths:
    #   - SIGNAL (additionalContext) fires only on RISING EDGE (count crosses
    #     threshold) or ESCALATION (multiple of threshold past). Previous code
    #     fired on every call past threshold → context polluted with N copies of
    #     the same warning on legitimate polls / pagination.
    #   - HARD-BLOCK (permissionDecision: deny) fires on every call past
    #     threshold when LOOP_BREAKER_HARD_BLOCK=1 — that's its whole purpose.
    if count < threshold:
        return 0

    edge = count == threshold
    escalation = count > threshold and count % threshold == 0
    deny = hard_block and count > threshold
    if not (edge or escalation or deny):
        return 0

    signal = build_signal(tool_name, state["last_tool_input_preview"], count, threshold)
    hook_out: dict = {"hookEventName": "PreToolUse"}
    if edge or escalation:
        hook_out["additionalContext"] = signal
    if deny:
        # H7 fix: keep the multi-paragraph replan signal in additionalContext
        # (where multi-line text renders fine) and put a single concise line in
        # permissionDecisionReason (where the Claude Code permission UI expects
        # a one-liner — multi-paragraph text gets truncated or rendered poorly).
        hook_out["permissionDecision"] = "deny"
        hook_out["permissionDecisionReason"] = build_deny_reason(tool_name, count)
        if "additionalContext" not in hook_out:
            hook_out["additionalContext"] = signal

    sys.stdout.write(json.dumps({"hookSpecificOutput": hook_out}))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
