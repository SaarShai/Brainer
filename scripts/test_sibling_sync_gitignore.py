#!/usr/bin/env python3
"""Regression guard for the gitignored-runtime-cruft-copied-into-sibling bug.

Live incident (2026-07-07): `--apply-absent` copied a gitignored canary state
file (`skills/compliance-canary/tools/.brainer/compliance-canary/<hash>.json`)
from canonical Brainer into screenery-lean. A gitignored path is runtime
state, never canonical source, and must never be carried cross-repo by
--apply-absent / --apply-stale / --adopt-new-skills.

Follow-up hardening (2026-07-07, 3 codex findings against the original fix):
1. Unicode/special-char paths: `git check-ignore --stdin` C-style-quotes
   non-ASCII paths in its output (e.g. `"...\\303\\251.json"`), so a raw-string
   membership check against that output misses — the file is wrongly treated
   as NOT ignored.
2. Embedded-newline filenames: newline-delimited `--stdin` output splits one
   such path into two bogus entries, corrupting the ignored-set.
3. `skill_files()` itself (the enumeration classify/audit/apply all share) did
   not filter gitignored paths, so phantom `.brainer/` runtime files still
   showed up as absent/differs rows in reports even though the copy-time
   guards correctly skipped copying them.

Fully hermetic: builds a throwaway canonical git repo (with the script copied
in so BRAINER/DOCS resolve INTO the tmp tree) + a throwaway sibling dir, and
drives the real CLI end-to-end. NEVER touches the real siblings (screenery-lean,
the product-images repo, etc). Needs `git`; SKIPs (does not FAIL) when absent.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "sibling_sync_audit.py"

FAILS: list[str] = []


def check(name, cond):
    if cond:
        print(f"  [PASS] {name}")
    else:
        FAILS.append(name)
        print(f"  [FAIL] {name}")


def write(p: Path, text: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def git(cwd: Path, *args: str):
    r = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True)
    assert r.returncode == 0, (args, r.stdout, r.stderr)
    return r


def build_canon(canon: Path):
    """Throwaway canonical repo: skills/ + install.sh, script copied in so it
    resolves BRAINER=canon, DOCS=canon.parent. A gitignored runtime-state file
    (mirroring compliance-canary's `.brainer/` state JSON) sits alongside a
    normal tracked skill file — both absent from the sibling."""
    (canon / "scripts").mkdir(parents=True)
    shutil.copy2(SCRIPT, canon / "scripts" / "sibling_sync_audit.py")
    write(canon / "skills" / "demo" / "SKILL.md", "---\nname: demo\n---\nbody\n")
    write(canon / "skills" / "demo" / "tools" / "helper.py", "def f(): pass\n")
    write(canon / "install.sh", "#!/usr/bin/env bash\n")
    write(canon / ".gitignore", ".brainer/\n")
    # Runtime cruft: gitignored, must never be treated as canonical source.
    write(canon / "skills" / "demo" / "tools" / ".brainer" / "demo"
          / "cafef00dcafef00d.json", '{"fires": 3}\n')
    # Finding 1: non-ASCII filename — git check-ignore --stdin (no -z) C-style
    # quotes this in its output, so a raw-string membership check misses it.
    write(canon / "skills" / "demo" / "tools" / ".brainer" / "demo"
          / "unicode" / "é.json", '{"fires": 1}\n')
    # Finding 2: embedded-newline filename — newline-delimited --stdin splits
    # this single path into two bogus entries.
    write(canon / "skills" / "demo" / "tools" / ".brainer" / "demo"
          / "weird\nname.json", '{"fires": 1}\n')
    git(canon, "init", "-q")
    git(canon, "config", "user.email", "t@t")
    git(canon, "config", "user.name", "t")
    git(canon, "add", "-A")
    git(canon, "commit", "-qm", "v1")


def main() -> int:
    if shutil.which("git") is None:
        print("SKIP test_sibling_sync_gitignore (git not on PATH)")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="sibsync-gitignore-"))
    try:
        docs = tmp / "Documents"
        canon = docs / "BrainerCanon"
        build_canon(canon)

        # Sanity: canonical repo actually ignores the runtime-state file.
        r = git(canon, "check-ignore", "-q",
                "skills/demo/tools/.brainer/demo/cafef00dcafef00d.json")
        check("canonical git-ignores the runtime-state fixture", r.returncode == 0)
        r = git(canon, "check-ignore", "-q",
                "skills/demo/tools/.brainer/demo/unicode/é.json")
        check("canonical git-ignores the unicode fixture", r.returncode == 0)
        r = git(canon, "check-ignore", "-q",
                "skills/demo/tools/.brainer/demo/weird\nname.json")
        check("canonical git-ignores the embedded-newline fixture", r.returncode == 0)

        # Throwaway sibling: has adopted the `demo` skill dir (so absent files
        # inside it are eligible for --apply-absent) but lacks BOTH the
        # gitignored state file and the tracked helper.py.
        sib = docs / "sib"
        write(sib / "skills" / "demo" / "SKILL.md", "---\nname: demo\n---\nbody\n")
        write(sib / "install.sh", "#!/usr/bin/env bash\n")

        audit_py = canon / "scripts" / "sibling_sync_audit.py"

        def run(*args, expect=0):
            r = subprocess.run([sys.executable, str(audit_py), *args],
                               cwd=canon, text=True, capture_output=True)
            assert r.returncode == expect, (args, r.returncode, r.stdout, r.stderr)
            return r

        # --- enumeration-level check: classify/audit must never even LIST
        # these as absent/differs rows (not just skip copying them). ---
        audit_json = json.loads(run("--repo", "sib", "--json").stdout)
        sib_report = next(s for s in audit_json["siblings"] if s["repo"] == "sib")
        absent = sib_report["absent"]
        check("gitignored runtime-state file absent from classify/audit report",
              not any("cafef00dcafef00d.json" in a for a in absent))
        check("unicode gitignored file absent from classify/audit report",
              not any("é.json" in a for a in absent))
        check("embedded-newline gitignored file absent from classify/audit report",
              not any("weird" in a and "name.json" in a for a in absent))
        check("tracked absent file (helper.py) still surfaces in the report",
              any("helper.py" in a for a in absent))

        classify_out = run("--repo", "sib", "--classify").stdout
        check("gitignored files do not surface anywhere in --classify output",
              "cafef00dcafef00d.json" not in classify_out
              and "é.json" not in classify_out
              and "weird" not in classify_out)

        out = run("--repo", "sib", "--apply-absent").stdout

        # (a) NEGATIVE: the gitignored runtime file must NOT be copied.
        copied_state = sib / "skills" / "demo" / "tools" / ".brainer" / "demo" \
            / "cafef00dcafef00d.json"
        check("gitignored runtime-state file NOT copied to sibling",
              not copied_state.exists())
        check("gitignored path not reported as 'added' in output",
              "cafef00dcafef00d.json" not in out)

        # (a2) NEGATIVE: unicode + embedded-newline gitignored fixtures also
        # must not be copied (findings 1 + 2 — the -z stdin fix).
        copied_unicode = sib / "skills" / "demo" / "tools" / ".brainer" / "demo" \
            / "unicode" / "é.json"
        check("unicode gitignored file NOT copied to sibling",
              not copied_unicode.exists())
        check("unicode gitignored path not reported as 'added' in output",
              "é.json" not in out)

        copied_newline = sib / "skills" / "demo" / "tools" / ".brainer" / "demo" \
            / "weird\nname.json"
        check("embedded-newline gitignored file NOT copied to sibling",
              not copied_newline.exists())
        check("embedded-newline gitignored path not reported as 'added' in output",
              "weird" not in out)

        # (b) POSITIVE: the tracked file still copies as before.
        copied_tracked = sib / "skills" / "demo" / "tools" / "helper.py"
        check("tracked absent file IS still copied to sibling",
              copied_tracked.is_file()
              and copied_tracked.read_text() == "def f(): pass\n")
        check("tracked path reported as 'added' in output",
              "added       skills/demo/tools/helper.py" in out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILS:
        print(f"FAILED: {len(FAILS)}")
        for x in FAILS:
            print("  -", x)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
