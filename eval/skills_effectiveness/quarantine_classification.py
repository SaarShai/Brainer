#!/usr/bin/env python3
"""Validate and render the hash-pinned quarantine classification."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DEFAULT_SOURCE = HERE / "quarantine_classification.json"
EXPECTED = {
    "caveman-ultra", "fable-mode", "lean-execution", "learn-skill",
    "loop-engineering", "plan-first-execute", "prompt-triage",
    "requirements-ledger", "standing-orders", "task-retrospective",
    "team-lead", "think", "verify-before-completion", "wayfinder",
}
DISPOSITIONS = {"retire", "demote-role-brief", "retain-manual", "split", "retired-removed"}


def load_and_validate(path: Path = DEFAULT_SOURCE) -> dict:
    data = json.loads(path.read_text())
    if data.get("schema_version") != 2:
        raise ValueError("unsupported classification schema")
    rows = data.get("skills", [])
    names = [row.get("name") for row in rows]
    if len(names) != len(set(names)):
        raise ValueError("duplicate skill classification")
    if set(names) != EXPECTED:
        raise ValueError(f"classification set mismatch: {sorted(set(names) ^ EXPECTED)}")
    if data.get("policy", {}).get("auto_surface") != "none":
        raise ValueError("quarantined skills must have no automatic prompt surface")
    policy = data.get("policy", {})
    if policy.get("delete_by_default") is not False:
        raise ValueError("quarantine must not authorize automatic deletion")
    if policy.get("decision_status") != "proposal_pending_candidate_specific_evidence":
        raise ValueError("classification must remain a proposal until candidate-specific evidence lands")
    for row in rows:
        if row.get("disposition") not in DISPOSITIONS:
            raise ValueError(f"invalid disposition for {row['name']}")
        if not row.get("reason") or not isinstance(row.get("retain"), list):
            raise ValueError(f"incomplete rationale for {row['name']}")
        skill = REPO / "skills" / row["name"] / "SKILL.md"
        if not skill.is_file():
            if row.get("disposition") != "retired-removed":
                raise ValueError(
                    f"missing SKILL.md for {row['name']} with no "
                    "\"disposition\": \"retired-removed\" to explain it "
                    "(silent gaps hide undocumented removals)"
                )
            # Body genuinely gone (row explicitly marks it retired-removed,
            # e.g. catalog contraction); nothing left to drift-check.
            continue
        actual = hashlib.sha256(skill.read_bytes()).hexdigest()
        if actual != row.get("skill_sha256"):
            raise ValueError(f"stale classification for {row['name']}: body hash changed")
        frontmatter = skill.read_text().split("---", 2)[1]
        if "status: experimental" not in frontmatter or "disable-model-invocation: true" not in frontmatter:
            raise ValueError(f"{row['name']} is no longer quarantined")
    return data


def render(data: dict) -> str:
    counts = Counter(row["disposition"] for row in data["skills"])
    lines = [
        "# Quarantined skill classification",
        "",
        f"Reviewed: {data['classified_at']}. Scope: {len(data['skills'])} experimental/manual prompt bodies.",
        "No body is default-on. Hash changes invalidate the classification and require re-review.",
        "",
        "## Candidate disposition summary",
        "",
        f"- Proposed retire, pending a candidate-specific gate: {counts['retire']}",
        f"- Proposed demotion into compact role briefs: {counts['demote-role-brief']}",
        f"- Retain as explicit tool/workflow skills: {counts['retain-manual']}",
        f"- Proposed split of prose from retained mechanisms: {counts['split']}",
        f"- Already retired and removed from the catalog (body gone): {counts['retired-removed']}",
        "",
        "These are content-taxonomy hypotheses, not causal outcome verdicts.",
        "",
        "| Skill | Class | Candidate disposition | Reason |",
        "|---|---|---|---|",
    ]
    for row in data["skills"]:
        reason = row["reason"].replace("|", "\\|")
        lines.append(f"| `{row['name']}` | {row['class']} | **{row['disposition']}** | {reason} |")
    lines.extend([
        "",
        "## Review rule",
        "",
        f"Re-review after {data['policy']['review_after_days']} days. Time alone never deletes a body. Removal requires candidate-specific evidence that clears the preregistered retirement or harmfulness gate, plus an explicit implementation change.",
        "",
        "Executable tools and compact canary mechanisms are retained or removed independently from their explanatory prose. No classification here authorizes propagation to consumer repositories.",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--markdown-out", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    data = load_and_validate(args.source)
    output = render(data)
    if args.markdown_out:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(output)
    if args.json:
        print(json.dumps({"valid": True, "skills": len(data["skills"]),
                          "dispositions": Counter(r["disposition"] for r in data["skills"])},
                         sort_keys=True))
    elif not args.markdown_out:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
