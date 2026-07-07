#!/usr/bin/env python3
"""Lint SKILL.md files for agentskills.io schema compliance.

Checks:
  - YAML frontmatter present and parses
  - `name` and `description` required
  - `description` ≤ 1536 chars (agentskills.io budget)
  - trigger keywords in first sentence of description
  - body has at least one section (## heading)
  - if EVAL.md is referenced, file exists
  - premortem contract (LEARNING_CONTRACT.md §8): a skill shipping a machine
    gate (tools/*.py or drift_probes.json) declares its failure modes and
    ships a negative test. WARN by default; --strict promotes to hard issues.
    The failure-modes check requires a real '## Failure modes' section (all
    three canonical bullet stems, each with real content, not just the word
    "premortem" anywhere).
    The negative-test check is static text analysis and cannot prove
    execution, so it is split into two honest tiers:
      Tier 1 (static, tightened): comment lines and string literals are
      stripped before scanning for assertion tokens, so a candidate whose
      only "assertion" lives inside a `#`-comment or a docstring no longer
      passes — it must contain a live (non-comment, non-string) assertion
      token. This does NOT catch `if False: assert ...` (unreachable code
      with a live token) — that hole is accepted at this tier because static
      analysis cannot decide reachability in general; Tier 2 is the backstop.
      Tier 2 (wiring): the negative-test file must be EXECUTED somewhere the
      suite actually runs — registered in scripts/run_all_tests.sh
      UNIT_TESTS, or invoked by the skill's own tools/test.sh (grepped for
      the filename). A test that satisfies Tier 1 but is never wired into
      anything that runs it is theater: --strict promotes this to a hard
      issue; default mode warns. Runtime proof that the assertion actually
      trips lives in the test itself when run, plus the e3/verify layer
      (LEARNING_CONTRACT.md §5, verifier independence) — not in this lint.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

try:  # PyYAML is optional — keep the "dependency-free" promise when absent.
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - exercised only on hosts without PyYAML
    yaml = None  # type: ignore

DESC_MAX = 1536
# Descriptions are ALWAYS resident in agent context (per SKILLS_INDEX.md) — a
# long one is a permanent token tax across every host and consumer repo. The
# 2026-07 pass compressed the 9 worst (62-153 words) to <=~90; warn past 100.
DESC_MAX_WORDS = 100
REQUIRED_FIELDS = ("name", "description")
TRIGGER_HINTS = (
    "use when", "use on", "use at", "use for", "use whenever", "use before", "use after", "use opt-in",
    "trigger", "fires on", "run on", "applies when",
)

# LEARNING_CONTRACT.md §8 — premortem is part of shipping: a skill that ships
# a machine gate (tools/*.py or drift_probes.json) must declare how it fails
# silently, and a gate that never tripped is unproven (§3, negative test
# first). NEGATIVE_TEST_HINTS is a content signal, not a filename convention —
# the file must actually assert a known-bad/reject/adversarial case, not just
# be named test*.
FAILURE_MODES_HEADING_RE = re.compile(r"^##\s*failure modes\b.*$", re.I | re.M)
# The three canonical premortem bullets (LEARNING_CONTRACT.md §8's own
# question set, restated as bolded stems in every real "## Failure modes"
# section written so far). A bare "premortem" keyword used to satisfy this
# check on its own — that's the theater hole: an EVAL.md containing only the
# word "premortem" passed with zero content. Each stem must now be followed by
# real prose (>=15 non-placeholder chars) inside the Failure modes section.
FAILURE_MODE_STEMS = (
    ("silent-failure", re.compile(r"silent[- ]failure", re.I)),
    ("rot-when-unwatched", re.compile(r"rot[- ]when[- ]unwatched", re.I)),
    ("no-hooks host", re.compile(r"no[- ]hooks?\s+host", re.I)),
)
PLACEHOLDER_RE = re.compile(
    r"^\s*(\.\.\.|to be filled( in)?( after.*)?|tbd|todo|n/?a)\W*\s*$", re.I
)
NEGATIVE_TEST_HINTS = (
    "reject", "adversarial", "known-bad", "known bad", "should_fail", "should fail",
    "must_fail", "must fail", "bad case", "bad_case", "negative test", "negative_test",
)


def _unquote(value: str) -> str:
    """Strip surrounding YAML double/single quotes and unescape `\\"`/`\\\\`.

    A value containing `: ` (colon-space) must ship as a quoted YAML scalar so
    real YAML parsers accept it; the hand-rolled `partition(":")` below would
    otherwise leak the surrounding quotes into the extracted value (and break
    the length / trigger-keyword checks). Normalize to the logical value here.
    """
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        inner = v[1:-1]
        if v[0] == '"':
            inner = inner.replace('\\"', '"').replace("\\\\", "\\")
        return inner
    return v


def parse_frontmatter(text: str) -> tuple[dict, str, str | None]:
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not m:
        return {}, text, None
    fm_block, body = m.group(1), m.group(2)
    fm: dict[str, str] = {}
    for line in fm_block.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        fm[k.strip()] = _unquote(v)
    return fm, body, fm_block


def _ships_machine_gate(skill_dir: Path) -> bool:
    """A skill ships a machine gate if it has tools/*.py or drift_probes.json."""
    if (skill_dir / "drift_probes.json").exists():
        return True
    tools_dir = skill_dir / "tools"
    if tools_dir.is_dir():
        return any(tools_dir.glob("*.py"))
    return False


def _section_body(text: str, heading_match: re.Match) -> str:
    """Slice the text from just after a heading match to the next `##` heading
    (or EOF), so stem-matching is confined to that section and can't be
    satisfied by unrelated prose elsewhere in the file."""
    start = heading_match.end()
    rest = text[start:]
    nxt = re.search(r"^##\s", rest, re.M)
    return rest[: nxt.start()] if nxt else rest


def _stem_has_content(section: str, stem_re: re.Pattern) -> bool:
    """A stem 'counts' only if, after the matched stem text on its bullet
    line, there are >=15 chars of non-placeholder content before the bullet
    ends (next `- ` at line-start, or section end)."""
    m = stem_re.search(section)
    if not m:
        return False
    tail = section[m.end():]
    # Bound to the rest of this bullet: up to the next top-level bullet start
    # or end of section.
    nxt_bullet = re.search(r"\n\s*-\s", tail)
    bullet_tail = tail[: nxt_bullet.start()] if nxt_bullet else tail
    # Strip markdown noise (bold markers, leading punctuation/dashes/colons)
    # that shouldn't count toward the content-length floor.
    cleaned = re.sub(r"[*_]", "", bullet_tail).strip(" \t\n:—-")
    if not cleaned:
        return False
    if PLACEHOLDER_RE.match(cleaned):
        return False
    return len(cleaned) >= 15


def _has_failure_modes_note(skill_dir: Path) -> bool:
    """§8: a declared failure-modes note. Requires a '## Failure modes'
    heading whose section body contains ALL THREE canonical bullet stems
    (silent-failure / rot-when-unwatched / no-hooks host, case-insensitive),
    each followed by >=15 chars of real (non-placeholder) content. A bare
    'premortem' keyword — the theater hole this replaces — no longer
    satisfies the check on its own."""
    for name in ("SKILL.md", "EVAL.md"):
        p = skill_dir / name
        if not p.exists():
            continue
        text = p.read_text()
        heading = FAILURE_MODES_HEADING_RE.search(text)
        if not heading:
            continue
        section = _section_body(text, heading)
        if all(_stem_has_content(section, stem_re) for _, stem_re in FAILURE_MODE_STEMS):
            return True
    return False


# §3 assertion-ish tokens: a candidate negative test must actually check
# something, not just narrate that it does. This is a static heuristic
# (grep-level content signal), not proof of execution — it cannot tell
# whether the assertion is ever reached, or whether the test is ever run.
# The e3/verify layer (LEARNING_CONTRACT.md §5, verifier independence) owns
# runtime proof; this check only gates whether a plausible artifact exists.
ASSERTION_TOKENS_RE = re.compile(
    r"\bassert\b|\bexit\s*2\b|\bexit\(2\)|\brc\s*=|\breturncode\b|\bFAIL\b",
)

# Recognizes a `#`-comment (shell or Python) or a quoted string literal
# ('...' / "..." / '''...''' / """...""") so both can be blanked out before
# the assertion-token scan. Order matters: triple-quoted strings first so a
# `#` inside a docstring doesn't get mistaken for a comment start, and the
# whole thing is one alternation so re.sub replaces non-overlapping spans
# left-to-right in a single pass.
_COMMENT_OR_STRING_RE = re.compile(
    r"""(?P<triple>'''(?:[^\\]|\\.)*?'''|\"\"\"(?:[^\\]|\\.)*?\"\"\")
      | (?P<str>'(?:[^'\\\n]|\\.)*'|"(?:[^"\\\n]|\\.)*")
      | (?P<comment>\#[^\n]*)""",
    re.VERBOSE | re.DOTALL,
)


def _strip_comments_and_strings(text: str) -> str:
    """Tier 1 fix (hole a): blank out `#` comments and string/docstring
    literals so an assertion token that only appears INSIDE a comment (e.g.
    `# assert gate.check(-1) is False`) or a string no longer counts as a
    live assertion. Each match is replaced by same-length whitespace (not
    deleted) so surrounding token boundaries / line numbers are preserved."""
    return _COMMENT_OR_STRING_RE.sub(lambda m: " " * len(m.group(0)), text)


def _has_negative_test(skill_dir: Path) -> bool:
    """§3: a negative-test artifact — tools/test*.py or test*.sh that BOTH (a)
    references a name from the skill's own tools/ (the gate it tests) and (b)
    contains an assertion-ish token (assert / exit 2 / rc= / returncode / FAIL
    check) in LIVE code — not inside a `#` comment or a string literal — and
    a known-bad/reject/adversarial content signal. This is a static heuristic
    on file content, not proof the test runs or that its assertions are ever
    reached (e.g. `if False: assert ...` still passes this tier — see
    _negative_test_is_wired for the execution-side backstop) — see
    ASSERTION_TOKENS_RE docstring / --help.
    """
    tools_dir = skill_dir / "tools"
    if not tools_dir.is_dir():
        return False
    candidates = list(tools_dir.glob("test*.py")) + list(tools_dir.glob("test*.sh"))
    if not candidates:
        return False
    # Gate module names this skill actually ships (excluding the tests
    # themselves) — what a real negative test must reference to prove it
    # exercises THIS skill's gate, not an unrelated file merely named test*.
    gate_stems = {
        f.stem for f in tools_dir.glob("*.py") if not f.name.startswith("test")
    } | {
        f.stem for f in tools_dir.glob("*.sh") if not f.name.startswith("test")
    }
    for f in candidates:
        text = f.read_text()
        text_lc = text.lower()
        if not any(h in text_lc for h in NEGATIVE_TEST_HINTS):
            continue
        # Tier 1: the assertion token must appear in LIVE code, i.e. survive
        # comment/string stripping — a token only ever seen inside a `#`
        # comment or a quoted string no longer satisfies this check.
        if not ASSERTION_TOKENS_RE.search(_strip_comments_and_strings(text)):
            continue
        if gate_stems and not any(stem.lower() in text_lc for stem in gate_stems):
            continue
        return True
    return False


def _negative_test_candidates(skill_dir: Path) -> list[Path]:
    """The same tools/test*.py|test*.sh candidate set _has_negative_test
    scans, exposed separately so the Tier 2 wiring check can ask "is THIS
    specific file ever executed" without re-deriving the glob."""
    tools_dir = skill_dir / "tools"
    if not tools_dir.is_dir():
        return []
    return list(tools_dir.glob("test*.py")) + list(tools_dir.glob("test*.sh"))


def _is_test_wired(skill_dir: Path, test_file: Path, repo_root: Path) -> bool:
    """Tier 2 (wiring): a negative-test artifact that passes Tier 1 is still
    theater if nothing in the suite ever runs it. Wired means ANY of:
      - registered by relative path in scripts/run_all_tests.sh's UNIT_TESTS
        array (the repo's own unit-test roster), or
      - the skill's own tools/test.sh greps for the filename (i.e. test.sh
        invokes it as part of the skill's self-test entrypoint), or
      - the file *is* tools/test.sh itself — that file is the thing
        run_all_tests.sh calls directly per-skill (e.g. `hook:<skill>`), so
        it is self-executing via the suite rather than needing to be listed.
    This cannot prove the run actually happens in CI, only that a real,
    grep-able wiring reference exists — same static-heuristic caveat as
    Tier 1.
    """
    if test_file.name == "test.sh":
        return True
    try:
        rel = test_file.relative_to(repo_root)
    except ValueError:
        rel = test_file
    rel_str = str(rel)
    run_all = repo_root / "scripts" / "run_all_tests.sh"
    if run_all.exists() and rel_str in run_all.read_text():
        return True
    own_test_sh = skill_dir / "tools" / "test.sh"
    if own_test_sh.exists() and own_test_sh != test_file:
        sh_text = own_test_sh.read_text()
        if test_file.name in sh_text or rel_str in sh_text:
            return True
    return False


def _unwired_negative_tests(skill_dir: Path, repo_root: Path) -> list[str]:
    """Tier 2 candidates that pass the Tier-1 content check but are wired
    nowhere the suite runs. Returns file names (for the warning message);
    empty if there is no such file, OR if no candidate passes Tier 1 at all
    (nothing to report — that's a Tier-1/§3 finding, not a wiring one)."""
    tools_dir = skill_dir / "tools"
    if not tools_dir.is_dir():
        return []
    gate_stems = {
        f.stem for f in tools_dir.glob("*.py") if not f.name.startswith("test")
    } | {
        f.stem for f in tools_dir.glob("*.sh") if not f.name.startswith("test")
    }
    unwired: list[str] = []
    for f in _negative_test_candidates(skill_dir):
        text = f.read_text()
        text_lc = text.lower()
        if not any(h in text_lc for h in NEGATIVE_TEST_HINTS):
            continue
        if not ASSERTION_TOKENS_RE.search(_strip_comments_and_strings(text)):
            continue
        if gate_stems and not any(stem.lower() in text_lc for stem in gate_stems):
            continue
        if not _is_test_wired(skill_dir, f, repo_root):
            unwired.append(f.name)
    return unwired


def lint_one(path: Path, strict: bool = False, repo_root: Path | None = None) -> tuple[list[str], list[str]]:
    issues: list[str] = []
    warnings: list[str] = []
    text = path.read_text()
    fm, body, fm_block = parse_frontmatter(text)
    if not fm:
        issues.append("missing YAML frontmatter")
        return issues, warnings
    # Strict YAML gate: when PyYAML is importable, the frontmatter MUST parse
    # with the SAME parser GitHub/agentskills.io use. This is the check the old
    # hand-rolled `partition(":")` could never do — it is why 7 SKILL.md files
    # with `: ` (colon-space) in an unquoted description shipped broken. Skipped
    # (with the dependency-free promise intact) only where PyYAML is absent.
    if yaml is not None and fm_block is not None:
        try:
            loaded = yaml.safe_load(fm_block)
        except yaml.YAMLError as exc:  # type: ignore[union-attr]
            first = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
            issues.append(f"frontmatter is not valid YAML (yaml.safe_load: {first})")
            return issues, warnings
        if not isinstance(loaded, dict):
            issues.append("frontmatter YAML did not parse to a mapping")
            return issues, warnings
    for k in REQUIRED_FIELDS:
        if k not in fm:
            issues.append(f"missing required field: {k}")
    desc = fm.get("description", "")
    if len(desc) > DESC_MAX:
        issues.append(f"description {len(desc)} chars > {DESC_MAX} cap")
    n_words = len(desc.split())
    if n_words > DESC_MAX_WORDS:
        issues.append(f"description {n_words} words > {DESC_MAX_WORDS} — "
                      "resident-context tax; move detail into the body")
    desc_lc = desc.lower()
    # Slash-only skills (`disable-model-invocation: true`) trigger on the literal
    # token, not description-matching — they don't need trigger keywords.
    slash_only = fm.get("disable-model-invocation", "").strip().lower() == "true"
    # Deprecation stubs ("DEPRECATED — use X. Do not use.") must NOT carry
    # trigger keywords — their whole point is to never fire (PROMPTER field
    # deploy 2026-06-12: linter demanded 'Use when' on do-not-use stubs).
    # Match the canonical stub SHAPE, not just a "DEPRECATED" prefix: the old
    # `startswith("DEPRECATED")` falsely exempted real skills like
    # "Deprecated-API scanner" (a live trigger that legitimately needs 'Use
    # when'). Require the do-not-use marker that only a real stub carries.
    deprecated = bool(re.match(r"\s*DEPRECATED\b.*\bdo not use\b", desc, re.I | re.S))
    if not slash_only and not deprecated and not any(h in desc_lc for h in TRIGGER_HINTS):
        issues.append("description should front-load trigger keywords (e.g. 'Use when...', 'Trigger on...')")
    # Section headings are recommended only for longer skill bodies. 40-line
    # floor: a ~30-line measured-tuned body (caveman-ultra) doesn't need nav,
    # and restructuring a measured artifact to satisfy lint inverts priorities.
    if "##" not in body and len(body.splitlines()) > 40:
        issues.append("body has no `## section` headings (long body benefits from sections)")
    # Premortem contract (LEARNING_CONTRACT.md §8): a skill shipping a machine
    # gate must declare its failure modes and ship a negative test. WARN by
    # default so the repo stays green; --strict promotes both to hard issues.
    skill_dir = path.parent
    if _ships_machine_gate(skill_dir):
        findings: list[str] = []
        if not _has_failure_modes_note(skill_dir):
            findings.append(
                "ships a machine gate (tools/*.py or drift_probes.json) but has no "
                "declared failure-modes note (a case-insensitive '## Failure modes' "
                "section covering all three canonical bullets — silent-failure / "
                "rot-when-unwatched / no-hooks host — each with real, non-placeholder "
                "content in SKILL.md or EVAL.md; a bare 'premortem' mention no longer "
                "counts) — see LEARNING_CONTRACT.md §8"
            )
        if not _has_negative_test(skill_dir):
            findings.append(
                "ships a machine gate (tools/*.py or drift_probes.json) but has no "
                "negative-test artifact (a tools/test*.py or test*.sh that both "
                "references one of this skill's own tools/ gate modules and contains "
                "a known-bad/reject/adversarial signal plus an assertion-ish token in "
                "LIVE code — assert/exit 2/rc=/returncode/FAIL, not inside a comment "
                "or string literal; a static heuristic, not proof of execution) — see "
                "LEARNING_CONTRACT.md §3"
            )
        elif repo_root is not None:
            # Tier 2 (wiring): only meaningful once a Tier-1-passing candidate
            # exists — a skill with no negative test at all already got the
            # §3 finding above; don't double-report.
            unwired = _unwired_negative_tests(skill_dir, repo_root)
            if unwired:
                findings.append(
                    "negative test exists but nothing runs it — a test that never "
                    "runs is theater ({}): not registered in scripts/run_all_tests.sh "
                    "UNIT_TESTS, and not invoked by this skill's own tools/test.sh — "
                    "see LEARNING_CONTRACT.md §3".format(", ".join(sorted(unwired)))
                )
        if strict:
            issues.extend(findings)
        else:
            warnings.extend(findings)
    return issues, warnings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="lint.py")
    parser.add_argument("files", nargs="*")
    parser.add_argument(
        "--strict", action="store_true",
        help="promote premortem-contract findings (LEARNING_CONTRACT.md §8) from "
             "warnings to hard issues. The negative-test check is static text "
             "analysis and cannot prove execution, so it runs in two tiers: "
             "Tier 1 (static, tightened) requires the test file to reference one "
             "of the skill's own tools/ gate modules AND contain an assertion-ish "
             "token (assert/exit 2/rc=/returncode/FAIL) in LIVE code — comments "
             "and string literals are stripped first, so a token only present "
             "inside a `#` comment no longer counts; `if False: assert ...` "
             "(unreachable but live) still passes Tier 1, that hole is accepted "
             "as statically undecidable. Tier 2 (wiring) additionally requires "
             "the test file to be registered in scripts/run_all_tests.sh "
             "UNIT_TESTS or invoked by the skill's own tools/test.sh — a test "
             "nothing runs is theater. The failure-modes check requires a real "
             "'## Failure modes' section with all three canonical bullets "
             "(silent-failure / rot-when-unwatched / no-hooks host) each "
             "carrying real content. None of this confirms the test actually "
             "runs in CI or that its assertion is ever reached — runtime proof "
             "belongs to the e3/verify layer (LEARNING_CONTRACT.md §5)",
    )
    args = parser.parse_args(argv[1:])
    if not args.files:
        print("usage: lint.py [--strict] <SKILL.md> [...]", file=sys.stderr)
        return 2
    # In CI the strict-YAML gate (lines ~76) is the whole point — silently
    # degrading to the dependency-free path there would let malformed frontmatter
    # ship. Fail loudly so a missing dep is fixed, not ignored.
    if os.environ.get("CI") and yaml is None:
        print("ERROR: PyYAML is required in CI for strict SKILL.md frontmatter "
              "validation, but it is not installed.", file=sys.stderr)
        return 2
    repo_root = Path(__file__).resolve().parent.parent
    rc = 0
    for arg in args.files:
        p = Path(arg)
        if not p.exists():
            print(f"{arg}: not found")
            rc = 1
            continue
        issues, warnings = lint_one(p, strict=args.strict, repo_root=repo_root)
        if issues:
            rc = 1
            print(f"{arg}: {len(issues)} issue(s)")
            for i in issues:
                print(f"  - {i}")
        elif not warnings:
            print(f"{arg}: ok")
        if warnings:
            print(f"{arg}: {len(warnings)} warning(s)")
            for w in warnings:
                print(f"  - [warn] {w}")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
