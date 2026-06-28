---
name: security-oversight
description: "Use before committing or claiming work done to triage a code edit for INTRODUCED security risk — leaked secrets, dangerous sinks, untrusted dependencies, and security-sensitive logic that scanners can't judge. Trigger on \"is this safe to ship?\", \"did I leak a secret?\", \"any security issues with this change?\", \"did the agent introduce a vulnerability?\", or as the security gate in a generate→verify loop. Parses `git diff` added lines, classifies into 4 OWASP-anchored classes (secret/injection/supply_chain/authz), scores HIGH/MEDIUM/REVIEW, routes HIGH/MEDIUM to verify-before-completion and surfaces REVIEW for a human; detects reputable scanners (gitleaks/semgrep/osv-scanner) and recommends them for depth. Does NOT modify code, auto-fix, or block. Absence of a finding is NOT proof of safety. Also: /security-oversight."
status: proposed
effort: low
tools: [Bash, Read]
auto-install: false
disable-model-invocation: false
pulse_reminder: "before committing or closing a task with edits, run security_scan.py — emit the introduced attack surface (secrets / dangerous sinks / new deps / security-sensitive logic) so verify-before-completion knows what to check and a human can clear the REVIEW items. Fast lexical triage; absence of a finding ≠ proof of safety — say so."
---

# security-oversight

Karpathy names **security oversight** as a core skill of agentic engineering:
*"You are not allowed to introduce vulnerabilities because of vibe coding."* The
danger is not obviously-broken code — it is **plausible-but-insecure** code that
slips in **silently** when no one inspects the diff (his MenuGen example: an agent
matched Stripe accounts to Google accounts by email — looked right, was a hole).

This is the inspection layer — the **security sibling of
[impact-of-change](../impact-of-change/SKILL.md)**:

| | question | output |
|---|---|---|
| impact-of-change | what **breaks** if I change this? | blast radius (callers) |
| security-oversight | what could be **abused** in what I changed? | attack surface |

Both parse `git diff`, triage, and hand the high-risk list to
`verify-before-completion`. This one is **graph-free**: it reads the diff's
**added lines** and flags introduced risk. It does **not** run tests, modify
code, auto-fix, or block — it tells you (and a human) *what to look at*.

Born **opt-in / untrusted** (`auto-install: false`, `status: proposed`): wire it
deliberately, promote after it earns trust on real diffs.

## When to use

- Before a commit or a done-claim: "is this safe to ship?", "did I leak a
  secret?", "did the agent introduce a vulnerability here?"
- Composed with **verify-before-completion**: emit the attack surface first, so
  the human/agent verifies the HIGH/MEDIUM zones (this skill never runs tests).
- Composed with **impact-of-change**: run both pre-commit — *what breaks* and
  *what's exploitable* are different axes of the same diff.
- Composed with **loop-engineering**: the security gate of a generate→verify loop
  (a fleet that writes code should triage what it wrote before integrating).

Do **not** use it as a full SAST engine (it triages, then points you at
`semgrep`/`gitleaks`/`osv-scanner`), an auto-fixer, or a blocker. And it covers
the **coding-agent** subset of the OWASP Agentic Top 10 — not the
deployment-runtime threats (ASI07 inter-agent comms, ASI08 cascading failures,
ASI09 human-agent trust, ASI10 rogue agents); those live at the deployment layer,
outside a code-editing skill.

## The four classes (OWASP-anchored)

| class | catches | OWASP |
|---|---|---|
| `secret` | hardcoded key/token/credential; a secret-bearing file (`.env`, `*.pem`, `HANDOFF.md`) in the diff | LLM02 / ASI03 |
| `injection` | dangerous sink the agent wrote — `eval`/`exec`/`os.system`/`shell=True`/`pickle`/unsafe-`yaml`/SQL-by-format/TLS-off/`curl\|sh` | ASI05 / LLM05 |
| `supply_chain` | new/unpinned dependency in a manifest; a change to the **skill/hook/installer injection surface** (Snyk: 13% of agent-skill packages ship critical flaws) | ASI04 / LLM03 |
| `authz` | security-sensitive **business logic** changed (auth / payment / token / permission) — the plausible-but-insecure class scanners can't judge → **REVIEW** | ASI03 / ASI02 |

The `authz` class is the part automated scanners miss and the reason a human stays
in the loop: it can only be flagged for **REVIEW**, never mechanically cleared.

## Protocol

1. Run the triage on the change under consideration:
   ```bash
   # uncommitted edits, markdown report
   python3 skills/security-oversight/tools/security_scan.py --repo . --diff working
   # what a pre-commit hook sees (staged), JSON for piping
   python3 skills/security-oversight/tools/security_scan.py --diff staged --json
   # a specific commit / range
   python3 skills/security-oversight/tools/security_scan.py --diff <sha>
   ```
2. Read the report: **Summary** (risk + REVIEW count), **Findings**
   (severity/class/`file:line`/owasp/why), **Needs human REVIEW**, **Scanners**,
   **Recommendations**.
3. **Route HIGH/MEDIUM** to `verify-before-completion`. **Hand REVIEW items to a
   human** — do not self-clear business-logic authz. For any **secret**, treat a
   committed credential as compromised: rotate it, don't just delete it.
4. For verified depth, run the reputable scanner the report names (it detects
   which are installed). Surface ambiguity; don't silently pick.

## How it triages severity

- **HIGH** — a secret/secret-file; an input-bearing or always-dangerous sink
  (`os.system`, `pickle`, `shell=True`, `curl|sh`); a known-vuln dependency.
- **MEDIUM** — a bare dangerous sink; a new/unpinned dependency; TLS-off; debug.
- **REVIEW** — security-sensitive business logic, and weak primitives
  (`md5`/`sha1`, `DEBUG=True`): a human must judge these; they cannot be cleared
  mechanically. (The honest analogue of impact-of-change's `UNKNOWN`.)
- **Test paths downgrade one notch** (a sink in `test_*.py` is lower signal),
  matching impact-of-change's tests/deprecated handling.

Overall risk is the max over findings; REVIEW is surfaced separately so it is
never masked by a low overall score.

## Soundness limit — absence of a finding is NOT proof of safety

This is **fast lexical triage over the diff's added lines**. It sees only
introduced text — **not** semantic vulnerabilities, **multi-file taint** (input
that arrives two lines or two files away — so a genuinely-dangerous `eval(x)` can
read MEDIUM if the taint isn't on its line), or anything in **unchanged** code.
Clearing this gate means *"no obvious introduced risk found,"* never *"secure."*
The report always carries this caveat. This is the security-side twin of
impact-of-change's **static-call-graph soundness limit** (a LOW is a floor, not
proof): a clean security triage is a floor, not proof. For real assurance, run a
full secret/SAST/dependency scan and route REVIEW to a human.

**Named blind spots — patterns this does NOT have (run `semgrep` for these):**
SSRF (input → URL fetch), path traversal (input → file path), template-injection
/ SSTI, taint that crosses lines or files (e.g. `eval(x)` where `x` was tainted
earlier reads only MEDIUM), and secrets hidden by indirection (base64/env-var/
non-listed providers — that is gitleaks' job). These are out of scope for
line-local lexical triage *by design*; the value here is the fast first pass that
catches the obvious introduced risk and routes the rest. Don't read a clean
result as "no SSRF/traversal/SSTI" — read it as "those weren't checked."

## Scanner-aware, not a scanner wrapper

By design the tool does **not** shell into heavy scanners (fragile, slow, hard to
test). It runs its own high-precision lexical triage, then **detects** which
reputable tools are installed (`gitleaks`, `trufflehog`, `semgrep`, `bandit`,
`osv-scanner`, `pip-audit`) and **recommends** the right one per finding class —
the same way impact-of-change consumes graphify rather than rebuilding it. (A
future enhancement may auto-corroborate via gitleaks/semgrep when present.)

## Output

Structured `dict` (→ JSON with `--json`, or markdown by default). Top-level keys:
`mode` (`lexical-triage`|`error`), `risk`, `summary`, `findings` (each: `class`,
`severity`, `file`, `line`, `snippet`, `owasp`, `why`, `detector`, `verified`),
`routed` (HIGH/MEDIUM), `review`, `scanners_available`, `recommendations`,
`caveat`, `warnings`. Parseable by downstream skills. Never raises on the diff
path — a git failure degrades to an `error`-mode report (still carrying the
caveat), never a block.

## Files

```
tools/
├── security_scan.py        # git diff added-lines → 4-class triage → severity → routing
└── test_security_scan.py   # standalone S1–S10 probes (assert + exit 1), temp-git fixture
```

## Tests

```bash
python3 skills/security-oversight/tools/test_security_scan.py
```

Covers (S1–S14): **S1** secret (AWS key/credential → HIGH), **S2** injection
(`eval(input)`=HIGH, clean=none), **S3** supply_chain (manifest → MEDIUM), **S4**
authz (payment logic → REVIEW), **S5** clean (no findings, risk NONE), **S6**
never-block (bad diff spec degrades, never raises), **S7** structure (parseable
JSON shape), **S8** honest-limit (caveat always present), **S9** sensitive-file
(`HANDOFF.md` → HIGH — the session hard rule), **S10** test-path downgrade
(precision); plus the adversarial-review hardening: **S11** no-false-positives
(benign code + markdown prose stay clean), **S12** untracked-file secret caught in
default `working` mode (the git-diff-omits-new-files blind spot), **S13**
UPPER_SNAKE secret (`DB_PASSWORD=…` — the `\b`-underscore bug), **S14** in-string
sink (`curl|sh` inside a string, `bash -c` argv — the raw-scan path).

## Lineage (most-reputable sources)

- **[OWASP Top 10 for Agentic Applications 2026](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/)**
  (ASI01–ASI10; peer-reviewed by 100+ researchers) — the class taxonomy; this
  skill scopes to the code-level subset (ASI02/03/04/05).
- **OWASP Top 10 for LLM Applications** (LLM01 prompt-injection, LLM02 sensitive-
  info disclosure, LLM03 supply chain, LLM05 improper output handling) — the
  per-finding anchors.
- **Karpathy, "From Vibe Coding to Agentic Engineering"** (Sequoia AI Ascent 2026)
  — the mandate (security as a co-equal pillar; the plausible-but-insecure / silent
  failure framing).
- Detection tools recommended, not wrapped: `gitleaks`/`trufflehog` (secrets),
  `semgrep`/`bandit` (SAST), `osv-scanner` (Google OSV) / `pip-audit` (PyPA) (deps).

## Status

**Opt-in / unmeasured.** Plumbing self-tested offline (`test_security_scan.py`,
no network, 10/10). Per catalog policy it earns trust on real diffs before any
default promotion — target: catching introduced secrets/sinks/untrusted-deps and
correctly escalating business-logic authz to a human, at a false-positive rate low
enough not to be ignored. **Promotion-time follow-up:** add a `compliance-canary`
drift probe (fires when a security-sensitive diff heads for commit without a
security pass) so it fires mechanically rather than by description — the same way
the canary enforces other gates. Until then it is invoked manually / on trigger,
like impact-of-change.
