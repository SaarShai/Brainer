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
RETIRED_TOOL = "def retired(): pass  # v1 canonical, deleted in v2\n"
LESSON_V1 = "---\nname: lesson-demo\n---\n## Lesson: gotcha\nfor-brainer: yes\nbody v1\n"
LESSON_V2 = "---\nname: lesson-demo\n---\nbody v2 (lesson harvested & removed)\n"
SYMLINK_V1 = "---\nname: symlink-demo\n---\nbody v1\n"
SYMLINK_V2 = "---\nname: symlink-demo\n---\nbody v2\n"
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
    builder.md gets TWO committed versions so a sibling holding v1 is STALE.
    `dummy/tools/retired_tool.py` exists in v1 and is deleted in v2 — the
    canonical-deletion case a sibling that never re-synced would still hold."""
    (canon / "scripts").mkdir(parents=True)
    shutil.copy2(SCRIPT, canon / "scripts" / "sibling_sync_audit.py")
    write(canon / "skills" / "dummy" / "SKILL.md", "---\nname: dummy\n---\nbody\n")
    write(canon / "skills" / "dummy" / "tools" / "retired_tool.py", RETIRED_TOOL)
    write(canon / "skills" / "indent-demo" / "SKILL.md", INDENT_CANON)
    write(canon / "skills" / "lesson-demo" / "SKILL.md", LESSON_V1)
    write(canon / "skills" / "symlink-demo" / "SKILL.md", SYMLINK_V1)
    write(canon / "install.sh", "#!/usr/bin/env bash\n")
    # Mirror the real carve-out: agents are tracked, rest of .claude is not.
    # ".brainer/" mirrors the real repo's runtime-state carve-out (a canary's
    # `.brainer/<hash>.json`) — never canonical source, never a deletion
    # candidate even though it is absent from canonical HEAD by design.
    write(canon / ".gitignore", ".claude/*\n!.claude/agents/\n.brainer/\n")
    write(canon / AGENTS / "builder.md", BUILDER_V1)
    write(canon / AGENTS / "verifier.md", VERIFIER)
    write(canon / AGENTS / "reviewer.md", REVIEWER)
    git(canon, "init", "-q")
    git(canon, "config", "user.email", "t@t")
    git(canon, "config", "user.name", "t")
    git(canon, "add", "-A")
    git(canon, "commit", "-qm", "v1")
    write(canon / AGENTS / "builder.md", BUILDER_V2)   # v2 supersedes v1
    (canon / "skills" / "dummy" / "tools" / "retired_tool.py").unlink()  # v2 retires it
    write(canon / "skills" / "lesson-demo" / "SKILL.md", LESSON_V2)   # lesson harvested upstream
    write(canon / "skills" / "symlink-demo" / "SKILL.md", SYMLINK_V2)
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
        sib = docs / "PROMPTER"
        write(sib / "skills" / "dummy" / "SKILL.md", "---\nname: dummy\n---\nbody\n")
        write(sib / "skills" / "indent-demo" / "SKILL.md", INDENT_LOCAL)
        write(sib / "install.sh", "#!/usr/bin/env bash\n")
        write(sib / AGENTS / "builder.md", BUILDER_V1)              # STALE (== v1)
        write(sib / AGENTS / "verifier.md", VERIFIER + LOCAL_LINE)  # CUSTOMIZED
        write(sib / AGENTS / "local-only.md", "sibling roster\n")   # sibling-only
        # (reviewer.md deliberately absent -> new_agents)
        # canon_deleted case: retired_tool.py never re-synced after canonical
        # v2 retired it -> DELETE; local_only_tool.py never existed canonically
        # -> CONFLICT; the gitignored runtime file is never a candidate at all.
        write(sib / "skills" / "dummy" / "tools" / "retired_tool.py", RETIRED_TOOL)
        write(sib / "skills" / "dummy" / "tools" / "local_only_tool.py",
              "def sibling_local(): pass  # never canonical\n")
        write(sib / "skills" / "dummy" / "tools" / ".brainer" / "dummy"
              / "state.json", '{"fires": 1}\n')
        write(sib / "skills" / "lesson-demo" / "SKILL.md", LESSON_V1)  # STALE + unharvested lesson
        symlink_target = docs / "symlink-target.md"
        write(symlink_target, SYMLINK_V1)
        (sib / "skills" / "symlink-demo").mkdir(parents=True, exist_ok=True)
        (sib / "skills" / "symlink-demo" / "SKILL.md").symlink_to(symlink_target)

        # --- sib2: opt-out case (declines an agent AND a skill via one file) ---
        sib2 = docs / "screenery-lean"
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
        data = json.loads(run("--repo", "PROMPTER", "--json").stdout)
        s = next(x for x in data["siblings"] if x["repo"] == "PROMPTER")
        check("canonical_agents == 3", data["canonical_agents"] == 3)
        check("builder+verifier in agent_differs",
              f"{AGENTS}/builder.md" in s["agent_differs"]
              and f"{AGENTS}/verifier.md" in s["agent_differs"])
        check("reviewer is a new_agent", "reviewer" in s["new_agents"])
        check("local-only is sibling_only_agent", s["sibling_only_agents"] == ["local-only"])
        check("skills track isolates the indentation-only difference",
              s["identical"] == 1
              and sorted(s["differs"]) == sorted([
                  "skills/indent-demo/SKILL.md",
                  "skills/lesson-demo/SKILL.md",
                  "skills/symlink-demo/SKILL.md",
              ])
              and s["absent_count"] == 0)
        check("canon_deleted lists retired_tool.py and local_only_tool.py only "
              "(gitignored runtime state is never a deletion candidate)",
              set(s["canon_deleted"]) == {
                  "skills/dummy/tools/retired_tool.py",
                  "skills/dummy/tools/local_only_tool.py",
              })

        # 2. classify: builder STALE, verifier CUSTOMIZED with its local line shown;
        #    retired_tool.py DELETE (byte-matches canonical v1), local_only_tool.py
        #    CONFLICT (content never matched any canonical version).
        c = run("--repo", "PROMPTER", "--classify").stdout
        check("classify marks builder AGENT-STALE",
              "AGENT-STALE" in c and "builder.md" in c)
        check("classify marks verifier AGENT-CUSTOMIZED",
              "AGENT-CUSTOMIZED" in c and "verifier.md" in c)
        check("classify surfaces the local line", "LOCAL SIBLING TWEAK" in c)
        check("classify marks indentation-only edit CUSTOMIZED",
              any("CUSTOMIZED" in line and "skills/indent-demo/SKILL.md" in line
                  for line in c.splitlines()))
        check("classify marks retired_tool.py DELETE",
              any(line.strip().startswith("DELETE") and "retired_tool.py" in line
                  for line in c.splitlines()))
        check("classify marks local_only_tool.py CONFLICT",
              any(line.strip().startswith("CONFLICT") and "local_only_tool.py" in line
                  for line in c.splitlines()))
        check("gitignored runtime state never surfaces as DELETE/CONFLICT",
              "state.json" not in c)

        # 2b. dry-run: --classify alone (no --apply-deletions) deletes nothing.
        retired_path = sib / "skills" / "dummy" / "tools" / "retired_tool.py"
        conflict_path = sib / "skills" / "dummy" / "tools" / "local_only_tool.py"
        check("dry-run (--classify only) leaves retired_tool.py in place",
              retired_path.is_file())
        check("dry-run (--classify only) leaves local_only_tool.py in place",
              conflict_path.is_file())

        # 3. apply: STALE fast-forwards, absent adopts, CUSTOMIZED + sibling-only
        #    are left exactly as-is.
        r3 = run("--repo", "PROMPTER", "--apply-stale", "--adopt-agents")
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

        # 3b. --apply-deletions: DELETE-class retired_tool.py is removed;
        #     CONFLICT-class local_only_tool.py is left exactly as-is.
        applied = run("--repo", "PROMPTER", "--apply-deletions").stdout
        check("apply-deletions reports retired_tool.py deleted",
              "deleted     skills/dummy/tools/retired_tool.py" in applied)
        check("apply-deletions removes DELETE-class retired_tool.py",
              not retired_path.exists())
        check("apply-deletions leaves CONFLICT-class local_only_tool.py untouched",
              conflict_path.is_file()
              and conflict_path.read_text() == "def sibling_local(): pass  # never canonical\n")
        check("apply-deletions never mentions deleting the CONFLICT file",
              "deleted     skills/dummy/tools/local_only_tool.py" not in applied)

        # 3c. harvest-before-overwrite guard: STALE file with an unharvested
        #     lesson artifact is refused without --force-stale-lessons.
        check("LESSON-HAZARD reported for lesson-demo", "LESSON-HAZARD" in r3.stdout
              and "lesson-demo/SKILL.md" in r3.stdout)
        check("STALE-but-lesson file NOT overwritten without force flag",
              (sib / "skills" / "lesson-demo" / "SKILL.md").read_text() == LESSON_V1)
        run("--repo", "PROMPTER", "--apply-stale", "--force-stale-lessons")
        check("--force-stale-lessons overwrites once explicitly forced",
              (sib / "skills" / "lesson-demo" / "SKILL.md").read_text() == LESSON_V2)

        # 3d. symlink hazard: applying through a symlinked sibling path is
        #     detected and skipped, never written through.
        check("SYMLINK-HAZARD reported for symlink-demo", "SYMLINK-HAZARD" in r3.stdout
              and "symlink-demo/SKILL.md" in r3.stdout)
        check("symlinked sibling path left untouched",
              (sib / "skills" / "symlink-demo" / "SKILL.md").is_symlink()
              and symlink_target.read_text() == SYMLINK_V1)

        # 4. opt-out: `agent:reviewer` declines the roster def; `dummy` still
        #    parses as a skill opt-out (shared file, both prefixes coexist).
        d2 = json.loads(run("--repo", "screenery-lean", "--json").stdout)
        s2 = next(x for x in d2["siblings"] if x["repo"] == "screenery-lean")
        check("declined agent excluded from new_agents", "reviewer" not in s2["new_agents"])
        check("declined agent listed in declined_agents", s2["declined_agents"] == ["reviewer"])
        check("skill opt-out still parsed from shared file",
              s2["declined_skills"] == ["dummy"] and "dummy" not in s2["new_skills"])

        # 5. write-guard: an apply flag without --repo refuses (exit 2).
        run("--adopt-agents", expect=2)

        # 6. Scope guard: discovery omits adjacent lookalikes, and an explicit
        #    non-approved target needs the deliberate override flag.
        stray = docs / "accidental-sibling"
        write(stray / "skills" / "dummy" / "SKILL.md", "---\nname: dummy\n---\nbody\n")
        write(stray / "install.sh", "#!/usr/bin/env bash\n")
        default_repos = {
            item["repo"] for item in json.loads(run("--json").stdout)["siblings"]
        }
        check("default discovery excludes unapproved adjacent repos",
              "accidental-sibling" not in default_repos)
        run("--repo", "accidental-sibling", "--json", expect=2)
        override = json.loads(run(
            "--repo", "accidental-sibling", "--allow-unapproved", "--json"
        ).stdout)
        check("explicit override admits one user-authorized extra repo",
              [item["repo"] for item in override["siblings"]]
              == ["accidental-sibling"])

        # 7. Dirty-worktree gate: a REAL git sibling with an uncommitted change
        #    sitting exactly on an apply-stale destination path must refuse the
        #    entire run before touching anything; --force-dirty overrides with
        #    a warning. (a) + (c) share one fixture since refusal is a no-op.
        sib_a = docs / "farey-hecke"
        write(sib_a / "skills" / "dummy" / "SKILL.md", "---\nname: dummy\n---\nbody\n")
        write(sib_a / "install.sh", "#!/usr/bin/env bash\n")
        write(sib_a / AGENTS / "builder.md", "placeholder committed content\n")
        git(sib_a, "init", "-q")
        git(sib_a, "config", "user.email", "t@t")
        git(sib_a, "config", "user.name", "t")
        git(sib_a, "add", "-A")
        git(sib_a, "commit", "-qm", "baseline")
        # Uncommitted (dirty) edit landing exactly on the STALE apply target:
        # on-disk bytes match canonical v1 (STALE), but the sibling's own git
        # history never committed this content — in-flight local work.
        write(sib_a / AGENTS / "builder.md", BUILDER_V1)
        builder_a = sib_a / AGENTS / "builder.md"

        refused = run("--repo", "farey-hecke", "--apply-stale", expect=1)
        check("dirty overlap: apply-stale refuses (exit 1)",
              "REFUSED" in refused.stderr and f"{AGENTS}/builder.md" in refused.stderr)
        check("dirty overlap: refused run left the overlapping file unchanged",
              builder_a.read_text() == BUILDER_V1)

        forced = run("--repo", "farey-hecke", "--apply-stale", "--force-dirty")
        check("--force-dirty proceeds despite overlap",
              builder_a.read_text() == BUILDER_V2)
        check("--force-dirty prints a prominent overlap warning",
              "WARNING" in forced.stderr and f"{AGENTS}/builder.md" in forced.stderr)

        # 7b. Dirty non-overlapping file must NOT block: unrelated in-flight
        #     work elsewhere in the sibling (e.g. screenery-lean's birds-nest
        #     files) is legitimate and must never stop an unrelated apply.
        sib_b = docs / "screenery-design-master"
        write(sib_b / "skills" / "dummy" / "SKILL.md", "---\nname: dummy\n---\nbody\n")
        write(sib_b / "install.sh", "#!/usr/bin/env bash\n")
        write(sib_b / AGENTS / "builder.md", BUILDER_V1)
        git(sib_b, "init", "-q")
        git(sib_b, "config", "user.email", "t@t")
        git(sib_b, "config", "user.name", "t")
        git(sib_b, "add", "-A")
        git(sib_b, "commit", "-qm", "baseline")
        write(sib_b / "UNRELATED_NOTES.md", "in-flight unrelated work\n")  # untracked, no overlap

        proceeded = run("--repo", "screenery-design-master", "--apply-stale")
        check("dirty non-overlapping file: apply-stale proceeds",
              (sib_b / AGENTS / "builder.md").read_text() == BUILDER_V2)
        check("dirty non-overlapping file: unrelated dirt untouched",
              (sib_b / "UNRELATED_NOTES.md").read_text() == "in-flight unrelated work\n")
        check("dirty non-overlapping file: no refusal printed",
              "REFUSED" not in proceeded.stderr)
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
