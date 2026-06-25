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
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Harness tools are always present (the agent runtime provides them); only external
# CLI binaries named in `requires_tools:` are checked with shutil.which.
_HARNESS_TOOLS = {"bash", "read", "write", "edit", "grep", "glob", "webfetch", "websearch", "task"}

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
    ("Verification", r"(?im)^#{1,3}\s+verification\b"),
]


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
    for label, pat in REQUIRED_SECTIONS:
        if not re.search(pat, text):
            errors.append(f"missing required section: {label}")
    if not re.search(r"(?im)^#{1,3}\s+pitfalls\b", text):
        warnings.append("no Pitfalls section (recommended)")

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

def _missing_tools(requires: str) -> list[str]:
    """Return the external CLI tools a skill needs that are NOT on PATH. Harness tools
    (Bash/Read/...) are assumed present and skipped."""
    out = []
    for raw in (requires or "").split(","):
        tool = raw.strip()
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
    aborts = [r for r in telemetry._records(False, _slug(args.name))
              if r.get("outcome") == "abort"]
    print(f"=== REFINEMENT BRIEF: {_slug(args.name)} ===")
    print(f"aborts on record (post-checkpoint): "
          f"{telemetry.compute_stats().get(_slug(args.name), {}).get('aborts', 0)}")
    for r in aborts[-5:]:
        print(f"  - [{r.get('ts','?')}] {r.get('note','(no note)')}")
    print("\n--- current SKILL.md ---")
    print(path.read_text(encoding="utf-8"))
    print("\n--- next steps ---")
    print("Diagnose why it aborted, then propose a targeted fix:")
    print(f"  learn.py patch --name {_slug(args.name)} --old '<exact text>' "
          f"--new '<fix>' --rationale '<why, with because/so that>'")
    print("patch is gated (write-gate + lint), resets status->proposed, and checkpoints")
    print("telemetry so the skill re-earns trust from a clean slate.")
    return 0


def cmd_patch(args) -> int:
    """Gated, exact-string patch to a learned skill's body — the refinement WRITE path.
    Gate: the rationale must clear write-gate AND the patched file must lint clean (else
    revert). On success: stamp refined_at, reset status->proposed (re-earn trust), and
    write a telemetry checkpoint (clean-slate the abort streak)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import telemetry  # noqa: E402
    path = _skill_path(args.skills_dir, args.name)
    if not path.is_file():
        print(f"FAIL: no such skill: {path}")
        return 1
    original = path.read_text(encoding="utf-8")
    if args.old not in original:
        print("FAIL: --old text not found verbatim in the skill (copy it exactly).")
        return 1
    if original.count(args.old) > 1:
        print("FAIL: --old text is not unique; add surrounding context to disambiguate.")
        return 1

    # GATE 1: rationale must clear write-gate.
    rg = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[1].parent
                              / "write-gate" / "tools" / "write_gate.py"),
         "gate", "--kind", "sop", "--text", args.rationale],
        capture_output=True, text=True)
    if rg.returncode != 0:
        print("REFUSED: patch rationale did not clear write-gate (add the reason / evidence).")
        return 1

    patched = original.replace(args.old, args.new)
    path.write_text(patched, encoding="utf-8")
    # GATE 2: patched file must lint clean, else revert.
    lint_code, lint_out = _capture(lambda: cmd_lint(argparse.Namespace(file=str(path))))
    if lint_code != 0:
        path.write_text(original, encoding="utf-8")  # revert
        print("REFUSED: patched skill fails lint — reverted.\n" + lint_out)
        return 1

    _rewrite_frontmatter(path, {
        "status": "proposed",
        "disable-model-invocation": "true",
        "refined_at": datetime.date.today().isoformat(),
    })
    telemetry.main(["record", "--skill", _slug(args.name), "--outcome", "checkpoint",
                    "--note", f"refined: {args.rationale[:80]}"])
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
    pa.set_defaults(func=cmd_patch)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
