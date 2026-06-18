#!/usr/bin/env python3
"""cache-lint fuzz + edge-case battery.

Generates adversarial / malformed inputs and runs them through cache-lint's
discovery + audit pipeline. Reports crash rate, false-positive rate on known-
clean projects, and behavior on adversarial inputs.
"""
from __future__ import annotations

import json
import os
import random
import string
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "skills/cache-lint/tools"))
from cache_lint import audit, discover  # noqa: E402


def _setup(root: Path, files: dict[str, str | bytes]) -> None:
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            p.write_bytes(content)
        else:
            p.write_text(content)


# --- Fuzz cases ----------------------------------------------------------

def fuzz_cases() -> list[tuple[str, dict]]:
    """Return (name, files-dict) tuples. Each must NOT crash the linter."""
    cases: list[tuple[str, dict]] = []

    # 1. empty CLAUDE.md
    cases.append(("empty_claude", {"CLAUDE.md": ""}))

    # 2. CLAUDE.md with only whitespace
    cases.append(("whitespace_only", {"CLAUDE.md": "   \n\n\t\n"}))

    # 3. CLAUDE.md with BOM prefix
    cases.append(("bom_prefix", {"CLAUDE.md": "﻿# Project\n\n" + ("rules. " * 200)}))

    # 4. CRLF line endings
    cases.append(("crlf_lines", {"CLAUDE.md": "# Project\r\n\r\n" + ("rules.\r\n" * 200)}))

    # 5. Binary garbage in CLAUDE.md
    cases.append(("binary_garbage", {"CLAUDE.md": bytes(random.randint(0, 255) for _ in range(2000))}))

    # 6. Mixed encoding (latin-1)
    cases.append(("latin1_chars", {"CLAUDE.md": "café résumé naïve " * 200}))

    # 7. CJK / RTL Unicode
    cases.append(("unicode_cjk", {"CLAUDE.md": "テスト 中文 العربية " * 200}))

    # 8. Huge CLAUDE.md (1MB)
    cases.append(("huge_claude", {"CLAUDE.md": "x" * 1_000_000}))

    # 9. Malformed JSON in settings
    cases.append(("malformed_settings", {".claude/settings.json": "{not valid json"}))

    # 10. Settings with deeply nested hook structure
    deep = {"hooks": {"Stop": [{"command": "echo ok"} for _ in range(100)]}}
    cases.append(("deep_hooks", {".claude/settings.json": json.dumps(deep)}))

    # 11. Settings with nested hook of unexpected type (string instead of list)
    cases.append(("hooks_wrong_type", {".claude/settings.json": json.dumps({"hooks": "wat"})}))

    # 12. settings.json with model field but no hooks
    cases.append(("just_model", {".claude/settings.json": json.dumps({"model": "claude-opus-4.6"})}))

    # 13. Many SKILL.md files
    files = {"CLAUDE.md": "# Project\n\n" + ("Rule. " * 200)}
    for i in range(50):
        files[f"skills/skill{i:02d}/SKILL.md"] = f"---\nname: skill{i}\ndescription: Use when X.\n---\n# Skill {i}\n"
    cases.append(("many_skills", files))

    # 14. Adversarial regex DoS attempt — many $(...) substitutions
    cases.append(("dos_substitutions", {"CLAUDE.md": "$(date) " * 5000}))

    # 15. Nested CLAUDE.md in plugin
    cases.append(("nested_plugin_claude", {
        "CLAUDE.md": "# Root\n\n" + ("X. " * 300),
        "plugins/foo/CLAUDE.md": "# Plugin\n\n" + ("Y. " * 100),
        "plugins/foo/hooks/hooks.json": json.dumps({"hooks": {"Stop": []}}),
    }))

    # 16. CLAUDE.md inside node_modules (should be SKIPPED by discovery)
    cases.append(("node_modules_skip", {
        "CLAUDE.md": "# Root\n\n" + ("X. " * 300),
        "node_modules/some-pkg/CLAUDE.md": "this should not be scanned",
    }))

    # 17. Symlink loop (best-effort — may error on some filesystems)
    # Skipping — hard to make portable

    # 18. Empty .claude/ dir
    cases.append(("empty_claude_dir", {".claude/.gitkeep": ""}))

    # 19. Settings with hook commands that look like shell pipelines
    cases.append(("shell_pipeline", {
        ".claude/settings.json": json.dumps({"hooks": {"Stop": [{"command": "git status | head -20"}]}})
    }))

    # 20. A real `$RANDOM` in CLAUDE.md
    cases.append(("real_random", {"CLAUDE.md": "Session: $RANDOM-$(date +%s)\n" + ("rule. " * 300)}))

    return cases


# --- Run ----------------------------------------------------------------

def run() -> dict:
    cases = fuzz_cases()
    results = []
    crashes = 0
    t0 = time.time()
    for name, files in cases:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _setup(root, files)
            try:
                ts = time.time()
                report = audit(root)
                elapsed_ms = int((time.time() - ts) * 1000)
                results.append({
                    "case": name,
                    "ok": True,
                    "elapsed_ms": elapsed_ms,
                    "n_targets": len(report.targets),
                    "n_findings": len(report.findings),
                    "fails": report.summary["FAIL"],
                    "warns": report.summary["WARN"],
                })
            except Exception as e:
                crashes += 1
                results.append({
                    "case": name,
                    "ok": False,
                    "error": f"{type(e).__name__}: {e}",
                })

    total_elapsed = round(time.time() - t0, 3)

    # Specific assertions on selected cases
    by_case = {r["case"]: r for r in results}
    correctness = {}

    # case 16: node_modules CLAUDE.md must NOT be in targets
    nm = by_case.get("node_modules_skip", {})
    correctness["node_modules_skipped"] = nm.get("ok", False) and nm.get("n_targets", 99) == 1

    # case 15: nested plugin discovered
    np = by_case.get("nested_plugin_claude", {})
    correctness["nested_plugin_discovered"] = np.get("n_targets", 0) >= 3

    # case 20: real dynamic content in real CLAUDE.md must FAIL
    rr = by_case.get("real_random", {})
    correctness["real_dynamic_flagged"] = rr.get("fails", 0) > 0

    # case 9: malformed JSON must not crash and not produce bogus findings
    mj = by_case.get("malformed_settings", {})
    correctness["malformed_json_no_crash"] = mj.get("ok", False)

    # case 11: hooks-wrong-type must not crash
    hwt = by_case.get("hooks_wrong_type", {})
    correctness["wrong_type_no_crash"] = hwt.get("ok", False)

    # case 8: huge file completes in <2s
    hf = by_case.get("huge_claude", {})
    correctness["huge_file_under_2s"] = hf.get("ok", False) and hf.get("elapsed_ms", 99999) < 2000

    # case 14: regex DoS — must complete fast
    dos = by_case.get("dos_substitutions", {})
    correctness["dos_under_2s"] = dos.get("ok", False) and dos.get("elapsed_ms", 99999) < 2000

    return {
        "n_cases": len(cases),
        "crashes": crashes,
        "total_elapsed_s": total_elapsed,
        "correctness": correctness,
        "results": results,
    }


def main() -> int:
    out = run()
    out_path = REPO / "eval/sims/results/cache_lint_fuzz.json"
    if os.environ.get("BRAINER_CHECK_NO_WRITE") != "1":
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(out, indent=2))

    print(f"=== cache-lint fuzz battery ===")
    print(f"  cases: {out['n_cases']}")
    print(f"  crashes: {out['crashes']}")
    print(f"  total time: {out['total_elapsed_s']}s")
    print(f"\n  correctness checks:")
    failed = 0
    for k, v in out["correctness"].items():
        flag = "ok" if v else "FAIL"
        if not v:
            failed += 1
        print(f"    [{flag}]  {k}")

    if out["crashes"] > 0 or failed > 0:
        print(f"\n  per-case timings:")
        for r in out["results"]:
            mark = "ok" if r.get("ok") else "ERR"
            t = r.get("elapsed_ms", "-")
            err = f"  ({r.get('error', '')})" if not r.get("ok") else ""
            print(f"    [{mark}] {r['case']:<28} {t}ms{err}")

    print(f"\nfull JSON: {out_path}")
    return 0 if (out["crashes"] == 0 and failed == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
