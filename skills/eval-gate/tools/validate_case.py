#!/usr/bin/env python3
"""validate_case.py — pre-authoring ground-truth gate for eval-gate case-sets.

The one rule this enforces: **ground truth never comes from the system under
test.** Before a question is written into a case-set, the *facts the question
asks about* (its targets) must originate from independently-verifiable sources —
a file on disk, a git object, an LSP symbol, a config key, an API contract — and
NEVER from a model-generated answer. This is the circularity break: the author
of the question cannot also invent the answer key.

It also enforces the external-taxonomy anchor (spec §3.1): every case declares a
Sillito dimension (D1..D5) so questions map to a citable question taxonomy
(Sillito/Murphy/De Volder, IEEE TSE 2008) rather than being authored ad-hoc.

INPUT — a questions.jsonl, one JSON object per line:

    {"id": "wiki-d1-01",
     "skill": "wiki-memory",
     "text": "Recall the decision recorded for the eval upgrade.",
     "targets": [
        {"fact": "validate_case.py is the pre-authoring gate",
         "source": "file",
         "source_path": "skills/eval-gate/tools/validate_case.py"}
     ],
     "sillito_dim": "D1"}

VALIDATION (static only — MUST NOT run any skill or model):
  - source         in {file, git, lsp_symbol, config, api_contract}  (enum)
  - source_path    is independently verifiable for its source kind:
      file         -> the path exists on disk (relative to --repo-root)
      config       -> the file exists AND contains the named key (path#key) or
                      the bare path exists (key check skipped if no '#')
      git          -> the commit / object SHA resolves (`git cat-file -e`)
      lsp_symbol   -> the symbol is found by a static grep of a definition site
                      (a stand-in for a real LSP query; no language server run)
      api_contract -> the contract file exists on disk
  - sillito_dim    in {D1, D2, D3, D4, D5, cross-cutting}
  - a target with NO source / NO source_path (i.e. authored from a model answer
    with nothing to verify) FAILS — this is the circularity catch.

EXIT CODES:
  0  every case + every target verified -> ready for rubric authoring
  1  one or more targets failed -> per-target reasons printed
  2  usage / unreadable-input error (fails safe; never a silent pass)

This validator never imports eval_gate, never opens a socket, never spawns the
skill under test. The only subprocess it may run is read-only `git` for SHA
resolution.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

VALID_SOURCES = {"file", "git", "lsp_symbol", "config", "api_contract"}
VALID_DIMS = {"D1", "D2", "D3", "D4", "D5", "cross-cutting"}

# Marker substrings that betray a target whose "source" is actually a model run
# rather than an independent fact. Rejected even if the enum is spoofed into a
# valid value — a defense for the circularity rule, not just the enum.
MODEL_SOURCE_MARKERS = (
    "model", "llm", "judge", "generated", "gpt", "claude", "ollama",
    "answer-key", "answer_key", "completion", "skill-output", "skill_output",
)


def _is_model_sourced(target: dict) -> bool:
    """True if the target appears to be authored from a model/skill output."""
    blob = " ".join(
        str(target.get(k, "")) for k in ("source", "source_path", "fact")
    ).lower()
    return any(m in blob for m in MODEL_SOURCE_MARKERS)


def _git_object_exists(sha: str, repo_root: Path) -> bool:
    """Read-only: does this git object resolve in the repo?"""
    if not re.fullmatch(r"[0-9a-fA-F]{4,40}", sha or ""):
        return False
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_root), "cat-file", "-e", sha + "^{commit}"],
            capture_output=True, timeout=10,
        )
        if r.returncode == 0:
            return True
        # not a commit — accept any resolvable object (blob/tree/tag)
        r = subprocess.run(
            ["git", "-C", str(repo_root), "cat-file", "-e", sha],
            capture_output=True, timeout=10,
        )
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _symbol_defined(symbol: str, repo_root: Path) -> bool:
    """Static stand-in for an LSP definition query: grep for a plausible
    definition site of the symbol across tracked source. No language server is
    run — this only confirms the symbol name corresponds to a real definition,
    which is enough to refute a target invented from a model answer."""
    if not symbol:
        return False
    # def/class/function/const/let/var/fn NAME — language-agnostic enough for a gate.
    pat = re.compile(
        r"(?:^|\b)(?:def|class|func|function|fn|const|let|var|type|interface|struct)\s+"
        + re.escape(symbol) + r"\b"
    )
    exts = {".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".java", ".rb", ".sh"}
    skip = {".git", "node_modules", "__pycache__"}
    for p in repo_root.rglob("*"):
        if p.is_dir() or p.suffix not in exts:
            continue
        if any(part in skip for part in p.parts):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if pat.search(text):
            return True
    return False


def _config_ok(source_path: str, repo_root: Path) -> tuple[bool, str]:
    """A config target may be 'path#key' (verify the key is present) or a bare
    path (verify the file exists)."""
    raw = source_path or ""
    if "#" in raw:
        path_part, key = raw.split("#", 1)
    else:
        path_part, key = raw, None
    fp = (repo_root / path_part).resolve()
    if not fp.is_file():
        return False, f"config file not found: {path_part}"
    if key:
        try:
            text = fp.read_text(encoding="utf-8", errors="ignore")
        except OSError as e:
            return False, f"config unreadable: {e}"
        if key not in text:
            return False, f"config key '{key}' not present in {path_part}"
    return True, ""


def validate_target(target: dict, repo_root: Path) -> tuple[bool, str]:
    """Return (ok, reason). reason is '' on success."""
    if not isinstance(target, dict):
        return False, "target is not an object"
    source = target.get("source")
    source_path = target.get("source_path")

    if source is None or source_path in (None, ""):
        return False, (
            "missing source/source_path — a target with no verifiable origin is "
            "a model-authored answer key (circularity); reject"
        )
    if source not in VALID_SOURCES:
        return False, f"source '{source}' not in {sorted(VALID_SOURCES)}"
    if _is_model_sourced(target):
        return False, (
            "target appears model-/skill-generated (matched a model-source "
            "marker) — ground truth must come from file/git/lsp/config, not the "
            "system under test"
        )

    sp = str(source_path)
    if source in ("file", "api_contract"):
        if not (repo_root / sp).resolve().is_file():
            return False, f"{source} does not exist: {sp}"
        return True, ""
    if source == "config":
        return _config_ok(sp, repo_root)
    if source == "git":
        if not _git_object_exists(sp, repo_root):
            return False, f"git object does not resolve: {sp}"
        return True, ""
    if source == "lsp_symbol":
        if not _symbol_defined(sp, repo_root):
            return False, f"lsp_symbol not found at any definition site: {sp}"
        return True, ""
    return False, f"unhandled source kind: {source}"  # unreachable


def validate_case(case: dict, repo_root: Path) -> tuple[bool, list[str]]:
    """Return (ok, reasons). One reason per failure; empty on success."""
    reasons: list[str] = []
    if not isinstance(case, dict):
        return False, ["<non-object>: case is not an object"]
    cid = case.get("id", "<no-id>")

    dim = case.get("sillito_dim")
    if dim not in VALID_DIMS:
        reasons.append(f"{cid}: sillito_dim '{dim}' not in {sorted(VALID_DIMS)}")

    targets = case.get("targets")
    if not isinstance(targets, list) or not targets:
        reasons.append(f"{cid}: 'targets' must be a non-empty list")
        targets = []

    for i, t in enumerate(targets):
        ok, reason = validate_target(t, repo_root)
        if not ok:
            reasons.append(f"{cid}: target[{i}] {reason}")

    return (not reasons), reasons


def load_cases(path: Path) -> list[dict]:
    """Read questions.jsonl (one object per line) -> list of dicts.
    Raises ValueError on malformed JSON / wrong shape."""
    text = path.read_text(encoding="utf-8")
    cases: list[dict] = []
    for ln, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"line {ln}: invalid JSON ({e})") from e
        if not isinstance(obj, dict):
            raise ValueError(f"line {ln}: not a JSON object")
        cases.append(obj)
    return cases


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="validate_case.py",
        description="Pre-authoring ground-truth gate for eval-gate case-sets. "
        "Static-only: never runs the skill or model under test.",
    )
    ap.add_argument(
        "--questions", required=True,
        help="path to questions.jsonl ({id,skill,text,targets,sillito_dim})",
    )
    ap.add_argument(
        "--repo-root", default=".",
        help="root the source_paths are resolved against (default: cwd)",
    )
    ap.add_argument(
        "--mode", default="preflight", choices=["preflight", "audit"],
        help="preflight (pre-authoring) | audit (post-hoc case-set audit); "
        "both run identical checks — the label is for the report only",
    )
    ap.add_argument("--quiet", action="store_true", help="only print on failure")
    args = ap.parse_args(argv)

    qpath = Path(args.questions)
    repo_root = Path(args.repo_root).resolve()
    if not qpath.is_file():
        print(f"error: questions file not found: {qpath}", file=sys.stderr)
        return 2
    if not repo_root.is_dir():
        print(f"error: repo-root not a directory: {repo_root}", file=sys.stderr)
        return 2

    try:
        cases = load_cases(qpath)
    except (ValueError, OSError) as e:
        print(f"error: cannot read questions: {e}", file=sys.stderr)
        return 2
    if not cases:
        print("error: no cases found in questions file", file=sys.stderr)
        return 2

    all_reasons: list[str] = []
    n_pass = 0
    for case in cases:
        ok, reasons = validate_case(case, repo_root)
        if ok:
            n_pass += 1
        else:
            all_reasons.extend(reasons)

    if all_reasons:
        print(f"[validate_case:{args.mode}] FAIL — "
              f"{n_pass}/{len(cases)} cases ready; "
              f"{len(all_reasons)} target/case problem(s):")
        for r in all_reasons:
            print(f"  - {r}")
        return 1

    if not args.quiet:
        print(f"[validate_case:{args.mode}] OK — {n_pass}/{len(cases)} cases "
              f"ready for rubric authoring (all targets independently verified).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
