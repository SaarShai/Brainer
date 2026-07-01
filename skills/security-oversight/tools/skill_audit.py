#!/usr/bin/env python3
"""security-oversight — pre-install audit of a whole (untrusted) agent skill.

The diff-scanner sibling `security_scan.py` asks "what risk did the agent
INTRODUCE in this diff?". This asks the other supply-chain question:

    "is THIS third-party skill safe to install / vendor / trust?"

Brainer vendors external skills into sibling repos and adopts skills from a
fast-moving ecosystem (Snyk: 13% of agent-skill packages ship critical flaws).
Before a skill folder is trusted, walk it and flag:

    prompt_injection  SKILL.md / *.md prose that tries to hijack the agent —
                      system-prompt override, role hijack, safety-bypass,
                      data-exfil instructions, hidden (zero-width / HTML-comment)
                      directives. THE distinctive check: a skill body IS a prompt,
                      so a malicious one attacks via text, which the code-focused
                      diff-scanner never inspects.
    code_exec         dangerous sinks in bundled scripts (reuses security_scan's
                      eval / exec / os-system / pickle / shell-true / curl-pipe-sh library)
    obfuscation       base64/hex/chr-chain payloads feeding an evaluator (hidden code)
    net_exfil         outbound network in a skill that has no business phoning home
    cred_harvest      reads of ~/.ssh, ~/.aws, keyrings, bulk env secrets
    (net_exfil + cred_harvest in the SAME file  ->  EXFIL, escalated to CRITICAL)
    priv_esc          privilege escalation, world-writable/setuid perms, scheduled
                      tasks, and shell-init / authorized-keys writes (persistence)
    fs_structure      symlink escaping the skill dir, bundled binaries/executables,
                      committed secret files (.env/.pem)
    supply_chain      unpinned / typosquatted dependencies in manifests

Verdict:  PASS (install ok) | WARN (review by hand) | FAIL (do not install).
  CRITICAL -> FAIL ; HIGH -> WARN (FAIL under --strict) ; else PASS.

SOUNDNESS LIMIT (always reported): this is fast LEXICAL, STATIC triage. A clean
result means "no obvious malicious pattern found," never "safe." A determined
attacker can evade lexical patterns (indirection, novel encodings, logic bombs);
absence of a finding is NOT proof of safety. Run gitleaks/semgrep for depth and
read the skill yourself before trusting it. This NEVER executes the skill.

CLI:
  python3 skill_audit.py <skill-dir> [--strict] [--json]
  python3 skill_audit.py --repo-url <git-url> [--skill NAME] [--strict] [--json]

Lines/files carrying a `noqa: skill-audit` marker are skipped (so this file and a
skill that legitimately documents these patterns can be audited without self-FP).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import security_scan as ss  # noqa: E402  reuse SECRET/INJECTION patterns + helpers

SEV_ORDER = {"INFO": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
_DOWN = {"CRITICAL": "HIGH", "HIGH": "MEDIUM", "MEDIUM": "LOW", "LOW": "INFO", "INFO": "INFO"}
NOQA = re.compile(r"noqa:\s*skill-audit")

# --------------------------------------------------------------------------
# prompt-injection in SKILL.md / *.md  (THE net-new layer — scanned on RAW text)
# Word gaps are `\s+` so this file's OWN pattern strings do not contain the literal
# trigger phrases (same self-non-match discipline as security_scan.py).
# --------------------------------------------------------------------------
INJECTION_MD = [
    (re.compile(r"(?i)\bignore\s+(?:all\s+|any\s+|the\s+)?(?:previous|prior|above|earlier)\s+"
                r"(?:instructions?|prompts?|rules?|context)"),
     "CRITICAL", "prompt_injection", "system-prompt override ('ignore previous instructions')"),
    (re.compile(r"(?i)\bdisregard\s+(?:all\s+|the\s+|your\s+)?(?:previous|prior|above|system)\b"),
     "CRITICAL", "prompt_injection", "system-prompt override (disregard prior/system)"),
    (re.compile(r"(?i)\byou\s+are\s+now\s+(?:a\s+|an\s+|the\s+)?(?:dan\b|root\b|admin|unrestricted|"
                r"jailbroken|free\s+of|no\s+longer\s+bound|in\s+developer\s+mode|able\s+to\s+ignore)"),
     "CRITICAL", "prompt_injection", "role reassignment to an unrestricted persona"),
    (re.compile(r"(?i)\b(?:act|behave|respond)\s+as\s+(?:root|admin|a\s+superuser|an\s+unrestricted)\b"),
     "CRITICAL", "prompt_injection", "role hijack (act as root/unrestricted)"),
    (re.compile(r"(?i)\bjailbreak\b|\bDAN\s+mode\b|\bpretend\s+(?:you|to\s+have)\b|"
                r"\byou\s+(?:have|are\s+free\s+of|are\s+without)\s+no?\s*"
                r"(?:restrictions|guardrails|limits|rules|safety|filters?)\b|"
                r"\bno\s+(?:guardrails|safety\s+filters?|content\s+filters?)\b"),
     "CRITICAL", "prompt_injection", "guardrail-removal / jailbreak framing"),
    (re.compile(r"(?i)\b(?:disable|skip|bypass|turn\s+off|ignore)\s+(?:the\s+|all\s+|any\s+)?"
                r"(?:safety|security|content\s+filter|guardrails?|moderation)\s*(?:checks?|filters?)?"),
     "CRITICAL", "prompt_injection", "safety-bypass instruction"),
    (re.compile(r"(?i)\b(?:send|upload|post|exfiltrate|transmit|email|leak)\s+(?:the\s+|all\s+|your\s+)?"
                r"(?:secrets?|credentials?|env(?:ironment)?\s+var\w*|\.env\b|api[_-]?keys?|access\s+keys?|"
                r"tokens?|passwords?|private\s+keys?|~/\.(?:ssh|aws))\b"
                r"[^.\n]{0,40}\b(?:to|http|https|@|url|endpoint|server|webhook)\b"),
     "CRITICAL", "prompt_injection", "data-exfiltration instruction (send secrets to ...)"),
    (re.compile(r"(?i)\b(?:run|execute)\s+any\s+(?:command|code|shell)\b|\bfull\s+(?:file\s*system|disk|"
                r"root)\s+access\b|\bunrestricted\s+(?:shell|access|execution)\b"),
     "HIGH", "prompt_injection", "excessive-permission request"),
    (re.compile(r"[​‌‍‎‏⁠﻿]"),
     "HIGH", "prompt_injection", "hidden zero-width unicode (possible concealed instruction)"),
    (re.compile(r"(?is)<!--[^>]*\b(?:ignore|disregard|run|execute|send|upload|disable|act\s+as|"
                r"you\s+are\s+now)\b[^>]*-->"),
     "HIGH", "prompt_injection", "hidden instruction in an HTML comment"),
]

# --------------------------------------------------------------------------
# script-borne risks BEYOND security_scan's INJECTION library (scanned on scripts)
# call patterns use `\s*\(` -> they do not self-match this file's pattern strings.
# --------------------------------------------------------------------------
# Decoders are DUAL-USE (legit data handling uses base64/hex constantly) -> MEDIUM
# on their own. The malicious signal is a decoder FEEDING an evaluator (below) -> CRITICAL.
OBFUSCATION = [
    (re.compile(r"\bbase64\.b64decode\s*\("), "MEDIUM", "obfuscation", "base64 decode (dual-use)"),
    (re.compile(r"\bcodecs\.decode\s*\([^)]*(?:hex|rot13|base64)"), "MEDIUM", "obfuscation", "codecs.decode"),
    (re.compile(r"\bbytes\.fromhex\s*\("), "MEDIUM", "obfuscation", "hex decode (dual-use)"),
    (re.compile(r"(?:\\x[0-9a-fA-F]{2}){8,}"), "MEDIUM", "obfuscation", "long hex-escaped blob"),
    (re.compile(r"\bchr\s*\(\s*\d+\s*\)(?:\s*\+\s*chr\s*\(\s*\d+\s*\)){3,}"),
     "HIGH", "obfuscation", "chr()-chain string building"),
]
# obfuscation feeding an evaluator on the same line = executing hidden code -> CRITICAL
_EVAL_SINK = re.compile(r"\b(?:eval|exec)\s*\(")

NET_SEND = [
    (re.compile(r"\brequests\.(?:post|put|patch)\s*\("), "HIGH", "net_exfil", "outbound HTTP write (requests)"),
    (re.compile(r"\brequests\.get\s*\("), "MEDIUM", "net_exfil", "outbound HTTP GET (requests)"),
    (re.compile(r"\b(?:httpx|aiohttp)\.[A-Za-z_]*(?:post|put|patch|Client|ClientSession)\s*\("),
     "HIGH", "net_exfil", "outbound HTTP (httpx/aiohttp)"),
    (re.compile(r"\burllib\.request\.(?:urlopen|Request)\s*\("), "MEDIUM", "net_exfil", "outbound HTTP (urllib)"),
    (re.compile(r"\bsocket\.(?:connect|create_connection)\s*\("), "HIGH", "net_exfil", "raw socket connection"),
]
# Credential access is DUAL-USE: reading ~/.aws or copying os.environ is common in
# legit tooling (passing env to a subprocess, an aws-helper skill). So these are
# MEDIUM on their own; the CRITICAL signal is the EXFIL COMBO — cred-read AND an
# outbound send in the same file (escalated after the walk).
CRED_HARVEST = [
    (re.compile(r"(?:open|read_text|read_bytes|Path)\s*\([^)]*(?:\.ssh|\.aws|\.gnupg|\.npmrc|\.pypirc|"
                r"\.config/(?:gcloud|gh|secrets)|id_rsa|\.docker/config)"),
     "MEDIUM", "cred_harvest", "reads a credential store (~/.ssh, ~/.aws, ...)"),
    (re.compile(r"\bos\.environ\s*\[\s*['\"](?:AWS_|GITHUB_TOKEN|GH_TOKEN|API[_-]?KEY|SECRET|"
                r"PASSWORD|TOKEN|PRIVATE|OPENAI|ANTHROPIC)"),
     "MEDIUM", "cred_harvest", "reads a secret environment variable"),
    (re.compile(r"\b(?:dict\s*\(\s*os\.environ|os\.environ\.copy\s*\(|json\.dumps\s*\(\s*dict\s*\(\s*os\.environ)"),
     "MEDIUM", "cred_harvest", "reads the full environment (dual-use — flagged only if also sent)"),
]
PRIV_ESC = [
    (re.compile(r"\bsudo\b"), "HIGH", "priv_esc", "sudo / privilege escalation"),  # noqa: skill-audit
    (re.compile(r"\bchmod\s+(?:-R\s+)?(?:0?777|\+s)\b"), "HIGH", "priv_esc", "world-writable/setuid chmod"),  # noqa: skill-audit
    (re.compile(r"(?:>>|>|tee)\s*[^\n]*(?:\.bashrc|\.zshrc|\.profile|\.bash_profile|authorized_keys|"
                r"/etc/(?:cron|passwd|sudoers))"),
     "CRITICAL", "priv_esc", "writes a shell-init / authorized_keys / system file (persistence)"),
    (re.compile(r"\bcrontab\s+|\bschtasks\b|launchctl\s+load"), "HIGH", "priv_esc", "installs a scheduled task"),  # noqa: skill-audit
    (re.compile(r"\b(?:pip|pip3|npm|pnpm|yarn)\s+install\b"), "MEDIUM", "supply_chain", "installs a package at runtime"),  # noqa: skill-audit
]

BINARY_EXT = {".so", ".dll", ".exe", ".dylib", ".bin", ".o", ".a", ".class",
              ".pyc", ".pyo", ".wasm", ".node", ".jar"}
_BIN_MAGIC = (b"\x7fELF", b"MZ", b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xfe\xed\xfa")
SCRIPT_EXT = {".py", ".sh", ".bash", ".zsh", ".js", ".mjs", ".cjs", ".ts", ".rb", ".pl", ".ps1"}
DOC_EXT = {".md", ".markdown", ".rst", ".txt", ".mdx"}

POPULAR_PKGS = {
    "requests", "urllib3", "numpy", "pandas", "flask", "django", "boto3", "botocore",
    "pyyaml", "setuptools", "pip", "cryptography", "certifi", "aiohttp", "httpx",
    "click", "rich", "pytest", "scipy", "pillow", "beautifulsoup4", "lxml",
    "sqlalchemy", "redis", "celery", "jinja2", "fastapi", "pydantic", "openai",
    "anthropic", "tqdm", "python-dateutil", "six", "wheel", "packaging",
}


def _lev1(a: str, b: str) -> bool:
    """True iff a is one Damerau edit from b — a single substitution, insert,
    delete, or ADJACENT TRANSPOSITION. Transpositions (reqeusts<->requests,
    recieve<->receive) are the most common typosquat, so they must count."""
    if a == b:
        return False
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        diffs = [i for i in range(la) if a[i] != b[i]]
        if len(diffs) == 1:
            return True
        if len(diffs) == 2:
            i, j = diffs
            return j == i + 1 and a[i] == b[j] and a[j] == b[i]  # adjacent swap
        return False
    if la > lb:
        a, b = b, a  # a is the shorter
    return any(b[:i] + b[i + 1:] == a for i in range(lb))  # delete one char from b


def _is_binary(fp: Path) -> bool:
    if fp.suffix.lower() in BINARY_EXT:
        return True
    try:
        head = fp.read_bytes()[:512]
    except OSError:
        return False
    if b"\x00" in head:
        return True
    return any(head.startswith(m) for m in _BIN_MAGIC)


def _finding(sev, cat, file, line, snippet, why):
    snip = (snippet or "").strip()
    if len(snip) > 160:
        snip = snip[:157] + "..."
    return {"severity": sev, "category": cat, "file": file, "line": line,
            "snippet": snip, "why": why}


# ss injection labels that signal a MALICIOUS skill (code exec / deserialization /
# remote shell). The app-security ones ss also carries (SQL injection, JWT/TLS off,
# __import__) are NOT skill-trust signals and would false-positive on legit skills,
# so skill-audit ignores them.
_CRIT_SINK = ("eval(", "exec(", "os.system", "os.popen", "shell=true",  # noqa: skill-audit
              "built argv", "pickle", "marshal", "curl|sh")  # noqa: skill-audit


def _scan_script_line(text: str) -> list[tuple[str, str, str]]:
    """Return [(sev, category, why)] for one script line. Reuses security_scan's
    injection + secret libraries (curated for skill-trust), then adds obfuscation/
    exfil/cred/priv layers. Comment lines run only the secret check (a leaked key in
    a comment is real; a dangerous WORD in a comment is noise)."""
    hits: list[tuple[str, str, str]] = []
    code = ss._strip_literals(text)
    for rx, _cls, sev, _owasp, label in ss.SECRET_PATTERNS:
        if rx.search(text):  # secrets live in quotes -> scan raw
            hits.append((sev, "secret", label))
    if text.lstrip().startswith(("#", "//", "*", "/*", "--")):
        return hits  # comment: skip sink/priv/exfil word-matching (pure noise)
    for rx, _cls, _sev, _owasp, label, _inp, scan_raw in ss.INJECTION_PATTERNS:
        if rx.search(text if scan_raw else code):
            lbl = label.lower()
            if any(k in lbl for k in _CRIT_SINK):
                hits.append(("CRITICAL", "code_exec", label))
            elif "yaml" in lbl:
                hits.append(("HIGH", "code_exec", label))
            # else: SQL/JWT/TLS/SSL/__import__ -> not a malicious-skill signal, skip
    # obfuscation & cred paths & hex/base64 blobs live in strings -> scan RAW;
    # net_exfil (the CALL) and priv_esc/pip-install (else a doc string 'pip install X'
    # or a comment/regex mentioning sudo false-positives) -> scan literal-STRIPPED code.
    for rx, sev, cat, label in OBFUSCATION:
        if rx.search(text):
            hits.append((sev, cat, label))
    for rx, sev, cat, label in CRED_HARVEST:
        if rx.search(text):
            hits.append((sev, cat, label))
    for rx, sev, cat, label in NET_SEND:
        if rx.search(code):
            hits.append((sev, cat, label))
    for rx, sev, cat, label in PRIV_ESC:
        if rx.search(code):
            hits.append((sev, cat, label))
    if _EVAL_SINK.search(code) and any(rx.search(text) for rx, *_ in OBFUSCATION):
        hits.append(("CRITICAL", "obfuscation", "decoded payload passed to eval/exec"))
    return hits


def audit_skill(path: str, strict: bool = False) -> dict[str, Any]:
    root = Path(path).resolve()
    warnings: list[str] = []
    if not root.exists() or not root.is_dir():
        return _report(str(root), [], warnings + [f"not a directory: {root}"], strict,
                       mode="error")
    findings: list[dict[str, Any]] = []
    files_scanned = 0
    per_file_cats: dict[str, set[str]] = {}
    # third-party dependency / cache / VCS dirs are NOT the skill's own code —
    # auditing them (pip's shell=True, .venv/bin symlinks, .pyc) drowns the real
    # signal in noise. Prune them; note that the skill bundles vendored deps.
    SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "site-packages",
                 ".mypy_cache", ".pytest_cache", ".tox", ".ruff_cache", ".gradle"}
    vendored = False

    for dirpath, dirnames, filenames in os.walk(root):
        if any(d in SKIP_DIRS or d.endswith(".egg-info") for d in dirnames):
            vendored = True
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info")]
        for name in filenames:
            fp = Path(dirpath) / name
            rel = str(fp.relative_to(root))
            # ---- symlink escape (classic supply-chain trick) ----
            if fp.is_symlink():
                try:
                    target = fp.resolve()
                    if root not in target.parents and target != root:
                        findings.append(_finding("CRITICAL", "fs_structure", rel, 0,
                                                 os.readlink(fp), "symlink escapes the skill directory"))
                    else:
                        findings.append(_finding("INFO", "fs_structure", rel, 0, os.readlink(fp),
                                                 "in-tree symlink"))
                except OSError:
                    findings.append(_finding("HIGH", "fs_structure", rel, 0, name,
                                             "broken/unresolvable symlink"))
                continue
            # ---- committed secret file (.env/.pem/...) ----
            if ss.SENSITIVE_FILE.search(rel):
                findings.append(_finding("HIGH", "fs_structure", rel, 0, name,
                                         "secret-bearing file bundled in the skill"))
            # ---- binaries / executables ----
            if _is_binary(fp):
                findings.append(_finding("HIGH", "fs_structure", rel, 0, name,
                                         "bundled binary/executable — cannot be reviewed as text"))
                continue
            files_scanned += 1
            ext = fp.suffix.lower()
            try:
                if fp.stat().st_size > 2_000_000:
                    findings.append(_finding("LOW", "fs_structure", rel, 0, name,
                                             "unusually large file (>2MB) — could hide a payload"))
                text = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            lines = text.splitlines()
            cats = per_file_cats.setdefault(rel, set())
            for i, line in enumerate(lines, 1):
                if NOQA.search(line):
                    continue
                if ext in DOC_EXT or name.lower() == "skill.md":
                    for rx, sev, cat, label in INJECTION_MD:
                        if rx.search(line):
                            findings.append(_finding(sev, cat, rel, i, line, label))
                            cats.add(cat)
                if ext in SCRIPT_EXT:
                    for sev, cat, why in _scan_script_line(line):
                        findings.append(_finding(sev, cat, rel, i, line, why))
                        cats.add(cat)
            # ---- dependency manifests ----
            if ss.MANIFEST.search(rel):
                findings.extend(_scan_manifest(rel, text))

    if vendored:
        findings.append(_finding("INFO", "fs_structure", ".", 0, "",
                                 "skill bundles vendored deps / caches (.venv/node_modules/site-packages) "
                                 "— not audited here; review those separately, a skill rarely ships them"))
    # net_exfil + cred_harvest in the SAME file  ->  exfiltration, escalate CRITICAL
    for rel, cats in per_file_cats.items():
        if "net_exfil" in cats and "cred_harvest" in cats:
            findings.append(_finding("CRITICAL", "net_exfil", rel, 0, "",
                                     "reads credentials AND sends over the network in the same file "
                                     "— likely exfiltration"))
    # a skill's OWN test fixtures carry deliberate attack strings -> downgrade one
    # notch (lower signal), mirroring security_scan's test-path handling. Not
    # skipped: a payload hidden in a 'test' file still shows, just at lower severity.
    for f in findings:
        if ss._in_test_path(f["file"]):
            f["severity"] = _DOWN[f["severity"]]
            f["why"] += " (test path — lower signal)"
    return _report(str(root), findings, warnings, strict, files_scanned=files_scanned)


def _scan_manifest(rel: str, text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, line in enumerate(text.splitlines(), 1):
        if NOQA.search(line):
            continue
        m = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]+)\s*([<>=!~^]=?)?", line)
        if not m:
            continue
        pkg = m.group(1).lower()
        pinned = bool(re.search(r"==|:\s*['\"]?\d", line)) or "==" in line
        for pop in POPULAR_PKGS:
            if _lev1(pkg, pop):
                out.append(_finding("HIGH", "supply_chain", rel, i, line.strip(),
                                    f"possible typosquat of '{pop}' (dependency confusion)"))
                break
        if not pinned and m.group(2) and rel.lower().endswith((".txt",)):
            out.append(_finding("INFO", "supply_chain", rel, i, line.strip(),
                                "unpinned dependency version"))
    return out


CAVEAT = (
    "SOUNDNESS LIMIT — a clean result means 'no obvious malicious pattern found,' "
    "never 'safe.' This is fast LEXICAL, STATIC triage; it never executes the skill. "
    "A determined attacker can evade lexical patterns (indirection, novel encodings, "
    "logic bombs, multi-file assembly). Absence of a finding is NOT proof of safety: "
    "run gitleaks/semgrep for depth and READ the skill before trusting it."
)


def _report(skill, findings, warnings, strict, files_scanned=0, mode="lexical-audit"):
    # dedupe
    seen, uniq = set(), []
    for f in findings:
        k = (f["severity"], f["category"], f["file"], f["line"], f["why"])
        if k not in seen:
            seen.add(k)
            uniq.append(f)
    findings = sorted(uniq, key=lambda f: (-SEV_ORDER[f["severity"]], f["file"], f["line"]))
    crit = sum(1 for f in findings if f["severity"] == "CRITICAL")
    high = sum(1 for f in findings if f["severity"] == "HIGH")
    if mode == "error":
        verdict = "ERROR"
    elif crit:
        verdict = "FAIL"
    elif high:
        verdict = "FAIL" if strict else "WARN"
    else:
        verdict = "PASS"
    top = "NONE"
    for f in findings:
        if SEV_ORDER[f["severity"]] > SEV_ORDER.get(top, -1):
            top = f["severity"]
    counts = {s: sum(1 for f in findings if f["severity"] == s) for s in SEV_ORDER}
    summary = (f"{Path(skill).name}: {verdict} — {len(findings)} finding(s) across "
               f"{files_scanned} scanned file(s) "
               f"(CRITICAL={counts['CRITICAL']} HIGH={counts['HIGH']} "
               f"MEDIUM={counts['MEDIUM']} LOW={counts['LOW']} INFO={counts['INFO']})")
    return {
        "mode": mode, "skill": skill, "verdict": verdict, "top_severity": top,
        "summary": summary, "counts": counts, "findings": findings,
        "caveat": CAVEAT, "warnings": warnings, "strict": strict,
    }


# --------------------------------------------------------------------------
# repo-URL mode: shallow-clone to a temp dir, audit, clean up. Cloning does NOT
# execute skill code (static files only) -> safe to do before trusting.
# --------------------------------------------------------------------------
def audit_repo_url(url: str, skill: str | None, strict: bool) -> dict[str, Any]:
    if not re.match(r"^https://[\w.-]+/[\w./-]+$", url):
        return _report(url, [], [f"refusing to clone non-https/odd URL: {url}"], strict, mode="error")
    tmp = tempfile.mkdtemp(prefix="skill-audit-")
    try:
        r = subprocess.run(["git", "clone", "--depth", "1", "--no-tags", url, tmp],
                           capture_output=True, text=True, timeout=120,
                           env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
        if r.returncode != 0:
            return _report(url, [], [f"git clone failed: {r.stderr.strip()[:200]}"], strict, mode="error")
        target = Path(tmp)
        if skill:
            hits = [p for p in target.rglob(skill) if p.is_dir()]
            if hits:
                target = hits[0]
            else:
                return _report(url, [], [f"skill '{skill}' not found in repo"], strict, mode="error")
        rep = audit_skill(str(target), strict=strict)
        rep["skill"] = f"{url}" + (f" [{skill}]" if skill else "")
        return rep
    except Exception as exc:
        return _report(url, [], [f"clone/audit error: {exc}"], strict, mode="error")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def render_markdown(rep: dict[str, Any]) -> str:
    badge = {"PASS": "✅ PASS", "WARN": "⚠️ WARN", "FAIL": "❌ FAIL"}.get(rep["verdict"], rep["verdict"])
    L = [f"# Skill security audit — {badge}", "", f"**{rep['summary']}**", "",
         f"> {rep['caveat']}", ""]
    for w in rep.get("warnings", []):
        L.append(f"> WARNING: {w}")
    if rep.get("warnings"):
        L.append("")
    L += ["## Findings", "", "| severity | category | file:line | detail |",
          "| --- | --- | --- | --- |"]
    for f in rep["findings"]:
        loc = f"{f['file']}:{f['line']}" if f["line"] else f["file"]
        L.append(f"| {f['severity']} | {f['category']} | `{loc}` | {f['why']} |")
    if not rep["findings"]:
        L.append("| _(none found — see soundness limit)_ | | | |")
    L += ["", "## Verdict", "",
          {"FAIL": "Do NOT install without remediation — critical/high findings above.",
           "WARN": "Review the findings by hand before installing.",
           "PASS": "No obvious malicious pattern found — but this is triage, not proof; read it yourself.",
           "ERROR": "Could not audit (see warnings) — treat as unverified; do not trust."}.get(rep["verdict"], ""),
          ""]
    return "\n".join(L)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Pre-install security audit of an agent skill.")
    ap.add_argument("path", nargs="?", help="skill directory to audit")
    ap.add_argument("--repo-url", help="git URL to shallow-clone and audit")
    ap.add_argument("--skill", help="skill subfolder name inside the repo")
    ap.add_argument("--strict", action="store_true", help="any HIGH becomes FAIL")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of markdown")
    args = ap.parse_args(argv[1:])
    try:
        if args.repo_url:
            rep = audit_repo_url(args.repo_url, args.skill, args.strict)
        elif args.path:
            rep = audit_skill(args.path, strict=args.strict)
        else:
            ap.error("give a skill directory or --repo-url")
            return 2
    except Exception as exc:  # never crash: degrade
        rep = _report(args.path or args.repo_url or "?", [], [f"audit error: {exc}"],
                      args.strict, mode="error")
    print(json.dumps(rep, indent=2) if args.json else render_markdown(rep))
    # exit code: 0 PASS, 1 WARN, 2 FAIL/ERROR (so CI / hooks can gate)
    return {"PASS": 0, "WARN": 1, "FAIL": 2, "ERROR": 2}.get(rep["verdict"], 0)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
