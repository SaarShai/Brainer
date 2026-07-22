<!-- demoted-from-skill: wiki-refresh — 2026-07-22 (Great Pruning A2, usage-evidence purge) -->
<!-- The nine (+disuse) quality-scan tooling and the staleness-nudge hook were
     retired with this demotion. This brief is method guidance only; run
     wiki-memory's own tools/wiki.py verbs directly for the mechanical checks
     still available. -->

# wiki-refresh (delegate brief) — reconcile wiki pages against the codebase

Ground-truth maintenance for `wiki-memory`: does a page still match reality?
(`write-gate` decides what enters the wiki; this decided whether a page
*still* matches reality — heavier, occasional.)

## Signal sources (read first, don't eyeball the tree)

```bash
python3 skills/wiki-memory/tools/wiki.py --root wiki audit-refs    # cited paths that vanished
python3 skills/wiki-memory/tools/wiki.py --root wiki lint --strict  # broken links, stale verified:, dupes, contradictions
```

`audit-refs` returns pages whose cited paths no longer exist on disk — the
primary drift signal.

## The five outcomes

| Outcome | When | Action |
|---|---|---|
| **Keep** | accurate + useful | no write |
| **Update** | refs/paths/links drifted, core claim still correct | edit in place; bump `updated:`/`verified:` |
| **Consolidate** | two correct pages cover the same subject, one subsumes the other | merge into the canonical page, delete the subsumed one |
| **Replace** | the claim itself is now misleading (implementation changed) | write a successor, wire `supersedes:`/`superseded-by:` both ways |
| **Delete** | code gone AND problem domain gone AND no substantive inbound links | delete the file |

**Update vs Replace:** if you're rewriting the claim/solution, it's Replace,
not Update — Update only touches references.

**Before Delete, all three gates must hold:** implementation gone, problem
*domain* gone (not just the file), inbound links absent or merely
decorative ("see also"). A substantive citation downgrades Delete to
Replace or Keep-with-narrowed-scope.

## Contradiction edges

When a page conflicts with current reality or with another page and you
can't immediately resolve it, don't drop it silently — add `contradicts:
[[other-page]]` on both pages (reciprocal), then re-run `lint --strict` so
retrieval keeps flagging the pair until an agent resolves it.

## Report

Always print scanned/kept/updated/consolidated/replaced/deleted counts and a
per-page outcome + evidence + action line. Headless/unattended runs must
mark ambiguous cases stale rather than auto-writing a Replace successor.

## Recoverable machinery

The `audit-refs`/`contradict-scan`/`stale-citers` verbs, staleness-nudge
hook, and disuse scan live in `wiki-memory`'s own tooling or are recoverable
from git history under the retired `skills/wiki-refresh/` tree.
