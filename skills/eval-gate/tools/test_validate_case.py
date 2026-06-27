#!/usr/bin/env python3
"""Standalone offline tests for validate_case.py (assert + exit-1, no pytest).

Covers the spec's required cases:
  1. a case whose target file exists + valid dim            -> PASS (exit 0)
  2. a target pointing at a missing file                    -> FAIL (exit 1)
  3. a target with a bad source enum                        -> FAIL
  4. a case missing the Sillito dim                         -> FAIL
  5. a case authored from a model answer (no verifiable     -> FAIL
     source) — the circularity catch
Plus: git-SHA target resolves, lsp_symbol found, model-marker source rejected,
loader rejects malformed JSON, and the CLI exit codes (0/1/2).

No network, no model, no skill run. Uses this repo as the verifiable ground
truth (validate_case.py itself is the file target; HEAD is the git target).
"""
from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


@contextlib.contextmanager
def _muted():
    """Silence the CLI's own stdout/stderr while exercising its exit codes,
    so this test's transcript only carries its own ok/FAIL lines."""
    with open(os.devnull, "w") as dn, \
            contextlib.redirect_stdout(dn), contextlib.redirect_stderr(dn):
        yield

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import validate_case as vc  # noqa: E402

# repo root = .../skills/eval-gate/tools -> up 3
REPO_ROOT = HERE.parent.parent.parent
fails: list[str] = []


def check(cond: bool, label: str) -> None:
    if cond:
        print(f"  ok: {label}")
    else:
        print(f"  FAIL: {label}")
        fails.append(label)


def head_sha() -> str:
    r = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        capture_output=True, text=True,
    )
    return r.stdout.strip()


print("[validate_case self-test]")

# --- 1. valid: real file target + valid dim -> case passes ---
good = {
    "id": "good-01", "skill": "eval-gate",
    "text": "Where is the pre-authoring gate defined?",
    "targets": [{
        "fact": "validate_case.py is the gate",
        "source": "file",
        "source_path": "skills/eval-gate/tools/validate_case.py",
    }],
    "sillito_dim": "D1",
}
ok, reasons = vc.validate_case(good, REPO_ROOT)
check(ok and not reasons, "valid case (existing file + D1) passes")

# --- 2. missing file target -> fail with a reason ---
missing = {
    "id": "missing-01", "skill": "eval-gate", "text": "q",
    "targets": [{
        "fact": "f", "source": "file",
        "source_path": "skills/eval-gate/tools/does_not_exist.py",
    }],
    "sillito_dim": "D2",
}
ok, reasons = vc.validate_case(missing, REPO_ROOT)
check(not ok and any("does not exist" in r for r in reasons),
      "missing file target fails with 'does not exist' reason")

# --- 3. bad source enum -> fail ---
bad_enum = {
    "id": "badenum-01", "skill": "eval-gate", "text": "q",
    "targets": [{
        "fact": "f", "source": "stackoverflow",
        "source_path": "skills/eval-gate/tools/validate_case.py",
    }],
    "sillito_dim": "D3",
}
ok, reasons = vc.validate_case(bad_enum, REPO_ROOT)
check(not ok and any("not in" in r for r in reasons),
      "bad source enum fails")

# --- 4. missing / bad Sillito dim -> fail (even when the target is fine) ---
no_dim = {
    "id": "nodim-01", "skill": "eval-gate", "text": "q",
    "targets": [{
        "fact": "f", "source": "file",
        "source_path": "skills/eval-gate/tools/validate_case.py",
    }],
    "sillito_dim": "D9",
}
ok, reasons = vc.validate_case(no_dim, REPO_ROOT)
check(not ok and any("sillito_dim" in r for r in reasons),
      "invalid sillito_dim fails")

missing_dim = dict(no_dim, id="nodim-02")
missing_dim.pop("sillito_dim")
ok, reasons = vc.validate_case(missing_dim, REPO_ROOT)
check(not ok and any("sillito_dim" in r for r in reasons),
      "absent sillito_dim fails")

# --- 5. case authored from a model answer (no verifiable source) -> fail ---
# 5a: target literally has no source/source_path
model_authored = {
    "id": "model-01", "skill": "eval-gate",
    "text": "What is the right answer?",
    "targets": [{"fact": "the model said the answer is 42"}],
    "sillito_dim": "D1",
}
ok, reasons = vc.validate_case(model_authored, REPO_ROOT)
check(not ok and any("circularity" in r for r in reasons),
      "model-authored target (no source) fails on circularity")

# 5b: source enum is valid but the path/fact betrays a model origin
model_marker = {
    "id": "model-02", "skill": "eval-gate", "text": "q",
    "targets": [{
        "fact": "ground truth taken from the model completion",
        "source": "file",
        "source_path": "eval/results/model_answer_key.json",
    }],
    "sillito_dim": "D1",
}
ok, reasons = vc.validate_case(model_marker, REPO_ROOT)
check(not ok and any("model-" in r or "model" in r.lower() for r in reasons),
      "model-marker target rejected even with a valid enum")

# --- git target resolves ---
sha = head_sha()
git_case = {
    "id": "git-01", "skill": "eval-gate", "text": "q",
    "targets": [{"fact": "f", "source": "git", "source_path": sha}],
    "sillito_dim": "D3",
}
ok, _ = vc.validate_case(git_case, REPO_ROOT)
check(ok, "real HEAD git sha resolves -> passes")

bad_git = dict(git_case, id="git-02",
               targets=[{"fact": "f", "source": "git",
                         "source_path": "deadbeefdeadbeef"}])
ok, reasons = vc.validate_case(bad_git, REPO_ROOT)
check(not ok and any("does not resolve" in r for r in reasons),
      "bogus git sha fails")

# --- lsp_symbol target (validate_case itself defines validate_target) ---
sym_case = {
    "id": "sym-01", "skill": "eval-gate", "text": "q",
    "targets": [{"fact": "f", "source": "lsp_symbol",
                 "source_path": "validate_target"}],
    "sillito_dim": "D1",
}
ok, _ = vc.validate_case(sym_case, REPO_ROOT)
check(ok, "real symbol (validate_target) found by static def-grep")

bad_sym = dict(sym_case, id="sym-02",
               targets=[{"fact": "f", "source": "lsp_symbol",
                         "source_path": "zzz_no_such_symbol_zzz"}])
ok, reasons = vc.validate_case(bad_sym, REPO_ROOT)
check(not ok and any("not found" in r for r in reasons),
      "nonexistent symbol fails")

# --- config target with #key ---
cfg_ok = {
    "id": "cfg-01", "skill": "eval-gate", "text": "q",
    "targets": [{"fact": "f", "source": "config",
                 "source_path": "skills/eval-gate/SKILL.md#name: eval-gate"}],
    "sillito_dim": "D1",
}
ok, _ = vc.validate_case(cfg_ok, REPO_ROOT)
check(ok, "config path#key with a present key passes")

cfg_bad = dict(cfg_ok, id="cfg-02",
               targets=[{"fact": "f", "source": "config",
                         "source_path": "skills/eval-gate/SKILL.md#NONEXISTENT_KEY_XYZ"}])
ok, reasons = vc.validate_case(cfg_bad, REPO_ROOT)
check(not ok and any("not present" in r for r in reasons),
      "config with an absent key fails")

# --- loader rejects malformed JSONL ---
with tempfile.TemporaryDirectory() as td:
    bad = Path(td) / "bad.jsonl"
    bad.write_text("{not valid json}\n")
    raised = False
    try:
        vc.load_cases(bad)
    except ValueError:
        raised = True
    check(raised, "loader raises ValueError on malformed JSONL")

# --- CLI end-to-end: exit 0 on a good file, 1 on a bad file, 2 on missing input ---
with tempfile.TemporaryDirectory() as td:
    good_f = Path(td) / "good.jsonl"
    good_f.write_text(json.dumps(good) + "\n")
    with _muted():
        rc = vc.main(["--questions", str(good_f), "--repo-root", str(REPO_ROOT)])
    check(rc == 0, "CLI exit 0 on an all-valid questions file")

    bad_f = Path(td) / "bad.jsonl"
    bad_f.write_text(json.dumps(missing) + "\n" + json.dumps(model_authored) + "\n")
    with _muted():
        rc = vc.main(["--questions", str(bad_f), "--repo-root", str(REPO_ROOT)])
    check(rc == 1, "CLI exit 1 when a case fails validation")

    with _muted():
        rc = vc.main(["--questions", str(Path(td) / "nope.jsonl"),
                      "--repo-root", str(REPO_ROOT)])
    check(rc == 2, "CLI exit 2 on a missing questions file")

print()
if fails:
    print(f"FAILURES ({len(fails)}): " + "; ".join(fails))
    sys.exit(1)
print("ALL PASS")
sys.exit(0)
