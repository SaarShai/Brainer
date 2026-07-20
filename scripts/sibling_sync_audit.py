#!/usr/bin/env python3
"""Cross-repo sync audit: are Brainer's vendored skill copies in sibling repos
in sync with the canonical source here?

WHY THIS EXISTS: every check in this repo was per-FILE (propagation byte-diff of
the files I happened to touch) or per-TOOL (unit tests). Nothing audited the
SKILL SET across the sibling repos. A bug fixed here can sit unfixed in N
vendored copies indefinitely, and a duplicate/renamed skill in a sibling stays
invisible — both were found late, by accident, for exactly this missing-lens
reason. This is that missing lens as a standing, repeatable check.

For every sibling repo (a dir alongside Brainer that has skills/ + install.sh),
and every file under Brainer's skills/ (real files only — no .venv/__pycache__)
PLUS every canonical agent-def (`.claude/agents/*.md` — team-lead's
builder/verifier roster + labor-tier lanes, tracked SOURCE per .gitignore),
classify the sibling's copy:

  identical   byte-for-byte == canonical Brainer
  DIFFERS     present but not identical (stale fix OR local customization —
              run `--diff <repo> <relpath>` or sibling_sync judgment to tell which)
  absent      Brainer has it, sibling does not (partial adoption — informational)

Also reports skills present in a sibling but NOT in Brainer (sibling-only —
candidate divergence / a skill that should be upstreamed or is a local fork).

This is REPORT-ONLY and NOT a gate: siblings are independent repos that may
legitimately customize or partially adopt. The point is visibility — you can no
longer be unaware that 8 repos are behind.

Usage:
  python3 scripts/sibling_sync_audit.py            # summary table
  python3 scripts/sibling_sync_audit.py --files    # list every DIFFERS file
  python3 scripts/sibling_sync_audit.py --repo X   # only sibling X (post-propagate verify)
  python3 scripts/sibling_sync_audit.py --json
  python3 scripts/sibling_sync_audit.py --classify           # DIFFERS -> STALE vs CUSTOMIZED
  python3 scripts/sibling_sync_audit.py --repo X --apply-stale  # fast-forward STALE files only
  python3 scripts/sibling_sync_audit.py --repo X --adopt-agents # add missing .claude/agents/*.md
  python3 scripts/sibling_sync_audit.py --repo X --apply-deletions # remove DELETE-class retired files

Canonical DELETIONS also travel: a file present in a sibling's copy of a
shared skill dir but absent from canonical HEAD (retired machinery the sibling
never dropped) is reported under `canon_deleted`, and `--classify` splits it
into DELETE (byte-matches a version this path once held canonically — safe to
remove) vs CONFLICT (content that never matched canonical history — sibling-
customized, never auto-deleted). `--apply-deletions` removes DELETE-class
files only and requires --repo; omitting it (audit/--classify alone) is a dry
run — nothing is ever deleted without that flag. A skill absent canonically in
its entirety is NOT covered here — it already surfaces as sibling_only_skills,
a deliberate local-fork signal left untouched.

Agent-defs ride the SAME classify machinery as skills: a stale roster def (the
sibling holds an older builder.md that byte-matches a historical canonical
version) fast-forwards under --apply-stale; a customized one is protected; a
missing one adopts by default under --adopt-agents (a sibling declines one with
an `agent:<name>` line in its .brainer-sync-optout). Agent defs live DIRECTLY in
the host loader path (.claude/agents/), so — unlike skills — the copy is live
immediately with no install.sh symlink step.

--classify mechanizes the topology hard-rule's "git-archaeology each file":
a DIFFERS file whose content byte-matches ANY historical canonical version of
that path is STALE (the sibling simply never received later fixes — safe to
fast-forward to canonical HEAD); a DIFFERS file matching NO canonical version
ever committed is CUSTOMIZED (sibling-local work — never auto-overwrite, merge
by hand). --apply-stale copies canonical HEAD over STALE files only, requires
--repo, and still expects you to re-run that sibling's install.sh and re-verify
with --repo afterwards (the hard rule's steps 3-4 stay manual and sequential).
"""
from __future__ import annotations

import argparse
import filecmp
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

BRAINER = Path(__file__).resolve().parent.parent
DOCS = BRAINER.parent
APPROVED_SIBLINGS = frozenset({
    "PROMPTER",
    "farey-hecke",
    "product images repo",
    "screenery-design-master",
    "screenery-lean",
})
SKIP = {".venv", "venv", "__pycache__", ".git", ".pytest_cache", "node_modules",
        ".mypy_cache", ".ruff_cache", "dist", "build"}
# Agent-defs are tracked SOURCE (see .gitignore carve-out `.claude/*` +
# `!.claude/agents/`), NOT runtime state — they are team-lead's builder/verifier
# roster + labor-tier lanes. They live directly in each host's agent loader path,
# so the ONLY thing they need is the cross-repo carry that skills already get.
AGENTS_DIR = ".claude/agents"


def is_sibling(d: Path) -> bool:
    return (d.is_dir() and d != BRAINER
            and (d / "skills").is_dir() and (d / "install.sh").is_file())


def skill_files(root: Path) -> list[Path]:
    out = []
    for p in (root / "skills").rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(part in SKIP for part in rel.parts):
            continue
        out.append(rel)
    # A gitignored path (e.g. a canary's `.brainer/` runtime-state JSON) is
    # never canonical source. Filtering it out HERE — the single enumeration
    # every consumer (classify/audit/apply) shares — means none of them can
    # see a phantom absent/differs row for it; the copy-time guards below
    # remain as defense-in-depth, not the only line of defense.
    ignored = _canon_gitignored([str(p) for p in out])
    return [p for p in out if str(p) not in ignored]


def skill_names(root: Path) -> set[str]:
    return {d.name for d in (root / "skills").iterdir()
            if d.is_dir() and d.name != "_shared" and (d / "SKILL.md").is_file()}


def agent_files(root: Path) -> list[Path]:
    """Canonical agent-defs: the flat `.claude/agents/*.md` roster. Classified
    with the same git-archaeology as skill files (they are tracked source), but
    kept as their own track so folding them in never perturbs the skills counts."""
    d = root / AGENTS_DIR
    if not d.is_dir():
        return []
    return sorted(p.relative_to(root) for p in d.glob("*.md") if p.is_file())


def agent_names(root: Path) -> set[str]:
    d = root / AGENTS_DIR
    return {p.stem for p in d.glob("*.md") if p.is_file()} if d.is_dir() else set()


def _blob_id(p: Path) -> str:
    """git hash-object equivalent, no subprocess."""
    data = p.read_bytes()
    return hashlib.sha1(b"blob %d\x00" % len(data) + data).hexdigest()


def _canon_blob_history(rel: str, max_commits: int = 400) -> set[str]:
    """Every blob id this path has ever had in canonical history (bounded)."""
    revs = subprocess.run(
        ["git", "rev-list", f"--max-count={max_commits}", "HEAD", "--", rel],
        cwd=BRAINER, capture_output=True, text=True).stdout.split()
    blobs: set[str] = set()
    for sha in revs:
        ls = subprocess.run(["git", "ls-tree", sha, "--", rel],
                            cwd=BRAINER, capture_output=True, text=True).stdout.strip()
        if ls:
            blobs.add(ls.split()[2])
    return blobs


def _canon_line_corpus(rel: str, max_commits: int = 400) -> set[str]:
    """Every line this path has ever contained across canonical history + HEAD.

    Whole-file hashing has a blind spot: a sibling file that is a MIX of
    already-synced and not-yet-synced canonical sections byte-matches no single
    historical snapshot, so hash-classification calls it CUSTOMIZED even though
    it holds zero local work. Line-level provenance closes that: a line the
    sibling has that appears in NO canonical version (ever) is the only real
    signal of sibling-local authorship."""
    revs = subprocess.run(
        ["git", "rev-list", f"--max-count={max_commits}", "HEAD", "--", rel],
        cwd=BRAINER, capture_output=True, text=True).stdout.split()
    corpus: set[str] = set()
    for sha in revs:
        blob = subprocess.run(["git", "show", f"{sha}:{rel}"],
                              cwd=BRAINER, capture_output=True, text=True)
        if blob.returncode == 0:
            corpus.update(ln.rstrip() for ln in blob.stdout.splitlines() if ln.strip())
    return corpus


def classify_differs(sib: Path, differs: list[str]) -> dict:
    """Split a sibling's DIFFERS list into STALE (safe to fast-forward) vs
    CUSTOMIZED (holds sibling-local lines — never overwrite).

    A file is STALE if it holds no line absent from all canonical history —
    i.e. it is some pure or mixed subset of canonical content that simply never
    caught up. It is CUSTOMIZED only if it has genuinely local lines; those
    exact lines are returned so a manual merge knows what to preserve."""
    stale, customized = [], []
    local_lines: dict[str, list[str]] = {}
    for rel in differs:
        # Fast path: whole-file byte-match against a historical snapshot.
        if _blob_id(sib / rel) in _canon_blob_history(rel):
            stale.append(rel)
            continue
        # Line-provenance fallback: does the sibling hold any never-canonical line?
        corpus = _canon_line_corpus(rel)
        sib_lines = [ln.rstrip() for ln in (sib / rel).read_text(
            errors="replace").splitlines() if ln.strip()]
        novel = [ln for ln in sib_lines if ln not in corpus]
        if novel:
            customized.append(rel)
            local_lines[rel] = novel
        else:
            stale.append(rel)
    return {"stale": stale, "customized": customized, "local_lines": local_lines}


def _canon_gitignored(rels: list[str]) -> set[str]:
    """Batch-classify which of `rels` (paths relative to BRAINER) are gitignored
    in the canonical repo — via one `git check-ignore --stdin` call rather than
    per-file spawning. A gitignored path is runtime state (e.g. a canary's
    `.brainer/` state JSON), never canonical source, and must never be copied
    into a sibling by --apply-absent/--apply-stale/--adopt-new-skills.

    Uses `-z` (NUL-delimited, both directions): plain newline-delimited
    `--stdin` breaks on two path shapes git otherwise mangles — a non-ASCII
    filename comes back C-style-quoted (`"...\\303\\251.json"`), and a
    filename containing an embedded newline splits into two bogus entries.
    `-z` disables that quoting and delimits on NUL instead, so both round-trip
    byte-exact."""
    if not rels:
        return set()
    payload = ("\x00".join(rels) + "\x00").encode("utf-8", "surrogateescape")
    out = subprocess.run(["git", "check-ignore", "--stdin", "-z"], cwd=BRAINER,
                          input=payload, capture_output=True)
    return {p.decode("utf-8", "surrogateescape")
            for p in out.stdout.split(b"\x00") if p}


def _optout_skills(sib: Path) -> set[str]:
    """Skills a sibling has explicitly DECLINED — one skill name per line in
    `.brainer-sync-optout` at the sibling root. Everything not listed here is
    adopted by default, so a NEW canonical skill reaches every sibling with no
    per-skill opt-in from the author (declining is the deliberate, explicit act).
    `agent:<name>` lines belong to _optout_agents and are skipped here."""
    f = sib / ".brainer-sync-optout"
    if not f.is_file():
        return set()
    return {ln.strip() for ln in f.read_text().splitlines()
            if ln.strip() and not ln.startswith("#")
            and not ln.strip().startswith("agent:")}


def _optout_agents(sib: Path) -> set[str]:
    """Agent-defs a sibling has DECLINED — an `agent:<name>` line in the SAME
    `.brainer-sync-optout` file. Everything not listed adopts by default, so a
    new roster def (a freshly added team-lead lane) reaches every sibling with
    no per-agent opt-in — declining is the deliberate, explicit act."""
    f = sib / ".brainer-sync-optout"
    if not f.is_file():
        return set()
    out = set()
    for ln in f.read_text().splitlines():
        s = ln.strip()
        if s.startswith("agent:"):
            name = s[len("agent:"):].strip()
            if name:
                out.add(name)
    return out


def new_agents_for(sib: Path) -> list[str]:
    """Canonical agent-defs wholly absent from the sibling and not opted out —
    the auto-adoption roster (mirrors new_skills_for)."""
    return sorted(agent_names(BRAINER) - agent_names(sib) - _optout_agents(sib))


def canon_deleted_for(sib: Path, shared_skills: set[str]) -> list[str]:
    """Sibling files that sit inside a shared skill dir (adopted both
    canonically and by this sibling) but no longer exist ANYWHERE in canonical
    HEAD — the missing half of the stale/absent picture. `skill_files`/`audit`
    only ever enumerate CANONICAL paths and report what a sibling LACKS; a path
    canonically DELETED (retired machinery) never appears there, so it
    silently persists in every sibling forever. Restricted to shared skill
    dirs: a skill absent canonically in its ENTIRETY already surfaces as
    sibling_only_skills (a deliberate local-fork signal) and is never treated
    as deletable here. Gitignored canonical paths (runtime state, e.g. a
    canary's `.brainer/` state JSON) are excluded — never canonical source, so
    never a deletion candidate either."""
    if not shared_skills:
        return []
    canon_rel = {str(p) for p in skill_files(BRAINER)}
    out = []
    for p in (sib / "skills").rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(sib)
        if any(part in SKIP for part in rel.parts):
            continue
        if len(rel.parts) < 2 or rel.parts[1] not in shared_skills:
            continue
        if str(rel) in canon_rel:
            continue
        out.append(str(rel))
    ignored = _canon_gitignored(out)
    return sorted(r for r in out if r not in ignored)


def classify_deleted(sib: Path, rels: list[str]) -> dict:
    """Split canon_deleted_for's candidates into DELETE (the sibling's bytes
    byte-match a version this exact path held at SOME point in canonical
    history — retired machinery the sibling never dropped, safe to remove) vs
    CONFLICT (content that never matched canonical history at that path —
    sibling-local customization; never auto-deleted, requires an explicit
    operator decision). Canonical repo history is all we have git access to —
    siblings are separate repos with no shared history to archaeology against,
    so a canonically-absent path is judged purely by whether ITS bytes ever
    were canonical, not by anything in the sibling's own history."""
    delete, conflict = [], []
    for rel in rels:
        if _blob_id(sib / rel) in _canon_blob_history(rel):
            delete.append(rel)
        else:
            conflict.append(rel)
    return {"delete": delete, "conflict": conflict}


def sibling_dirty_status(sib: Path) -> tuple[set[str], set[str]] | None:
    """(dirty_files, dirty_dirs) from `git -C sib status --porcelain` — both
    tracked modifications AND untracked paths (git collapses a wholly-untracked
    directory into one `?? dir/` entry rather than listing every file inside
    it, hence the separate dirty_dirs set for prefix matching). Returns None
    if `sib` is not itself a git repo (git status fails): the dirty-worktree
    gate then has nothing to check and is a no-op, never a false block."""
    r = subprocess.run(["git", "-C", str(sib), "status", "--porcelain"],
                        capture_output=True, text=True)
    if r.returncode != 0:
        return None
    files, dirs = set(), set()
    for line in r.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip('"')
        if " -> " in path:  # rename/copy: "XY old -> new" — new is the live path
            path = path.split(" -> ", 1)[1]
        if path.endswith("/"):
            dirs.add(path.rstrip("/"))
        else:
            files.add(path)
    return files, dirs


def dirty_overlap(targets: set[str], dirty_files: set[str], dirty_dirs: set[str]) -> list[str]:
    """Which of `targets` (destination paths an apply run would write/delete)
    sit inside the sibling's dirty worktree — as an exact dirty file, inside a
    dirty (possibly untracked) directory, or itself a directory (e.g. a
    newly-adopted skill dir) that CONTAINS a dirty file or dir."""
    hits = []
    for t in sorted(targets):
        if (t in dirty_files
                or any(t == d or t.startswith(d + "/") for d in dirty_dirs)
                or any(f == t or f.startswith(t + "/") for f in dirty_files)
                or any(d == t or d.startswith(t + "/") for d in dirty_dirs)):
            hits.append(t)
    return hits


def plan_apply_targets(sib: Path, s: dict, args) -> set[str]:
    """Every destination path (file, or skill-dir prefix for a wholesale new
    skill) this apply run would write or delete in `sib` — computed dry (no
    I/O) so the dirty-worktree gate can run BEFORE any mutation happens."""
    targets: set[str] = set()
    if args.apply_stale and s["differs"]:
        cl = classify_differs(sib, s["differs"])
        ignored = _canon_gitignored(cl["stale"])
        targets.update(f for f in cl["stale"] if f not in ignored)
    if args.apply_stale and s["agent_differs"]:
        acl = classify_differs(sib, s["agent_differs"])
        ignored = _canon_gitignored(acl["stale"])
        targets.update(f for f in acl["stale"] if f not in ignored)
    if args.apply_absent and s.get("absent"):
        ignored = _canon_gitignored(s["absent"])
        for f in s["absent"]:
            if f in ignored:
                continue
            rel = Path(f)
            skill_dir = sib / rel.parts[0] / rel.parts[1]
            if len(rel.parts) > 2 and not skill_dir.is_dir():
                continue
            targets.add(f)
    if args.adopt_new_skills and s["new_skills"]:
        targets.update(f"skills/{name}" for name in s["new_skills"])
    if args.adopt_agents and s["new_agents"]:
        targets.update(f"{AGENTS_DIR}/{name}.md" for name in s["new_agents"])
    if args.apply_deletions and s["canon_deleted"]:
        dcl = classify_deleted(sib, s["canon_deleted"])
        targets.update(dcl["delete"])
    return targets


def new_skills_for(sib: Path) -> list[str]:
    """Canonical skills wholly absent from the sibling and not opted out —
    the auto-adoption set."""
    canon = skill_names(BRAINER)
    have = skill_names(sib)
    declined = _optout_skills(sib)
    return sorted(canon - have - declined)


def audit(repo: str | None = None, *, allow_unapproved: bool = False) -> dict:
    canon_files = skill_files(BRAINER)
    canon_skills = skill_names(BRAINER)
    canon_agents = agent_files(BRAINER)
    sibs = sorted(
        (d for d in DOCS.iterdir()
         if is_sibling(d) and d.name in APPROVED_SIBLINGS),
        key=lambda p: p.name,
    )
    if repo is not None:
        target = DOCS / repo
        sibs = [target] if (is_sibling(target)
                            and (repo in APPROVED_SIBLINGS or allow_unapproved)) else []
    report = {"canonical_files": len(canon_files), "canonical_skills": len(canon_skills),
              "canonical_agents": len(canon_agents), "siblings": []}
    for sib in sibs:
        differs, absent = [], []
        identical = 0
        for rel in canon_files:
            sp = sib / rel
            if not sp.is_file():
                absent.append(str(rel))
            elif filecmp.cmp(BRAINER / rel, sp, shallow=False):
                identical += 1
            else:
                differs.append(str(rel))
        sib_skills = skill_names(sib)
        canon_deleted = canon_deleted_for(sib, canon_skills & sib_skills)
        # Agent-def roster: its own track (a missing roster def surfaces as
        # new_agents, adopt-by-default — never as a skills `absent` file).
        agent_differs = []
        agent_identical = 0
        for rel in canon_agents:
            sp = sib / rel
            if not sp.is_file():
                continue  # surfaced via new_agents below
            elif filecmp.cmp(BRAINER / rel, sp, shallow=False):
                agent_identical += 1
            else:
                agent_differs.append(str(rel))
        sib_agents = agent_names(sib)
        report["siblings"].append({
            "repo": sib.name,
            "shared_skills": sorted(canon_skills & sib_skills),
            "identical": identical,
            "differs": sorted(differs),
            "absent_count": len(absent),
            "absent": sorted(absent),
            "canon_deleted": canon_deleted,
            "sibling_only_skills": sorted(sib_skills - canon_skills),
            "new_skills": new_skills_for(sib),
            "declined_skills": sorted(_optout_skills(sib)),
            "agent_identical": agent_identical,
            "agent_differs": sorted(agent_differs),
            "new_agents": new_agents_for(sib),
            "sibling_only_agents": sorted(sib_agents - agent_names(BRAINER)),
            "declined_agents": sorted(_optout_agents(sib)),
        })
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", action="store_true", help="list every DIFFERS file")
    ap.add_argument("--repo", help="audit only this sibling (exact dir name) — "
                    "post-propagation single-sibling verify")
    ap.add_argument("--allow-unapproved", action="store_true",
                    help="permit an explicit --repo outside Brainer's approved "
                         "sibling allowlist; use only when the user names that "
                         "additional target")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--classify", action="store_true",
                    help="split DIFFERS into STALE (byte-matches a historical "
                         "canonical version — safe fast-forward) vs CUSTOMIZED "
                         "(sibling-local work — manual merge)")
    ap.add_argument("--apply-stale", action="store_true",
                    help="copy canonical HEAD over each STALE file (requires "
                         "--repo; CUSTOMIZED files are never touched; re-run the "
                         "sibling's install.sh + --repo verify afterwards)")
    ap.add_argument("--apply-absent", action="store_true",
                    help="copy canonical files the sibling lacks, ONLY inside "
                         "skills the sibling already adopted (a wholly-absent "
                         "skill dir is deliberate non-adoption — left alone). "
                         "Requires --repo.")
    ap.add_argument("--adopt-new-skills", action="store_true",
                    help="copy every canonical skill the sibling wholly lacks "
                         "(new skills reach every sibling by default — no "
                         "per-skill opt-in from the author). A sibling declines "
                         "explicitly by listing the skill in its root "
                         ".brainer-sync-optout. Requires --repo.")
    ap.add_argument("--adopt-agents", action="store_true",
                    help="copy every canonical .claude/agents/*.md the sibling "
                         "lacks (team-lead's builder/verifier roster + labor "
                         "lanes travel by default — decline one with an "
                         "`agent:<name>` line in .brainer-sync-optout). STALE "
                         "roster defs fast-forward under --apply-stale; "
                         "CUSTOMIZED ones are never overwritten. Agent defs live "
                         "in the loader path, so a copy is live with no install "
                         "step. Requires --repo.")
    ap.add_argument("--apply-deletions", action="store_true",
                     help="delete sibling files classified DELETE — present in "
                          "a shared skill dir, absent from canonical HEAD, and "
                          "byte-matching a version canonical once held (retired "
                          "machinery the sibling never dropped). CONFLICT files "
                          "(sibling-local content that never matched canonical "
                          "history) are never touched. Requires --repo; omit "
                          "this flag (audit/--classify alone) for a dry run — "
                          "nothing is deleted unless this flag is passed.")
    ap.add_argument("--post-check", action="store_true",
                    help="mechanical target-repo test after a propagation: "
                         "byte-compile every .py under the sibling's skills/ "
                         "(exit 1 on any failure). Requires --repo.")
    ap.add_argument("--force-dirty", action="store_true",
                    help="proceed with an apply run even though the sibling's "
                         "worktree has uncommitted changes overlapping a "
                         "destination path (prints a warning listing the "
                         "overlaps). Without this flag, any such overlap "
                         "refuses the entire apply run before touching anything.")
    args = ap.parse_args()
    if (args.repo and args.repo not in APPROVED_SIBLINGS
            and not args.allow_unapproved):
        approved = ", ".join(sorted(APPROVED_SIBLINGS))
        print(f"repo {args.repo!r} is outside the approved Brainer sibling "
              f"allowlist ({approved}); explicit user authorization plus "
              "--allow-unapproved is required", file=sys.stderr)
        return 2
    if args.post_check and not args.repo:
        print("--post-check requires --repo <sibling>", file=sys.stderr)
        return 2
    if args.post_check:
        sib = DOCS / args.repo
        if not is_sibling(sib):
            print(f"no sibling repo named {args.repo!r}", file=sys.stderr)
            return 2
        import py_compile
        failures = []
        n = 0
        for p in (sib / "skills").rglob("*.py"):
            if any(part in SKIP for part in p.relative_to(sib).parts):
                continue
            n += 1
            try:
                py_compile.compile(str(p), doraise=True)
            except py_compile.PyCompileError as exc:
                failures.append(f"{p.relative_to(sib)}: {exc.msg.splitlines()[0]}")
        if failures:
            print(f"post-check FAIL: {len(failures)}/{n} .py files do not compile "
                  f"in {args.repo}:")
            for f in failures:
                print(f"  {f}")
            return 1
        print(f"post-check OK: {n} .py files byte-compile clean in {args.repo}.")
        return 0
    if (args.apply_stale or args.apply_absent or args.adopt_new_skills
            or args.adopt_agents or args.apply_deletions) and not args.repo:
        print("--apply-stale/--apply-absent/--adopt-new-skills/--adopt-agents/"
              "--apply-deletions require --repo <sibling> (one deliberate "
              "sibling at a time — installs write user-global settings)",
              file=sys.stderr)
        return 2
    rep = audit(args.repo, allow_unapproved=args.allow_unapproved)
    if args.repo and not rep["siblings"]:
        print(f"no sibling repo named {args.repo!r} found alongside Brainer "
              f"(must have skills/ + install.sh)", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(rep, indent=2))
        return 0
    apply_mode = (args.apply_stale or args.apply_absent or args.adopt_new_skills
                  or args.adopt_agents or args.apply_deletions)
    if apply_mode:
        # Dirty-worktree gate: --repo (validated above) means exactly one
        # sibling here. Refuse the ENTIRE apply run if any destination path
        # this run would write/delete overlaps the sibling's uncommitted
        # work (tracked or untracked) — an in-flight sibling edit must never
        # be silently clobbered. Unrelated dirt elsewhere in the sibling
        # (e.g. screenery-lean's birds-nest files) never blocks.
        sib_path = DOCS / args.repo
        s0 = rep["siblings"][0]
        targets = plan_apply_targets(sib_path, s0, args)
        dirty = sibling_dirty_status(sib_path)
        if dirty is not None and targets:
            overlap = dirty_overlap(targets, *dirty)
            if overlap:
                if args.force_dirty:
                    print(f"WARNING: --force-dirty overriding the dirty-worktree "
                          f"gate for {args.repo} — {len(overlap)} path(s) with "
                          "uncommitted sibling changes will be overwritten/deleted:",
                          file=sys.stderr)
                    for p in overlap:
                        print(f"  {p}", file=sys.stderr)
                else:
                    print(f"REFUSED: {args.repo} has uncommitted changes "
                          f"overlapping {len(overlap)} destination path(s) this "
                          "apply run would write or delete — in-flight sibling "
                          "work could be lost:", file=sys.stderr)
                    for p in overlap:
                        print(f"  {p}", file=sys.stderr)
                    print("Resolve first: commit or stash these paths in the "
                          f"sibling ({args.repo}), or pass --force-dirty to "
                          "proceed anyway.", file=sys.stderr)
                    return 1
    print(f"canonical: {rep['canonical_files']} skill files, "
          f"{rep['canonical_skills']} skills, {rep['canonical_agents']} agent-defs (Brainer)\n")
    print(f"{'sibling':<18}{'shared':>7}{'ident':>7}{'differ':>7}{'absent':>7}{'new-sk':>7}"
          f"{'ag-id':>7}{'ag-df':>7}{'ag-new':>7}  sibling-only-skills")
    for s in rep["siblings"]:
        print(f"{s['repo']:<18}{len(s['shared_skills']):>7}{s['identical']:>7}"
              f"{len(s['differs']):>7}{s['absent_count']:>7}{len(s['new_skills']):>7}"
              f"{s['agent_identical']:>7}{len(s['agent_differs']):>7}{len(s['new_agents']):>7}  "
              f"{','.join(s['sibling_only_skills']) or '-'}")
        if s["new_skills"]:
            print(f"      NEW-SKILL   {','.join(s['new_skills'])}  "
                  f"(--adopt-new-skills to add{'' if not s['declined_skills'] else '; declined: '+','.join(s['declined_skills'])})")
        if s["new_agents"]:
            print(f"      NEW-AGENT   {','.join(s['new_agents'])}  "
                  f"(--adopt-agents to add{'' if not s['declined_agents'] else '; declined: '+','.join(s['declined_agents'])})")
        if s["sibling_only_agents"]:
            print(f"      AGENT-ONLY  {','.join(s['sibling_only_agents'])}  "
                  f"(sibling-local roster — never touched)")
        if s["canon_deleted"]:
            print(f"      CANON-DEL   {len(s['canon_deleted'])} file(s) present "
                  f"in a shared skill dir, absent from canonical HEAD — run "
                  f"--classify for the DELETE/CONFLICT split, --apply-deletions "
                  f"to remove DELETE-class files")
        if args.files and s["differs"]:
            for f in s["differs"]:
                print(f"      DIFFERS  {f}")
        if (args.classify or args.apply_stale) and s["differs"]:
            cl = classify_differs(DOCS / s["repo"], s["differs"])
            for f in cl["stale"]:
                print(f"      STALE       {f}")
            for f in cl["customized"]:
                print(f"      CUSTOMIZED  {f}")
                for ln in cl["local_lines"].get(f, [])[:6]:
                    print(f"          local: {ln[:100]}")
            if args.apply_stale:
                ignored = _canon_gitignored(cl["stale"])
                for f in cl["stale"]:
                    if f in ignored:
                        continue  # gitignored = runtime state, never canonical source
                    shutil.copy2(BRAINER / f, DOCS / s["repo"] / f)
                    print(f"      applied     {f}")
                if cl["stale"]:
                    print(f"\n  {len(cl['stale'])} stale file(s) fast-forwarded in "
                          f"{s['repo']}. NOW: re-run {s['repo']}/install.sh, then "
                          f"verify with --repo {s['repo']} (topology hard-rule "
                          f"steps 3-4).")
        if (args.classify or args.apply_stale) and s["agent_differs"]:
            acl = classify_differs(DOCS / s["repo"], s["agent_differs"])
            for f in acl["stale"]:
                print(f"      AGENT-STALE       {f}")
            for f in acl["customized"]:
                print(f"      AGENT-CUSTOMIZED  {f}")
                for ln in acl["local_lines"].get(f, [])[:6]:
                    print(f"          local: {ln[:100]}")
            if args.apply_stale:
                ignored = _canon_gitignored(acl["stale"])
                for f in acl["stale"]:
                    if f in ignored:
                        continue  # gitignored = runtime state, never canonical source
                    shutil.copy2(BRAINER / f, DOCS / s["repo"] / f)
                    print(f"      applied           {f}")
                if acl["stale"]:
                    print(f"\n  {len(acl['stale'])} stale agent-def(s) "
                          f"fast-forwarded in {s['repo']} (live immediately — "
                          f".claude/agents/ is the loader path, no install step).")
        if (args.classify or args.apply_deletions) and s["canon_deleted"]:
            dcl = classify_deleted(DOCS / s["repo"], s["canon_deleted"])
            for f in dcl["delete"]:
                print(f"      DELETE      {f}")
            for f in dcl["conflict"]:
                print(f"      CONFLICT    {f}  (sibling-customized — never "
                      f"auto-deleted; requires an explicit operator decision)")
            if args.apply_deletions:
                for f in dcl["delete"]:
                    (DOCS / s["repo"] / f).unlink()
                    print(f"      deleted     {f}")
                if dcl["conflict"]:
                    print(f"\n  {len(dcl['conflict'])} CONFLICT file(s) in "
                          f"{s['repo']} left untouched — sibling-customized "
                          f"content, resolve manually.")
                if dcl["delete"]:
                    print(f"\n  {len(dcl['delete'])} canonically-deleted file(s) "
                          f"removed from {s['repo']}.")
        if args.apply_absent and s.get("absent"):
            sib = DOCS / s["repo"]
            applied = 0
            ignored = _canon_gitignored(s["absent"])
            for f in s["absent"]:
                if f in ignored:
                    continue  # gitignored = runtime state, never canonical source
                rel = Path(f)
                # skills/<file> rides with the skills/ tree itself; deeper paths
                # require the sibling to have adopted that skill's dir.
                skill_dir = sib / rel.parts[0] / rel.parts[1]
                if len(rel.parts) > 2 and not skill_dir.is_dir():
                    continue  # wholly-absent skill = deliberate non-adoption
                (sib / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(BRAINER / rel, sib / rel)
                print(f"      added       {f}")
                applied += 1
            if applied:
                print(f"\n  {applied} absent file(s) added to {s['repo']} "
                      f"(inside already-adopted skills only).")
        if args.adopt_new_skills and s["new_skills"]:
            sib = DOCS / s["repo"]
            for name in s["new_skills"]:
                src = BRAINER / "skills" / name
                dst = sib / "skills" / name
                skill_rels = [str(p) for p in skill_files(BRAINER)
                              if p.parts[:2] == ("skills", name)]
                ignored_rels = _canon_gitignored(skill_rels)

                def _ignore(cur_dir, names, _ignored=ignored_rels):
                    skip = set(shutil.ignore_patterns(*SKIP)(cur_dir, names))
                    rel_dir = Path(cur_dir).resolve().relative_to(BRAINER)
                    skip |= {n for n in names if str(rel_dir / n) in _ignored}
                    return skip

                shutil.copytree(src, dst, dirs_exist_ok=True, ignore=_ignore)
                print(f"      adopted     skills/{name}/")
            print(f"\n  {len(s['new_skills'])} new skill(s) adopted into "
                  f"{s['repo']}. NOW: re-run {s['repo']}/install.sh (wires the "
                  f"new skill's carriers/hooks), then verify with --repo "
                  f"{s['repo']}.")
        if args.adopt_agents and s["new_agents"]:
            sib = DOCS / s["repo"]
            (sib / AGENTS_DIR).mkdir(parents=True, exist_ok=True)
            for name in s["new_agents"]:
                shutil.copy2(BRAINER / AGENTS_DIR / f"{name}.md",
                             sib / AGENTS_DIR / f"{name}.md")
                print(f"      adopted     {AGENTS_DIR}/{name}.md")
            print(f"\n  {len(s['new_agents'])} agent-def(s) adopted into "
                  f"{s['repo']} — team-lead's roster now travels. They are live "
                  f"immediately (.claude/agents/ is the loader path); no "
                  f"install.sh step needed for agent defs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
