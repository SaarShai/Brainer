#!/usr/bin/env python3
"""Self-test for augment.py — the opt-in index-first PreToolUse hook.

Plain-python (assert + exit 1 style; no pytest dep), mirroring the Brainer
convention in scripts/run_all_tests.sh. Feeds synthetic Claude Code PreToolUse
hook JSON on stdin and asserts the cardinal rule: the hook NEVER blocks and
emits additionalContext only on a real index hit; every other path is a clean
no-op (exit 0, no stdout).

Cases:
  1. valid token + index hit      -> additionalContext on stdout, exit 0
  2. Read tool                    -> no stdout, exit 0 (never gate Read)
  3. <4-char pattern              -> no stdout, exit 0
  4. glob-only pattern            -> no stdout, exit 0
  5. regex-only pattern           -> no stdout, exit 0
  6. index command fails          -> no stdout, exit 0
  7. slow query exceeds deadline  -> exit 0, no partial stdout
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
AUGMENT = os.path.join(HERE, "augment.py")


def run(payload, env_extra=None, timeout=10):
    """Run augment.py with `payload` (dict) on stdin; return (rc, stdout)."""
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if env_extra:
        env.update(env_extra)
    p = subprocess.run(
        [sys.executable, AUGMENT],
        input=json.dumps(payload).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        timeout=timeout,
    )
    return p.returncode, p.stdout.decode("utf-8", "replace")


def assert_noop(rc, out, label):
    assert rc == 0, f"{label}: expected exit 0, got {rc} (stdout: {out!r})"
    assert out.strip() == "", f"{label}: expected NO stdout, got {out!r}"
    print(f"PASS {label}")


def assert_context(rc, out, token, label):
    assert rc == 0, f"{label}: expected exit 0, got {rc}"
    assert out.strip(), f"{label}: expected stdout, got empty"
    doc = json.loads(out)  # must be valid JSON, emitted exactly once
    hso = doc.get("hookSpecificOutput", {})
    assert hso.get("hookEventName") == "PreToolUse", f"{label}: bad hookEventName: {doc!r}"
    ctx = hso.get("additionalContext", "")
    assert ctx, f"{label}: empty additionalContext"
    assert token in ctx, f"{label}: token {token!r} not in context: {ctx!r}"
    print(f"PASS {label}")


def main():
    assert os.path.exists(AUGMENT), f"augment.py not found at {AUGMENT}"

    tmp = tempfile.mkdtemp()

    # A fake index command we control. Emits a wiki.py-shaped JSON array so the
    # hook's parser has a real hit to format; echoes the token (last argv) back
    # so the test can assert it round-tripped into the context.
    fake_ok = os.path.join(tmp, "fake_index_ok.py")
    with open(fake_ok, "w") as f:
        f.write(
            "import json,sys\n"
            "tok=sys.argv[-1]\n"
            "print(json.dumps([\n"
            "  {'id':'a/'+tok,'path':'a/'+tok+'.md','title':tok+' page','preview':'p'},\n"
            "  {'id':'b/'+tok,'path':'b/'+tok+'.md','title':'second','preview':'q'},\n"
            "]))\n"
        )

    # A fake index command that fails (non-zero exit, garbage on stdout).
    fake_fail = os.path.join(tmp, "fake_index_fail.py")
    with open(fake_fail, "w") as f:
        f.write("import sys\nsys.stdout.write('not json {[')\nsys.exit(3)\n")

    # A fake index command that sleeps well past the hook's deadline.
    fake_slow = os.path.join(tmp, "fake_index_slow.py")
    with open(fake_slow, "w") as f:
        f.write("import time\ntime.sleep(5)\nprint('[]')\n")

    ok_cmd = json.dumps([sys.executable, fake_ok])
    fail_cmd = json.dumps([sys.executable, fake_fail])
    slow_cmd = json.dumps([sys.executable, fake_slow])

    # 1. valid token + index hit -> additionalContext
    rc, out = run(
        {"tool_name": "Grep", "tool_input": {"pattern": "handleRequest"}},
        env_extra={"INDEX_FIRST_QUERY_CMD": ok_cmd},
    )
    assert_context(rc, out, "handleRequest", "valid_token_grep")

    # 1b. Glob with a real token also augments
    rc, out = run(
        {"tool_name": "Glob", "tool_input": {"pattern": "**/payment_service*.py"}},
        env_extra={"INDEX_FIRST_QUERY_CMD": ok_cmd},
    )
    assert_context(rc, out, "payment_service", "valid_token_glob")

    # 2. Read tool -> never gated, clean no-op even with a juicy pattern/path
    rc, out = run(
        {"tool_name": "Read", "tool_input": {"file_path": "/x/handleRequest.py"}},
        env_extra={"INDEX_FIRST_QUERY_CMD": ok_cmd},
    )
    assert_noop(rc, out, "read_tool_noop")

    # 3. <4-char pattern -> no usable token
    rc, out = run(
        {"tool_name": "Grep", "tool_input": {"pattern": "foo"}},
        env_extra={"INDEX_FIRST_QUERY_CMD": ok_cmd},
    )
    assert_noop(rc, out, "short_pattern_noop")

    # 4. glob-only pattern -> no identifier of length >=4
    rc, out = run(
        {"tool_name": "Glob", "tool_input": {"pattern": "**/*.py"}},
        env_extra={"INDEX_FIRST_QUERY_CMD": ok_cmd},
    )
    assert_noop(rc, out, "glob_only_noop")

    # 5. regex-only pattern -> punctuation/anchors, no identifier run >=4
    rc, out = run(
        {"tool_name": "Grep", "tool_input": {"pattern": "^\\s*[{}()]+\\s*$"}},
        env_extra={"INDEX_FIRST_QUERY_CMD": ok_cmd},
    )
    assert_noop(rc, out, "regex_only_noop")

    # 6. index command fails -> clean pass-through
    rc, out = run(
        {"tool_name": "Grep", "tool_input": {"pattern": "handleRequest"}},
        env_extra={"INDEX_FIRST_QUERY_CMD": fail_cmd},
    )
    assert_noop(rc, out, "index_failure_noop")

    # 6b. missing index command (binary doesn't exist) -> clean pass-through
    rc, out = run(
        {"tool_name": "Grep", "tool_input": {"pattern": "handleRequest"}},
        env_extra={"INDEX_FIRST_QUERY_CMD": json.dumps(["/no/such/binary/xyzzy"])},
    )
    assert_noop(rc, out, "missing_index_noop")

    # 7. slow query exceeding the deadline -> exit 0, no partial stdout
    rc, out = run(
        {"tool_name": "Grep", "tool_input": {"pattern": "handleRequest"}},
        env_extra={"INDEX_FIRST_QUERY_CMD": slow_cmd, "INDEX_FIRST_DEADLINE_MS": "300"},
    )
    assert_noop(rc, out, "slow_query_deadline_noop")

    # 8. empty / malformed stdin -> clean no-op
    p = subprocess.run(
        [sys.executable, AUGMENT],
        input=b"not json at all",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
    )
    assert_noop(p.returncode, p.stdout.decode("utf-8", "replace"), "malformed_stdin_noop")

    print("\nALL augment tests passed")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)
