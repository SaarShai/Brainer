<!-- demoted-from-skill: security-oversight — 2026-07-22 (Great Pruning A2, usage-evidence purge) -->
<!-- Tool scripts (security_scan.py, skill_audit.py, and their tests) were
     MOVED — not deleted — to skills/_shared/tools/security-oversight/, since
     they remain directly callable. Only the SKILL.md prose body is demoted
     to this brief. -->

# security-oversight (delegate brief) — pre-ship security triage of a diff

Triages a `git diff`'s **added lines** for INTRODUCED risk across four
OWASP-anchored classes. Report-only: never blocks, never auto-fixes.
Absence of a finding is NOT proof of safety — this is fast lexical triage,
not a full SAST engine.

## The four classes

| class | catches |
|---|---|
| `secret` | hardcoded key/token/credential; a secret-bearing file (`.env`, `*.pem`) in the diff |
| `injection` | dangerous sink — `eval`/`exec`/`os.system`/`shell=True`/`pickle`/unsafe-yaml/SQL-by-format/`curl\|sh` |
| `supply_chain` | new/unpinned dependency; a change to the skill/hook/installer injection surface |
| `authz` | security-sensitive business logic changed (auth/payment/token/permission) — flagged REVIEW only, never auto-cleared |

## Protocol

```bash
python3 skills/_shared/tools/security-oversight/security_scan.py --repo . --diff working   # uncommitted, markdown
python3 skills/_shared/tools/security-oversight/security_scan.py --diff staged --json       # what a pre-commit hook sees
python3 skills/_shared/tools/security-oversight/security_scan.py --diff <sha>                # a specific commit/range
```

Read the report (Summary/Findings/Needs-human-REVIEW/Scanners/
Recommendations). Route HIGH/MEDIUM to a verification pass before shipping;
hand REVIEW items to a human — never self-clear business-logic authz. Any
committed secret is compromised — rotate it, don't just delete it.

## Severity

**HIGH** — secret/secret-file; an input-bearing or always-dangerous sink;
a known-vuln dependency. **MEDIUM** — a bare dangerous sink; unpinned
dependency; TLS-off; debug flag left on. **REVIEW** — security-sensitive
business logic, weak primitives (`md5`/`sha1`, `DEBUG=True`) — human
judgment only. Test paths downgrade one notch.

## Pre-install skill audit (`skill_audit.py`)

Vets an untrusted skill folder/repo before you install/vendor it —
PASS/WARN/FAIL (exit 0/1/2):

```bash
python3 skills/_shared/tools/security-oversight/skill_audit.py <skill-dir>
python3 skills/_shared/tools/security-oversight/skill_audit.py <skill-dir> --strict   # any HIGH -> FAIL
```

Flags prompt-injection in `SKILL.md`/`*.md` prose (role hijack, safety-
bypass, exfil instructions, hidden zero-width/HTML-comment directives),
code-exec/obfuscation, net-exfil + credential-harvest combos (escalate to
CRITICAL), priv-esc/symlink-escape/supply-chain. Tuned so legit skills PASS
— dual-use patterns (env reads, base64, `pip install`) are MEDIUM, not FAIL.

## Soundness limit

Line-local lexical triage only — no multi-file taint tracking, no SSRF/
path-traversal/SSTI detection (run `semgrep`/`gitleaks` for those), no
semantic vulnerability analysis. A clean result means "no obvious
introduced risk," never "secure."

## Tests

```bash
python3 skills/_shared/tools/security-oversight/test_security_scan.py   # S1–S14 scanner probes
python3 skills/_shared/tools/security-oversight/test_skill_audit.py     # A1–A18 skill-audit probes
```
