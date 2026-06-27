#!/usr/bin/env python3
"""Plain-python tests for artifact_guard.py (no pytest dep). Exit code = verdict.

Tests:
  - seal → verify-import roundtrip passes
  - truncated artifact → verify-import fails loudly (nonzero exit)
  - missing sidecar → verify-import fails loudly (nonzero exit)
  - mismatched checksum in sidecar → verify-import fails loudly (nonzero exit)
  - protect writes the .gitattributes line once
  - protect is idempotent (second call does not duplicate the line)
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import artifact_guard as ag

FAILS: list[str] = []
TOOL = Path(__file__).resolve().parent / "artifact_guard.py"


def check(name: str, got, want) -> None:
    if got != want:
        FAILS.append(f"{name}: got {got!r} want {want!r}")
        print(f"  [FAIL] {name}: got {got!r} want {want!r}")
    else:
        print(f"  [PASS] {name}")


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=False)


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True,
        text=True,
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _git(root, "init", "-q")
        _git(root, "config", "user.email", "t@t")
        _git(root, "config", "user.name", "t")

        artifact = root / "output.db"
        artifact.write_bytes(b"fake db content for testing " * 10)

        # ── seal → verify-import roundtrip ────────────────────────────────
        print("== seal → verify-import roundtrip ==")
        seal_r = ag.seal(artifact)
        check("seal returns ok", seal_r["ok"], True)
        meta_path = Path(seal_r["meta"])
        check("sidecar written", meta_path.exists(), True)
        check("sidecar is <artifact>.meta.json", meta_path.name, artifact.name + ".meta.json")

        vi_r = ag.verify_import(artifact)
        check("verify-import roundtrip ok", vi_r["ok"], True)

        # ── truncated artifact → must fail ────────────────────────────────
        print("== truncated artifact → verify-import fails ==")
        artifact2 = root / "output2.db"
        artifact2.write_bytes(b"original content")
        ag.seal(artifact2)  # seal on the full content
        artifact2.write_bytes(b"truncated")  # mutate after sealing
        vi_bad = ag.verify_import(artifact2)
        check("truncated fails", vi_bad["ok"], False)
        check("truncated has error", bool(vi_bad.get("error")), True)

        # CLI exits nonzero on truncated
        cli_r = _cli("verify-import", str(artifact2))
        check("truncated CLI nonzero", cli_r.returncode != 0, True)
        check("truncated CLI message non-empty", bool(cli_r.stdout.strip() or cli_r.stderr.strip()), True)

        # ── missing sidecar → must fail ───────────────────────────────────
        print("== missing sidecar → verify-import fails ==")
        artifact3 = root / "output3.db"
        artifact3.write_bytes(b"no sidecar written here")
        vi_nosidecar = ag.verify_import(artifact3)
        check("missing sidecar fails", vi_nosidecar["ok"], False)
        check("missing sidecar error mentions sidecar/missing", any(
            kw in vi_nosidecar.get("error", "").lower()
            for kw in ("sidecar", "missing", "not found", "meta")
        ), True)

        cli_r2 = _cli("verify-import", str(artifact3))
        check("missing sidecar CLI nonzero", cli_r2.returncode != 0, True)

        # ── mismatched sha256 in sidecar → must fail ──────────────────────
        print("== mismatched checksum → verify-import fails ==")
        artifact4 = root / "output4.db"
        artifact4.write_bytes(b"good content")
        ag.seal(artifact4)
        # tamper with the sidecar's checksum
        import json
        meta4 = Path(str(artifact4) + ".meta.json")
        data = json.loads(meta4.read_text())
        data["sha256"] = "0" * 64
        meta4.write_text(json.dumps(data))

        vi_mismatch = ag.verify_import(artifact4)
        check("mismatch fails", vi_mismatch["ok"], False)
        check("mismatch error mentions checksum/sha256/mismatch", any(
            kw in vi_mismatch.get("error", "").lower()
            for kw in ("checksum", "sha256", "mismatch", "integrity")
        ), True)

        cli_r3 = _cli("verify-import", str(artifact4))
        check("mismatch CLI nonzero", cli_r3.returncode != 0, True)

        # ── protect: writes line once ─────────────────────────────────────
        print("== protect writes .gitattributes line once ==")
        ga_path = root / ".gitattributes"
        check("no .gitattributes yet", ga_path.exists(), False)

        pr = ag.protect(artifact, repo_root=root)
        check("protect ok", pr["ok"], True)
        check(".gitattributes created", ga_path.exists(), True)
        content = ga_path.read_text()
        line = "output.db merge=ours"
        check("line present", line in content, True)
        count_before = content.count(line)
        check("line appears exactly once", count_before, 1)

        # ── protect is idempotent ─────────────────────────────────────────
        print("== protect is idempotent ==")
        pr2 = ag.protect(artifact, repo_root=root)
        check("protect idempotent ok", pr2["ok"], True)
        content2 = ga_path.read_text()
        check("no duplicate line", content2.count(line), 1)

        # CLI protect also idempotent
        cli_p = _cli("protect", str(artifact), "--repo-root", str(root))
        check("CLI protect exit 0", cli_p.returncode, 0)
        check("CLI protect no duplicate", ga_path.read_text().count(line), 1)

        # ── protect creates .gitattributes when absent ────────────────────
        print("== protect creates .gitattributes when absent ==")
        artifact5 = root / "other.db"
        artifact5.write_bytes(b"x")
        ga2 = root / "sub" / ".gitattributes"
        sub_root = root / "sub"
        sub_root.mkdir()
        _git(sub_root, "init", "-q")
        _git(sub_root, "config", "user.email", "t@t")
        _git(sub_root, "config", "user.name", "t")
        pr3 = ag.protect(sub_root / "data.bin", repo_root=sub_root)
        check("create .gitattributes in new root", pr3["ok"], True)
        check(".gitattributes created in sub", ga2.exists(), True)

    print()
    if FAILS:
        print(f"FAILED: {len(FAILS)}")
        for x in FAILS:
            print("  -", x)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
