#!/usr/bin/env python3
"""harness_acceptance — grades the CURRENT harness against SPEC.md's H-check
table (.brainer/plans/10x-harness/SPEC.md). Deterministic, offline, stdlib-only,
filesystem-only: no network, no model calls. Runs in <10s from repo root.

H1a-H7 only. H8 is explicitly EXCLUDED (model-dependent; tracked separately in
eval/MEASUREMENT_QUEUE.md).

Each check is a pure function returning (id, axis, ok: bool, reason: str). A
check that raises is caught by the runner and reported as FAIL, not a crash.

Modes:
  --report (default)  print a table of all checks; ALWAYS exits 0.
  --gate               same table; exits nonzero if any check FAILs.

The FAIL rows are the point — a FAIL on the current repo is the expected,
honest baseline this suite exists to certify (see BASELINE.md).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parents[2]

Check = Callable[[], tuple[str, str, bool, str]]


# ---------------------------------------------------------------------------
# H1 — token
# ---------------------------------------------------------------------------

def check_h1a() -> tuple[str, str, bool, str]:
    """Resident-block byte budget.

    Judgment call: "budget = 60% of the CURRENT measured size" is a moving
    target that would make this check un-failable (the budget rides with
    whatever CLAUDE.md happens to measure today). Per SPEC M1 ("resident
    block <= 60% of current bytes") and the acceptance-manifest row ("start:
    current -40%"), the diet target is a FIXED constant derived from the
    size measured when this harness was scaffolded (2026-07-05), not a
    live recomputation — otherwise growing the block would silently grow
    its own budget. Constant below = round(0.6 * 7990), the pre-diet
    resident-block size (bytes strictly between the sentinels) on that date.
    """
    BUDGET_BYTES = 4794  # SPEC M1: 60% of the 2026-07-05 baseline (7990 bytes)
    claude_md = REPO / "CLAUDE.md"
    if not claude_md.exists():
        return ("H1a", "token", False, "CLAUDE.md not found")
    text = claude_md.read_text(encoding="utf-8")
    start_marker = "<!-- brainer:skills-catalog:start -->"
    end_marker = "<!-- brainer:skills-catalog:end -->"
    s = text.find(start_marker)
    e = text.find(end_marker)
    if s == -1 or e == -1 or e < s:
        return ("H1a", "token", False, "sentinel block not found in CLAUDE.md")
    block = text[s + len(start_marker):e]
    size = len(block.encode("utf-8"))
    ok = size <= BUDGET_BYTES
    return ("H1a", "token", ok,
            f"resident block {size}B vs budget {BUDGET_BYTES}B (60% of 7990B baseline)")


def check_h1b() -> tuple[str, str, bool, str]:
    """No skills/*/SKILL.md > 12,288 bytes without a split-justified marker.

    Fix (round 2, cold-verifier NEEDS-FIXES): a bare `<!-- split-justified -->`
    string used to flip an oversized body straight to PASS with no evidence a
    split actually happened — a token gesture, not tiering. The marker only
    counts now if the skill dir ALSO ships >=1 companion deep-dive .md file
    (any *.md beside SKILL.md/EVAL.md) that SKILL.md's body actually links to
    by relative path (e.g. `[...](FOO.md)` or `[...](./FOO.md)`) — real
    evidence of a core+deep-dive split, not just an unenforced comment.
    """
    LIMIT = 12288
    offenders = []
    for f in sorted((REPO / "skills").glob("*/SKILL.md")):
        size = f.stat().st_size
        if size <= LIMIT:
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        skill_dir = f.parent
        if "<!-- split-justified -->" not in text:
            offenders.append(f"{skill_dir.name} ({size}B, no split-justified marker)")
            continue
        companions = sorted(
            p.name for p in skill_dir.glob("*.md")
            if p.name not in ("SKILL.md", "EVAL.md")
        )
        linked_companions = [
            name for name in companions
            if re.search(r"\]\(\.?/?" + re.escape(name) + r"\)", text)
        ]
        if not linked_companions:
            offenders.append(
                f"{skill_dir.name} ({size}B, split-justified marker present but "
                f"no linked deep-dive companion .md found)"
            )
    ok = not offenders
    reason = "all SKILL.md <= 12,288B or genuinely split (marker + linked deep-dive file)" if ok else \
        f"{len(offenders)} oversized without a real split: {', '.join(offenders)}"
    return ("H1b", "token", ok, reason)


def check_h1c() -> tuple[str, str, bool, str]:
    """Skill-count consistency: skills/ dirs vs README vs marketplace vs SKILLS_INDEX."""
    skills_dirs = sorted(p.parent.name for p in (REPO / "skills").glob("*/SKILL.md"))
    n_dirs = len(skills_dirs)

    readme = (REPO / "README.md").read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"\((\d+)\s+skills\)", readme)
    n_readme = int(m.group(1)) if m else None

    marketplace_path = REPO / ".claude-plugin" / "marketplace.json"
    n_marketplace = None
    try:
        mp = json.loads(marketplace_path.read_text(encoding="utf-8"))
        plugins = mp.get("plugins", [])
        if plugins and isinstance(plugins, list):
            n_marketplace = len(plugins[0].get("skills", []))
    except Exception:
        n_marketplace = None

    index_path = REPO / "skills" / "SKILLS_INDEX.md"
    n_index = None
    if index_path.exists():
        idx_text = index_path.read_text(encoding="utf-8", errors="ignore")
        n_index = len(re.findall(r"^\|\s*\[", idx_text, re.MULTILINE))

    counts = {"skills/": n_dirs, "README.md": n_readme,
              "marketplace.json": n_marketplace, "SKILLS_INDEX.md": n_index}
    values = [v for v in counts.values() if v is not None]
    ok = len(values) == 4 and len(set(values)) == 1
    reason = "; ".join(f"{k}={v}" for k, v in counts.items())
    return ("H1c", "token", ok, reason)


# ---------------------------------------------------------------------------
# H2 — reliability
# ---------------------------------------------------------------------------

def _frontmatter(text: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm


def check_h2a() -> tuple[str, str, bool, str]:
    """Every default-on skill needs >=1 of: non-empty drift_probes.json,
    tools/*.py with an adjacent test file, a hook file, or an EVAL.md with a
    measured number outside pending/unmeasured lines.

    Population fix (round 2, cold-verifier NEEDS-FIXES): the original version
    scoped to frontmatter `auto-install: true` literally (5 skills), which
    under-counts "default-on" — install.sh's own opt-in test
    (`skill_is_optin()`, ~L151) greps for `auto-install: *false` specifically;
    a skill with NO auto-install key (absent) is installed by default just
    the same as one that says `true`. SPEC's H2a axis text is "every
    default-on skill has hook/probe/test/measured-evidence" — the SPEC
    population is default-on skills (~21 per install.sh semantics: auto-install
    != false), not the narrower auto-install-EXPLICITLY-true set (5 skills).
    Rescoped accordingly; this is a materially larger and stricter population.

    Named exception (per brief): requirements-ledger passes by user fiat
    regardless of the mechanical evidence found.
    """
    NAMED_EXCEPTION = {"requirements-ledger"}
    measured_re = re.compile(r"(%|\bN\s*=|\bn\s*=|×|\bvs\b)", re.IGNORECASE)
    offenders = []
    checked = []
    for skill_md in sorted((REPO / "skills").glob("*/SKILL.md")):
        name = skill_md.parent.name
        fm = _frontmatter(skill_md.read_text(encoding="utf-8", errors="ignore"))
        if fm.get("auto-install", "").lower() == "false":
            continue  # opt-in per install.sh's skill_is_optin(); not in scope
        checked.append(name)
        if name in NAMED_EXCEPTION:
            continue
        skill_dir = skill_md.parent
        has_probes = False
        probes_path = skill_dir / "drift_probes.json"
        if probes_path.exists():
            try:
                data = json.loads(probes_path.read_text(encoding="utf-8"))
                has_probes = bool(data)
            except Exception:
                has_probes = False

        has_tool_test = False
        tools_dir = skill_dir / "tools"
        if tools_dir.is_dir():
            py_files = {p.name for p in tools_dir.glob("*.py")}
            non_test = [p for p in py_files if not p.startswith("test_")]
            for p in non_test:
                if f"test_{p}" in py_files:
                    has_tool_test = True
                    break

        has_hook = False
        if tools_dir.is_dir():
            has_hook = any(tools_dir.glob("hook*"))

        has_eval_measured = False
        eval_path = skill_dir / "EVAL.md"
        if eval_path.exists():
            for line in eval_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                low = line.lower()
                if "pending" in low or "unmeasured" in low:
                    continue
                if measured_re.search(line):
                    has_eval_measured = True
                    break

        if not (has_probes or has_tool_test or has_hook or has_eval_measured):
            offenders.append(name)

    ok = not offenders
    reason = (f"{len(checked)} default-on (auto-install != false) skills all have "
              f"hook/probe/test/measured-evidence (or named exception)" if ok else
              f"{len(offenders)}/{len(checked)} default-on skills missing mechanical "
              f"evidence: {', '.join(offenders)}")
    return ("H2a", "reliability", ok, reason)


def check_h2b() -> tuple[str, str, bool, str]:
    """wiki.py's `new` write path actually ENFORCES write-gate: a low-signal,
    reasonless page must be REFUSED (nonzero exit), not just theoretically
    wired.

    Fix (round 2, cold-verifier NEEDS-FIXES): the original version grepped
    wiki.py's source for a write-gate import/call — presence, not enforcement
    (a call that's present but short-circuited, or a code path that skips the
    gate at runtime, would still grep-match). Upgraded to a behavioral probe:
    invoke the REAL `wiki.py new` CLI against a throwaway `wiki init`
    tempdir with a low-signal/reasonless page (empty body + empty reason) and
    assert it exits nonzero with a refusal. Offline (wiki.py is stdlib-only:
    json/re/sqlite3/dataclasses/datetime/math/pathlib/typing — no network, no
    external deps), writes confined to the tempdir, and both `init` + `new`
    complete in well under a second, so this stays inside the <10s total
    budget for the whole --report run.
    """
    wiki_py = REPO / "skills" / "wiki-memory" / "tools" / "wiki.py"
    if not wiki_py.exists():
        return ("H2b", "reliability", False, "wiki.py not found")

    with tempfile.TemporaryDirectory(prefix="harness_acceptance_h2b_") as td:
        wiki_root = Path(td) / "wiki"
        try:
            init_proc = subprocess.run(
                [sys.executable, str(wiki_py), "--root", str(wiki_root), "init"],
                capture_output=True, text=True, timeout=10,
            )
        except Exception as e:
            return ("H2b", "reliability", False, f"wiki.py init errored: {e}")
        if init_proc.returncode != 0:
            return ("H2b", "reliability", False,
                     f"wiki.py init failed (exit {init_proc.returncode}); cannot probe write path")

        try:
            new_proc = subprocess.run(
                [sys.executable, str(wiki_py), "--root", str(wiki_root), "new",
                 "--template", "page", "--title", "low-signal probe page",
                 "--body", "", "--reason", ""],
                capture_output=True, text=True, timeout=10,
            )
        except Exception as e:
            return ("H2b", "reliability", False, f"wiki.py new errored: {e}")

    refused = new_proc.returncode != 0
    mentions_refusal = "REFUSED" in new_proc.stdout or "refused" in new_proc.stdout
    ok = refused and mentions_refusal
    if ok:
        reason = (f"behavioral probe: low-signal/reasonless `new` REFUSED "
                  f"(exit {new_proc.returncode}) — write-gate is enforced, not merely wired")
    else:
        reason = (f"behavioral probe: low-signal/reasonless `new` was NOT refused "
                  f"(exit {new_proc.returncode}, refused-text-present={mentions_refusal}) — "
                  f"write-gate is not enforced on this write path")
    return ("H2b", "reliability", ok, reason)


def check_h2c() -> tuple[str, str, bool, str]:
    """loop_lint must FAIL (exit code 2, its FAIL-severity tier) an unattended
    spec whose generator names an irreversible action with no human gate.

    Judgment call: the brief's phrasing ("check FAILs (exit nonzero)") is
    ambiguous because loop_lint.py has THREE non-zero exit codes with distinct
    meaning (0 clean / 1 WARN / 2 FAIL / 3 unparseable). Read literally as
    "any nonzero" this check would PASS today (R7 already exits 1 on WARN),
    contradicting SPEC.md's explicit "today: FAIL" for H2c and its own axis
    text ("loop_lint FAILs irreversible+unattended"). The conservative,
    SPEC-consistent reading: this check requires loop_lint's FAIL tier
    specifically (exit code == 2), not merely a nonzero exit.
    """
    fixture = REPO / "eval" / "harness_acceptance" / "fixtures" / "unattended_irreversible.loop.md"
    loop_lint = REPO / "skills" / "loop-engineering" / "tools" / "loop_lint.py"
    if not fixture.exists():
        return ("H2c", "reliability", False, "fixture file missing")
    if not loop_lint.exists():
        return ("H2c", "reliability", False, "loop_lint.py not found")
    try:
        proc = subprocess.run(
            [sys.executable, str(loop_lint), str(fixture)],
            capture_output=True, text=True, timeout=10, cwd=str(REPO),
        )
    except Exception as e:
        return ("H2c", "reliability", False, f"loop_lint invocation errored: {e}")
    ok = proc.returncode == 2
    reason = (f"loop_lint exit={proc.returncode} (2=FAIL expected); "
              f"{'FAIL-severity as required' if ok else 'not FAIL-severity (see WARN/exit-code judgment call)'}")
    return ("H2c", "reliability", ok, reason)


# ---------------------------------------------------------------------------
# H3 — portability
# ---------------------------------------------------------------------------

def _extract_paths_from_hook_config(text: str) -> list[str]:
    """Pull repo-relative file paths out of hook command strings like
    `bash "${CLAUDE_PROJECT_DIR:-$PWD}/.claude/skills/foo/tools/hook.sh"`."""
    paths = []
    for m in re.finditer(r"\$PWD\}/([^\"'\\\s]+)", text):
        paths.append(m.group(1))
    return paths


def check_h3a() -> tuple[str, str, bool, str]:
    """Every path referenced in a host's own generated hook config must
    resolve UNDER THAT HOST'S OWN skills dir (per-host install model).

    Fix (round 2, cold-verifier NEEDS-FIXES): the original version checked
    `(REPO/rel).exists()` — a tautology in this repo's dual/multi-install dev
    tree, where .claude/skills/, .codex/skills/, and .gemini/skills/ all
    happen to exist side by side. That masked the real SPEC defect: a
    CODEX-ONLY install only runs install_codex() (install.sh), which creates
    .codex/skills/ and NEVER creates .claude/skills/ — so a path referenced by
    .codex/hooks.json that lives under .claude/skills/ would be missing on a
    codex-only machine even though it happens to resolve here. Same principle
    for .gemini/settings.json vs .gemini/skills/. Model this per-host: any
    path referenced by a host's config that points into ANOTHER host's
    skills/ dir is a cross-host reference bug, regardless of whether this
    particular checkout happens to have every host installed.
    """
    HOST_OWN_PREFIX = {
        ".codex/hooks.json": ".codex/skills/",
        ".gemini/settings.json": ".gemini/skills/",
    }
    OTHER_HOST_PREFIXES = (".claude/skills/", ".codex/skills/", ".gemini/skills/")

    configs = [
        REPO / ".codex" / "hooks.json",
        REPO / ".gemini" / "settings.json",
    ]
    cross_host = []
    truly_missing = []
    checked_any = False
    for cfg in configs:
        if not cfg.exists():
            continue
        checked_any = True
        cfg_key = f"{cfg.parent.name}/{cfg.name}"
        own_prefix = HOST_OWN_PREFIX.get(cfg_key)
        text = cfg.read_text(encoding="utf-8", errors="ignore")
        for rel in _extract_paths_from_hook_config(text):
            is_skills_path = any(rel.startswith(p) for p in OTHER_HOST_PREFIXES)
            if is_skills_path and own_prefix and not rel.startswith(own_prefix):
                cross_host.append(f"{cfg_key}:{rel} (not under {own_prefix})")
                continue
            # non-skills-dir paths (rare) still need to exist somewhere real.
            if not is_skills_path and not (REPO / rel).exists():
                truly_missing.append(f"{cfg_key}:{rel}")
    if not checked_any:
        return ("H3a", "portability", False, "no hook config files found (.codex/hooks.json, .gemini/settings.json)")
    ok = not cross_host and not truly_missing
    if ok:
        reason = "every host config references only its own skills/ dir (no cross-host paths)"
    else:
        parts = []
        if cross_host:
            parts.append(f"cross-host references (missing on a single-host install): {', '.join(cross_host)}")
        if truly_missing:
            parts.append(f"missing: {', '.join(truly_missing)}")
        reason = "; ".join(parts)
    return ("H3a", "portability", ok, reason)


def check_h3b() -> tuple[str, str, bool, str]:
    """scripts/check_carrier_sync.py and scripts/check_generated_files.py exit 0."""
    results = []
    for script in ["scripts/check_carrier_sync.py", "scripts/check_generated_files.py"]:
        path = REPO / script
        if not path.exists():
            results.append((script, 1, "not found"))
            continue
        try:
            proc = subprocess.run(
                [sys.executable, str(path)], capture_output=True, text=True,
                timeout=15, cwd=str(REPO),
            )
            results.append((script, proc.returncode, proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""))
        except Exception as e:
            results.append((script, 1, f"error: {e}"))
    ok = all(code == 0 for _, code, _ in results)
    reason = "; ".join(f"{s}=exit{c}" for s, c, _ in results)
    return ("H3b", "portability", ok, reason)


# ---------------------------------------------------------------------------
# H4 — memory
# ---------------------------------------------------------------------------

def check_h4a() -> tuple[str, str, bool, str]:
    """Every wiki/concepts|queries|patterns page with non-empty superseded-by
    must point to an existing page; supersedes entries must exist too."""
    dirs = ["concepts", "queries", "patterns"]
    page_ids = set()
    for d in dirs:
        for p in (REPO / "wiki" / d).glob("*.md"):
            page_ids.add(p.stem)
    dangling = []
    for d in dirs:
        for p in (REPO / "wiki" / d).glob("*.md"):
            fm = _frontmatter(p.read_text(encoding="utf-8", errors="ignore"))
            for key in ("superseded-by", "supersedes"):
                raw = fm.get(key, "")
                if not raw or raw == "[]":
                    continue
                targets = re.findall(r"[\w./-]+", raw)
                for t in targets:
                    t_clean = Path(t).stem
                    if t_clean and t_clean not in page_ids:
                        dangling.append(f"{p.relative_to(REPO)}:{key}={t}")
    ok = not dangling
    reason = "no dangling supersede chains" if ok else f"dangling: {', '.join(dangling)}"
    return ("H4a", "memory", ok, reason)


def check_h4b() -> tuple[str, str, bool, str]:
    """wiki/.brainer/usage.json exists AND a prune-report mechanism consumes
    usage/read-count data in wiki-refresh tools."""
    usage_json = REPO / "wiki" / ".brainer" / "usage.json"
    has_usage_file = usage_json.exists()
    consumes_usage = False
    refresh_tools = REPO / "skills" / "wiki-refresh" / "tools"
    if refresh_tools.is_dir():
        for f in refresh_tools.glob("*.py"):
            text = f.read_text(encoding="utf-8", errors="ignore")
            if re.search(r"usage\.json|read.?count", text, re.IGNORECASE):
                consumes_usage = True
                break
    ok = has_usage_file and consumes_usage
    reason = (f"usage.json exists={has_usage_file}, "
              f"wiki-refresh consumes usage/read-count={consumes_usage}")
    return ("H4b", "memory", ok, reason)


def check_h4c() -> tuple[str, str, bool, str]:
    """A covered-verdicts index page exists."""
    candidates = [
        REPO / "wiki" / "queries" / "covered-verdicts.md",
    ]
    found = [str(c.relative_to(REPO)) for c in candidates if c.exists()]
    if not found:
        # broader grep fallback, in case it lives under a different slug
        for p in (REPO / "wiki").rglob("*.md"):
            if "covered-verdict" in p.name.lower():
                found.append(str(p.relative_to(REPO)))
    ok = bool(found)
    reason = f"found: {', '.join(found)}" if ok else "no covered-verdicts index page found under wiki/"
    return ("H4c", "memory", ok, reason)


# ---------------------------------------------------------------------------
# H5 — efficiency
# ---------------------------------------------------------------------------

def check_h5a() -> tuple[str, str, bool, str]:
    """orchestration_trace.py writes/accepts a source/provenance field; also
    check .brainer/trace/lanes.jsonl lines for the field."""
    trace_py = REPO / "skills" / "_shared" / "orchestration_trace.py"
    has_field_in_code = False
    if trace_py.exists():
        text = trace_py.read_text(encoding="utf-8", errors="ignore")
        has_field_in_code = bool(re.search(r'["\'](source|provenance)["\']', text))

    has_field_in_trace = False
    lanes_jsonl = REPO / ".brainer" / "trace" / "lanes.jsonl"
    if lanes_jsonl.exists():
        for line in lanes_jsonl.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if "source" in rec or "provenance" in rec:
                has_field_in_trace = True
                break

    ok = has_field_in_code or has_field_in_trace
    reason = (f"orchestration_trace.py declares source/provenance={has_field_in_code}, "
              f"lanes.jsonl carries it={has_field_in_trace}")
    return ("H5a", "efficiency", ok, reason)


def check_h5b() -> tuple[str, str, bool, str]:
    """A per-skill activation-telemetry mechanism exists beyond learn-skill."""
    search_dirs = [
        REPO / "skills" / "_shared",
        REPO / "skills" / "compliance-canary" / "tools",
    ]
    found = []
    for d in search_dirs:
        if not d.is_dir():
            continue
        for f in d.glob("*.py"):
            text = f.read_text(encoding="utf-8", errors="ignore")
            if re.search(r"activation.?(telemetry|recorder|event)|per.skill.*(usage|activation)", text, re.IGNORECASE):
                found.append(str(f.relative_to(REPO)))
    ok = bool(found)
    reason = f"found: {', '.join(found)}" if ok else \
        "no shared activation/usage recorder in skills/_shared/ or compliance-canary/tools/ (learn-skill's telemetry.py is skill-scoped only)"
    return ("H5b", "efficiency", ok, reason)


# ---------------------------------------------------------------------------
# H6 — quality
# ---------------------------------------------------------------------------

def check_h6a() -> tuple[str, str, bool, str]:
    """EVAL.md 'tools/ payload' KB rows vs recomputed size. Mismatch >25%
    relative AND >4KB absolute -> FAIL, naming the files.

    Judgment call: the brief says "recompute du -sk of that skill's tools/
    dir". Literal `du -sk` measures disk blocks (4KB-rounded on APFS/most
    filesystems), which diverges from the byte-sum KB figures the repo's own
    generator (eval/static_cost.py, dir_size(): sum of file byte sizes / 1024)
    produces — comparing EVAL.md's claims against `du -sk` would flag every
    skill as a "mismatch" purely from block-rounding noise, not real drift.
    Recompute using the SAME byte-based method that produced the numbers
    being checked (eval/static_cost.py's dir_size), so a mismatch reflects
    actual drift, not filesystem block granularity.
    """
    tolerance_rel = 0.25
    tolerance_abs_kb = 4.0
    row_re = re.compile(r"tools/\s*payload\s*\|\s*\*{0,2}([\d.]+)\s*KB", re.IGNORECASE)
    mismatches = []
    checked = 0
    for skill_dir in sorted((REPO / "skills").iterdir()):
        if not skill_dir.is_dir():
            continue
        eval_path = skill_dir / "EVAL.md"
        if not eval_path.exists():
            continue
        text = eval_path.read_text(encoding="utf-8", errors="ignore")
        m = row_re.search(text)
        if not m:
            continue
        checked += 1
        claimed_kb = float(m.group(1))
        tools_dir = skill_dir / "tools"
        actual_bytes = sum(f.stat().st_size for f in tools_dir.rglob("*") if f.is_file()) if tools_dir.is_dir() else 0
        actual_kb = round(actual_bytes / 1024, 1)
        abs_diff = abs(actual_kb - claimed_kb)
        rel_diff = abs_diff / claimed_kb if claimed_kb else (1.0 if actual_kb else 0.0)
        if rel_diff > tolerance_rel and abs_diff > tolerance_abs_kb:
            mismatches.append(f"{skill_dir.name} (claimed {claimed_kb}KB, actual {actual_kb}KB)")
    ok = not mismatches
    reason = (f"{checked} EVAL.md tools/ payload rows checked, all within tolerance" if ok else
              f"{len(mismatches)}/{checked} mismatched: {', '.join(mismatches)}")
    return ("H6a", "quality", ok, reason)


def check_h6b() -> tuple[str, str, bool, str]:
    """schema/skill_conflicts.json contains a pair covering team-lead + prompt-triage."""
    path = REPO / "schema" / "skill_conflicts.json"
    if not path.exists():
        return ("H6b", "quality", False, "schema/skill_conflicts.json not found")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return ("H6b", "quality", False, f"invalid JSON: {e}")
    pair = {"team-lead", "prompt-triage"}
    found = any(pair.issubset(set(c.get("skills", []))) for c in data.get("conflicts", []))
    reason = "team-lead/prompt-triage pair present" if found else \
        "no conflict entry covers the team-lead + prompt-triage pair"
    return ("H6b", "quality", found, reason)


# ---------------------------------------------------------------------------
# H7 — orchestration
# ---------------------------------------------------------------------------

def check_h7() -> tuple[str, str, bool, str]:
    """ORCHESTRATION.md contains the digest-cap rule AND brief_header.py has
    >=7 test functions in test_brief_header.py."""
    orch = REPO / "skills" / "_shared" / "ORCHESTRATION.md"
    has_digest_cap = False
    if orch.exists():
        text = orch.read_text(encoding="utf-8", errors="ignore")
        has_digest_cap = "2,500" in text or "digests, not dumps" in text

    test_path = REPO / "skills" / "_shared" / "test_brief_header.py"
    n_tests = 0
    if test_path.exists():
        text = test_path.read_text(encoding="utf-8", errors="ignore")
        n_tests = len(re.findall(r"^def test_", text, re.MULTILINE))

    MIN_TESTS = 7
    ok = has_digest_cap and n_tests >= MIN_TESTS
    reason = (f"digest-cap rule present={has_digest_cap}, "
              f"test_brief_header.py has {n_tests} test functions (>= {MIN_TESTS} required)")
    return ("H7", "orchestration", ok, reason)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

CHECKS: list[Check] = [
    check_h1a, check_h1b, check_h1c,
    check_h2a, check_h2b, check_h2c,
    check_h3a, check_h3b,
    check_h4a, check_h4b, check_h4c,
    check_h5a, check_h5b,
    check_h6a, check_h6b,
    check_h7,
]


def run_checks(checks: list[Check] = CHECKS) -> list[tuple[str, str, bool, str]]:
    """Run every check; a raising check is reported as FAIL, never a crash."""
    results = []
    for fn in checks:
        try:
            results.append(fn())
        except Exception as e:  # noqa: BLE001 — a check must never crash the runner
            check_id = fn.__name__.replace("check_", "").upper()
            results.append((check_id, "unknown", False, f"CRASHED: {type(e).__name__}: {e}"))
    return results


def format_table(results: list[tuple[str, str, bool, str]]) -> str:
    lines = ["id | axis | verdict | reason", "---|---|---|---"]
    for check_id, axis, ok, reason in results:
        verdict = "PASS" if ok else "FAIL"
        lines.append(f"{check_id} | {axis} | {verdict} | {reason}")
    n_pass = sum(1 for _, _, ok, _ in results if ok)
    n_fail = len(results) - n_pass
    lines.append("")
    lines.append(f"{n_pass}/{len(results)} PASS, {n_fail} FAIL")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="harness_acceptance/run.py",
        description="Grades the current Brainer harness against SPEC.md's H1-H7 checks.",
    )
    ap.add_argument("--report", action="store_true",
                     help="print the table; always exit 0 (default mode)")
    ap.add_argument("--gate", action="store_true",
                     help="print the table; exit nonzero if any check FAILs")
    args = ap.parse_args(argv)

    results = run_checks()
    print(format_table(results))

    if args.gate:
        return 0 if all(ok for _, _, ok, _ in results) else 1
    return 0  # --report (default): always exits 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
