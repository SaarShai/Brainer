# Merge provenance — audit-mode stack

Maps each logical change to the commit that carries it on `main`, so the merge
history is auditable without detective work. (Addresses the external review's
"PR provenance is harder to audit than it should be" finding.)

## Audit-mode stack (PR #5–#10 → direct fast-forward push to `main`)

The stack was developed as branches #5→#9 and fast-forwarded to `main` as
`c828f56..97b4505`. PRs #5–#9 were closed "included in `main`"; #10 was folded
into #9.

| PR | Title | Commit on `main` |
|----|-------|------------------|
| #5 | Clarify task-retrospective as user-triggered project learning | `3daa6b2` |
| #6 | Add task-retrospective evidence recorder | `c514a9e` |
| #7 | Add Brainer audit offline MVP | `d1278df` |
| #8 | Add Claude and Codex audit hook adapters | `2e2eed9` |
| #9 | Add Antigravity audit sidecar | `111907f` |
| #10 | Harden audit modes and split checks (folded into #9) | `97b4505` |

`origin/main` tip after the push: `97b4505953c82796e70812e7be6f4acae980ee95`.

## Audit-mode hardening pass

Follow-up addressing the external execution review (valid-YAML frontmatter +
strict lint, unified path-confinement, unified+broadened redaction, report
mode derived from collection source, detector adversarial precision corpus,
performance benchmarks, catalog/doctrine integrity tests). Landed via a
reviewable GitHub PR rather than a direct push — see the PR linked from this
commit's branch.
