#!/usr/bin/env python3
"""hook_validate.py — static safety checker for Brainer hook entrypoints.

Ported from codebase-memory-mcp's hook cardinal rule (hook_augment.c): a hook
NEVER blocks the tool / prompt / compaction it is attached to. Every error,
timeout, or odd-input path must end in `exit 0` with no partial output, and the
hook must not stall the host.

This is a REPORT-ONLY static linter. It scans every Brainer hook entrypoint
(the `hook.py` / `hook.sh` files under `skills/*/tools/`) and FLAGS any that:

  (a) nonzero_exit          — can exit non-zero on an error path
  (b) partial_stdout        — emit stdout before an error/raise (risking a
                              half-written payload when the error path runs)
  (c) subprocess_no_timeout — call a subprocess without a timeout
  (d) stdout_log            — write a log/diagnostic line to stdout instead of
                              stderr (stdout is the host-consumed channel)

Findings are heuristic and per-file. Exit code: 0 = clean, 1 = findings,
2 = usage error.

KNOWN LIMITS (this is a heuristic lint, not a sandbox). It detects the literal
forms — `sys.exit(N)`, `os._exit(N)`, `subprocess.run`/`Popen`/aliased imports,
`os.system`/`os.popen`, comment-stripped shell guards. It CANNOT see exits or
subprocess calls reached through arbitrary indirection: a rebound name
(`e = os._exit; e(1)`), a `getattr(os, "_exit")()`, an `exec`/`eval`, or a call
through a returned callable. Treat a clean result as "no literal violation
found", not "proven safe". Author hooks in the direct style so the linter can
see them.

Usage:
  hook_validate.py                 # sweep skills/<skill>/tools/hook.{py,sh}
  hook_validate.py FILE [FILE...]  # check specific entrypoints
  hook_validate.py --json          # machine-readable findings
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # repo root: skills/<s>/tools/ -> repo

# Finding codes (stable — referenced by tests + the hook_output_anomaly probe).
NONZERO_EXIT = "nonzero_exit"
PARTIAL_STDOUT = "partial_stdout"
SUBPROCESS_NO_TIMEOUT = "subprocess_no_timeout"
STDOUT_LOG = "stdout_log"

_SUBPROCESS_FNS = {"run", "call", "check_call", "check_output", "Popen"}
# Words that mark a print/stdout.write as a diagnostic/log rather than the
# hook's real payload. Heuristic, deliberately conservative.
_LOG_HINT = re.compile(
    r"\b(error|err|warn|warning|fail|failed|debug|log|exception|traceback|"
    r"missing|empty|timeout|skip|skipped)\b",
    re.I,
)


# ── Python entrypoint analysis (AST) ────────────────────────────────────────
def _is_stdout_write(node: ast.Call) -> bool:
    # sys.stdout.write(...) / stdout.write(...)
    f = node.func
    if isinstance(f, ast.Attribute) and f.attr == "write":
        v = f.value
        if isinstance(v, ast.Attribute) and v.attr == "stdout":
            return True
        if isinstance(v, ast.Name) and v.id == "stdout":
            return True
    return False


def _print_to_stdout(node: ast.Call) -> bool:
    # print(...) with no file= (or file=sys.stdout) → goes to stdout.
    f = node.func
    if not (isinstance(f, ast.Name) and f.id == "print"):
        return False
    for kw in node.keywords:
        if kw.arg == "file":
            tgt = kw.value
            if isinstance(tgt, ast.Attribute) and tgt.attr == "stdout":
                return True
            return False  # file=<something else, e.g. sys.stderr> → not stdout
    return True  # no file= → stdout


def _call_text(node: ast.Call) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _nonzero_exit_lineno(node: ast.AST) -> int | None:
    """Return lineno if node is a non-zero process exit, else None.

    Flags: sys.exit(N!=0), exit(N!=0), raise SystemExit(N!=0).
    `sys.exit(main())` / `sys.exit(0)` / bare `sys.exit()` are clean.
    """
    target = None
    args: list[ast.expr] = []
    if isinstance(node, ast.Call):
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr in ("exit", "_exit"):
            target, args = "exit", node.args  # sys.exit / os._exit
        elif isinstance(f, ast.Name) and f.id == "exit":
            target, args = "exit", node.args
    elif isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
        f = node.exc.func
        if isinstance(f, ast.Name) and f.id == "SystemExit":
            target, args = "exit", node.exc.args
    if target is None:
        return None
    if not args:
        return None  # exit() with no arg == exit(0)
    a0 = args[0]
    if isinstance(a0, ast.Constant):
        if isinstance(a0.value, int) and a0.value != 0:
            return node.lineno
        if a0.value is None:
            return None
        return None  # constant 0 / "string"-ish handled by host as nonzero-str
    return None  # dynamic (e.g. sys.exit(main())) — not a static error path


def _check_python(text: str, rel: str) -> list[tuple[str, int, str]]:
    findings: list[tuple[str, int, str]] = []
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        return [(NONZERO_EXIT, e.lineno or 0, f"unparseable: {e}")]

    stdout_writes: list[int] = []
    exit_or_raise: list[int] = []

    # Track subprocess module aliases + bare imported names so a call via an
    # alias (`import subprocess as sp; sp.run(...)`) or a direct import
    # (`from subprocess import run`) isn't missed by the timeout check.
    sub_aliases = {"subprocess"}
    sub_bare: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                if n.name == "subprocess":
                    sub_aliases.add(n.asname or "subprocess")
        elif isinstance(node, ast.ImportFrom) and node.module == "subprocess":
            for n in node.names:
                if n.name in _SUBPROCESS_FNS or n.name == "Popen":
                    sub_bare.add(n.asname or n.name)

    for node in ast.walk(tree):
        # (a) non-zero exit on an error path
        ln = _nonzero_exit_lineno(node)
        if ln is not None:
            findings.append((NONZERO_EXIT, ln, "non-zero process exit"))
            exit_or_raise.append(ln)
        # bare `raise` (re-raise) and `raise Exc(...)` that isn't SystemExit(0)
        if isinstance(node, ast.Raise):
            exit_or_raise.append(node.lineno)

        if isinstance(node, ast.Call):
            # (c) subprocess without timeout=
            f = node.func
            is_sub = (
                isinstance(f, ast.Attribute)
                and f.attr in _SUBPROCESS_FNS
                and (
                    (isinstance(f.value, ast.Name) and f.value.id in sub_aliases)
                    or f.attr == "Popen"
                )
            ) or (isinstance(f, ast.Name) and (f.id == "Popen" or f.id in sub_bare))
            if is_sub:
                has_timeout = any(kw.arg == "timeout" for kw in node.keywords)
                # Popen has no timeout= kwarg; it needs a later .wait(timeout=)/
                # .communicate(timeout=). Flag Popen without an obvious timeout
                # token anywhere in its call text (conservative).
                if not has_timeout:
                    findings.append(
                        (
                            SUBPROCESS_NO_TIMEOUT,
                            node.lineno,
                            f"{_call_text(node)[:80]}",
                        )
                    )
            # os.system / os.popen — subprocess-equivalent with no timeout knob.
            if (
                isinstance(f, ast.Attribute)
                and f.attr in ("system", "popen")
                and isinstance(f.value, ast.Name)
                and f.value.id == "os"
            ):
                findings.append(
                    (SUBPROCESS_NO_TIMEOUT, node.lineno, f"os.{f.attr}() (no timeout)")
                )
            # (b)/(d) stdout writes
            if _is_stdout_write(node) or _print_to_stdout(node):
                stdout_writes.append(node.lineno)
                # (d) stdout used for a log/diagnostic line
                txt = _call_text(node)
                if _LOG_HINT.search(txt):
                    findings.append(
                        (STDOUT_LOG, node.lineno, "diagnostic written to stdout")
                    )

    # (b) partial stdout before an error path: any stdout write that occurs at a
    # source line BEFORE a non-zero exit or a raise. The cardinal rule wants the
    # payload emitted exactly once at the very end; a write preceding an error
    # path risks a half-written payload when that path runs.
    if stdout_writes and exit_or_raise:
        last_err = max(exit_or_raise)
        for w in stdout_writes:
            if w < last_err:
                findings.append(
                    (
                        PARTIAL_STDOUT,
                        w,
                        f"stdout write at L{w} precedes error path at L{last_err}",
                    )
                )
                break

    return findings


# ── Shell entrypoint analysis (text) ────────────────────────────────────────
def _check_shell(text: str, rel: str) -> list[tuple[str, int, str]]:
    findings: list[tuple[str, int, str]] = []
    lines = text.splitlines()

    # `set -e` (or -e within a combined flag like `set -euo pipefail`) makes any
    # unguarded command failure abort with a non-zero exit — unsafe for a hook.
    set_e_ln = 0
    set_plus_e = False
    for i, raw in enumerate(lines, 1):
        s = raw.strip()
        m = re.match(r"set\s+([-+][A-Za-z]+(?:\s+[-+A-Za-z]+)*)", s)
        if m:
            flags = m.group(0)
            if re.search(r"-[A-Za-z]*e", flags) and "+e" not in flags:
                # a `-...e...` flag group that isn't a `+e`
                if re.search(r"-[A-Za-z]*e[A-Za-z]*\b", flags):
                    set_e_ln = set_e_ln or i
            if re.search(r"\+[A-Za-z]*e", flags):
                set_plus_e = True

    # Strip comments first: a guard token that appears ONLY in a comment (e.g.
    # "# falls back to || true") must not be mistaken for a real guard. Naive —
    # drops from the first '#' at line-start or after whitespace; hook shims
    # rarely put '#' inside a string.
    code_lines = [re.sub(r"(^|\s)#.*$", "", ln) for ln in lines]
    code_text = "\n".join(code_lines)
    has_final_exit0 = any(
        re.match(r"exit\s+0\b", ln.strip()) for ln in code_lines
    )
    # Guards that neutralise a failing command: `|| true`, `|| exit 0`.
    has_or_guard = bool(re.search(r"\|\|\s*(true|exit\s+0)\b", code_text))

    if set_e_ln and not set_plus_e:
        findings.append(
            (
                NONZERO_EXIT,
                set_e_ln,
                "`set -e` can abort the hook with a non-zero exit; a hook must "
                "exit 0 on every path",
            )
        )

    # No `set -e`, but also no final `exit 0` and no `|| true`/`|| exit 0`
    # guard → the script's exit status is that of its last command, which can be
    # non-zero on an error path.
    if not has_final_exit0 and not has_or_guard:
        findings.append(
            (
                NONZERO_EXIT,
                len(lines),
                "no terminal `exit 0` and no `|| true` guard; last command's "
                "status leaks to the host",
            )
        )

    # subprocess-without-timeout doesn't map cleanly to shell; a hook shell
    # wrapper should delegate to a python worker that owns its own timeout (the
    # Brainer convention). We do not flag (c) for shell.
    return findings


# ── Driver ──────────────────────────────────────────────────────────────────
def check_file(path: Path) -> list[tuple[str, int, str]]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return [(NONZERO_EXIT, 0, f"unreadable: {e}")]
    if path.suffix == ".py":
        return _check_python(text, path.name)
    if path.suffix == ".sh":
        return _check_shell(text, path.name)
    return []


def discover() -> list[Path]:
    skills = ROOT / "skills"
    out: list[Path] = []
    for name in ("hook.py", "hook.sh"):
        out.extend(sorted(skills.glob(f"*/tools/{name}")))
    return out


def main(argv: list[str]) -> int:
    as_json = "--json" in argv
    args = [a for a in argv if not a.startswith("--")]

    if args:
        targets = [Path(a).resolve() for a in args]
    else:
        targets = discover()

    if not targets:
        print("hook_validate: no hook entrypoints found", file=sys.stderr)
        return 0

    report: dict[str, list[dict]] = {}
    total = 0
    for path in targets:
        findings = check_file(path)
        if findings:
            try:
                key = str(path.relative_to(ROOT))
            except ValueError:
                key = str(path)
            report[key] = [
                {"code": c, "line": ln, "detail": d} for c, ln, d in findings
            ]
            total += len(findings)

    if as_json:
        print(json.dumps({"findings": total, "files": report}, indent=2))
    else:
        if total == 0:
            print(f"hook_validate: {len(targets)} entrypoint(s) clean.")
        else:
            print(f"hook_validate: {total} finding(s) across {len(report)} file(s):")
            for key, items in report.items():
                print(f"\n{key}")
                for it in items:
                    print(f"  L{it['line']:<4} {it['code']}: {it['detail']}")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
