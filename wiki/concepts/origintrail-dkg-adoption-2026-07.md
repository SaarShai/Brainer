---
schema_version: 2
title: "OriginTrail DKG adoption review — local analogues sufficient, correlation key adopted"
type: concept
domain: "framework-hardening"
tier: semantic
confidence: 0.9
created: "2026-07-14"
updated: "2026-07-14"
verified: "2026-07-14"
trust: verified
sources:
  - "https://github.com/OriginTrail/dkg/tree/462a98f3f5b1c5ad5eaaed9dec69e1f8c7b1d402"
  - "local source review: /Users/za/.graphify/repos/OriginTrail/dkg at 462a98f3f5b1c5ad5eaaed9dec69e1f8c7b1d402"
  - "local verification: skills/_shared/test_model_roster.py"
  - "local verification: skills/_shared/test_orchestration_trace.py"
tags: [origintrail, dkg, adoption, provenance, trust, memory, telemetry]
supersedes: []
superseded-by:
---

# OriginTrail DKG adoption review — local analogues sufficient, correlation key adopted

## Summary

**Trigger / symptom:** an external distributed-memory framework appears to offer trust, maturity, provenance, or lifecycle-observability mechanisms that Brainer may lack.

**Verdict:** ADOPTED 1 narrow mechanism, kept 3 weaker repo-local analogues as sufficient for Brainer's current scope, and REJECTED the distributed stack. These analogues do not provide DKG's identity, permission, attestation, or cryptographic guarantees. We rejected a new DKG-inspired skill because DKG is a networked knowledge protocol while Brainer is a portable, repo-local agent framework; the reusable gap was in shared telemetry, not a new user workflow.

## Adopted

1. **One bounded lifecycle correlation key.** DKG's publish ADR requires one stable, grep-friendly key through a lifecycle, with bounded and redacted log fragments. Brainer's lane telemetry called its field `task_digest` but wrote the full task text. `skills/_shared/model_roster.py` now emits a bounded random `correlation_id`: every lane in one panel shares it, independent dispatches get distinct IDs, and an orchestrating caller can deliberately carry one ID across a larger lifecycle. The ID is never derived from task text. The trace writer documents that contract. This was adopted because it improves an existing persistence surface without introducing a distributed subsystem.

## Repo-local analogues retained

1. **Local evidence tiers and quorum.** DKG distinguishes draft/shared/self-attested/endorsed/partially verified/consensus verified through actors and network policy. Brainer has a weaker local analogue: `asserted < corroborated < verified < user_confirmed`, caller-supplied source-count/verification flags, quarantine below a filing threshold, and trust-ranked conflict resolution in `skills/wiki-memory/tools/provenance.py:44-113`. This is sufficient for gating repo-local memory writes; it is not actor identity, endorsement, permission, or consensus verification.
2. **Gated promotion to durable memory.** DKG's WM/SWM/VM layers combine scope and trust. Brainer does not implement that ladder. Its relevant local analogue is simpler: transient session/scratch state stays outside the curated wiki, while `write-gate` plus wiki provenance rules gate durable repo memory. Brainer's observation/hypothesis/rule maturity lens remains a separate claim-quality mechanism, not an equivalent to DKG's memory layers.
3. **Local provenance and revision history.** DKG Knowledge Assets provide stable UAL identity plus Merkle and blockchain commitments. Brainer's v2 wiki schema records sources and verification metadata, path-derived page IDs, links, and Git history; raw immutability is a convention. Those are sufficient for an owned local repository, but they are neither cryptographic commitments nor stable cross-network asset identities.

## Rejected or adapted

1. **Exact WM/SWM/VM replication rejected.** Brainer has local scratch state and durable repo memory, but no peer gossip network or blockchain finality boundary. Adding three storage engines would create categories with no consumer. The current local promotion boundary is sufficient; DKG's distributed guarantees are deliberately not claimed.
2. **RDF Knowledge Assets and Context Graph registries rejected.** Brainer already uses Markdown pages, paths, frontmatter, wikilinks, and a generated index. RDF canonicalization, Merkle roots, named-graph ACLs, and publisher registries would replace a deliberate local-first representation without a measured retrieval or integrity gap.
3. **Blockchain anchoring, decentralized identity, gossip, quorum ACK protocols, token economics, and integration-marketplace trust tiers rejected.** These solve cross-node adversarial coordination and public verification. Brainer does not operate that network or install integrations from DKG's registry, so the mechanisms are category mismatches rather than missing skills.
4. **A new skill rejected.** No distinct trigger-to-outcome workflow remains after the covered and category-mismatch mechanisms are removed. The one real delta belongs in `_shared` orchestration telemetry.

## Boundary and remaining risk

- A generated ID correlates one `run_panel` invocation, not a global task or all causally related work. Callers spanning a larger lifecycle must pass the same bounded `correlation_id` explicitly.
- This change is prospective. A non-content inspection on 2026-07-14 counted 3,753 existing `.brainer/trace/lanes.jsonl` rows: 3,633 legacy non-hashed `task_digest` rows, 96 interim `sha256:` rows, and 24 new `correlation_id` rows. No historical telemetry was deleted or rewritten. If confidentiality is the goal, rotation or redaction needs explicit operator approval.
- DKG V10 at the reviewed commit is a release candidate under active change. Re-review if Brainer later gains multi-repo concurrent writers, remote peers, or public verification requirements.

## Evidence

- DKG source commit: `462a98f3f5b1c5ad5eaaed9dec69e1f8c7b1d402`.
- DKG memory lifecycle: `docs/how-dkg-works/memory-layers.md:12-50`.
- DKG trust ladder: `docs/how-dkg-works/agents-and-trust.md:21-35`.
- DKG correlation-key ADR: `docs/adr/0001-log-ka-publish-lifecycle-by-asset-ual.md:3-31`.
- Brainer telemetry change: `skills/_shared/model_roster.py`; contract: `skills/_shared/orchestration_trace.py:5-8`.
- Existing-trace non-content inventory (2026-07-14): 3,753 rows, 0 malformed; 3,633 legacy raw-field rows, 96 hash rows, 24 UUID-correlation rows.

## Related

- [[queries/covered-verdicts]]
- [[concepts/adoption-covered-needs-merits-citation]]
- [[queries/llm-wiki-compile-on-ingest-adoptions]]
- [[projects/okf-adoption]]
