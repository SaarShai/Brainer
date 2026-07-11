#!/usr/bin/env python3
"""Plain-python tests (no pytest dep) for sibling_sync_audit.py's agent-def
coverage. Exit code = verdict.

Regression guard for the gap where team-lead's builder/verifier roster shipped
INERT to siblings: `.claude/agents/*.md` were never carried cross-repo because
only `skills/` propagated. The roster must now classify + apply exactly like
skills — STALE fast-forwards, CUSTOMIZED is protected, a wholly-absent roster
def adopts by default (opt out with an `agent:<name>` line), and a
sibling-local agent is never touched.

Fully hermetic: builds a throwaway canonical git repo (with the script copied in
so BRAINER/DOCS resolve INTO the tmp tree) + fake siblings, and drives the real
CLI end-to-end. Needs `git`; SKIPs (does not FAIL) when git is absent.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "sibling_sync_audit.py"
AGENTS = ".claude/agents"

BUILDER_V1 = "---\nname: builder\n---\nbuilder roster v1\n"
BUILDER_V2 = "---\nname: builder\n---\nbuilder roster v2 (fixed)\n"
VERIFIER = "---\nname: verifier\n---\ncold-context verifier\n"
REVIEWER = "---\nname: reviewer\n---\nnew roster lane\n"
LOCAL_LINE = "LOCAL SIBLING TWEAK: keep me\n"
INDENT_CANON = "---\nname: indent-demo\n---\n## Steps\n  - preserve indentation\n"
INDENT_LOCAL = "---\nname: indent-demo\n---\n## Steps\n    - preserve indentation\n"
APPLY_FLAGS = ("--apply-stale", "--apply-absent", "--adopt-new-skills", "--adopt-agents")

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
    """A throwaway canonical repo: skills/ + .claude/agents/ + install.sh, with
    the audit script copied in so it resolves BRAINER=canon, DOCS=canon.parent.
    builder.md gets TWO committed versions so a sibling holding v1 is STALE."""
    (canon / "scripts").mkdir(parents=True)
    shutil.copy2(SCRIPT, canon / "scripts" / "sibling_sync_audit.py")
    write(canon / "skills" / "dummy" / "SKILL.md", "---\nname: dummy\n---\nbody\n")
    write(canon / "skills" / "indent-demo" / "SKILL.md", INDENT_CANON)
    write(canon / "install.sh", "#!/usr/bin/env bash\n")
    # Mirror the real carve-out: agents are tracked, rest of .claude is not.
    write(canon / ".gitignore", ".claude/*\n!.claude/agents/\n")
    write(canon / AGENTS / "builder.md", BUILDER_V1)
    write(canon / AGENTS / "verifier.md", VERIFIER)
    write(canon / AGENTS / "reviewer.md", REVIEWER)
    git(canon, "init", "-q")
    git(canon, "config", "user.email", "t@t")
    git(canon, "config", "user.name", "t")
    git(canon, "add", "-A")
    git(canon, "commit", "-qm", "v1")
    write(canon / AGENTS / "builder.md", BUILDER_V2)   # v2 supersedes v1
    git(canon, "add", "-A")
    git(canon, "commit", "-qm", "v2")


def check_two_carrier_consistency():
    """Real-repo invariant behind propagate/SKILL.md's "two carriers never fight":
    the six agent-defs prompt-triage bundles + `cp -f`s at install time must stay
    byte-identical to their tracked top-level `.claude/agents/` copy. If they ever
    diverge, sibling_sync_audit (which carries the top-level copy) and
    prompt-triage's installer (authoritative, runs last) would push different
    bytes. Skipped if the bundle isn't present (running outside the real repo)."""
    repo = Path(__file__).resolve().parents[1]
    bundle = repo / "skills" / "prompt-triage" / "tools" / "agents"
    top = repo / AGENTS
    if not bundle.is_dir() or not top.is_dir():
        print("  [SKIP] two-carrier consistency (prompt-triage bundle absent)")
        return
    mismatches = [p.name for p in sorted(bundle.glob("*.md"))
                  if not (top / p.name).is_file()
                  or (top / p.name).read_bytes() != p.read_bytes()]
    check("prompt-triage bundle == top-level .claude/agents (byte-identical)",
          mismatches == [])
    if mismatches:
        print("      diverged:", ",".join(mismatches))


def check_propagate_probe_lists_all_apply_flags():
    repo = Path(__file__).resolve().parents[1]
    probe_path = repo / "skills" / "propagate" / "drift_probes.json"
    probes = json.loads(probe_path.read_text(encoding="utf-8"))
    message = next(p["message"] for p in probes if p.get("id") == "propagate-intent")
    check("propagate-intent probe names all four apply flags",
          all(flag in message for flag in APPLY_FLAGS))


def main() -> int:
    if shutil.which("git") is None:
        print("SKIP test_sibling_sync_audit (git not on PATH)")
        return 0

    check_two_carrier_consistency()
    check_propagate_probe_lists_all_apply_flags()

    tmp = Path(tempfile.mkdtemp(prefix="sibsync-"))
    try:
        docs = tmp / "Documents"
        canon = docs / "BrainerCanon"
        build_canon(canon)

        # Canonical must actually TRACK the agent defs, else archaeology is blind
        # and every roster def would look CUSTOMIZED. Prove the carve-out works.
        tracked = git(canon, "ls-files", AGENTS).stdout.split()
        check("canonical git-tracks .claude/agents/*.md", len(tracked) == 3)

        # --- sib: the drift case (stale + customized + missing + sibling-only) ---
        sib = docs / "sib"
        write(sib / "skills" / "dummy" / "SKILL.md", "---\nname: dummy\n---\nbody\n")
        write(sib / "skills" / "indent-demo" / "SKILL.md", INDENT_LOCAL)
        write(sib / "install.sh", "#!/usr/bin/env bash\n")
        write(sib / AGENTS / "builder.md", BUILDER_V1)              # STALE (== v1)
        write(sib / AGENTS / "verifier.md", VERIFIER + LOCAL_LINE)  # CUSTOMIZED
        write(sib / AGENTS / "local-only.md", "sibling roster\n")   # sibling-only
        # (reviewer.md deliberately absent -> new_agents)

        # --- sib2: opt-out case (declines an agent AND a skill via one file) ---
        sib2 = docs / "sib2"
        write(sib2 / "skills" / "dummy" / "SKILL.md", "---\nname: dummy\n---\nbody\n")
        write(sib2 / "skills" / "indent-demo" / "SKILL.md", INDENT_CANON)
        write(sib2 / "install.sh", "#!/usr/bin/env bash\n")
        write(sib2 / AGENTS / "builder.md", BUILDER_V2)             # up to date
        write(sib2 / AGENTS / "verifier.md", VERIFIER)              # up to date
        write(sib2 / ".brainer-sync-optout", "agent:reviewer\ndummy\n")

        audit_py = canon / "scripts" / "sibling_sync_audit.py"

        def run(*args, expect=0):
            r = subprocess.run([sys.executable, str(audit_py), *args],
                               cwd=canon, text=True, capture_output=True)
            assert r.returncode == expect, (args, r.returncode, r.stdout, r.stderr)
            return r

        # 1. JSON structure: agent track is populated and independent of skills.
        data = json.loads(run("--repo", "sib", "--json").stdout)
        s = next(x for x in data["siblings"] if x["repo"] == "sib")
        check("canonical_agents == 3", data["canonical_agents"] == 3)
        check("builder+verifier in agent_differs",
              f"{AGENTS}/builder.md" in s["agent_differs"]
              and f"{AGENTS}/verifier.md" in s["agent_differs"])
        check("reviewer is a new_agent", "reviewer" in s["new_agents"])
        check("local-only is sibling_only_agent", s["sibling_only_agents"] == ["local-only"])
        check("skills track isolates the indentation-only difference",
              s["identical"] == 1
              and s["differs"] == ["skills/indent-demo/SKILL.md"]
              and s["absent_count"] == 0)

        # 2. classify: builder STALE, verifier CUSTOMIZED with its local line shown.
        c = run("--repo", "sib", "--classify").stdout
        check("classify marks builder AGENT-STALE",
              "AGENT-STALE" in c and "builder.md" in c)
        check("classify marks verifier AGENT-CUSTOMIZED",
              "AGENT-CUSTOMIZED" in c and "verifier.md" in c)
        check("classify surfaces the local line", "LOCAL SIBLING TWEAK" in c)
        check("classify marks indentation-only edit CUSTOMIZED",
              any("CUSTOMIZED" in line and "skills/indent-demo/SKILL.md" in line
                  for line in c.splitlines()))

        # 3. apply: STALE fast-forwards, absent adopts, CUSTOMIZED + sibling-only
        #    are left exactly as-is.
        run("--repo", "sib", "--apply-stale", "--adopt-agents")
        check("STALE builder fast-forwarded to v2",
              (sib / AGENTS / "builder.md").read_text() == BUILDER_V2)
        check("absent reviewer adopted verbatim",
              (sib / AGENTS / "reviewer.md").is_file()
              and (sib / AGENTS / "reviewer.md").read_text() == REVIEWER)
        check("CUSTOMIZED verifier NOT overwritten",
              (sib / AGENTS / "verifier.md").read_text() == VERIFIER + LOCAL_LINE)
        check("sibling-only roster def untouched",
              (sib / AGENTS / "local-only.md").read_text() == "sibling roster\n")
        check("indentation-only customization NOT overwritten",
              (sib / "skills" / "indent-demo" / "SKILL.md").read_text() == INDENT_LOCAL)

        # 4. opt-out: `agent:reviewer` declines the roster def; `dummy` still
        #    parses as a skill opt-out (shared file, both prefixes coexist).
        d2 = json.loads(run("--repo", "sib2", "--json").stdout)
        s2 = next(x for x in d2["siblings"] if x["repo"] == "sib2")
        check("declined agent excluded from new_agents", "reviewer" not in s2["new_agents"])
        check("declined agent listed in declined_agents", s2["declined_agents"] == ["reviewer"])
        check("skill opt-out still parsed from shared file",
              s2["declined_skills"] == ["dummy"] and "dummy" not in s2["new_skills"])

        # 5. write-guard: an apply flag without --repo refuses (exit 2).
        run("--adopt-agents", expect=2)
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
