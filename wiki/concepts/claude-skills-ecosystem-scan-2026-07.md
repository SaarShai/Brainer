---
trust: user_confirmed
schema_version: 2
title: "Claude skills ecosystem scan (2026-07) — 32 items, 1 adopted"
type: concept
domain: "skill-authoring"
tier: semantic
confidence: 0.85
created: "2026-07-01"
updated: "2026-07-01"
verified: "2026-07-01"
sources:
  - "article: 'You're competing against people who treat Claude like an operating system' — 32 skills across 9 hubs"
  - "review workflow wye5dpptd (34 agents: fetch/compare/verify/synthesize) + gh-api verification of real repos"
  - "built: skills/security-oversight/tools/skill_audit.py (+ test_skill_audit.py A1–A17)"
tags: [skills, ecosystem, adoption, security, supply-chain, review, negative-result]
---

# Claude skills ecosystem scan (2026-07) — 32 items, 1 adopted

## Summary

Reviewed an article listing ~32 skills across ~9 hubs (Anthropic, Rezvani,
Composio, BehiSecc, Jezweb, standalone repos). **Net: one capability adopted** —
a pre-install **skill auditor**, added to `security-oversight` — the rest are
already-covered, out-of-scope-by-design (domain/output verticals), or mechanisms
Brainer already uses. Don't re-litigate these 32; only reconsider new/changed ones.

## What was adopted — `skill_audit.py`

`security-oversight` gained a second tool: audit a **whole untrusted skill folder/
repo before install/vendor** → PASS/WARN/FAIL. Distinctive net-new over the
diff-scanner: **prompt-injection detection in `SKILL.md` prose** (a skill body IS a
prompt) — plus dangerous scripts, base64→exec obfuscation, the cred-read+network
**exfil combo**, symlink-escape, bundled binaries, typosquatted deps. **Why it fits
Brainer:** Brainer vendors external skills into siblings and the maintainer actively
adopts from this ecosystem, so a vet-before-trust gate is a real agent-ops gap
(the diff-scanner only sees introduced code, not an incoming skill's prose).

Ported from the reference `alirezarezvani/.../skill-security-auditor` patterns,
reimplemented Brainer-native (reuses `security_scan.py`'s library). **Tuned for
precision** — dual-use patterns (env reads, base64, `pip install`) are MEDIUM not
FAIL; CRITICAL is reserved for unambiguous malice — because a noisy security gate
gets ignored. Verified: 23/24 Brainer skills PASS their own audit (the 1 WARN is
this skill's own test fixtures), a real external skill PASSed, and a realistic
multi-file exfil skill FAILs. A1–A17 tests + 14/14 diff-scanner regression.

## Everything else (already-have / out-of-scope)

- **skill-authoring** (Anthropic/Composio skill-creator) → `learn-skill` (strict
  superset; Brainer removed its own skill-creator v1.1.0).
- **self-improving-agent** (real 6-skill bundle: review/promote/extract/remember/
  status) → `learn-skill` + `wiki-memory` + `write-gate` + `wiki-refresh` + native memory.
- **research/rag/tapestry** → `wiki-memory` (compile-not-retrieve) + `loop-engineering`.
- **worktrees** → already Brainer's writer-isolation primitive.
- **domain/output verticals** (doc-coauthoring, docx, frontend, mcp-server-builder,
  rag-architect, observability/perf/release/tech-debt, email, apollo, aws, wondelai's
  42 business skills, Skill_Seekers' scraper+RAG engine) → excluded by design; Brainer
  carries no domain skills.

## Process lesson (the load-bearing one)

The review **workflow initially reported the entire Rezvani cluster as "vaporware /
404"** — WRONG. Its fetch agents hit the bare repo URL and `.codex/.gemini` **symlink
mirrors**, got false 404s, and inferred absence. The repo is real (19.5k stars, 337
skills) with sources under domain folders. **A single `gh`-api spot-check overturned
34 agents' central factual claim** and surfaced the one genuine candidate they'd
dismissed. Lesson for future ecosystem scans: **resolve real paths via `gh`/GitHub
API, not bare-URL `WebFetch`** — symlink-mirror repos 404; and always spot-check a
strong "it doesn't exist" claim before relaying it. Same discipline as
[[concepts/systematic-debugging-skill-measured-null]] and
[[concepts/premortem-and-think-edits-measured]]: verify, don't relay unread claims.

## Related

- [[concepts/premortem-and-think-edits-measured]]
- [[concepts/systematic-debugging-skill-measured-null]]
- [[concepts/lean-execution]]

## Open Questions

- Should `skill_audit.py` become a pre-vendor gate in `scripts/sibling_sync_audit.py`
  (auto-audit a skill before it's copied into a sibling)? Deferred — wire only if
  sibling propagation starts pulling external skills.
