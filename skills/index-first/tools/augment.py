#!/usr/bin/env python3
"""augment.py — opt-in index-first PreToolUse augmenter for Claude Code.

Ported from codebase-memory-mcp's src/cli/hook_augment.c. Reads the PreToolUse
hook JSON from stdin and, for Grep/Glob calls only, injects the top index hits
for the longest identifier in the search pattern as `additionalContext` so the
agent gets structured context alongside its normal search results.

CARDINAL RULE (verbatim intent from hook_augment.c): this NEVER blocks a tool
call. Every error, timeout, missing index, parse failure, or short/odd pattern
results in `exit 0` with NO stdout (a clean pass-through). Output is written
exactly ONCE at the very end, so firing mid-work yields a clean no-op, never
partial JSON. NEVER acts on Read — gating Read would break read-before-edit.

HARD DEADLINE: a signal.alarm budget (~300ms) os._exit(0)s on fire so a slow
index query can never stall the agent. Where SIGALRM is unavailable (Windows),
a threading.Timer fallback arms the same os._exit(0).
"""
import json
import os
import re
import subprocess
import sys

MIN_TOKEN = 4            # skip short/noisy patterns before any work
MAX_TOKEN = 96
RESULT_LIMIT = 3         # inject the top ~3 hits
DEADLINE_MS = int(os.environ.get("INDEX_FIRST_DEADLINE_MS", "300"))

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


# ── Hard deadline ───────────────────────────────────────────────────────────
def _deadline_exit(*_a):
    # Fire-and-die: no stdout has been written yet (we emit exactly once, last),
    # so a clean no-op is guaranteed.
    os._exit(0)


def _arm_deadline():
    secs = max(DEADLINE_MS, 1) / 1000.0
    try:
        import signal

        signal.signal(signal.SIGALRM, _deadline_exit)
        signal.setitimer(signal.ITIMER_REAL, secs)
    except (ImportError, AttributeError, ValueError):
        # No SIGALRM (e.g. Windows): fall back to a daemon timer thread.
        import threading

        t = threading.Timer(secs, _deadline_exit)
        t.daemon = True
        t.start()


# ── pattern → token ─────────────────────────────────────────────────────────
def _extract_token(pattern):
    """Longest identifier-like run ([A-Za-z_][A-Za-z0-9_]*) of length >=MIN_TOKEN.

    A pure identifier is always safe to embed in a query. Returns None when the
    pattern has no usable token (path globs, short/regex-only patterns) — the
    caller then no-ops, keeping the common cheap case cheap.
    """
    if not pattern:
        return None
    best = ""
    for m in _IDENT.finditer(pattern):
        if len(m.group(0)) > len(best):
            best = m.group(0)
    if len(best) < MIN_TOKEN:
        return None
    return best[:MAX_TOKEN]


# ── index query ─────────────────────────────────────────────────────────────
def _query_cmd(token):
    """Pick the index command for `token`.

    Precedence:
      1. INDEX_FIRST_QUERY_CMD (JSON argv list) — test/override hook; `token`
         is appended as the final arg.
      2. graphify, if graphify-out/graph.json exists -> `graphify explain`.
      3. wiki-memory search -> `python3 skills/wiki-memory/tools/wiki.py search`.
    Returns an argv list or None.
    """
    override = os.environ.get("INDEX_FIRST_QUERY_CMD")
    if override:
        argv = json.loads(override)
        if not isinstance(argv, list):
            return None
        return [str(a) for a in argv] + [token]

    if os.path.exists(os.path.join("graphify-out", "graph.json")):
        return ["graphify", "explain", token]

    wiki = os.path.join("skills", "wiki-memory", "tools", "wiki.py")
    if os.path.exists(wiki):
        return [sys.executable, wiki, "search", token]

    return None


def _run_query(argv, budget_ms):
    """Run the index command with a wall-clock cap; return stdout or None.

    Any failure (missing binary, non-zero exit, timeout) -> None (no-op).
    """
    try:
        p = subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            timeout=max(budget_ms, 50) / 1000.0,
        )
    except Exception:
        return None
    if p.returncode != 0:
        return None
    try:
        return p.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None  # non-UTF8 output is broken; never emit replacement garbage


def _format_context(raw, token, freetext_ok=False):
    """Format the top RESULT_LIMIT hits as a compact additionalContext string.

    Accepts the two index shapes this hook queries:
      - wiki.py search: JSON array of {id/path/title/preview, ...}
      - graphify explain: free text (used as-is, trimmed).
    Returns None on empty/unparseable/zero-hit output.
    """
    if not raw or not raw.strip():
        return None
    text = raw.strip()

    hits = None
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        data = None

    if isinstance(data, list):
        hits = data
    elif isinstance(data, dict):
        for key in ("results", "hits", "matches"):
            if isinstance(data.get(key), list):
                hits = data[key]
                break

    if hits is not None:
        if not hits:
            return None  # valid index, no matching entries -> no-op
        lines = []
        for h in hits[:RESULT_LIMIT]:
            if isinstance(h, dict):
                disp = h.get("path") or h.get("id") or h.get("qualified_name") or h.get("name") or ""
                title = h.get("title") or h.get("label") or ""
                lines.append(f"- {disp}  {title}".rstrip())
            else:
                lines.append(f"- {h}")
        if not lines:
            return None
        body = "\n".join(lines)
        return (
            f"[index-first] {min(len(hits), RESULT_LIMIT)} index hit(s) match "
            f'"{token}" (structured context; your search results below are '
            f"unaffected):\n{body}"
        )

    # Non-JSON output. Only the graphify-explain backend legitimately returns
    # free text; a JSON backend (wiki search / test override) returning non-JSON
    # is broken output and must NOT be emitted (cardinal rule: noop on bad data).
    if not freetext_ok:
        return None
    # Strip control chars a backend could emit (NUL, 0x01-0x1f) — keep tab/
    # newline. graphify output is otherwise trusted; this is belt-and-braces.
    snippet = "".join(c for c in text[:3500] if c in "\t\n" or ord(c) >= 0x20)
    return (
        f'[index-first] index context for "{token}" (your search results '
        f"below are unaffected):\n{snippet}"
    )


def _emit(text):
    """Emit the PreToolUse additionalContext payload to stdout (exactly once)."""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": text,
        }
    }
    sys.stdout.write(json.dumps(payload))


def main():
    _arm_deadline()

    raw_in = sys.stdin.read()
    if not raw_in:
        return 0
    try:
        root = json.loads(raw_in)
    except (ValueError, TypeError):
        return 0
    if not isinstance(root, dict):
        return 0

    tool = root.get("tool_name")
    # Only Grep/Glob. NEVER act on Read or anything else.
    if tool not in ("Grep", "Glob"):
        return 0

    tin = root.get("tool_input")
    pattern = tin.get("pattern") if isinstance(tin, dict) else None
    token = _extract_token(pattern)
    if not token:
        return 0

    argv = _query_cmd(token)
    if not argv:
        return 0

    # Cap the subprocess below the in-process deadline so the common slow-query
    # case returns cleanly via subprocess timeout; the SIGALRM deadline is the
    # hard backstop for any other stall (e.g. a hung syscall).
    raw = _run_query(argv, max(DEADLINE_MS - 50, 50))
    # Free text is trusted ONLY from the real graphify-explain backend, detected
    # by the graphify-out/graph.json index — NOT by argv[0]'s name, which an
    # INDEX_FIRST_QUERY_CMD override could spoof with a 'graphify'-named script.
    # Any override / wiki backend must return parseable JSON or this noops.
    freetext_ok = (
        not os.environ.get("INDEX_FIRST_QUERY_CMD")
        and os.path.exists(os.path.join("graphify-out", "graph.json"))
    )
    ctx = _format_context(raw, token, freetext_ok)
    if ctx:
        _emit(ctx)  # the single, final write
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Cardinal rule: any unforeseen failure is still a clean pass-through.
        os._exit(0)
