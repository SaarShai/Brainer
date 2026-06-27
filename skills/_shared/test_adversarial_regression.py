#!/usr/bin/env python3
"""Adversarial regression suite for the cbm-adoption items.

Each case below is a break a GLM-5.2 adversary found against the first cut of
the cbm-adoption branch, now fixed. They live here (cross-skill) so the exact
refuted inputs can never silently regress. Run from the repo root.

Breaks captured:
  #1 augment  — garbage / non-UTF8 backend output was emitted as additionalContext
  #2 degraded — absurd env (inf/-inf) disabled or forced the degraded check
  #3 search   — a unicode-only query was rejected as "unsupported" (false alarm)
  #7 validate — os._exit(N), aliased subprocess, and comment-only shell guards slipped
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # skills/_shared/ -> repo root
PY = sys.executable
fails: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" :: {detail}" if not ok else ""))
    if not ok:
        fails.append(name)


def _augment(hook: dict, query_cmd: list[str] | None) -> tuple[int, str]:
    env = dict(os.environ)
    if query_cmd is not None:
        env["INDEX_FIRST_QUERY_CMD"] = json.dumps(query_cmd)
    p = subprocess.run(
        [PY, str(ROOT / "skills/index-first/tools/augment.py")],
        input=json.dumps(hook), capture_output=True, text=True, env=env, cwd=ROOT,
    )
    return p.returncode, p.stdout


GREP = {"tool_name": "Grep", "tool_input": {"pattern": "handleRequest"}}

print("== #1 augment cardinal rule ==")
rc, out = _augment(GREP, ["printf", "not JSON {[ garbage"])
check("garbage backend output -> noop (no stdout)", out == "", f"emitted {out!r}")
rc, out = _augment(GREP, [PY, "-c", "import sys;sys.stdout.buffer.write(b'\\xff\\xfe g')"])
check("non-UTF8 backend output -> noop", out == "", f"emitted {out!r}")
rc, out = _augment(GREP, [PY, "-c", "import json;print(json.dumps([{'path':'a.py','title':'X'}]))"])
check("valid JSON hits -> emits additionalContext", "additionalContext" in out)
rc, out = _augment({"tool_name": "Read", "tool_input": {"file_path": "x"}}, [PY, "-c", "print('[]')"])
check("Read tool -> never acts (noop)", out == "" and rc == 0)
# round 2: an INDEX_FIRST_QUERY_CMD override is NEVER trusted for free text
# (freetext is gated on the real graphify-out index, not argv[0]'s name), so
# non-JSON from any override noops even if it looks graphify-ish.
rc, out = _augment(GREP, [PY, "-c", "print('graphify-ish free text, not json')"])
check("override backend non-JSON -> noop (no freetext spoof)", out == "", f"emitted {out!r}")

print("== #2 degraded env clamp ==")
sys.path.insert(0, str(ROOT / "skills/wiki-memory/tools"))
from wiki import WikiStore  # noqa: E402

for ratio, persisted, expected, want in [
    ("-inf", 0, 20, "degraded"),   # data loss must not be hidden by a garbage ratio
    ("inf", 19, 20, "ok"),         # healthy 19/20 must not be forced degraded
    ("2.0", 19, 20, "ok"),         # >1 clamped to default 0.5
    ("0", 10, 100, "degraded"),    # round 2: ratio=0 must NOT silently disable the check
    ("nan", 10, 100, "degraded"),  # nan reset to default 0.5
]:
    os.environ["WIKI_DEGRADED_RATIO"] = ratio
    w = WikiStore(tempfile.mkdtemp())
    got = w.verify_persistence(expected=expected, persisted=persisted)["status"]
    check(f"ratio={ratio} persisted={persisted}/{expected} -> {want}", got == want, f"got {got}")
os.environ.pop("WIKI_DEGRADED_RATIO", None)


def _search(root: str, q: str) -> int:
    return subprocess.run(
        [PY, str(ROOT / "skills/wiki-memory/tools/wiki.py"), "--root", root, "search", q],
        capture_output=True, text=True, cwd=ROOT,
    ).returncode


print("== #3 loud query: unicode is valid, punctuation is unsupported ==")
wroot = tempfile.mkdtemp()
subprocess.run([PY, str(ROOT / "skills/wiki-memory/tools/wiki.py"), "--root", wroot, "init"],
               capture_output=True, cwd=ROOT)
check("unicode-only query 'тест' -> exit 0 (valid zero-match)", _search(wroot, "тест") == 0)
check("unicode-only query '你好' -> exit 0", _search(wroot, "你好") == 0)
check("pure punctuation '!!!' -> exit 2 (unsupported)", _search(wroot, "!!!") == 2)
check("valid english zero-match -> exit 0", _search(wroot, "zzzqqxnomatch") == 0)
check("all-stopwords 'the and for' -> exit 2 (unsupported)", _search(wroot, "the and for") == 2)
# round 2: a single non-stopword content char is a VALID query, not "too short"
check("single content char '3' -> exit 0", _search(wroot, "3") == 0)
check("single content char 'k' -> exit 0", _search(wroot, "k") == 0)


def _validate(fname: str, body: str) -> int:
    d = tempfile.mkdtemp()
    Path(d, fname).write_text(body)
    return subprocess.run(
        [PY, str(ROOT / "skills/compliance-canary/tools/hook_validate.py"), str(Path(d, fname))],
        capture_output=True, text=True, cwd=ROOT,
    ).returncode


print("== #7 hook_validate recall ==")
check("os._exit(1) flagged", _validate("hook.py", "import os\nprint('x')\nos._exit(1)\n") == 1)
check("os._exit(0) clean", _validate("hook.py", "import os\nos._exit(0)\n") == 0)
check("aliased subprocess flagged",
      _validate("hook.py", "import subprocess as sp\nsp.run(['sleep','1'])\n") == 1)
check("from-import subprocess flagged",
      _validate("hook.py", "from subprocess import run\nrun(['sleep','1'])\n") == 1)
check("shell guard only in comment flagged",
      _validate("hook.sh", "#!/usr/bin/env bash\n# fallback uses || true\nsome_cmd\n") == 1)
check("real shell guard clean",
      _validate("hook.sh", "#!/usr/bin/env bash\nsome_cmd || true\nexit 0\n") == 0)
# round 2: os.system / os.popen are subprocess-equivalent with no timeout
check("os.system() flagged",
      _validate("hook.py", "import os\nos.system('ls')\n") == 1)
check("os.popen() flagged",
      _validate("hook.py", "import os\nos.popen('ls').read()\n") == 1)

print()
if fails:
    print(f"adversarial_regression: {len(fails)} FAILED: {fails}")
    sys.exit(1)
print("adversarial_regression: ALL PASS")
