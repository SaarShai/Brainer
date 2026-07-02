# security-oversight — EVAL

**Posture: opt-in (`auto-install: false`), unmeasured.** Ships symlinked +
listed; wires no hook. Promotion to default needs N≥50.

## What it is
Two lexical triage surfaces, both report-only: (1) `security_scan.py` — added
lines of a `git diff` classified into secret / injection / supply_chain / authz,
scored HIGH/MEDIUM/REVIEW, routed to `verify-before-completion` / a human;
(2) `skill_audit.py` — pre-install audit of an untrusted skill folder
(prompt-injection, dangerous scripts, exfil combo, symlink-escape, typosquat →
PASS/WARN/FAIL). Absence of a finding is NOT proof of safety.

## Deterministic self-tests (green)
`tools/test_security_scan.py` + `tools/test_skill_audit.py` (incl. the
untracked-file silent-miss regression); both run in `scripts/run_all_tests.sh`.
Field fact: 23/24 Brainer skills self-PASS `skill_audit.py` (2026-06 scan).

## What to measure (when N is available)
- **Detection P/R on seeded diffs** — plant known secrets / sinks / dep-adds /
  authz edits in synthetic diffs; measure hit rate and false-positive rate per
  class.
- **Scanner parity** — on the same corpus, overlap with gitleaks/semgrep
  (subset) to quantify what the fast lexical pass catches vs misses — keeps the
  "recommend real scanners for depth" claim honest.
- **skill_audit discrimination** — known-malicious skill corpus (public
  prompt-injection samples) vs the benign Brainer set: FAIL recall on bad,
  PASS rate on good.
