#!/usr/bin/env python3
"""artifact_guard — safe commit helper for regenerated artifacts.

THREAT MODEL (read before relying on verify-import). This gate detects
*corruption* — truncation, a partial/aborted write, bit-rot, a missing or
mismatched sidecar — of a regenerated artifact. It is NOT an anti-tamper /
authenticity gate: an actor who can rewrite BOTH the artifact and its sidecar
(i.e. re-`seal`) produces a self-consistent pair that verifies clean, by design
(re-sealing a freshly regenerated artifact is the normal, intended flow). For
authenticity against a malicious writer you need an out-of-band signature (e.g.
sigstore/cosign over the artifact), which is out of scope here.

Port of codebase-memory-mcp's src/pipeline/artifact.c:
  - ensure_gitattributes (~line 333): prevents merge conflicts via merge=ours
  - integrity gate (~line 626): requires artifact + sidecar checksum match before import

CLI:
  protect <artifact_path> [--repo-root R]
      Idempotently append "<artifact_path> merge=ours" to the repo's
      .gitattributes (create it if absent; never duplicate).

  seal <artifact_path>
      Write a <artifact_path>.meta.json sidecar containing:
        sha256   — hex digest of the artifact blob
        size     — byte count
        sealed_at — ISO timestamp
      Must be called before verify-import.

  verify-import <artifact_path>
      Gate: require BOTH the artifact AND its .meta.json sidecar to exist,
      and the sha256 to match. On any failure: nonzero exit + clear message
      to stdout. Never silently proceeds.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
from pathlib import Path


# ── SHA-256 helper ────────────────────────────────────────────────────────────

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ── Core operations ───────────────────────────────────────────────────────────

def seal(artifact_path: Path) -> dict:
    """Write a .meta.json sidecar for artifact_path.

    Returns {"ok": True, "meta": str(meta_path), "sha256": ..., "size": ...}
    or {"ok": False, "error": ...}.
    """
    artifact_path = Path(artifact_path)
    if not artifact_path.exists():
        return {"ok": False, "error": f"artifact not found: {artifact_path}"}

    try:
        digest = _sha256_file(artifact_path)
        size = artifact_path.stat().st_size
    except OSError as e:
        return {"ok": False, "error": f"cannot read artifact: {e}"}

    meta = {
        "sha256": digest,
        "size": size,
        "sealed_at": _dt.datetime.now().isoformat(timespec="seconds"),
    }
    meta_path = Path(str(artifact_path) + ".meta.json")
    try:
        meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    except OSError as e:
        return {"ok": False, "error": f"cannot write sidecar: {e}"}

    return {"ok": True, "meta": str(meta_path), "sha256": digest, "size": size}


def verify_import(artifact_path: Path) -> dict:
    """Gate import on integrity sidecar.

    Requires BOTH the artifact AND a <artifact_path>.meta.json sidecar.
    The sidecar's sha256 must match the artifact's actual digest.

    Returns {"ok": True} on success.
    Returns {"ok": False, "error": "<clear message>"} on any failure.
    Never silently proceeds — callers must check "ok".
    """
    artifact_path = Path(artifact_path)
    meta_path = Path(str(artifact_path) + ".meta.json")

    if not artifact_path.exists():
        return {"ok": False, "error": f"artifact not found: {artifact_path}"}

    if not meta_path.exists():
        return {
            "ok": False,
            "error": (
                f"integrity sidecar missing: {meta_path}\n"
                f"Run: artifact_guard.py seal {artifact_path}"
            ),
        }

    try:
        raw = meta_path.read_text()
        meta = json.loads(raw)
    except (OSError, json.JSONDecodeError) as e:
        return {"ok": False, "error": f"cannot parse sidecar {meta_path}: {e}"}

    expected_sha256 = meta.get("sha256")
    if not expected_sha256 or not isinstance(expected_sha256, str):
        return {"ok": False, "error": f"sidecar missing/invalid 'sha256' field: {meta_path}"}

    try:
        actual_sha256 = _sha256_file(artifact_path)
    except OSError as e:
        return {"ok": False, "error": f"cannot read artifact for checksum: {e}"}

    if actual_sha256 != expected_sha256:
        return {
            "ok": False,
            "error": (
                f"sha256 mismatch for {artifact_path}:\n"
                f"  sidecar:  {expected_sha256}\n"
                f"  actual:   {actual_sha256}\n"
                "Artifact may be corrupt or was modified after sealing. Re-seal or re-generate."
            ),
        }

    expected_size = meta.get("size")
    if expected_size is not None:
        try:
            actual_size = artifact_path.stat().st_size
        except OSError as e:
            return {"ok": False, "error": f"cannot stat artifact: {e}"}
        if actual_size != expected_size:
            return {
                "ok": False,
                "error": (
                    f"size mismatch for {artifact_path}: "
                    f"sidecar={expected_size} actual={actual_size}"
                ),
            }

    return {"ok": True}


def protect(artifact_path: Path, repo_root: Path | None = None) -> dict:
    """Idempotently append '<name> merge=ours' to the repo's .gitattributes.

    artifact_path: path to the artifact (only its name/relative path is used
                   in the .gitattributes entry).
    repo_root: directory containing .gitattributes (defaults to artifact_path's
               parent, i.e. the immediate dir). Pass the repo root explicitly
               when the artifact is nested.

    Returns {"ok": True, "added": bool, "gitattributes": str(path)}.
    """
    artifact_path = Path(artifact_path)
    root = Path(repo_root) if repo_root is not None else artifact_path.parent
    ga_path = root / ".gitattributes"

    # The entry uses only the filename (not the full path), mirroring the C
    # source which writes CBM_ARTIFACT_FILENAME (a bare filename constant).
    entry_name = artifact_path.name
    line = f"{entry_name} merge=ours\n"

    existing = ""
    if ga_path.exists():
        try:
            existing = ga_path.read_text()
        except OSError as e:
            return {"ok": False, "error": f"cannot read .gitattributes: {e}"}

    # Idempotency: check for the line already present (with or without trailing newline)
    if f"{entry_name} merge=ours" in existing:
        return {"ok": True, "added": False, "gitattributes": str(ga_path)}

    try:
        with ga_path.open("a") as f:
            # If file exists but doesn't end with a newline, add one first
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(line)
    except OSError as e:
        return {"ok": False, "error": f"cannot write .gitattributes: {e}"}

    return {"ok": True, "added": True, "gitattributes": str(ga_path)}


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="artifact_guard — integrity-gated artifact helper")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_protect = sub.add_parser("protect", help="protect artifact from merge conflicts")
    p_protect.add_argument("artifact_path")
    p_protect.add_argument("--repo-root", default=None,
                           help="repo root containing .gitattributes (default: artifact's parent dir)")

    p_seal = sub.add_parser("seal", help="write integrity sidecar (.meta.json)")
    p_seal.add_argument("artifact_path")

    p_verify = sub.add_parser("verify-import", help="gate import on integrity sidecar")
    p_verify.add_argument("artifact_path")

    a = ap.parse_args(argv)

    if a.cmd == "protect":
        repo_root = Path(a.repo_root) if a.repo_root else None
        result = protect(Path(a.artifact_path), repo_root=repo_root)
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1

    if a.cmd == "seal":
        result = seal(Path(a.artifact_path))
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1

    if a.cmd == "verify-import":
        result = verify_import(Path(a.artifact_path))
        if result["ok"]:
            print(json.dumps(result, indent=2))
            return 0
        # FAIL LOUDLY — nonzero exit + clear message (never silent)
        print(f"ERROR: verify-import failed\n{result['error']}", flush=True)
        return 1

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
