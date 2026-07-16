#!/usr/bin/env python3
"""learn-skill — turn a source into a *proposed* Brainer skill.

Prompt-only ingestion: the agent reads the source with existing tools (WebFetch /
Read / Grep / deep-research), then uses these stdlib helpers to dedup, lint, and
scaffold a `skills/<name>/SKILL.md`. No new ingestion engine, no network here.

Subcommands:
  dedup    --desc TEXT [--body-file F] [--skills-dir D] [--threshold T]
           Token-overlap of TEXT vs every existing skill description, plus an exact
           code/command-line scan of an optional candidate body vs existing skill
           bodies. Verdict: CREATE | LIKELY_PATCH (desc) | POSSIBLE_PATCH (body).
           Exit 0 = CREATE, 3 = PATCH suggested (advisory; abort & let the user decide).

  lint     --file SKILL.md
           Hard-fail on missing frontmatter keys (name/description/status) or missing
           required sections (When to Use / Procedure / Verification). `description<=60`
           is advisory (warn only) — Brainer uses long trigger descriptions and proposed
           skills are slash-only. Exit 0 pass / 1 fail.

  scaffold --name N --desc D --source S [--when ...] [--proc ...] [--pitfalls ...]
           [--verify ...] [--rationale ...] [--out PATH]
           Render the learned-skill template to skills/<name>/SKILL.md (or --out).

Trust subcommands (telemetry-gated, added v1.13 once usage instrumentation existed):
  promote  --name N [--min-successes 3] [--manual-only]
           proposed -> trusted IFF telemetry shows >= N consecutive hits, no trailing
           abort, and the skill lints clean. The verifier (this command, reading
           telemetry.py) is a SEPARATE actor from the generator (field usage). Earlier
           designs had NO promote because a hand counter is not evidence; telemetry.py
           supplies the evidence, so promotion is now counted rather than manual.
  demote   --name N [--reason ...]      trusted -> proposed (revoke model-invocation).
  staleness [--apply]                   per-skill source freshness (git/age aware).
"""
from __future__ import annotations

import argparse
import datetime
import json
import math
import os
import re
import shlex
import signal
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

# Harness tools are always present (the agent runtime provides them); only external
# CLI binaries named in `requires_tools:` are checked with shutil.which.
_HARNESS_TOOLS = {"bash", "read", "write", "edit", "grep", "glob", "webfetch", "websearch", "task"}
DEFAULT_GATE_TIMEOUT_SECONDS = 30.0
MAX_GATE_TIMEOUT_SECONDS = 300.0
DEFAULT_GATE_OUTPUT_LIMIT_BYTES = 16_384

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "with", "use",
    "when", "before", "after", "any", "that", "this", "it", "is", "are", "be",
    "as", "by", "from", "into", "via", "per", "not", "no", "you", "your", "if",
    "skill", "skills", "using", "used", "uses", "run", "runs",
}


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if len(w) > 2 and w not in STOPWORDS}


def _overlap_coeff(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def _unquote(v: str) -> str:
    """Strip a surrounding YAML quote pair so readers get the bare value. Needed
    now that scaffold quotes scalars carrying ': ' / '#' / brackets (see
    _yaml_scalar): without this, source/description would be read WITH the quotes
    and staleness/dedup would compare a quoted string."""
    if len(v) >= 2 and v[0] == v[-1] == '"':
        try:
            return json.loads(v)            # double-quoted: JSON-unescape
        except ValueError:
            return v[1:-1]
    if len(v) >= 2 and v[0] == v[-1] == "'":
        return v[1:-1].replace("''", "'")   # single-quoted: YAML '' -> '
    return v


def _frontmatter(text: str) -> dict[str, str]:
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.DOTALL)
    if not m:
        return {}
    fm: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            k, _, v = line.partition(":")
            fm[k.strip()] = _unquote(v.strip())
    return fm


def _existing_skills(skills_dir: Path, exclude: str | None = None):
    """Yield (name, description, body) for every existing skill."""
    for sm in sorted(skills_dir.glob("*/SKILL.md")):
        name = sm.parent.name
        if exclude and name == exclude:
            continue
        text = sm.read_text(encoding="utf-8", errors="replace")
        fm = _frontmatter(text)
        yield name, fm.get("description", ""), text


def _code_lines(text: str) -> set[str]:
    """Distinctive command/code lines worth matching verbatim (len>10, de-prosed)."""
    out: set[str] = set()
    in_fence = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        candidate = None
        if in_fence:
            candidate = line
        elif line.startswith(("$ ", "python ", "bash ", "./", "git ")):
            candidate = line
        if candidate and len(candidate) > 10 and not candidate.startswith("#"):
            out.add(candidate)
    return out


def cmd_dedup(args) -> int:
    skills_dir = Path(args.skills_dir)
    desc_tokens = _tokens(args.desc)
    body_text = ""
    if args.body_file:
        body_text = Path(args.body_file).read_text(encoding="utf-8", errors="replace")
    cand_code = _code_lines(body_text) if body_text else set()

    desc_hits = []
    body_hits = []
    for name, sdesc, sbody in _existing_skills(skills_dir, exclude=args.name):
        score = _overlap_coeff(desc_tokens, _tokens(sdesc))
        if score >= args.threshold:
            desc_hits.append((name, round(score, 3)))
        if cand_code:
            shared = cand_code & _code_lines(sbody)
            if shared:
                body_hits.append((name, sorted(shared)[:3]))

    desc_hits.sort(key=lambda x: -x[1])
    if desc_hits:
        verdict = "LIKELY_PATCH"
    elif body_hits:
        verdict = "POSSIBLE_PATCH"
    else:
        verdict = "CREATE"

    print(f"verdict: {verdict}")
    for name, score in desc_hits:
        print(f"  desc-overlap {score:>5}  -> {name}")
    for name, shared in body_hits:
        print(f"  body-code-match     -> {name}  e.g. {shared[0]!r}")
    if verdict != "CREATE":
        print(f"\nADVISORY: a similar skill may already exist. Do NOT create a duplicate.")
        print(f"Abort, show the user this summary, and decide: PATCH the existing skill,")
        print(f"or re-frame the new one. No auto-merge.")
        return 3
    print("\nNo near-duplicate found — safe to CREATE.")
    return 0


REQUIRED_SECTIONS = [
    ("When to Use", r"(?im)^#{1,3}\s+when to use\b"),
    ("Procedure", r"(?im)^#{1,3}\s+(procedure|steps)\b"),
    ("Pitfalls", r"(?im)^#{1,3}\s+pitfalls\b"),
    ("Verification", r"(?im)^#{1,3}\s+verification\b"),
]


def _without_fenced_blocks(text: str) -> str:
    """Return prose outside Markdown backtick/tilde fences."""
    out: list[str] = []
    fence_char = ""
    fence_len = 0
    for line in text.splitlines():
        if not fence_char:
            match = re.match(r"^[ \t]*(`{3,}|~{3,})", line)
            if match:
                marker = match.group(1)
                fence_char, fence_len = marker[0], len(marker)
                continue
            out.append(line)
            continue
        close = re.match(r"^[ \t]*([`~]{3,})[ \t]*$", line)
        if close and close.group(1)[0] == fence_char and len(close.group(1)) >= fence_len:
            fence_char, fence_len = "", 0
    return "\n".join(out)


def cmd_lint(args) -> int:
    text = Path(args.file).read_text(encoding="utf-8", errors="replace")
    fm = _frontmatter(text)
    errors, warnings = [], []

    # Strict YAML gate (when PyYAML is importable): _frontmatter is a lenient
    # regex reader that tolerates malformed YAML a strict host would reject, so a
    # scaffold/hand-edit that breaks the frontmatter (e.g. an unquoted ': ') must
    # be caught here, not silently passed.
    block = re.match(r"^﻿?---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n", text, re.DOTALL)
    try:
        import yaml  # type: ignore
        if block is not None:
            try:
                yaml.safe_load(block.group(1))
            except yaml.YAMLError as e:
                errors.append(f"frontmatter is not valid YAML ({e})")
    except ImportError:  # pragma: no cover - dependency-free fallback
        pass

    for key in ("name", "description", "status"):
        if not fm.get(key):
            errors.append(f"missing frontmatter key: {key}")
    prose = _without_fenced_blocks(text)
    for label, pat in REQUIRED_SECTIONS:
        if not re.search(pat, prose):
            errors.append(f"missing required section: {label}")

    desc = fm.get("description", "")
    if desc and len(desc) > 60:
        warnings.append(f"description is {len(desc)} chars (>60 advisory; fine for a "
                        f"proposed slash-only skill, tighten before model-invocation)")

    for w in warnings:
        print(f"WARN: {w}")
    for e in errors:
        print(f"FAIL: {e}")
    if errors:
        return 1
    print("lint: PASS")
    return 0


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# A frontmatter scalar needs quoting when it carries any YAML-significant char:
# a colon (mapping ambiguity — the #1 break, e.g. "Do X: then Y"), a leading
# flow/indicator char ([ { etc.), '#' (comment), quotes, leading/trailing space.
_YAML_NEEDS_QUOTE = re.compile(r"""[:#\[\]{}&*!|>'"%@`]|^[\s\-?]|\s$""")
_YAML_RESERVED = {"true", "false", "null", "yes", "no", "on", "off", "~"}


def _yaml_scalar(v: str) -> str:
    """Render a value safe to splice into `key: <here>` frontmatter.

    A description/source containing ': ' (or '#', brackets, quotes …) otherwise
    produces invalid YAML that the lenient _frontmatter reader silently tolerates
    but PyYAML / a strict host rejects. json.dumps yields a double-quoted string
    that is a valid YAML double-quoted scalar (JSON strings ⊂ YAML), with
    ensure_ascii=False keeping em-dashes etc. literal."""
    if v == "":
        return ""
    if _YAML_NEEDS_QUOTE.search(v) or v.lower() in _YAML_RESERVED:
        return json.dumps(v, ensure_ascii=False)
    return v


def cmd_scaffold(args) -> int:
    tmpl_path = Path(__file__).resolve().parent.parent / "templates" / "learned-skill.template.md"
    tmpl = tmpl_path.read_text(encoding="utf-8")
    name = _slug(args.name)
    learned_at = args.learned_at or datetime.date.today().isoformat()
    filled = (
        tmpl.replace("{{NAME}}", name)
        .replace("{{DESCRIPTION}}", _yaml_scalar(args.desc))
        .replace("{{SOURCE}}", _yaml_scalar(args.source))
        .replace("{{LEARNED_AT}}", learned_at)
        .replace("{{WHEN_TO_USE}}", args.when or "TODO: trigger conditions.")
        .replace("{{PROCEDURE}}", args.proc or "TODO: literal steps (exact commands).")
        .replace("{{PITFALLS}}", args.pitfalls or "TODO: known failure modes.")
        .replace("{{VERIFICATION}}", args.verify or "TODO: how to confirm it worked.")
        .replace("{{RATIONALE}}", args.rationale or "TODO: why this earns a skill.")
        .replace("{{REQUIRES_TOOLS}}", _yaml_scalar(getattr(args, "requires_tools", "") or ""))
    )
    out = Path(args.out) if args.out else Path("skills") / name / "SKILL.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(filled, encoding="utf-8")
    print(f"scaffolded: {out}")
    return 0


# -------------------------- frontmatter rewrite -----------------------------

def _rewrite_frontmatter(path: Path, updates: dict[str, str]) -> dict[str, str]:
    """Update/insert `key: value` pairs in a SKILL.md frontmatter block, preserving
    body and key order. Returns the merged frontmatter. Raises if no block.

    EOL-safe (adversarial-review bug): the body (`rest`), opening (`head`) and closing
    (`close`) fences are written back byte-for-byte, and the frontmatter region is
    rejoined with the file's OWN line ending — so a CRLF file is not silently
    flattened to LF. Critically we read AND write with newline='' to disable Python's
    universal-newline translation, which would otherwise erase every \\r before we
    even see it."""
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    m = re.match(r"^(---[ \t]*\r?\n)(.*?)(\r?\n---[ \t]*\r?\n)(.*)$", text, re.DOTALL)
    if not m:
        raise ValueError(f"{path}: no frontmatter block")
    head, fm_body, close, rest = m.groups()
    eol = "\r\n" if "\r\n" in head else "\n"
    merged = _frontmatter(text)
    remaining = dict(updates)
    out_lines = []
    for raw in fm_body.split("\n"):
        line = raw[:-1] if raw.endswith("\r") else raw   # normalize, re-add eol below
        key = line.partition(":")[0].strip() if ":" in line else None
        if key and key in remaining:
            out_lines.append(f"{key}: {remaining[key]}")
            merged[key] = str(remaining.pop(key))
        else:
            out_lines.append(line)
    for key, val in remaining.items():
        out_lines.append(f"{key}: {val}")
        merged[key] = str(val)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(head + eol.join(out_lines) + close + rest)
    return merged


def _skill_path(skills_dir: str, name: str) -> Path:
    return Path(skills_dir) / _slug(name) / "SKILL.md"


def cmd_promote(args) -> int:
    """Telemetry-gated promotion: proposed -> trusted (model-invocable) iff the skill
    has >= N consecutive successful uses with no trailing abort, AND it lints clean.
    Refuses otherwise. This is the closed gate that makes 'born untrusted' real —
    the verifier (this command, reading telemetry) is SEPARATE from the generator
    (accumulated usage)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import telemetry  # noqa: E402

    path = _skill_path(args.skills_dir, args.name)
    if not path.is_file():
        print(f"FAIL: no such skill: {path}")
        return 1
    fm = _frontmatter(path.read_text(encoding="utf-8"))
    status = fm.get("status", "")
    # Only 'proposed' is promotable. A 'stale' skill must be re-/learned first (which
    # refreshes its source + resets status to proposed) — promoting a stale skill on
    # residual telemetry would ship an out-of-date procedure (adversarial-review:
    # contradicted SKILL.md's "only after a re-/learn").
    if status != "proposed":
        print(f"FAIL: status is {status!r}, expected 'proposed'."
              + (" Re-/learn the stale skill first." if status == "stale" else ""))
        return 1

    stats = telemetry.compute_stats(manual_only=args.manual_only).get(_slug(args.name), {})
    hits = stats.get("consecutive_hits", 0)
    aborts = stats.get("consecutive_aborts", 0)
    total_hits = stats.get("hits", 0)
    # Check BOTH totals and streak on purpose: total_hits>=N proves enough lifetime
    # confidence; consecutive_hits>=N + aborts==0 proves the RECENT run is clean. A
    # skill with 10 old hits then a fresh abort fails the streak check even though its
    # total is high — recency must hold, not just volume.
    if total_hits < args.min_successes or hits < args.min_successes or aborts > 0:
        print(f"REFUSED: need >= {args.min_successes} consecutive successful uses with no "
              f"trailing abort; have hits={total_hits} streak_hits={hits} streak_aborts={aborts}."
              + ("  (counting manual records only)" if args.manual_only else ""))
        print("Record real uses first: telemetry.py record --skill "
              f"{_slug(args.name)} --outcome hit   (or scan a transcript).")
        return 1

    # Must lint clean before it earns model-invocation.
    lint_code, lint_out = _capture(lambda: cmd_lint(argparse.Namespace(file=str(path))))
    if lint_code != 0:
        print("REFUSED: skill does not pass lint:\n" + lint_out)
        return 1

    merged = _rewrite_frontmatter(path, {
        "status": "trusted",
        "disable-model-invocation": "false",
        "promoted_at": datetime.date.today().isoformat(),
        "promoted_after_hits": str(total_hits),
    })
    print(f"PROMOTED {_slug(args.name)} -> trusted (model-invocable). "
          f"hits={total_hits}, streak={hits}.")
    return 0


def cmd_demote(args) -> int:
    """trusted -> proposed (revoke model-invocation). For a skill telemetry has
    flagged with consecutive aborts, or a manual revoke."""
    path = _skill_path(args.skills_dir, args.name)
    if not path.is_file():
        print(f"FAIL: no such skill: {path}")
        return 1
    _rewrite_frontmatter(path, {
        "status": "proposed",
        "disable-model-invocation": "true",
        "demoted_at": datetime.date.today().isoformat(),
        "demote_reason": args.reason or "manual revoke",
    })
    print(f"DEMOTED {_slug(args.name)} -> proposed (slash-only). reason: {args.reason or 'manual revoke'}")
    return 0


def _git(root: Path, *a: str) -> tuple[str, int]:
    p = subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True)
    return p.stdout.strip(), p.returncode


def _source_freshness(source: str, learned_at: str, root: Path, max_age_days: int) -> tuple[str, str]:
    """Return (verdict, reason). verdict in {fresh, stale, recheck, unknown}.
    - repo path: stale iff commits touched it after learned_at.
    - URL: recheck iff older than max_age_days (stdlib can't fetch — agent re-WebFetches).
    - other (session:/described): recheck on age only."""
    src = source.strip()
    is_url = src.startswith(("http://", "https://"))
    # Strip a "session:..." or trailing "(focus ...)" note to a bare path.
    path_candidate = re.split(r"\s*\(", src)[0].strip()
    local = (root / path_candidate)
    if not is_url and path_candidate and local.exists():
        out, rc = _git(root, "log", "--oneline", f"--since={learned_at}", "--", path_candidate)
        if rc != 0:
            # A failed git log (not a repo / bad ref) must NOT be reported as an
            # authoritative "fresh" — that would silently vouch for an unchecked
            # source (adversarial-review honesty gap).
            return "unknown", f"git log failed (rc={rc}) for {path_candidate} — cannot verify freshness"
        if out.strip():
            n = len(out.strip().splitlines())
            return "stale", f"{n} commit(s) touched {path_candidate} since {learned_at}"
        return "fresh", f"no commits to {path_candidate} since {learned_at}"
    # age-based recheck for URLs / described / session sources
    try:
        la = datetime.date.fromisoformat((learned_at or "")[:10])
        age = (datetime.date.today() - la).days
    except ValueError:
        return "unknown", "no/invalid learned_at"
    if age > max_age_days:
        kind = "URL" if is_url else "non-code source"
        return "recheck", f"{kind} {age}d old (>{max_age_days}) — re-fetch {src} and re-/learn if changed"
    return "fresh", f"{age}d old (<= {max_age_days})"


def cmd_staleness(args) -> int:
    """Per learned-skill source freshness. Mirrors wiki-refresh's honest is_stale:
    git-truth for repo paths, age-flag for URLs (stdlib can't fetch)."""
    skills_dir = Path(args.skills_dir)
    root = Path(args.root).resolve()
    rows = []
    for sm in sorted(skills_dir.glob("*/SKILL.md")):
        try:
            fm = _frontmatter(sm.read_text(encoding="utf-8", errors="replace"))
            if fm.get("status") not in ("proposed", "trusted", "stale"):
                continue
            source = fm.get("source", "")
            if not source:
                continue
            verdict, reason = _source_freshness(source, fm.get("learned_at", ""), root, args.max_age_days)
            rows.append((sm.parent.name, verdict, reason, sm))
            mark = {"fresh": "  ok ", "stale": "STALE", "recheck": "CHECK", "unknown": " ??  "}[verdict]
            print(f"[{mark}] {sm.parent.name}: {reason}")
            if args.apply and verdict == "stale" and fm.get("status") != "stale":
                # A stale skill must not keep auto-firing: a promoted (trusted)
                # skill carries disable-model-invocation:false, so marking it stale
                # without re-disabling would leave a drifted skill model-invocable.
                _rewrite_frontmatter(sm, {"status": "stale",
                                          "disable-model-invocation": "true"})
                print(f"         -> marked status: stale (model-invocation disabled)")
        except (OSError, ValueError) as e:
            print(f"[ERR ] {sm.parent.name}: could not check ({e})")
    if not rows:
        print("(no learned skills with a source: field)")
    return 0


# -------------------------- #1 conditional activation -----------------------

def _requires_tool_names(requires: str) -> list[str]:
    """Parse the frontmatter forms used in the catalog.

    This intentionally handles both YAML's inline list (`[Read, Edit]`) and the
    historical comma scalar (`Read, Edit`) without pulling in a YAML dependency.
    """
    value = (requires or "").strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    out = []
    for raw in value.split(","):
        tool = raw.strip().strip("'\"")
        if tool:
            out.append(tool)
    return out


def _missing_tools(requires: str) -> list[str]:
    """Return the external CLI tools a skill needs that are NOT on PATH. Harness tools
    (Bash/Read/...) are assumed present and skipped."""
    out = []
    for tool in _requires_tool_names(requires):
        if not tool or tool.lower() in _HARNESS_TOOLS:
            continue
        if shutil.which(tool) is None:
            out.append(tool)
    return out


def cmd_check_tools(args) -> int:
    """Check a learned skill's `requires_tools:` against this environment. Advisory —
    Claude Code has no native requires_tools hiding, so this surfaces a skill that
    would misfire here (its CLI deps are absent) rather than hard-blocking it."""
    path = _skill_path(args.skills_dir, args.name)
    if not path.is_file():
        print(f"FAIL: no such skill: {path}")
        return 1
    fm = _frontmatter(path.read_text(encoding="utf-8"))
    requires = fm.get("requires_tools", "")
    if not requires:
        print(f"{_slug(args.name)}: declares no requires_tools — always available.")
        return 0
    missing = _missing_tools(requires)
    if missing:
        print(f"{_slug(args.name)}: MISSING tools {missing} — would misfire here. "
              f"Install them, or don't rely on this skill in this environment.")
        return 3
    print(f"{_slug(args.name)}: all required tools present ({requires}).")
    return 0


# -------------------------- #2 refinement loop ------------------------------

def cmd_refine(args) -> int:
    """Read-only refinement BRIEF: the skill body + its recent abort evidence, for the
    agent to read and propose a patch. The agent is the loop's generator; `learn.py
    patch` (write-gate + lint) is the SEPARATE verifier. Improve a failing skill instead
    of only retiring it (demote)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import telemetry  # noqa: E402
    path = _skill_path(args.skills_dir, args.name)
    if not path.is_file():
        print(f"FAIL: no such skill: {path}")
        return 1
    active_records = telemetry._post_checkpoint_records(
        False, _slug(args.name)).get(_slug(args.name), [])
    aborts = [r for r in active_records
              if r.get("outcome") == "abort"]
    print(f"=== REFINEMENT BRIEF: {_slug(args.name)} ===")
    print(f"aborts on record (post-checkpoint): "
          f"{telemetry.compute_stats().get(_slug(args.name), {}).get('aborts', 0)}")
    recent = aborts[-5:]
    for r in recent:
        causal_status = r.get("causal_status") or "unknown"
        print(f"  - [{r.get('ts','?')}] {r.get('note','(no note)')}")
        print(f"    verifier_cause: {r.get('verifier_cause') or '(not recorded)'}")
        print(f"    causal_status: {causal_status}")
        print(f"    mechanism: {r.get('mechanism') or '(not recorded)'}")
        print(f"    evidence_ref: {r.get('evidence_ref') or '(not recorded)'}")
    print("\n--- current SKILL.md ---")
    print(path.read_text(encoding="utf-8"))
    print("\n--- next steps ---")
    statuses = {r.get("causal_status") or "unknown" for r in recent}
    if "skill-caused" in statuses:
        print("Confirmed skill-caused evidence exists. Propose a targeted fix that preserves passing behavior:")
        print(f"  learn.py patch --name {_slug(args.name)} --old '<exact text>' "
              f"--new '<fix>' --rationale '<why, with because/so that>' "
              f"--held-in-cmd '<fails before; passes after>' "
              f"--held-out-cmd '<passes before and after>'")
        print("patch is gated by write-gate, behavioral baselines, lint, and post-patch")
        print("held-in/held-out checks; success resets status and checkpoints telemetry.")
    elif statuses and statuses <= {"task-difficulty", "model-capability"}:
        print("NON-ADDRESSABLE: recorded failures are exclusively task-difficulty/model-capability.")
        print("Do not patch the skill from this evidence; change the task route or executor instead.")
    else:
        print("UNCONFIRMED: no recorded abort is confirmed skill-caused.")
        print("Collect verifier cause, mechanism, and evidence before proposing a skill patch.")
    return 0


def _gate_process_backend() -> str | None:
    """Return a write-denying, no-fork gate backend or None to fail closed.

    A process group alone is insufficient: a hostile gate can call ``setsid``
    and mutate the skill after its direct parent exits.  The macOS sandbox
    denies all writes outside a private temp root and denies process creation;
    other hosts refuse this patch route until they have an equivalent backend.
    """
    if (os.name != "posix" or not hasattr(os, "killpg")
            or sys.platform != "darwin" or not shutil.which("sandbox-exec")):
        return None
    profile = "(version 1)(deny default)(allow process*)(allow file-read*)(deny process-fork)"
    try:
        probe = subprocess.run(
            ["sandbox-exec", "-p", profile, "/usr/bin/true"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=2, check=False,
            env={"PATH": os.defpath},
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if probe.returncode == 0:
        return "sandbox-exec-readonly-no-fork"
    return None


def _sandbox_gate_argv(backend: str, argv: list[str], writable_root: Path,
                       denied_read_paths: tuple[Path, ...] = ()) -> list[str]:
    if backend != "sandbox-exec-readonly-no-fork":
        raise ValueError(f"unsupported gate backend: {backend}")
    read_rule = "(allow file-read*)"
    if denied_read_paths:
        exclusions = "".join(
            "(require-not (literal " + json.dumps(os.path.realpath(path)) + "))"
            for path in denied_read_paths)
        read_rule = "(allow file-read* (require-all " + exclusions + "))"
    profile = (
        "(version 1)(deny default)(allow process*)" + read_rule +
        "(allow file-write* (subpath " + json.dumps(str(writable_root)) + "))"
        "(deny process-fork)(deny network*)"
    )
    return ["sandbox-exec", "-p", profile, *argv]


def _gate_group_exists(pgid: int) -> bool:
    if sys.platform == "darwin":
        try:
            check = subprocess.run(
                ["/bin/ps", "-axo", "pgid=,stat="], capture_output=True,
                text=True, timeout=1, check=False, env={"PATH": os.defpath},
            )
        except (OSError, subprocess.TimeoutExpired):
            return True
        if check.returncode != 0:
            return True
        for line in check.stdout.splitlines():
            fields = line.split()
            if len(fields) >= 2 and fields[0] == str(pgid):
                # An orphan zombie cannot execute or mutate anything and cannot
                # be reaped by this process; launchd owns its final collection.
                if not fields[1].startswith("Z"):
                    return True
        return False
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _signal_gate_group(pgid: int) -> bool:
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    return True


def _terminate_gate_group(proc: subprocess.Popen, *, wait_seconds: float = 1.0) -> bool:
    """SIGKILL a gate group, reap its leader, and verify no member remains."""
    pgid = proc.pid
    if not _signal_gate_group(pgid):
        return False
    try:
        proc.wait(timeout=wait_seconds)
    except subprocess.TimeoutExpired:
        return False
    deadline = time.monotonic() + wait_seconds
    while True:
        if not _gate_group_exists(pgid):
            return True
        if not _signal_gate_group(pgid):
            return False
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.01)


def _run_behavior_gate(command: str | list[str], *, timeout_seconds: float,
                       output_limit_bytes: int,
                       denied_read_paths: tuple[Path, ...] = (),
                       hide_output: bool = False) -> tuple[int | None, str]:
    """Run a shell-free gate with bounded wall time and surfaced output.

    None is a controlled execution refusal (invalid command, launch failure, or
    timeout, unsupported process backend, or output-cap breach), never a
    traceback. Output is retained in a fixed-size in-memory buffer. Crossing the
    cap terminates the process group; no unbounded spool is created.
    """
    if isinstance(command, list):
        argv = command.copy()
    else:
        try:
            argv = shlex.split(command)
        except ValueError as e:
            return None, "invalid hidden gate command" if hide_output else f"invalid command quoting: {e}"
    if not argv:
        return None, "empty command"
    if (not math.isfinite(timeout_seconds) or timeout_seconds <= 0
            or timeout_seconds > MAX_GATE_TIMEOUT_SECONDS):
        return None, ("gate timeout must be finite and > 0 seconds, with maximum "
                      f"{MAX_GATE_TIMEOUT_SECONDS:g} seconds")
    if output_limit_bytes <= 0:
        return None, "gate output limit must be > 0 bytes"
    backend = _gate_process_backend()
    if backend is None:
        return None, ("unsupported gate isolation backend: patch gates require a "
                      "write-denying, no-fork sandbox")
    with tempfile.TemporaryDirectory(prefix="brainer-learn-gate-") as temp:
        writable_root = Path(temp).resolve()
        (writable_root / "home").mkdir(mode=0o700)
        (writable_root / "tmp").mkdir(mode=0o700)
        execution_argv = (_sandbox_gate_argv(backend, argv, writable_root,
                                             denied_read_paths)
                          if denied_read_paths else
                          _sandbox_gate_argv(backend, argv, writable_root))
        env = os.environ.copy()
        env.update({
            "HOME": str(writable_root / "home"),
            "TMPDIR": str(writable_root / "tmp"),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        try:
            proc = subprocess.Popen(
                execution_argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                shell=False, start_new_session=True, bufsize=0, env=env)
        except (OSError, ValueError) as e:
            if hide_output:
                return None, "hidden gate could not execute"
            return None, f"could not execute {argv[0]!r}: {e}"

        captured = bytearray()
        output_exceeded = threading.Event()
        reader_error: list[str] = []

        def _drain() -> None:
            try:
                assert proc.stdout is not None
                while True:
                    chunk = proc.stdout.read(4096)
                    if not chunk:
                        return
                    if len(captured) <= output_limit_bytes:
                        remaining = output_limit_bytes + 1 - len(captured)
                        captured.extend(chunk[:remaining])
                        if len(captured) > output_limit_bytes:
                            output_exceeded.set()
                            _signal_gate_group(proc.pid)
            except OSError as e:
                reader_error.append(str(e))

        reader = threading.Thread(target=_drain, name="learn-gate-output", daemon=True)
        reader.start()
        deadline = time.monotonic() + timeout_seconds
        timed_out = False
        while proc.poll() is None:
            if output_exceeded.is_set():
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            try:
                proc.wait(timeout=min(0.02, remaining))
            except subprocess.TimeoutExpired:
                continue
        # Every path, including a clean direct-parent exit, tears down and then
        # verifies the entire original process group before accepting the result.
        group_clean = _terminate_gate_group(proc)
        reader.join(timeout=1.0)
        if reader.is_alive():
            group_clean = False
        if proc.stdout is not None:
            proc.stdout.close()
    raw = bytes(captured)
    text = raw[:output_limit_bytes].decode("utf-8", errors="replace").rstrip()
    if hide_output:
        text = ""
    if not group_clean:
        return None, "gate process group cleanup could not be verified"
    if output_exceeded.is_set():
        detail = f"output exceeded {output_limit_bytes} bytes; process group terminated"
        return None, detail + (("\n" + text) if text else "")
    if timed_out:
        detail = f"timed out after {timeout_seconds:g} seconds"
        return None, detail + (("\n" + text) if text else "")
    if reader_error:
        return None, ("could not read hidden gate output" if hide_output
                      else f"could not read gate output: {reader_error[0]}")
    return proc.returncode, text


@dataclass(frozen=True)
class _TargetSnapshot:
    """Leaf-path state that a behavior gate is forbidden to change."""
    file_type: int
    device: int
    inode: int
    links: int
    mode: int
    data: bytes


@dataclass(frozen=True)
class _GateRegistry:
    path: Path
    snapshot: _TargetSnapshot
    held_in: list[str]
    held_out: list[str]


_GATE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _strict_json_object(data: bytes) -> dict:
    def reject_constant(value: str):
        raise ValueError(f"non-finite JSON constant {value!r} is forbidden")

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r} is forbidden")
            result[key] = value
        return result

    return json.loads(data.decode("utf-8"), parse_constant=reject_constant,
                      object_pairs_hook=unique_object)


def _freeze_gate_registry_path(raw_path: str) -> Path:
    """Reject symlinked ancestry, then return the strict canonical path.

    This is a fail-closed preflight, not a claim of race-proof descriptor
    traversal. The registry's parent hierarchy must remain operator-controlled
    and stable for the duration of the patch command.
    """
    candidate = Path(os.path.abspath(raw_path))
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as e:
        raise ValueError(f"gate registry path cannot be resolved: {e}") from None
    # macOS exposes these filesystem roots as stable system aliases into
    # /private. They are the anchor, not an operator-controlled registry parent.
    root_aliases = ({Path("/var"), Path("/tmp"), Path("/etc")}
                    if sys.platform == "darwin" else set())
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current = current / part
        try:
            node = os.lstat(current)
        except OSError as e:
            raise ValueError(f"gate registry path component is unavailable: {current} ({e})") from None
        if stat.S_ISLNK(node.st_mode) and current not in root_aliases:
            raise ValueError(f"gate registry path contains a symlink component: {current}")
    return resolved


def _load_gate_registry(path: Path, held_in_id: str,
                        held_out_id: str) -> _GateRegistry:
    """Resolve opaque IDs from a guarded, shell-free JSON argv registry."""
    if held_in_id == held_out_id:
        raise ValueError("held-in and held-out gate IDs must be distinct")
    if not _GATE_ID_RE.fullmatch(held_in_id) or not _GATE_ID_RE.fullmatch(held_out_id):
        raise ValueError("gate IDs must be opaque ASCII identifiers")
    snapshot, fd = _open_regular_target(path)
    try:
        raw = _strict_json_object(snapshot.data)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as e:
        raise ValueError(f"gate registry is not valid JSON: {e}") from None
    finally:
        os.close(fd)
    if not isinstance(raw, dict):
        raise ValueError("gate registry must be a JSON object mapping IDs to argv")
    for gate_id, argv in raw.items():
        if not isinstance(gate_id, str) or not _GATE_ID_RE.fullmatch(gate_id):
            raise ValueError("gate registry contains a non-opaque ID")
        if (not isinstance(argv, list) or not argv
                or any(not isinstance(arg, str) or not arg or "\0" in arg for arg in argv)):
            raise ValueError(f"gate registry entry {gate_id!r} must be non-empty string argv")
    if held_in_id not in raw or held_out_id not in raw:
        raise ValueError("held-in or held-out gate ID is absent from the registry")
    return _GateRegistry(path=path, snapshot=snapshot,
                         held_in=raw[held_in_id].copy(),
                         held_out=raw[held_out_id].copy())


def _open_regular_target(path: Path) -> tuple[_TargetSnapshot, int]:
    """Snapshot a regular non-symlink target and keep its inode open.

    The caller closes the returned descriptor. Keeping it open across a gate
    prevents delete/recreate from hiding behind immediate inode-number reuse.
    """
    before = os.lstat(path)
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("target must be a regular non-symlink file")
    if before.st_nlink != 1:
        raise ValueError(f"target must not be hardlinked (st_nlink={before.st_nlink})")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        if (not stat.S_ISREG(opened.st_mode)
                or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)):
            raise ValueError("target changed while it was being opened")
        if opened.st_nlink != 1:
            raise ValueError(f"target must not be hardlinked (st_nlink={opened.st_nlink})")
        with os.fdopen(os.dup(fd), "rb") as handle:
            data = handle.read()
        return _TargetSnapshot(
            file_type=stat.S_IFMT(opened.st_mode),
            device=opened.st_dev,
            inode=opened.st_ino,
            links=opened.st_nlink,
            mode=stat.S_IMODE(opened.st_mode),
            data=data,
        ), fd
    except Exception:
        os.close(fd)
        raise


def _snapshot_regular_target(path: Path) -> _TargetSnapshot:
    snapshot, fd = _open_regular_target(path)
    os.close(fd)
    return snapshot


def _target_matches_snapshot(path: Path, expected: _TargetSnapshot) -> bool:
    try:
        actual, fd = _open_regular_target(path)
    except (OSError, ValueError):
        return False
    try:
        return actual == expected
    finally:
        os.close(fd)


def _restore_regular_target(path: Path, expected: _TargetSnapshot) -> None:
    """Restore leaf type + bytes + permission bits without following a symlink.

    A same-directory temporary regular file atomically replaces a file or
    symlink leaf. Empty directory replacements are removed without recursion;
    broader side effects are deliberately outside this helper's authority.
    """
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.restore-", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(expected.data)
            handle.flush()
            os.fsync(handle.fileno())
            os.fchmod(handle.fileno(), expected.mode)
        try:
            current = os.lstat(path)
        except FileNotFoundError:
            current = None
        if current is not None and stat.S_ISDIR(current.st_mode):
            os.rmdir(path)
        # os.replace replaces the leaf directory entry itself; a symlink target
        # is never opened or modified.
        os.replace(temp_path, path)
        restored = _snapshot_regular_target(path)
        if (restored.file_type != stat.S_IFREG or restored.mode != expected.mode
                or restored.data != expected.data):
            raise OSError("restored target failed type/content/permission verification")
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def _run_target_protected_gate(path: Path, command: str | list[str], **gate_options
                               ) -> tuple[int | None, str, bool, str | None]:
    """Run one gate while detecting and repairing any target-path mutation."""
    expected, guard_fd = _open_regular_target(path)
    try:
        code, output = _run_behavior_gate(command, **gate_options)
        if _target_matches_snapshot(path, expected):
            return code, output, False, None
        try:
            _restore_regular_target(path, expected)
        except OSError as e:
            return code, output, True, str(e)
        return code, output, True, None
    finally:
        os.close(guard_fd)


def _run_patch_gate(path: Path, command: str | list[str], registry: _GateRegistry | None,
                    **gate_options) -> tuple[int | None, str, bool, str | None]:
    """Run a target-protected gate and bind it to the frozen hidden registry."""
    if registry is not None and not _target_matches_snapshot(registry.path, registry.snapshot):
        return None, "hidden gate registry changed", False, None
    code, output, target_mutated, restore_error = _run_target_protected_gate(
        path, command,
        denied_read_paths=((registry.path,) if registry is not None else ()),
        hide_output=registry is not None,
        **gate_options)
    if registry is not None and not _target_matches_snapshot(registry.path, registry.snapshot):
        return None, "hidden gate registry changed", target_mutated, restore_error
    return code, output, target_mutated, restore_error


def cmd_patch(args) -> int:
    """Resolve an optional hidden-ID registry, then use the existing patch verifier."""
    registry_path = getattr(args, "gate_registry", None)
    held_in_id = getattr(args, "held_in_id", None)
    held_out_id = getattr(args, "held_out_id", None)
    hidden_values = (registry_path, held_in_id, held_out_id)
    if any(hidden_values):
        if not all(hidden_values):
            print("FAIL: hidden gates require --gate-registry, --held-in-id, and --held-out-id.")
            return 1
        if args.held_in_cmd is not None or args.held_out_cmd is not None:
            print("FAIL: choose hidden gate IDs or legacy raw commands, not both.")
            return 1
        try:
            registry = _load_gate_registry(_freeze_gate_registry_path(registry_path),
                                           held_in_id, held_out_id)
        except (OSError, ValueError) as e:
            print(f"FAIL: invalid hidden gate registry ({e}).")
            return 1
        args.held_in_cmd = registry.held_in
        args.held_out_cmd = registry.held_out
        args._gate_registry = registry
    else:
        if args.held_in_cmd is None or args.held_out_cmd is None:
            print("FAIL: provide both legacy raw gate commands or the hidden-ID registry mode.")
            return 1
        args._gate_registry = None
    return _cmd_patch(args)


def _cmd_patch(args) -> int:
    """Gated, exact-string patch to a learned skill's body — the refinement WRITE path.
    Gate: rationale clears write-gate; held-in fails and held-out passes before mutation;
    after patch + lint, both pass. Any failure restores regular type, bytes, and mode.
    On success, reset status->proposed and write a telemetry checkpoint."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import telemetry  # noqa: E402
    path = _skill_path(args.skills_dir, args.name)
    try:
        original_snapshot = _snapshot_regular_target(path)
    except (OSError, ValueError) as e:
        print(f"FAIL: target skill must be a regular non-symlink file: {path} ({e})")
        return 1
    original_bytes = original_snapshot.data
    try:
        original = original_bytes.decode("utf-8")
    except UnicodeDecodeError as e:
        print(f"FAIL: skill is not valid UTF-8 ({e}).")
        return 1
    if args.old not in original:
        print("FAIL: --old text not found verbatim in the skill (copy it exactly).")
        return 1
    if original.count(args.old) > 1:
        print("FAIL: --old text is not unique; add surrounding context to disambiguate.")
        return 1

    # GATE 1: rationale must clear write-gate. Learned-skill artifacts default to
    # this-skill scope (LEARNING_CONTRACT §1: tied to one skill's own tools/SKILL.md);
    # --scope lets the caller classify otherwise (e.g. a repo-wide lesson).
    rg = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[1].parent
                              / "write-gate" / "tools" / "write_gate.py"),
         "gate", "--kind", "sop", "--text", args.rationale,
         "--scope", getattr(args, "scope", "this-skill")],
        capture_output=True, text=True)
    if rg.returncode != 0:
        print("REFUSED: patch rationale did not clear write-gate (add the reason / evidence).")
        return 1

    # GATE 2: prove the baseline shape before touching the skill. A missing/broken
    # command is not evidence that held-in fails; it is a malformed gate.
    gate_options = {
        "timeout_seconds": args.gate_timeout_seconds,
        "output_limit_bytes": args.gate_output_limit_bytes,
    }
    registry = getattr(args, "_gate_registry", None)
    held_in_before, held_in_before_out, target_mutated, restore_error = (
        _run_patch_gate(path, args.held_in_cmd, registry, **gate_options))
    if target_mutated:
        if restore_error:
            print("REFUSED: held-in baseline mutated the target skill; "
                  f"rollback failed: {restore_error}")
            return 1
        print("REFUSED: held-in baseline mutated the target skill — restored exact original "
              "bytes/mode as a regular file.")
        return 1
    if held_in_before is None:
        print(f"REFUSED: held-in baseline could not run: {held_in_before_out}")
        return 1
    if held_in_before == 0:
        print("REFUSED: held-in baseline must fail before the patch, but it passed.")
        return 1
    held_out_before, held_out_before_out, target_mutated, restore_error = (
        _run_patch_gate(path, args.held_out_cmd, registry, **gate_options))
    if target_mutated:
        if restore_error:
            print("REFUSED: held-out baseline mutated the target skill; "
                  f"rollback failed: {restore_error}")
            return 1
        print("REFUSED: held-out baseline mutated the target skill — restored exact original "
              "bytes/mode as a regular file.")
        return 1
    if held_out_before is None:
        print(f"REFUSED: held-out baseline could not run: {held_out_before_out}")
        return 1
    if held_out_before != 0:
        suffix = f"\n{held_out_before_out}" if held_out_before_out else ""
        print("REFUSED: held-out baseline must pass before the patch, but it failed."
              + suffix)
        return 1

    patched = original.replace(args.old, args.new)
    checkpoint_id: int | None = None
    try:
        path.write_text(patched, encoding="utf-8")
        # GATE 3: syntax/house-standard validity.
        lint_code, lint_out = _capture(lambda: cmd_lint(argparse.Namespace(file=str(path))))
        if lint_code != 0:
            raise RuntimeError("patched skill fails lint\n" + lint_out.rstrip())

        # GATE 4: held-in improvement plus held-out non-regression.
        held_in_after, held_in_after_out, target_mutated, restore_error = (
            _run_patch_gate(path, args.held_in_cmd, registry, **gate_options))
        if target_mutated:
            detail = f"; gate restore failed: {restore_error}" if restore_error else ""
            raise RuntimeError("held-in gate mutated the target skill" + detail)
        if held_in_after != 0:
            detail = held_in_after_out or ("command could not run" if held_in_after is None else "")
            raise RuntimeError("held-in still fails after the patch" + (f"\n{detail}" if detail else ""))
        held_out_after, held_out_after_out, target_mutated, restore_error = (
            _run_patch_gate(path, args.held_out_cmd, registry, **gate_options))
        if target_mutated:
            detail = f"; gate restore failed: {restore_error}" if restore_error else ""
            raise RuntimeError("held-out gate mutated the target skill" + detail)
        if held_out_after != 0:
            detail = held_out_after_out or ("command could not run" if held_out_after is None else "")
            raise RuntimeError("held-out regressed after the patch" + (f"\n{detail}" if detail else ""))

        # A post-gate lint is intentionally redundant with byte invariance: it is
        # the artifact-level backstop before metadata/checkpoint acceptance.
        final_lint_code, final_lint_out = _capture(
            lambda: cmd_lint(argparse.Namespace(file=str(path))))
        if final_lint_code != 0:
            raise RuntimeError("final patched skill fails lint after behavior gates\n"
                               + final_lint_out.rstrip())

        # Close the acceptance boundary under open inode guards. Metadata rewrite
        # must keep the same regular, single-link inode; the checkpoint lands only
        # after that final artifact is linted and byte/mode/inode-verified.
        candidate_snapshot, candidate_guard = _open_regular_target(path)
        final_snapshot: _TargetSnapshot | None = None
        final_guard: int | None = None
        try:
            if not _target_matches_snapshot(path, candidate_snapshot):
                raise RuntimeError("target invariant changed before metadata rewrite")
            _rewrite_frontmatter(path, {
                "status": "proposed",
                "disable-model-invocation": "true",
                "refined_at": datetime.date.today().isoformat(),
            })
            final_snapshot, final_guard = _open_regular_target(path)
            if ((final_snapshot.file_type, final_snapshot.device, final_snapshot.inode,
                 final_snapshot.links, final_snapshot.mode)
                    != (candidate_snapshot.file_type, candidate_snapshot.device,
                        candidate_snapshot.inode, 1, candidate_snapshot.mode)):
                raise RuntimeError("target invariant changed during metadata rewrite")
            metadata_lint_code, metadata_lint_out = _capture(
                lambda: cmd_lint(argparse.Namespace(file=str(path))))
            if metadata_lint_code != 0:
                raise RuntimeError("metadata-updated skill fails final lint\n"
                                   + metadata_lint_out.rstrip())
            if not _target_matches_snapshot(path, final_snapshot):
                raise RuntimeError("target invariant changed before telemetry checkpoint")

            now = telemetry._now()
            checkpoint = {
                "skill": _slug(args.name), "ts": now, "recorded_at": now,
                "outcome": "checkpoint", "source": "manual",
                "session": os.environ.get("CLAUDE_SESSION_ID", ""),
                "note": f"refined: {args.rationale[:80]}",
            }
            checkpoint_id = telemetry._append(telemetry._store(), checkpoint)
            if checkpoint_id is None:
                raise RuntimeError("telemetry checkpoint failed")
            if not _target_matches_snapshot(path, final_snapshot):
                raise RuntimeError("target invariant changed across telemetry checkpoint")
        finally:
            if final_guard is not None:
                os.close(final_guard)
            os.close(candidate_guard)
        if final_snapshot is None or not _target_matches_snapshot(path, final_snapshot):
            raise RuntimeError("target invariant changed after telemetry checkpoint")
    except Exception as e:
        rollback_errors = []
        if checkpoint_id is not None:
            try:
                if not telemetry._delete_event(checkpoint_id):
                    rollback_errors.append("telemetry checkpoint rollback found no event")
            except Exception as rollback_error:
                rollback_errors.append(f"telemetry checkpoint rollback failed: {rollback_error}")
        try:
            _restore_regular_target(path, original_snapshot)
        except (OSError, ValueError) as rollback_error:
            rollback_errors.append(f"skill rollback failed: {rollback_error}")
        if rollback_errors:
            print(f"REFUSED: {e} — rollback incomplete: {'; '.join(rollback_errors)}")
        else:
            print(f"REFUSED: {e} — restored exact original bytes/mode as a regular file (skill); "
                  "telemetry append remained atomic.")
        return 1

    print(f"PATCHED {_slug(args.name)} → status proposed (re-earns trust). "
          f"telemetry checkpointed (abort streak cleared).")
    return 0


def _capture(fn):
    """Run fn(), capture its stdout + exit int."""
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = fn()
    return code, buf.getvalue()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="learn.py", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("dedup", help="Check a candidate against existing skills.")
    d.add_argument("--desc", required=True)
    d.add_argument("--body-file", default=None)
    d.add_argument("--skills-dir", default="skills")
    d.add_argument("--threshold", type=float, default=0.5)
    d.add_argument("--name", default=None, help="Candidate slug (excluded from self-match).")
    d.set_defaults(func=cmd_dedup)

    l = sub.add_parser("lint", help="Validate a learned SKILL.md.")
    l.add_argument("--file", required=True)
    l.set_defaults(func=cmd_lint)

    s = sub.add_parser("scaffold", help="Render a proposed SKILL.md from the template.")
    s.add_argument("--name", required=True)
    s.add_argument("--desc", required=True)
    s.add_argument("--source", required=True)
    s.add_argument("--when", default=None)
    s.add_argument("--proc", default=None)
    s.add_argument("--pitfalls", default=None)
    s.add_argument("--verify", default=None)
    s.add_argument("--rationale", default=None)
    s.add_argument("--requires-tools", default="", help="Comma list of external CLI tools the skill needs (e.g. gh,jq).")
    s.add_argument("--learned-at", default=None)
    s.add_argument("--out", default=None)
    s.set_defaults(func=cmd_scaffold)

    pr = sub.add_parser("promote", help="Telemetry-gated proposed -> trusted promotion.")
    pr.add_argument("--name", required=True)
    pr.add_argument("--skills-dir", default="skills")
    pr.add_argument("--min-successes", type=int, default=3)
    pr.add_argument("--manual-only", action="store_true")
    pr.set_defaults(func=cmd_promote)

    dm = sub.add_parser("demote", help="trusted -> proposed (revoke model-invocation).")
    dm.add_argument("--name", required=True)
    dm.add_argument("--skills-dir", default="skills")
    dm.add_argument("--reason", default=None)
    dm.set_defaults(func=cmd_demote)

    stale = sub.add_parser("staleness", help="Per learned-skill source freshness.")
    stale.add_argument("--skills-dir", default="skills")
    stale.add_argument("--root", default=".")
    stale.add_argument("--max-age-days", type=int, default=90)
    stale.add_argument("--apply", action="store_true")
    stale.set_defaults(func=cmd_staleness)

    ct = sub.add_parser("check-tools", help="Check a skill's requires_tools vs this env (advisory).")
    ct.add_argument("--name", required=True)
    ct.add_argument("--skills-dir", default="skills")
    ct.set_defaults(func=cmd_check_tools)

    rf = sub.add_parser("refine", help="Read-only refinement brief for a failing skill.")
    rf.add_argument("--name", required=True)
    rf.add_argument("--skills-dir", default="skills")
    rf.set_defaults(func=cmd_refine)

    pa = sub.add_parser("patch", help="Gated exact-string fix to a skill (refinement write path).")
    pa.add_argument("--name", required=True)
    pa.add_argument("--skills-dir", default="skills")
    pa.add_argument("--old", required=True)
    pa.add_argument("--new", required=True)
    pa.add_argument("--rationale", required=True)
    pa.add_argument("--held-in-cmd",
                    help="Legacy raw command that must fail before and pass after.")
    pa.add_argument("--held-out-cmd",
                    help="Legacy raw regression command that must always pass.")
    pa.add_argument("--gate-registry",
                    help="Regular single-link JSON file mapping opaque gate IDs to argv.")
    pa.add_argument("--held-in-id", help="Opaque held-in ID from --gate-registry.")
    pa.add_argument("--held-out-id", help="Distinct opaque held-out ID from --gate-registry.")
    pa.add_argument("--gate-timeout-seconds", type=float,
                    default=DEFAULT_GATE_TIMEOUT_SECONDS,
                    help=f"Per behavior-gate timeout (default {DEFAULT_GATE_TIMEOUT_SECONDS:g}s).")
    pa.add_argument("--gate-output-limit-bytes", type=int,
                    default=DEFAULT_GATE_OUTPUT_LIMIT_BYTES,
                    help="Maximum gate output read/surfaced per command "
                         f"(default {DEFAULT_GATE_OUTPUT_LIMIT_BYTES} bytes).")
    pa.add_argument("--scope", default="this-skill",
                     help="LEARNING_CONTRACT §1 SCOPE classification for the patch rationale "
                          "(default this-skill: a learned-skill artifact tied to one skill's "
                          "own tools/SKILL.md). Pass explicitly to override.")
    pa.set_defaults(func=cmd_patch)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
