#!/usr/bin/env python3
"""knowledge_liveness — standing gate-liveness lint (LEARNING_CONTRACT.md §4).

"Enforcement machinery silently dead is worse than absent" (evidence: a
specs.yaml went unparseable for 3 days in screenery-lean while every gate
built on it stayed inert). This lint makes gate-substrate parse-ability and
reference-liveness a CHECKED invariant instead of an assumed one:

  (a) every skills/*/drift_probes.json and other machine-gate JSON
      (lesson_patterns.json etc.) parses as JSON, AND every probe's "kind"
      is a member of the detector set compliance-canary's hook.py actually
      implements (DETECTORS registry) — a probe with an unknown/typo'd kind
      parses fine but is silently skipped at runtime by
      `if kind not in DETECTORS: continue` (hook.py run_probes()) = an
      alive-looking dead gate. The valid-kind set is derived dynamically by
      loading hook.py as a module and reading DETECTORS.keys() — never
      hand-copied, since a hard-coded mirror is exactly the kind of drift
      this lint exists to catch.
  (b) every skills/*/SKILL.md frontmatter parses, and any tool path it
      references (tools/*.py, other relative script links) exists.
  (c) markdown links inside skills/**/SKILL.md and skills/_shared/*.md
      resolve to real files (relative-link liveness).
  (d) wiki link liveness — defers to scripts/check_wiki_hygiene.py for the
      checks it already owns (required top-level paths + doc mentions) and
      ADDS ONLY what that script does not cover: markdown-link resolution
      inside wiki/**/*.md.
  (e) hooks-map liveness — every hook entry/installer path that
      scripts/gen_hooks_map.py's own inventory reports must exist on disk.
      Reuses gen_hooks_map.skill_hook_inventory() rather than re-deriving
      hook-path discovery.
  (f) every skills/*/tools/**/*.json, recursive (gate substrate beyond
      drift_probes.json/lesson_patterns.json — e.g. eval-gate's
      criteria*.json, including any nested under tools/) parses as JSON.
      Parse-check only; no schema opinion on non-probe files.

Exit codes: 0 clean, 1 warn (checker hit a non-fatal internal snag but could
still complete, e.g. an optional dependency subsystem is unavailable — no
knowledge_liveness check in this repo currently has a legitimate "found an
issue but it's only a warning" tier; every FOUND dangling reference is a dead
gate per §4 and fails), 2 fail (a check found a genuinely broken/dangling
reference).

Stdlib only. Read-only — never edits/writes any of the paths it checks.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILLS = REPO / "skills"
SCRIPTS = REPO / "scripts"
CANARY_HOOK = SKILLS / "compliance-canary" / "tools" / "hook.py"

MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def _is_local_path_link(target: str) -> bool:
    """True if a markdown link target is a local file path worth checking.

    Skips external URLs, mailto:, in-page anchors (#foo), and bare anchors
    appended to a path we still want to check the file part of.
    """
    target = target.strip()
    if not target or target.startswith("#"):
        return False
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", target):
        return False
    if target.startswith("mailto:"):
        return False
    return True


def _strip_anchor(target: str) -> str:
    return target.split("#", 1)[0]


def _strip_fenced_code_blocks(text: str) -> str:
    """Remove ```...``` fenced code blocks so markdown-link scanning never
    mistakes code (e.g. a Python f-string `f"[{x}]({y})"` or dict/call syntax
    `foo['a'](b)`) for a real `[text](link)` construct."""
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)


def _derive_detector_kinds() -> set[str] | None:
    """The set of probe "kind" values compliance-canary's hook.py actually
    dispatches on, read straight from its DETECTORS registry (never
    hand-copied — a hard-coded mirror is exactly the drift this lint exists
    to catch). Loads hook.py as a module (same _load_module mechanism this
    file already uses for gen_hooks_map.py/check_wiki_hygiene.py); hook.py
    guards its stdin-reading main() behind `if __name__ == "__main__"`, so
    importing it as a library runs no I/O beyond building DETECTORS.

    Returns None (not an empty set) if hook.py is missing/unloadable or
    exposes no DETECTORS dict, so callers can distinguish "derivation
    failed, skip schema check" from "derivation succeeded, zero kinds"."""
    if not CANARY_HOOK.exists():
        return None
    try:
        hook = _load_module(CANARY_HOOK, "compliance_canary_hook")
        detectors = getattr(hook, "DETECTORS", None)
        if not isinstance(detectors, dict) or not detectors:
            return None
        return set(detectors.keys())
    except Exception:
        return None


def check_gate_json(errors: list[str]) -> None:
    """(a) every skills/*/drift_probes.json and other machine-gate JSON
    parses, and every drift_probes.json entry's "kind" is a member of the
    detector set compliance-canary's hook.py actually implements
    (DETECTORS). An unknown/typo'd kind parses fine as JSON but is silently
    skipped at runtime by hook.py's run_probes() — an alive-looking dead
    gate ([gate-schema])."""
    kinds = _derive_detector_kinds()
    if kinds is None:
        errors.append(
            f"[gate-schema] could not derive detector kind set from "
            f"{CANARY_HOOK.relative_to(REPO)} — schema check skipped, cannot "
            f"confirm probe kinds are live"
        )

    patterns = ("drift_probes.json", "lesson_patterns.json")
    for pattern in patterns:
        for path in sorted(SKILLS.glob(f"*/{pattern}")):
            rel = path.relative_to(REPO)
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                errors.append(f"[gate-json] {rel}: {type(exc).__name__}: {exc}")
                continue
            if kinds is None or pattern != "drift_probes.json" or not isinstance(data, list):
                continue
            for entry in data:
                if not isinstance(entry, dict) or "kind" not in entry:
                    continue
                kind = entry["kind"]
                if kind not in kinds:
                    probe_id = entry.get("id", "?")
                    errors.append(
                        f"[gate-schema] {rel}: probe {probe_id!r} has kind "
                        f"{kind!r} not implemented by any DETECTORS entry in "
                        f"{CANARY_HOOK.relative_to(REPO)} — dead at runtime "
                        f"(silently skipped by run_probes)"
                    )


def check_tools_json_parses(errors: list[str]) -> None:
    """(f) every skills/*/tools/**/*.json parses as JSON — gate substrate
    beyond drift_probes.json/lesson_patterns.json (e.g. eval-gate's
    criteria*.json). Recursive (tools/**/*.json), not just tools/*.json: a
    one-level glob silently skips nested gate substrate like
    tools/nested/criteria.json — an alive-looking dead gate identical in kind
    to the ones (a)/(b)/(c) already guard against. Parse-check only; the two
    special-cased filenames keep their deeper [gate-schema] check in
    check_gate_json above."""
    for path in sorted(SKILLS.glob("*/tools/**/*.json")):
        rel = path.relative_to(REPO)
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"[gate-json] {rel}: {type(exc).__name__}: {exc}")


def _parse_skill_frontmatter(text: str) -> tuple[dict, str] | None:
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not m:
        return None
    fm_block, body = m.group(1), m.group(2)
    fm: dict[str, str] = {}
    for line in fm_block.splitlines():
        if not line.strip() or line.strip().startswith("#") or ":" not in line:
            continue
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip()
    return fm, body


def check_skill_md_and_tool_paths(errors: list[str]) -> None:
    """(b) every SKILL.md frontmatter parses; referenced tool paths exist."""
    for skill_md in sorted(SKILLS.glob("*/SKILL.md")):
        skill_dir = skill_md.parent
        rel = skill_md.relative_to(REPO)
        text = skill_md.read_text(encoding="utf-8", errors="replace")
        parsed = _parse_skill_frontmatter(text)
        if parsed is None:
            errors.append(f"[skill-md] {rel}: no parseable YAML frontmatter block")
            continue
        _fm, body = parsed
        # Referenced tool paths: tools/*.py or any relative link ending in a
        # script/doc extension found in the body (markdown links handled more
        # generally in check_markdown_links; this pass targets bare
        # `tools/...` mentions in prose/backticks that aren't necessarily
        # inside a [text](link) construct).
        for m in re.finditer(r"`(tools/[\w./-]+)`", body):
            candidate = skill_dir / m.group(1)
            if not candidate.exists():
                errors.append(f"[skill-md] {rel}: referenced tool path does not exist: {m.group(1)}")


def check_markdown_links(errors: list[str]) -> None:
    """(c) markdown links inside skills/**/SKILL.md and skills/_shared/*.md resolve."""
    files: list[Path] = sorted(SKILLS.glob("*/SKILL.md"))
    files += sorted((SKILLS / "_shared").glob("*.md"))
    for path in files:
        rel = path.relative_to(REPO)
        text = _strip_fenced_code_blocks(path.read_text(encoding="utf-8", errors="replace"))
        for m in MD_LINK_RE.finditer(text):
            target = m.group(1)
            if not _is_local_path_link(target):
                continue
            target_path = _strip_anchor(target)
            if not target_path:
                continue
            resolved = (path.parent / target_path).resolve()
            if not resolved.exists():
                errors.append(f"[md-link] {rel}: dangling link target: {target}")


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def check_wiki_liveness(errors: list[str], warnings: list[str]) -> None:
    """(d) defer to check_wiki_hygiene.py for what it already covers; only add
    markdown-link resolution inside wiki/**/*.md, which that script does not
    check.
    """
    hygiene_path = SCRIPTS / "check_wiki_hygiene.py"
    if not hygiene_path.exists():
        warnings.append(f"[wiki] {hygiene_path.relative_to(REPO)} not found — skipping wiki hygiene delegation")
    else:
        try:
            hygiene = _load_module(hygiene_path, "check_wiki_hygiene")
            rc = hygiene.main()
            if rc != 0:
                errors.append("[wiki] scripts/check_wiki_hygiene.py reported failures (see its own output above)")
        except Exception as exc:
            errors.append(f"[wiki] failed to run scripts/check_wiki_hygiene.py: {type(exc).__name__}: {exc}")

    wiki_dir = REPO / "wiki"
    if not wiki_dir.exists():
        return  # no wiki adopted in this repo; nothing more to check
    for path in sorted(wiki_dir.rglob("*.md")):
        rel = path.relative_to(REPO)
        text = _strip_fenced_code_blocks(path.read_text(encoding="utf-8", errors="replace"))
        for m in MD_LINK_RE.finditer(text):
            target = m.group(1)
            if not _is_local_path_link(target):
                continue
            target_path = _strip_anchor(target)
            if not target_path:
                continue
            resolved = (path.parent / target_path).resolve()
            if not resolved.exists():
                errors.append(f"[wiki-md-link] {rel}: dangling link target: {target}")


def check_hooks_map_liveness(errors: list[str], warnings: list[str]) -> None:
    """(e) scripts/gen_hooks_map.py exists; every path its own inventory
    reports (hook entry files + installer) must resolve. Reuses
    gen_hooks_map.skill_hook_inventory() instead of re-deriving hook
    discovery.
    """
    gen_path = SCRIPTS / "gen_hooks_map.py"
    if not gen_path.exists():
        errors.append(f"[hooks-map] {gen_path.relative_to(REPO)} does not exist")
        return
    try:
        gen = _load_module(gen_path, "gen_hooks_map")
        inventory = gen.skill_hook_inventory()
    except Exception as exc:
        errors.append(f"[hooks-map] failed to import scripts/gen_hooks_map.py: {type(exc).__name__}: {exc}")
        return
    for row in inventory:
        for entry in row.get("entry", []):
            if not (REPO / entry).exists():
                errors.append(f"[hooks-map] {row['skill']}: entry path does not exist: {entry}")
        installer = row.get("installer")
        if installer and not (REPO / installer).exists():
            errors.append(f"[hooks-map] {row['skill']}: installer path does not exist: {installer}")


CHECKS = (
    ("gate-json", check_gate_json),
    ("tools-json", check_tools_json_parses),
    ("skill-md-tool-paths", check_skill_md_and_tool_paths),
    ("markdown-links", check_markdown_links),
)


def run(repo_root: Path | None = None) -> tuple[int, list[str], list[str]]:
    """Run all checks against repo_root (default: this repo). Returns
    (exit_code, errors, warnings)."""
    global REPO, SKILLS, SCRIPTS, CANARY_HOOK
    if repo_root is not None:
        REPO, SKILLS, SCRIPTS = repo_root, repo_root / "skills", repo_root / "scripts"
        CANARY_HOOK = SKILLS / "compliance-canary" / "tools" / "hook.py"

    errors: list[str] = []
    warnings: list[str] = []

    check_gate_json(errors)
    check_tools_json_parses(errors)
    check_skill_md_and_tool_paths(errors)
    check_markdown_links(errors)
    check_wiki_liveness(errors, warnings)
    check_hooks_map_liveness(errors, warnings)

    if errors:
        return 2, errors, warnings
    if warnings:
        return 1, errors, warnings
    return 0, errors, warnings


def main() -> int:
    code, errors, warnings = run()
    if errors:
        print(f"knowledge_liveness: FAIL ({len(errors)} dead-gate/dangling-reference finding(s)):")
        for e in errors:
            print(f"- {e}")
    if warnings:
        print(f"knowledge_liveness: {len(warnings)} warning(s):")
        for w in warnings:
            print(f"- {w}")
    if not errors and not warnings:
        print("knowledge_liveness: clean — all gate substrate parses, all referenced paths resolve.")
    return code


if __name__ == "__main__":
    sys.exit(main())
