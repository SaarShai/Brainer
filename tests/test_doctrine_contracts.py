"""Text-contract guard on the task-retrospective doctrine.

The external review fixed task-retrospective's doctrine: it is user-triggered,
supports both before-task arming and after-the-fact reconstruction, routes
durable writes to a ladder of project-owned targets through write-gate as a
*quality* filter (not the sole decider), allows concluding with no durable
lesson, and explicitly does NOT audit Brainer skill obedience, does NOT edit
canonical Brainer skills, and does NOT silently override write-gate.

These tests assert the REQUIRED ideas are present and the FORBIDDEN ones are
absent. Matching is on robust lowercased substrings / regex tuned to the
file's *actual* current wording (read from disk), not exact sentences — so the
test passes against the current correct doctrine while still failing if someone
reintroduces a forbidden claim or strips a required idea.

Frontmatter is parsed robustly: a sibling agent may quote the description as a
YAML scalar, so we separate the frontmatter from the body and assert against
each where the review specifies, rather than assuming raw unquoted text.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "task-retrospective" / "SKILL.md"


def _raw() -> str:
    return SKILL.read_text(encoding="utf-8")


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter, body). Both lowercased-safe; frontmatter '' if none.

    Robust to CRLF and to a missing closing fence (degrades to ('', text)).
    """
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if not m:
        return "", text
    return m.group(1), m.group(2)


_RAW = _raw()
_FM, _BODY = _split_frontmatter(_RAW)
_BODY_LC = _BODY.lower()
_FULL_LC = _RAW.lower()


def _present(*needles: str) -> list[str]:
    """Return the needles (lowercased) NOT found in the body."""
    return [n for n in needles if n.lower() not in _BODY_LC]


# --------------------------------------------------------------------------
# REQUIRED ideas
# --------------------------------------------------------------------------


def test_doctrine_is_user_triggered():
    # Header: "task-retrospective — user-triggered task audit mode";
    # also reinforced as "user-triggered project-learning ritual".
    assert "user-triggered" in _BODY_LC, "doctrine must state it is user-triggered"


def test_supports_before_task_arming_and_after_the_fact_fallback():
    # Before-task arming.
    assert re.search(r"ideally before the task", _BODY_LC), (
        "missing before-task arming language"
    )
    assert "arm" in _BODY_LC, "missing arm phase"
    # After-the-fact fallback / reconstruction.
    assert "after-the-fact" in _BODY_LC, "missing after-the-fact fallback"
    assert "reconstruct" in _BODY_LC, "missing after-the-fact reconstruction"


def test_lists_valid_project_learning_write_targets():
    # The narrowest-target ladder: no-write, wiki/project memory, SOP,
    # checklist, project-specific skill, project instructions (AGENTS/CLAUDE/GEMINI).
    missing = _present(
        "no durable write",        # the "write nothing" option
        "project memory",
        "sop",
        "checklist",
        "project-specific skill",
    )
    assert not missing, f"write-target ladder missing ideas: {missing}"
    # Project instructions as a broad-rule-only target.
    assert ("agents.md" in _BODY_LC) or ("project instructions" in _BODY_LC), (
        "missing project-instructions write target"
    )


def test_write_gate_is_a_quality_gate_not_sole_decider():
    assert "write-gate" in _BODY_LC, "write-gate must be referenced"
    # write-gate scoped to candidate/content QUALITY...
    assert ("content-quality" in _BODY_LC) or ("candidate quality" in _BODY_LC), (
        "write-gate must be framed as a content/candidate quality filter"
    )
    # ...while task-retrospective owns the routing/relevance decisions (not solely write-gate).
    assert "task-retrospective owns" in _BODY_LC, (
        "doctrine must keep routing/relevance ownership with task-retrospective, "
        "not delegate the whole decision to write-gate"
    )


def test_allows_no_durable_lesson_found():
    assert "no durable" in _BODY_LC and "lesson found" in _BODY_LC, (
        "doctrine must allow concluding with no durable lesson found"
    )


# --------------------------------------------------------------------------
# FORBIDDEN claims
# --------------------------------------------------------------------------


def test_does_not_claim_to_audit_brainer_skill_obedience():
    # The correct doctrine explicitly NEGATES this. Assert the negation exists...
    assert "does not audit brainer skill obedience" in _FULL_LC or (
        "do not audit brainer skill obedience" in _BODY_LC
    ), "doctrine must explicitly disclaim auditing Brainer skill obedience"

    # ...and that no AFFIRMATIVE claim to audit Brainer obedience is present.
    affirmative = [
        r"audits brainer skill obedience",
        r"audit brainer skill obedience for",
        r"track brainer skill usage",
        r"this mode audits brainer",
    ]
    hits = [p for p in affirmative if re.search(p, _BODY_LC)]
    assert not hits, f"forbidden affirmative Brainer-audit claim(s): {hits}"


def test_does_not_claim_to_edit_canonical_brainer_skills():
    # Negation present.
    assert "does not edit canonical brainer skills" in _FULL_LC or (
        "do not edit canonical brainer skills" in _BODY_LC
    ), "doctrine must disclaim editing canonical Brainer skills"
    assert "canonical brainer skill updates are not on this ladder" in _BODY_LC, (
        "canonical Brainer edits must be excluded from the write-target ladder"
    )

    # No affirmative permission to edit/update canonical Brainer skills.
    affirmative = [
        r"edit canonical brainer skills to",
        r"update canonical brainer skills",
        r"may edit canonical brainer skills",
        r"harvest .*lessons into canonical skills",  # the explicitly-forbidden auto-harvest
    ]
    hits = []
    for p in affirmative:
        for mt in re.finditer(p, _BODY_LC):
            # Allow the negated form ("must not ... harvest ... into canonical skills").
            window = _BODY_LC[max(0, mt.start() - 40): mt.start()]
            if re.search(r"\b(not|never|must not|do not|does not)\b", window):
                continue
            hits.append(mt.group(0))
    assert not hits, f"forbidden affirmative canonical-edit claim(s): {hits}"


def test_does_not_permit_silent_write_gate_override():
    # The explicit prohibition must be present.
    assert "do not silently override write-gate" in _BODY_LC, (
        "doctrine must forbid silently overriding write-gate"
    )
    # Overrides must be user-directed, with no agent-only override.
    assert "no agent-only override" in _BODY_LC, (
        "doctrine must state there is no agent-only write-gate override"
    )
    # No language permitting a silent / automatic override.
    forbidden = [
        r"silently override write-gate",  # only valid when preceded by "do not"
        r"automatically override write-gate",
        r"agent may override write-gate",
    ]
    hits = []
    for p in forbidden:
        for mt in re.finditer(p, _BODY_LC):
            window = _BODY_LC[max(0, mt.start() - 30): mt.start()]
            if re.search(r"\b(not|never|no)\b", window):
                continue
            hits.append(mt.group(0))
    assert not hits, f"forbidden silent-override language: {hits}"


def test_frontmatter_parsed_robustly_and_carries_user_trigger_disclaimers():
    """Frontmatter may be a quoted YAML scalar; parse robustly and check ideas.

    We do not assume raw text — we lowercase the separated frontmatter block
    and assert the doctrine's load-bearing ideas survive there too.
    """
    assert _FM, "task-retrospective SKILL.md has no parseable YAML frontmatter"
    fm_lc = _FM.lower()
    assert "explicitly arms task audit mode" in fm_lc, (
        "frontmatter must keep the explicit user-trigger framing"
    )
    assert "never audits brainer skill obedience" in fm_lc, (
        "frontmatter must disclaim auditing Brainer skill obedience"
    )
    assert "edits canonical brainer skills" in fm_lc, (
        "frontmatter must disclaim editing canonical Brainer skills"
    )
