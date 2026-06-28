#!/usr/bin/env python3
"""security-oversight — fast pre-ship security triage of a git diff.

Karpathy's mandate for agentic engineering: "You are not allowed to introduce
vulnerabilities because of vibe coding." Agents produce *plausible-but-insecure*
code that slips in **silently** when no one inspects the diff. This is the
inspection layer — the security sibling of `impact-of-change`:

    impact-of-change  -> "what BREAKS if I change this?"  (blast radius)
    security-oversight -> "what could be ABUSED in what I changed?"  (attack surface)

It reads the diff's **added** lines and flags four OWASP-anchored classes,
scoped to what a coding agent actually introduces in a repo:

    secret        leaked credential / key / token, or a secret-bearing file
                  about to be committed            (OWASP LLM02 / ASI03)
    injection     a dangerous sink an agent wrote — eval/exec/shell=True/
                  pickle/unsafe-yaml/SQL-by-format/TLS-off  (ASI05 / LLM05)
    supply_chain  a new/unpinned dependency, or a change to the skill / hook /
                  installer injection surface       (ASI04 / LLM03)
    authz         security-sensitive business logic changed (auth / payment /
                  token / permission) — the "plausible-but-insecure" class
                  (Karpathy's MenuGen Stripe-by-email bug) that scanners can
                  NOT mechanically judge -> emitted as REVIEW   (ASI03 / ASI02)

Design (mirrors impact-of-change, deliberately):
  - Fast LEXICAL triage over the diff is the engine. It does NOT shell into
    heavy scanners (fragile, slow, hard to test); instead it DETECTS which
    reputable scanners are installed (gitleaks/semgrep/osv-scanner/pip-audit)
    and RECOMMENDS running them for verified depth.
  - It NEVER blocks. Any error degrades to a minimal report (exit 0 on the
    happy/degraded path; only argparse/IO catastrophe returns 1 on stderr).
  - It does NOT modify code or auto-fix. It routes HIGH/MEDIUM findings to
    `verify-before-completion` and surfaces REVIEW findings for a human.

SOUNDNESS LIMIT (always reported): absence of a finding is NOT proof of safety.
This sees only introduced text — not semantic vulnerabilities, multi-file taint,
or anything in unchanged code. Clearing the gate means "no obvious introduced
risk found," never "secure."

CLI:
  python3 security_scan.py [--repo DIR] [--diff working|staged|<sha>|<a>..<b>]
                           [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

# Severity ordering. REVIEW sits ABOVE LOW but BELOW MEDIUM: a human-judgment
# item outranks a benign low, but a definite medium-severity sink outranks an
# unknown. (Mirrors impact-of-change's UNKNOWN placement vs LOW.)
SEV_ORDER = {"NONE": -1, "LOW": 0, "REVIEW": 1, "MEDIUM": 2, "HIGH": 3}


# ==========================================================================
# detection tables  (high-signal / precision-first — a noisy gate gets ignored)
# ==========================================================================
# Each: (compiled regex, class, base_severity, owasp_ref, label).
# Patterns match the *content* an agent introduces, not security_scan.py's own
# raw pattern strings (those contain `\s*\(`, not a literal `(`, so they don't
# self-match).
SECRET_PATTERNS = [
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP |DSA )?PRIVATE KEY-----"),
     "secret", "HIGH", "LLM02", "private key material"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
     "secret", "HIGH", "LLM02", "AWS access key id"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
     "secret", "HIGH", "LLM02", "GitHub token"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
     "secret", "HIGH", "LLM02", "Slack token"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
     "secret", "HIGH", "LLM02", "Google API key"),
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
     "secret", "HIGH", "LLM02", "OpenAI-style API key"),
    (re.compile(r"\b(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{16,}\b"),
     "secret", "HIGH", "LLM02", "Stripe API key"),
    # assignment of a quoted literal to a secret-named variable. Boundaries are
    # non-letter (NOT \b): `_` is a word char, so \b MISSES the common UPPER_SNAKE
    # form (DB_PASSWORD, SECRET_TOKEN, JWT_SECRET). Value class is non-quote/
    # non-space so symbol-laden passwords (S3cr3t@P4ss!) match but prose doesn't.
    (re.compile(r"(?i)(?<![A-Za-z])(?:api[_-]?key|secret|password|passwd|token|"
                r"client[_-]?secret|access[_-]?token|auth[_-]?token)(?![A-Za-z])"
                r"\s*[:=]\s*['\"][^'\"\s]{12,}['\"]"),
     "secret", "HIGH", "LLM02", "hardcoded credential assignment"),
]

# Dangerous sinks. Tuple: (rx, class, base_sev, owasp, label, input_bearing, scan_raw)
#   input_bearing=True -> HIGH if the line also smells of external input, else base.
#   scan_raw=True       -> match the RAW line (the danger lives INSIDE a string:
#                          curl|sh, SQL by %/concat, bash -c, JWT verify=False);
#                          scan_raw=False -> match the literal-stripped line (the
#                          danger is the CALL; stripping avoids string-data FPs).
INJECTION_PATTERNS = [
    (re.compile(r"\beval\s*\("), "injection", "MEDIUM", "ASI05", "eval()", True, False),
    (re.compile(r"\bexec\s*\("), "injection", "MEDIUM", "ASI05", "exec()", True, False),
    (re.compile(r"\bos\.system\s*\("), "injection", "HIGH", "ASI05", "os.system()", False, False),
    (re.compile(r"\bos\.popen\s*\("), "injection", "HIGH", "ASI05", "os.popen()", False, False),
    (re.compile(r"subprocess\.[A-Za-z_]+\([^)]*shell\s*=\s*True"),
     "injection", "HIGH", "ASI05", "subprocess(shell=True)", False, False),
    # subprocess([..., "-c", tainted]) — RCE even with shell=False
    (re.compile(r"['\"](?:ba)?sh['\"]\s*,\s*['\"]-c['\"]"),
     "injection", "HIGH", "ASI05", "sh/bash -c with a built argv — RCE without shell=True", False, True),
    (re.compile(r"\b(?:pickle|cPickle)\.loads?\s*\("),
     "injection", "HIGH", "ASI05", "pickle.load() — arbitrary deserialization", False, False),
    (re.compile(r"\bmarshal\.loads?\s*\("),
     "injection", "HIGH", "ASI05", "marshal.load()", False, False),
    (re.compile(r"\byaml\.load\s*\((?![^)]*Loader\s*=\s*[A-Za-z_]*Safe)"),
     "injection", "HIGH", "ASI05", "yaml.load() without SafeLoader", False, False),
    (re.compile(r"\byaml\.unsafe_load\s*\("),
     "injection", "HIGH", "ASI05", "yaml.unsafe_load()", False, False),
    (re.compile(r"\.execute\s*\(\s*f['\"]"),
     "injection", "HIGH", "ASI05", "SQL via f-string (injection)", False, False),
    (re.compile(r"\.execute\s*\([^)]*%[^)]*%"),
     "injection", "MEDIUM", "ASI05", "SQL via %-format (injection)", False, True),
    (re.compile(r"\.execute\s*\(\s*['\"][^'\"]*['\"]\s*\+"),
     "injection", "HIGH", "ASI05", "SQL via string concatenation (injection)", False, True),
    (re.compile(r"verify[_-]?signature['\"]?\s*[:=]\s*False"),
     "injection", "HIGH", "ASI03", "JWT/signature verification disabled — auth bypass", False, True),
    (re.compile(r"\bverify\s*=\s*False"),
     "injection", "MEDIUM", "ASI05", "TLS verification disabled", False, False),
    (re.compile(r"ssl\._create_unverified_context"),
     "injection", "MEDIUM", "ASI05", "unverified SSL context", False, False),
    (re.compile(r"\b__import__\s*\("),
     "injection", "MEDIUM", "ASI05", "__import__() dynamic import", True, False),
    # shell: curl|wget piped straight into a shell (danger is inside the string)
    (re.compile(r"\b(?:curl|wget)\b[^\n|]*\|\s*(?:sudo\s+)?(?:ba)?sh\b"),
     "injection", "HIGH", "ASI04", "curl|sh — remote code into shell", False, True),
]

# Weak primitives -> REVIEW (could be a non-security use; a human decides).
REVIEW_PATTERNS = [
    (re.compile(r"\bhashlib\.(?:md5|sha1)\s*\("),
     "authz", "REVIEW", "ASI03", "weak hash (md5/sha1) — REVIEW if used for auth/integrity"),
    (re.compile(r"(?i)\bDEBUG\s*=\s*True\b"),
     "authz", "REVIEW", "ASI03", "DEBUG=True — REVIEW (must be off in production)"),
]

# Security-sensitive business logic. A change touching these can be the
# plausible-but-insecure class scanners miss -> REVIEW (human must clear).
# Matched by IDENTIFIER TOKEN (snake_case + camelCase split), not by substring:
# `\bpayment\b` fails inside `charge_payment` (underscore is a word char), while
# substring matching would over-fire ('auth' inside 'author'). Tokenizing gives
# both precision and snake/camel coverage.
AUTHZ_STEMS = {
    "auth", "authn", "authz", "login", "logout", "password", "passwd", "token",
    "jwt", "oauth", "session", "cookie", "permission", "permissions", "role",
    "roles", "admin", "privilege", "acl", "payment", "payments", "stripe",
    "billing", "charge", "refund", "signature", "hmac", "csrf", "cors",
    "secret", "credential", "credentials", "encrypt", "decrypt", "verify",
    "verified",
}
_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")
# the line must look like CODE (def/call/assignment/control), not prose, so a
# keyword in a sentence doesn't fire.
_CODE_LINE = re.compile(
    r"\bdef\b|\bclass\b|\bfunction\b|=>|\bif\b|\breturn\b|\bfor\b|\bwhile\b"
    r"|[A-Za-z_]\w*\s*\(|[^=!<>]=[^=]")


def _id_tokens(text: str) -> set[str]:
    """Lowercased identifier tokens, splitting snake_case AND camelCase."""
    out: set[str] = set()
    for part in re.split(r"[^A-Za-z0-9]+", text):
        for t in _CAMEL.findall(part):
            out.add(t.lower())
    return out


def _strip_literals(text: str) -> str:
    """Blank out quoted string CONTENTS and trailing comments.

    Used for injection/authz/review matching so a security token that appears as
    DATA — a detection rule's own pattern, a label, an `AUTHZ_STEMS` entry, a doc
    comment — does not fire as if it were a dangerous CALL or an authz DECISION.
    A real sink keeps its call paren OUTSIDE the quotes (`os.system("ls")` ->
    `os.system("")`, still matched). SECRET scanning deliberately does NOT use
    this (a leaked credential lives inside the quotes)."""
    t = re.sub(r"'(?:[^'\\]|\\.)*'", "''", text)
    t = re.sub(r'"(?:[^"\\]|\\.)*"', '""', t)
    t = re.sub(r"\s+#.*$", "", t)
    t = re.sub(r"\s+//.*$", "", t)
    return t

# crude "external input" smell on a sink line -> escalate to HIGH
INPUT_SMELL = re.compile(
    r"(?i)\b(request|req\.|input\s*\(|sys\.argv|args\.|params|query|body|"
    r"payload|user[_-]?input|form\[|\.get\(|environ|stdin|recv)\b")

# files that should essentially never be committed. `credentials` is matched only
# with a DATA extension (credentials.json/.yaml) — a `credentials.py` MODULE is
# source, not a secret, and must not flag HIGH on its name alone.
SENSITIVE_FILE = re.compile(
    r"(?i)(^|/)(\.env(\.|$)|.*\.pem$|.*\.key$|id_rsa|id_dsa|id_ecdsa|.*\.pfx$|"
    r".*\.p12$|.*\.keystore$|\.npmrc$|\.pypirc$|"
    r"credentials\.(ya?ml|json|txt|ini|cfg|env)|"
    r"secrets?\.(ya?ml|json|txt|ini)$|HANDOFF\.md$)")

# dependency manifests -> a changed dep is a supply-chain event
MANIFEST = re.compile(
    r"(?i)(^|/)(requirements[^/]*\.txt|pyproject\.toml|setup\.(py|cfg)|"
    r"Pipfile(\.lock)?|poetry\.lock|package(-lock)?\.json|yarn\.lock|"
    r"pnpm-lock\.yaml|go\.(mod|sum)|Cargo\.(toml|lock)|Gemfile(\.lock)?|"
    r"[^/]*\.gemspec)$")

# the EXECUTABLE skill/hook/installer injection surface (Brainer-specific supply
# chain: Snyk found 13% of agent-skill packages ship critical flaws). Scoped to
# things that actually run — NOT SKILL.md/docs, which are prose (those would make
# every doc edit a finding in a skills repo).
INJECT_SURFACE = re.compile(
    r"(?i)(^|/)(install\.sh|.*/tools/install\.sh|hooks?\.(json|sh|py)|"
    r"settings\.json)$")

# doc/data files: scan for SECRETS and sensitive-file/manifest status, but NOT
# for code sinks or authz-keyword logic (prose mentioning 'token'/'session' is
# not a security decision — the dominant authz false-positive source).
_DOC_DATA_EXT = (".md", ".markdown", ".rst", ".txt", ".json", ".lock", ".toml",
                 ".cfg", ".ini", ".yaml", ".yml", ".csv", ".xml", ".html", ".svg")

# reputable external scanners this skill recommends (does not wrap)
SCANNERS = {
    "gitleaks": "secret scanning",
    "trufflehog": "secret scanning",
    "semgrep": "SAST / dangerous-sink detection",
    "osv-scanner": "dependency CVEs (Google OSV)",
    "pip-audit": "python dependency CVEs (PyPA)",
    "bandit": "python SAST",
}


# ==========================================================================
# git diff acquisition
# ==========================================================================
def _git(args: list[str], repo: str) -> str:
    res = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True,
        env={**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null",
             "GIT_CONFIG_SYSTEM": "/dev/null"},
    )
    if res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {res.stderr.strip()}")
    return res.stdout


def _diff_args(diff_spec: str, name_status: bool = False) -> list[str]:
    """Translate a diff spec into `git diff` arguments.

    working  -> uncommitted (working tree + index) vs HEAD
    staged   -> index vs HEAD (what a pre-commit hook sees)
    <a>..<b> -> range
    <sha>    -> that commit vs its parent
    """
    tail = ["--name-status"] if name_status else []
    if diff_spec in ("working", "", None):
        return ["diff", *tail, "HEAD"]
    if diff_spec == "staged":
        return ["diff", *tail, "--cached"]
    if ".." in diff_spec:
        return ["diff", *tail, diff_spec]
    return ["diff", *tail, f"{diff_spec}^", diff_spec]


def parse_added_lines(diff_text: str) -> list[dict[str, Any]]:
    """Yield {file, line, text} for each ADDED (+) line, with new-file line numbers."""
    cur_file: str | None = None
    new_lineno = 0
    out: list[dict[str, Any]] = []
    for line in diff_text.splitlines():
        if line.startswith("diff --git"):
            cur_file = None
            continue
        if line.startswith("+++ "):
            m = re.match(r"\+\+\+ b/(.+)$", line)
            cur_file = m.group(1) if m else None
            continue
        if line.startswith("--- "):
            continue
        if line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            new_lineno = int(m.group(1)) if m else 0
            continue
        if cur_file is None:
            continue
        if line.startswith("+"):
            out.append({"file": cur_file, "line": new_lineno, "text": line[1:]})
            new_lineno += 1
        elif line.startswith("-"):
            continue  # removed line: does not advance new-file numbering
        else:
            new_lineno += 1  # context line advances new-file numbering
    return out


def changed_files(repo: str, diff_spec: str) -> list[tuple[str, str]]:
    """[(status, path)] from --name-status. status in A/M/D/R... ; best-effort."""
    try:
        raw = _git(_diff_args(diff_spec, name_status=True), repo)
    except Exception:
        return []
    out: list[tuple[str, str]] = []
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            out.append((parts[0][:1], parts[-1]))
    return out


def _untracked_files(repo: str) -> list[str]:
    try:
        return [p for p in _git(["ls-files", "--others", "--exclude-standard"],
                                repo).splitlines() if p]
    except Exception:
        return []


def _untracked_added(repo: str, path: str, max_bytes: int = 512_000) -> list[dict[str, Any]]:
    """Synthesize added-line records for a whole untracked file. `git diff` OMITS
    untracked files, so a brand-NEW file's secret slips past the default `working`
    mode silently — the most common agent leak path. Skips binary/oversized files."""
    fp = Path(repo) / path
    try:
        if fp.stat().st_size > max_bytes:
            return []
        text = fp.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    if "\x00" in text:  # binary
        return []
    return [{"file": path, "line": i, "text": line}
            for i, line in enumerate(text.splitlines(), 1)]


# ==========================================================================
# detection
# ==========================================================================
def _in_test_path(path: str) -> bool:
    p = path.lower()
    return "test" in p or "/fixtures/" in p or p.endswith(".example")


def _skip_code_patterns(path: str) -> bool:
    """Doc/data file -> run only secret + file-level checks, not code sinks/authz."""
    return path.lower().endswith(_DOC_DATA_EXT)


def _downgrade(sev: str) -> str:
    order = ["HIGH", "MEDIUM", "REVIEW", "LOW"]
    i = order.index(sev) if sev in order else len(order) - 1
    return order[min(i + 1, len(order) - 1)]


def _finding(cls, severity, file, line, snippet, owasp, why, detector="lexical",
             verified=False):
    snip = snippet.strip()
    if len(snip) > 160:
        snip = snip[:157] + "..."
    return {
        "class": cls, "severity": severity, "file": file, "line": line,
        "snippet": snip, "owasp": owasp, "why": why,
        "detector": detector, "verified": verified,
    }


def scan_added_lines(added: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for rec in added:
        text, file, ln = rec["text"], rec["file"], rec["line"]
        in_test = _in_test_path(file)
        skip_code = _skip_code_patterns(file)
        # secrets are scanned RAW (they live inside quotes); code patterns use the
        # literal-stripped line UNLESS the pattern's danger is the string payload
        # (scan_raw). A security token used as DATA (a rule, a label, doc prose)
        # therefore doesn't misfire as a CALL or an authz DECISION.
        code = _strip_literals(text)

        for rx, cls, sev, owasp, label in SECRET_PATTERNS:
            if rx.search(text):
                s = _downgrade(sev) if in_test else sev
                findings.append(_finding(
                    cls, s, file, ln, text, owasp,
                    f"{label}" + (" (in test path)" if in_test else "")))

        # code-sink / authz classes do not apply to doc/data files (prose noise)
        if skip_code:
            continue

        for rx, cls, sev, owasp, label, input_bearing, scan_raw in INJECTION_PATTERNS:
            subject = text if scan_raw else code
            if rx.search(subject):
                s = sev
                if input_bearing and INPUT_SMELL.search(subject):
                    s = "HIGH"
                if in_test:
                    s = _downgrade(s)
                findings.append(_finding(
                    cls, s, file, ln, text, owasp,
                    f"{label}" + (" — reaches external input" if (input_bearing and
                     INPUT_SMELL.search(subject)) else "") +
                    (" (in test path)" if in_test else "")))

        for rx, cls, sev, owasp, label in REVIEW_PATTERNS:
            if rx.search(code):
                findings.append(_finding(cls, sev, file, ln, text, owasp, label))

        # authz / identity-sensitive business logic -> REVIEW. Fire only on code
        # lines (not comments/prose) whose identifier tokens hit a security stem.
        is_comment = text.lstrip().startswith(("#", "//", "*", "/*", "--"))
        authz_hit = _id_tokens(code) & AUTHZ_STEMS
        if authz_hit and not is_comment and _CODE_LINE.search(code):
            # don't double-report a line already caught as secret/injection
            already = any(f["file"] == file and f["line"] == ln for f in findings)
            if not already:
                kw = sorted(authz_hit)[0]
                findings.append(_finding(
                    "authz", "REVIEW", file, ln, text, "ASI03",
                    f"security-sensitive logic changed (matches '{kw}') — a human "
                    "must confirm the trust/identity/authorization decision is "
                    "correct; scanners cannot verify business-logic authz "
                    "(the MenuGen Stripe-by-email class)"))
    return findings


def _collapse_authz(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One file can change security-sensitive logic on many lines; N separate
    REVIEW rows is noise. Collapse the keyword-based authz REVIEW findings to ONE
    per file, listing the matched stems + line numbers. Weak-primitive REVIEWs
    (md5/DEBUG) and all other findings pass through untouched."""
    kw = [f for f in findings if f["class"] == "authz" and f["severity"] == "REVIEW"
          and f["why"].startswith("security-sensitive logic changed at ") is False
          and f["why"].startswith("security-sensitive logic changed")]
    if not kw:
        return findings
    rest = [f for f in findings if f not in kw]
    by_file: dict[str, list[dict[str, Any]]] = {}
    for f in kw:
        by_file.setdefault(f["file"], []).append(f)
    out = list(rest)
    for fp, group in by_file.items():
        stems = sorted({m.group(1) for g in group
                        if (m := re.search(r"matches '([^']+)'", g["why"]))})
        lines = sorted({g["line"] for g in group})
        shown = ", ".join(str(n) for n in lines[:8]) + ("…" if len(lines) > 8 else "")
        out.append(_finding(
            "authz", "REVIEW", fp, lines[0], "", "ASI03",
            f"security-sensitive logic changed at {len(lines)} site(s) "
            f"(stems: {', '.join(stems)}; lines: {shown}) — a human must confirm "
            "the trust/identity/authorization decisions are correct; scanners "
            "cannot verify business-logic authz (the MenuGen Stripe-by-email class)"))
    return out


def scan_files(files: list[tuple[str, str]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for status, path in files:
        if status == "D":
            continue
        in_test = _in_test_path(path)
        suffix = " (in test path)" if in_test else ""
        if SENSITIVE_FILE.search(path):
            sev = _downgrade("HIGH") if in_test else "HIGH"
            findings.append(_finding(
                "secret", sev, path, 0, path, "LLM02",
                "secret-bearing file present in the diff — do NOT commit "
                "credentials/keys (add to .gitignore)" + suffix))
        elif MANIFEST.search(path):
            sev = _downgrade("MEDIUM") if in_test else "MEDIUM"
            findings.append(_finding(
                "supply_chain", sev, path, 0, path, "ASI04",
                "dependency manifest changed — verify each added/updated package "
                "is trusted and version-pinned (typosquat / malicious-package risk)"
                + suffix))
        elif INJECT_SURFACE.search(path):
            findings.append(_finding(
                "supply_chain", "REVIEW", path, 0, path, "ASI04",
                "skill/hook/installer injection surface changed — confirm "
                "provenance before trusting (Snyk: 13% of agent-skill packages "
                "ship critical flaws); for siblings, never blind-copy"))
    return findings


# ==========================================================================
# top-level analysis
# ==========================================================================
CAVEAT = (
    "SOUNDNESS LIMIT — absence of a finding is NOT proof of safety. This is fast "
    "lexical triage over the diff's ADDED lines: it sees only introduced text, "
    "not semantic vulnerabilities, multi-file taint, or anything in unchanged "
    "code. Clearing this gate means 'no obvious introduced risk found,' never "
    "'secure.' Route HIGH/MEDIUM to verify-before-completion, hand REVIEW items "
    "to a human, and run the reputable scanners below for verified depth."
)


def analyze(repo: str, diff_spec: str = "working") -> dict[str, Any]:
    repo = str(Path(repo).resolve())
    warnings: list[str] = []
    try:
        diff_text = _git(_diff_args(diff_spec), repo)
    except Exception as exc:
        # degrade, never block
        return {
            "mode": "error", "risk": "NONE",
            "summary": f"could not read git diff ({exc}); nothing scanned.",
            "findings": [], "routed": [], "review": [],
            "scanners_available": [], "recommendations": [],
            "caveat": CAVEAT, "warnings": [f"git diff failed: {exc}"],
        }

    added = parse_added_lines(diff_text)
    files = changed_files(repo, diff_spec)
    # git diff OMITS untracked files; in working mode fold them in so a brand-NEW
    # file's secret/sink is not silently missed (the default-mode blind spot).
    if diff_spec in ("working", "", None):
        untracked = _untracked_files(repo)
        for p in untracked:
            files.append(("A", p))            # name-based checks (catches key.p12 etc.)
            added += _untracked_added(repo, p)  # content checks ([] if binary/oversized)
        if untracked:
            shown = ", ".join(untracked[:5]) + ("…" if len(untracked) > 5 else "")
            warnings.append(
                f"folded in {len(untracked)} untracked file(s) git diff omits "
                f"({shown}); any binary/oversized untracked file is name-checked only.")
    findings = scan_added_lines(added) + scan_files(files)
    findings = _collapse_authz(findings)

    # dedupe identical (class,file,line,why)
    seen = set()
    uniq: list[dict[str, Any]] = []
    for f in findings:
        k = (f["class"], f["file"], f["line"], f["why"])
        if k not in seen:
            seen.add(k)
            uniq.append(f)
    findings = sorted(uniq, key=lambda f: (-SEV_ORDER[f["severity"]], f["file"], f["line"]))

    overall = "NONE"
    for f in findings:
        if SEV_ORDER[f["severity"]] > SEV_ORDER[overall]:
            overall = f["severity"]

    routed = [f for f in findings if f["severity"] in ("HIGH", "MEDIUM")]
    review = [f for f in findings if f["severity"] == "REVIEW"]
    available = [n for n in SCANNERS if shutil.which(n)]

    summary = (
        f"{len(added)} added line(s) across {len(files)} file(s); "
        f"{len(findings)} finding(s) — risk = {overall}"
        + (f"; {len(review)} need human REVIEW" if review else "")
    )

    return {
        "mode": "lexical-triage",
        "risk": overall,
        "summary": summary,
        "findings": findings,
        "routed": routed,
        "review": review,
        "scanners_available": available,
        "recommendations": _recommendations(findings, available),
        "caveat": CAVEAT,
        "warnings": warnings,
    }


def _recommendations(findings, available) -> list[str]:
    recs: list[str] = []
    has = {f["class"] for f in findings}
    if any(f["severity"] == "HIGH" for f in findings):
        recs.append("HIGH finding(s): do not commit until cleared; route to "
                    "verify-before-completion before any done-claim.")
    if "secret" in has:
        tool = "gitleaks" if "gitleaks" in available else "trufflehog" if \
            "trufflehog" in available else None
        recs.append(f"secret(s): rotate any real credential NOW (a committed secret "
                    f"is compromised even if removed later)." + (
                        f" Corroborate with `{tool} detect`." if tool else
                        " Install gitleaks/trufflehog for verified secret scanning."))
    if "injection" in has:
        recs.append("injection sink(s): " + (
            "run `semgrep --config auto` on the changed files for verified SAST."
            if "semgrep" in available else
            "install semgrep/bandit for verified dangerous-sink analysis."))
    if "supply_chain" in has:
        recs.append("dependency/skill-surface change(s): " + (
            "run `osv-scanner` / `pip-audit` on the manifest for known CVEs."
            if ("osv-scanner" in available or "pip-audit" in available) else
            "install osv-scanner/pip-audit to check added packages for CVEs;") +
            " pin versions and confirm provenance.")
    if any(f["severity"] == "REVIEW" for f in findings):
        recs.append("REVIEW item(s): a human must judge these — business-logic "
                    "authz and weak-primitive uses cannot be cleared mechanically.")
    if not findings:
        recs.append("No introduced risk found in the diff — but see the soundness "
                    "limit; this is triage, not proof. Run a full scan before release.")
    recs.append("Then hand HIGH/MEDIUM to verify-before-completion to gate the done-claim.")
    return recs


# ==========================================================================
# markdown rendering
# ==========================================================================
def render_markdown(rep: dict[str, Any]) -> str:
    L: list[str] = []
    L.append(f"# Security oversight ({rep['mode']})")
    L.append("")
    for w in rep.get("warnings", []):
        L.append(f"> WARNING: {w}")
    if rep.get("warnings"):
        L.append("")
    L.append("## Summary")
    L.append("")
    L.append(rep["summary"])
    L.append("")
    L.append(f"> {rep['caveat']}")
    L.append("")
    L.append("## Findings")
    L.append("")
    L.append("| severity | class | file:line | owasp | detail |")
    L.append("| --- | --- | --- | --- | --- |")
    for f in rep["findings"]:
        loc = f"{f['file']}:{f['line']}" if f["line"] else f["file"]
        tag = "" if f["verified"] else " *(unverified)*"
        L.append(f"| {f['severity']} | {f['class']} | `{loc}` | {f['owasp']} | "
                 f"{f['why']}{tag} |")
    if not rep["findings"]:
        L.append("| _(none introduced in diff)_ | | | | |")
    L.append("")
    if rep["review"]:
        L.append("## Needs human REVIEW (cannot be cleared mechanically)")
        L.append("")
        for f in rep["review"]:
            loc = f"{f['file']}:{f['line']}" if f["line"] else f["file"]
            L.append(f"- `{loc}` — {f['why']}")
        L.append("")
    L.append("## Scanners")
    L.append("")
    if rep["scanners_available"]:
        L.append("Available for verified depth: "
                 + ", ".join(f"`{s}`" for s in rep["scanners_available"]))
    else:
        L.append("None of gitleaks/semgrep/osv-scanner/pip-audit detected — "
                 "install for verified depth.")
    L.append("")
    L.append("## Recommendations")
    L.append("")
    for r in rep["recommendations"]:
        L.append(f"- {r}")
    L.append("")
    return "\n".join(L)


# ==========================================================================
# CLI
# ==========================================================================
def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description="Fast security triage of a git diff (Karpathy/OWASP-anchored).")
    ap.add_argument("--repo", default=".", help="repo root (default: cwd)")
    ap.add_argument("--diff", default="working",
                    help="working | staged | <sha> | <a>..<b> (default: working)")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of markdown")
    args = ap.parse_args(argv[1:])
    try:
        rep = analyze(repo=args.repo, diff_spec=args.diff)
    except Exception as exc:
        print(f"# Security oversight (ERROR)\n\n> Could not analyze: {exc}",
              file=sys.stderr)
        return 1
    print(json.dumps(rep, indent=2) if args.json else render_markdown(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
