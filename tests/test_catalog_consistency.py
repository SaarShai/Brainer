"""Repo-integrity guards for the skills catalog.

Three invariants the external review called out:

1. Every skill directory under ``skills/`` that ships a ``SKILL.md`` is listed
   in ``skills/SKILLS_INDEX.md``.
2. Every skill linked from ``skills/SKILLS_INDEX.md`` exists on disk with a
   ``SKILL.md``.
3. The skill count is consistent between the index links and every host
   carrier's resident catalog block.

The carrier-side enumeration/parsing is NOT reinvented here: we import
``scripts/check_carrier_sync.py`` and reuse its ``discover_skills`` (filesystem
enumeration, ``_`` prefix skip, slash-only detection) and its
``catalog_block`` / sentinel constants. The expected count is always derived
from the filesystem, never hardcoded — siblings may add/remove skills.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "skills" / "SKILLS_INDEX.md"


def _load_check_carrier_sync():
    """Import scripts/check_carrier_sync.py by absolute path (cwd-independent).

    Mirrors how the repo's own checker enumerates skills and parses carrier
    catalog blocks, so this test cannot drift from the canonical logic.
    """
    path = ROOT / "scripts" / "check_carrier_sync.py"
    spec = importlib.util.spec_from_file_location("brainer_check_carrier_sync", path)
    assert spec and spec.loader, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CCS = _load_check_carrier_sync()


def _fs_skills() -> list[tuple[str, bool]]:
    """(name, slash_only) pairs from the filesystem, via the canonical checker."""
    return CCS.discover_skills()


def _fs_skill_names() -> set[str]:
    return {name for name, _ in _fs_skills()}


def _index_text() -> str:
    return INDEX.read_text(encoding="utf-8")


def _index_linked_skills() -> set[str]:
    """Skill names the index links as ``[name](name/SKILL.md)``.

    This is the index's authoritative per-skill reference (the catalog table
    and the most-recommended-stack table both use it). Robust to reordering
    and to prose mentions that are not real links.
    """
    text = _index_text()
    return set(re.findall(r"\(([a-z0-9][a-z0-9-]*)/SKILL\.md\)", text))


def test_every_fs_skill_is_listed_in_index():
    fs = _fs_skill_names()
    indexed = _index_linked_skills()
    missing = sorted(fs - indexed)
    assert not missing, (
        "skills with a SKILL.md on disk but not linked in skills/SKILLS_INDEX.md: "
        f"{missing}"
    )


def test_every_indexed_skill_exists_on_disk_with_skill_md():
    indexed = _index_linked_skills()
    assert indexed, "no [name](name/SKILL.md) links found in SKILLS_INDEX.md"
    for name in sorted(indexed):
        skill_md = ROOT / "skills" / name / "SKILL.md"
        assert skill_md.is_file(), (
            f"SKILLS_INDEX.md links {name} but skills/{name}/SKILL.md is missing"
        )


def test_index_links_match_filesystem_exactly():
    """No extra index links, no unlisted skills — the two sets are identical."""
    fs = _fs_skill_names()
    indexed = _index_linked_skills()
    assert fs == indexed, (
        f"index/filesystem skill mismatch: only-on-disk={sorted(fs - indexed)}, "
        f"only-in-index={sorted(indexed - fs)}"
    )


def test_carrier_catalog_blocks_cover_every_filesystem_skill():
    """Each carrier's catalog block tokenizes every fs skill (count-consistent).

    Reuses check_carrier_sync's sentinel constants, catalog_block parser, and
    token convention (`/name` for slash-only, `name` otherwise). The expected
    count is the filesystem count, not a literal.
    """
    skills = _fs_skills()
    assert skills, "discover_skills() returned nothing"
    for carrier in CCS.CARRIERS:
        path = ROOT / carrier
        assert path.is_file(), f"carrier {carrier} missing"
        block = CCS.catalog_block(path.read_text(encoding="utf-8"))
        assert block is not None, (
            f"{carrier}: no skills-catalog block "
            f"({CCS.START} .. {CCS.END})"
        )
        present = []
        for name, slash in skills:
            token = f"`/{name}`" if slash else f"`{name}`"
            if token in block:
                present.append(name)
        missing = sorted(set(n for n, _ in skills) - set(present))
        assert not missing, f"{carrier}: catalog block omits {missing}"
        # Count consistency: as many distinct skill tokens present as on disk.
        assert len(present) == len(skills), (
            f"{carrier}: catalog covers {len(present)} skills, "
            f"filesystem has {len(skills)}"
        )


def test_index_count_consistent_with_filesystem():
    """The index's linked-skill count equals the filesystem skill count.

    Also opportunistically check the 'N skills total' prose claim if present;
    skip silently if the index does not state a number (avoid brittleness).
    """
    fs_count = len(_fs_skills())
    indexed_count = len(_index_linked_skills())
    assert indexed_count == fs_count, (
        f"index links {indexed_count} skills, filesystem has {fs_count}"
    )

    m = re.search(r"(\d+)\s+skills?\s+total", _index_text(), re.IGNORECASE)
    if m:
        assert int(m.group(1)) == fs_count, (
            f"SKILLS_INDEX prose claims {m.group(1)} skills total, "
            f"filesystem has {fs_count}"
        )


def test_readme_skill_count_matches_filesystem_if_stated():
    """If README states an 'N skills' / 'N skills total' number, it must match.

    README phrasing is sibling-owned and may change; we only assert when a
    numeric claim is unambiguous, and we accept any of the claims agreeing
    with the filesystem rather than pinning a specific sentence.
    """
    readme = ROOT / "README.md"
    if not readme.is_file():
        return
    text = readme.read_text(encoding="utf-8")
    fs_count = len(_fs_skills())
    # Numbers immediately qualified by the word "skills" (e.g. "20 skills",
    # "all 20 skills", "(20 skills)"). Avoid version-number false positives.
    claims = re.findall(r"(\d+)\s+skills\b", text)
    if not claims:
        return  # no numeric skill claim in README prose; nothing brittle to assert
    for claim in claims:
        assert int(claim) == fs_count, (
            f"README states '{claim} skills' but filesystem has {fs_count}"
        )
