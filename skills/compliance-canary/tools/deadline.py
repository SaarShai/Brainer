#!/usr/bin/env python3
"""Hard-deadline wrapper for Brainer hook entrypoints.

Ported from codebase-memory-mcp's `ha_arm_deadline` (src/cli/hook_augment.c):
a slow subprocess, SQLite open, or regex blow-up must never stall the host.
When the deadline fires the hook abandons its work and yields a CLEAN no-op —
honoring the cardinal rule that a hook NEVER blocks the tool/prompt/compaction
it is attached to.

Two entry points, both Unix-first (`signal.alarm`) with a `threading.Timer`
fallback on platforms / threads where SIGALRM is unavailable (Windows, or a
non-main thread):

    # 1. Context manager — surface the timeout, let the caller fall through
    #    to its own clean `return 0`. Use INSIDE a hook's main():
    try:
        with hard_deadline(0.3):
            ...slow work...
    except HookDeadline:
        pass            # nothing emitted → clean pass-through
    return 0

    # 2. run_or_exit0 — the strictest cbm-equivalent: on timeout it _exit(0)s
    #    immediately (no partial output, no traceback). Use when there is no
    #    safe local fallback and the only correct action on overrun is to
    #    vanish:
    run_or_exit0(do_work, seconds=0.3)

HOOK-AUTHOR NOTES
-----------------
* Arm the deadline FIRST, before reading stdin or touching the filesystem —
  the whole point is to bound the *entire* hook, exactly as cbm calls
  `ha_arm_deadline()` as the first line of `cbm_cmd_hook_augment`.
* Write your stdout payload EXACTLY ONCE, at the very end. If the timer fires
  mid-work you then emit nothing — no partial JSON, no half-line. (cbm:
  "Output is written exactly once at the very end, so firing mid-work simply
  yields a clean no-op.")
* The SIGALRM path only works on the main thread of a Unix process. Off the
  main thread (or on Windows) we transparently fall back to a `threading.Timer`
  that, for `run_or_exit0`, calls `os._exit(0)`; for `hard_deadline` it sets a
  flag the body cannot observe cooperatively, so prefer `run_or_exit0` when you
  may run off-thread.
* `seconds` accepts a float; sub-second budgets (e.g. 0.3) match cbm's 300 ms.
"""
from __future__ import annotations

import os
import signal
import threading
from contextlib import contextmanager
from typing import Callable, Iterator, Optional, TypeVar

T = TypeVar("T")


class HookDeadline(Exception):
    """Raised inside `hard_deadline` when the wall-clock budget is exceeded."""


def _can_use_sigalrm() -> bool:
    # SIGALRM exists only on Unix, and signal handlers can only be installed
    # from the main thread of the main interpreter.
    return (
        hasattr(signal, "SIGALRM")
        and threading.current_thread() is threading.main_thread()
    )


@contextmanager
def hard_deadline(seconds: float) -> Iterator[None]:
    """Context manager arming a wall-clock deadline of `seconds`.

    On overrun raises `HookDeadline` inside the block (Unix/main-thread via
    SIGALRM). Always restores any previous SIGALRM handler / timer on exit, so
    nesting and reuse are safe. A non-positive budget is a no-op (runs the body
    unbounded) — callers that want "no deadline" can pass 0.
    """
    if seconds is None or seconds <= 0:
        yield
        return

    if _can_use_sigalrm():
        def _on_alarm(signum, frame):  # noqa: ANN001
            raise HookDeadline(f"hook exceeded {seconds:g}s deadline")

        prev_handler = signal.signal(signal.SIGALRM, _on_alarm)
        prev_timer = signal.setitimer(signal.ITIMER_REAL, seconds)[0]
        try:
            yield
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, prev_handler)
            # Best-effort restore of any outer timer that was pending.
            if prev_timer and prev_timer > 0:
                signal.setitimer(signal.ITIMER_REAL, prev_timer)
    else:
        # Fallback: a Timer can't inject an exception into arbitrary code, so
        # the body is NOT interrupted cooperatively here. We still bound the
        # process by hard-exiting 0 if the body overruns badly — preserving the
        # cardinal rule even though we can't raise HookDeadline off-thread.
        timer = threading.Timer(seconds, lambda: os._exit(0))
        timer.daemon = True
        timer.start()
        try:
            yield
        finally:
            timer.cancel()


def run_or_exit0(
    fn: Callable[[], T],
    seconds: float,
    on_timeout: Optional[Callable[[], None]] = None,
) -> Optional[T]:
    """Run `fn()` under a hard deadline; on overrun `os._exit(0)` immediately.

    The strict cbm-cardinal-rule form: there is no return-to-caller on timeout —
    the process vanishes with status 0 so the host sees a clean no-op (no
    partial output, no traceback). On success returns `fn()`'s value. Works on
    both the SIGALRM and Timer paths.

    `on_timeout` (optional) runs just before exit — keep it trivial and
    side-effect-light (e.g. an stderr log); any exception in it is swallowed.
    """
    def _bail() -> None:
        if on_timeout is not None:
            try:
                on_timeout()
            except Exception:
                pass
        os._exit(0)

    if seconds is None or seconds <= 0:
        return fn()

    if _can_use_sigalrm():
        def _on_alarm(signum, frame):  # noqa: ANN001
            _bail()

        prev_handler = signal.signal(signal.SIGALRM, _on_alarm)
        signal.setitimer(signal.ITIMER_REAL, seconds)
        try:
            return fn()
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, prev_handler)
    else:
        timer = threading.Timer(seconds, _bail)
        timer.daemon = True
        timer.start()
        try:
            return fn()
        finally:
            timer.cancel()


if __name__ == "__main__":
    # Tiny self-demo: prints the no-timeout result, then shows a fired deadline.
    import sys
    import time

    with hard_deadline(2):
        print("normal:", 2 + 2)
    try:
        with hard_deadline(0.1):
            time.sleep(2)
    except HookDeadline as e:
        print("fired:", e, file=sys.stderr)
    sys.exit(0)
