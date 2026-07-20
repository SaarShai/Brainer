#!/usr/bin/env python3
"""Static contract check for the manual `/think` skill."""

from __future__ import annotations

import json
import re
from pathlib import Path


REQUIRED_SKILL_MARKERS = (
    "disable-model-invocation: true",
    "manual-only",
    "## mandatory routes",
    "matched companion skill",
    "rigorous, resourceful collaborator on non-trivial or open-ended problems",
    "ground the work in evidence, the actual goal, and the real constraints",
    "creativity to generate materially distinct approaches",
    "smallest testable path instead of speculative machinery",
    "truth before fluency",
    "truth before agreement",
    "goal before solution",
    "smallest safe intervention",
    "preserve source provenance",
    "raw sources are immutable",
    "generated wiki pages are model-owned derived artifacts",
    "small heterogeneous pilot",
    "bounded, resumable batches",
    "compile and integrity checks",
    "read the actual target",
    "state the success criterion",
    "diagnose faults before patching",
    "no new dependency without concrete net benefit",
    "wiki-memory",
    "wiki-refresh",
    "write-gate",
    "verify-before-completion",
    "without a fixed quota",
    "branch when multiple causes are plausible",
    "mapping breaks",
    "stable input/output contract",
    "did i actually load and follow every matched companion skill",
)

FORBIDDEN_SKILL_MARKERS = (
    "effort: medium",
    "sharpest people in the world",
    "intellectual firepower",
    "erudition",
    "3 or 7",
    "never 5",
    "slop self-check",
    "random-word",
    "methods explicitly discouraged",
    "claude.md",
    "ideation — field rules",
    "method menu",
    "the user may add to this over time",
    "the best part is no part",
    "one source at a time",
    "do not batch-deposit",
    "cap the initial pilot at ten sources",
    "compile sources into the wiki, then retrieve",
    "the bottleneck gets the hammer",
    "standing permission to build",
    "repeat (~5×)",
    "recurs (≥2×)",
)

REQUIRED_EVAL_MARKERS = (
    "id: think-operational",
    "id: think-methods",
    "skill: think",
    "immutable raw source",
    "bounded resumable ingest",
    "per-source provenance",
    "dependency restraint",
    "root-cause debugging",
    "matching and non-matching method probes",
    "objectively best knowledge-management architecture",
    "smallest testable starting path",
)


def validate_contract(skill_text: str, eval_text: str, probes: object) -> list[str]:
    errors: list[str] = []
    skill_lower = skill_text.lower()
    eval_lower = eval_text.lower()

    for marker in REQUIRED_SKILL_MARKERS:
        if marker not in skill_lower:
            errors.append(f"SKILL.md missing required marker: {marker}")
    for marker in FORBIDDEN_SKILL_MARKERS:
        if marker in skill_lower:
            errors.append(f"SKILL.md restored removed marker: {marker}")
    # Consumer repos vendor skills but not Brainer's canonical eval/ harness.
    # Keep the fixture contract enforced where that harness exists, without
    # making the shipped skill test fail solely because the harness is absent.
    if eval_text:
        for marker in REQUIRED_EVAL_MARKERS:
            if marker not in eval_lower:
                errors.append(f"operational eval missing marker: {marker}")

    if not isinstance(probes, list) or not probes:
        errors.append("drift_probes.json must be a non-empty list")
        return errors
    for probe in probes:
        if not isinstance(probe, dict) or not probe.get("id"):
            errors.append("drift probe missing id")
            continue
        try:
            re.compile(str(probe["pattern"]))
        except (KeyError, re.error) as exc:
            errors.append(f"drift probe {probe.get('id')} has invalid regex: {exc}")
    return errors


def load_eval_text(repo_root: Path) -> str:
    paths = (
        repo_root / "eval" / "tasks" / "think-operational.yaml",
        repo_root / "eval" / "tasks" / "think.yaml",
        repo_root / "eval" / "tasks" / "think-methods.yaml",
    )
    return "\n".join(path.read_text(encoding="utf-8") for path in paths if path.is_file())


def main() -> int:
    repo_root = Path(__file__).resolve().parents[3]
    skill_dir = repo_root / "skills" / "think"
    errors = validate_contract(
        (skill_dir / "SKILL.md").read_text(encoding="utf-8"),
        load_eval_text(repo_root),
        json.loads((skill_dir / "drift_probes.json").read_text(encoding="utf-8")),
    )
    if errors:
        for error in errors:
            print(f"FAIL {error}")
        return 1
    print("PASS think operational contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
