#!/usr/bin/env python3
"""Deterministic contracts for the frontier-default skill surface."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from math import ceil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.prune_optin_hooks import prune  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
MANUAL_SKILLS = (
    "caveman-ultra",
    "learn-skill",
    "loop-engineering",
    "prompt-triage",
    "task-retrospective",
    "team-lead",
    "think",
    "verify-before-completion",
)
ROLE_FILES = (
    ROOT / ".claude/agents/builder.md",
    ROOT / ".claude/agents/verifier.md",
    ROOT / ".claude/agents/research-lite.md",
)
FRONTIER_ECONOMY_SKILLS = (
    "loop-engineering",
    "prompt-triage",
    "team-lead",
    "think",
    "verify-before-completion",
)
CARRIERS = ("AGENTS.md", "CLAUDE.md", "GEMINI.md")


def frontmatter(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), path
    return text.split("---", 2)[1]


def body(path: Path) -> str:
    return path.read_text(encoding="utf-8").split("---", 2)[2]


def token_estimate(text: str) -> int:
    return ceil(len(text) / 4) + text.count("\n")


def missing_phrases(text: str, required: tuple[str, ...]) -> list[str]:
    return [phrase for phrase in required if phrase not in text]


def test_generic_skills_are_manual_experiments() -> None:
    for name in MANUAL_SKILLS:
        fm = frontmatter(ROOT / "skills" / name / "SKILL.md")
        assert re.search(r"^status:\s*experimental\s*$", fm, re.M), name
        assert re.search(r"^disable-model-invocation:\s*true\s*$", fm, re.M), name
        assert re.search(r"^auto-install:\s*false\s*$", fm, re.M), name


def test_committed_host_configs_have_no_prompt_triage_hook() -> None:
    for rel in (".claude/settings.json", ".codex/hooks.json", ".gemini/settings.json"):
        path = ROOT / rel
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            assert "prompt-triage/tools/hook" not in json.dumps(data), rel


def test_reinstall_prune_removes_only_managed_optin_hooks() -> None:
    triage = 'bash "$PWD/.claude/skills/prompt-triage/tools/hook.sh"'
    audit = ('python3 "${CLAUDE_PROJECT_DIR:-$PWD}/skills/brainer-audit/tools/hook.py" '
             '--host codex --event UserPromptSubmit')
    canary = 'bash "$PWD/.claude/skills/compliance-canary/tools/hook.sh"'
    app = 'bash "$PWD/.app/hooks/prompt-triage/tools/hook.sh"'
    data = {
        "permissions": {"allow": ["Read"]},
        "hooks": {
            "UserPromptSubmit": [
                {"matcher": "*", "hooks": [
                    {"type": "command", "command": triage},
                    {"type": "command", "command": audit},
                    {"type": "command", "command": canary},
                    {"type": "command", "command": app},
                ]}
            ]
        },
    }
    result, removed = prune(data, {"prompt-triage", "brainer-audit"})
    commands = [
        hook["command"]
        for group in result["hooks"]["UserPromptSubmit"]
        for hook in group["hooks"]
    ]
    assert triage not in commands
    assert audit not in commands
    assert canary in commands and app in commands
    assert result["permissions"] == {"allow": ["Read"]}
    assert removed == [
        ("prompt-triage", "UserPromptSubmit", triage),
        ("brainer-audit", "UserPromptSubmit", audit),
    ]


def test_reinstall_prunes_optin_output_style_hook() -> None:
    installer = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert 'fm.get("auto-install", "")' in installer
    assert "disabled_styles.append" in installer
    assert 'hooks.pop("SessionStart", None)' in installer
    assert "[global-prune] removed opt-in output-style hook" in installer


def test_role_briefs_have_bounded_shape() -> None:
    for path in ROLE_FILES:
        text = body(path)
        estimate = token_estimate(text)
        imperatives = re.findall(r"(?m)^\d+\. ", text)
        assert 300 <= estimate <= 500, f"{path}: {estimate} estimated tokens"
        assert 1 <= len(imperatives) <= 8, f"{path}: {len(imperatives)} imperatives"


def test_research_role_mirrors_match() -> None:
    claude_body = body(ROOT / ".claude/agents/research-lite.md").strip()
    bundled_body = body(ROOT / "skills/prompt-triage/tools/agents/research-lite.md").strip()
    codex = (ROOT / ".codex/agents/research-lite.toml").read_text(encoding="utf-8")
    codex_body = codex.split('developer_instructions = """', 1)[1].split('"""', 1)[0].strip()
    assert claude_body == bundled_body
    assert claude_body == codex_body


def test_frontier_economy_policy_is_canonical_and_future_proof() -> None:
    doctrine = (ROOT / "skills/_shared/ORCHESTRATION.md").read_text(
        encoding="utf-8")
    required = (
        "Frontier economy invariant (hard)",
        "Fable 5",
        "GPT-5.6 Sol xhigh",
        "any equal-or-better future model",
        "cheapest reachable capable tier",
        "inseparable from live context",
        "Outside a\nmandatory route below",
        "sole cost/size exception to SPEC'D+GATED delegation",
        "expected diff of 30+ lines closes it regardless of\ndispatch cost",
        "Never delegate unresolved diagnosis",
    )
    assert not missing_phrases(doctrine, required)


def test_frontier_economy_policy_gate_rejects_drift() -> None:
    required = ("cheapest reachable capable tier",)
    doctrine = (ROOT / "skills/_shared/ORCHESTRATION.md").read_text(
        encoding="utf-8")
    drifted = doctrine.replace(required[0], "a capable tier", 1)
    assert missing_phrases(drifted, required) == list(required)


def test_contract_promotion_policy_is_canonical_and_bounded() -> None:
    doctrine = (ROOT / "skills/_shared/LEARNING_CONTRACT.md").read_text(
        encoding="utf-8")
    required = (
        "Contract-promotion gate",
        "cross-task",
        "material",
        "low-false-positive",
        "cheap on the decision's read path",
        "known-bad fixture",
        "trigger-local",
    )
    assert not missing_phrases(doctrine, required)


def test_end_to_end_ownership_policy_is_canonical_and_portable() -> None:
    doctrine = (ROOT / "skills/_shared/ORCHESTRATION.md").read_text(
        encoding="utf-8")
    required = (
        "End-to-end ownership invariant (hard)",
        "architecture, implementation, tests",
        "independent, non-colliding lanes",
        "goal, expected deliverable, verification gate, and done",
        "continuing\nunblocked lead work",
        "intervene when a lane drifts\nor lacks context",
        "a literal `/goal` command is not portable",
        "Commit only when authorized and ready",
        "Partial progress is not a stopping\ncondition",
    )
    assert not missing_phrases(doctrine, required)


def test_frontier_ownership_policy_is_resident_in_every_carrier() -> None:
    required = (
        "**Frontier ownership.**",
        "end-to-end goal and hard\n  judgment",
        "independent, gated work concurrently",
        "cheapest reliable",
        "explicit ~<30-line judgment-dense exception applies",
        "verify until done",
        "stop only for missing\n  authority or a real blocker",
        "`skills/_shared/ORCHESTRATION.md`\n  §6",
    )
    sources = [ROOT / "install.sh", *(ROOT / name for name in CARRIERS)]
    for path in sources:
        text = path.read_text(encoding="utf-8")
        assert not missing_phrases(text, required), path.name

    doctrine = (ROOT / "skills/_shared/ORCHESTRATION.md").read_text(encoding="utf-8")
    team_lead = (ROOT / "skills/team-lead/SKILL.md").read_text(encoding="utf-8")
    assert "expected diff of 30+ lines closes it regardless of\ndispatch cost" in doctrine
    assert "expected diff of 30+ lines closes the direct-execution exception" in team_lead


def test_routing_receipt_and_speed_semantics_are_resident_in_every_carrier() -> None:
    required = (
        "Before root/child mutation",
        "Project/AGENTS.md\n  authority beats generic default",
        "speed never waives required routes",
        "Delegate SPEC'D+GATED >~30-line work",
        "frontier owns unresolved diagnosis",
        "Late receipt: stop, re-route rest, cold-review early edits",
    )
    sources = [ROOT / "install.sh", *(ROOT / name for name in CARRIERS)]
    for path in sources:
        text = path.read_text(encoding="utf-8")
        assert not missing_phrases(text, required), path.name


def test_catalog_only_refreshes_external_carriers_without_host_install() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp)
        (target / "AGENTS.md").write_text("# Local\n", encoding="utf-8")
        subprocess.run(
            [str(ROOT / "install.sh"), "--project", tmp, "--catalog-only"],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )
        text = (target / "AGENTS.md").read_text(encoding="utf-8")
        assert text.startswith("# Local\n")
        assert "Delegate SPEC'D+GATED >~30-line work" in text
        assert not (target / ".codex").exists()


def test_end_to_end_ownership_policy_gate_rejects_partial_progress_drift() -> None:
    required = ("Partial progress is not a stopping\ncondition",)
    doctrine = (ROOT / "skills/_shared/ORCHESTRATION.md").read_text(
        encoding="utf-8")
    drifted = doctrine.replace(required[0], "Partial progress may stop work", 1)
    assert missing_phrases(drifted, required) == list(required)


def test_orchestration_skills_reference_canonical_economy_policy() -> None:
    for name in FRONTIER_ECONOMY_SKILLS:
        text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        assert "ORCHESTRATION.md" in text, name
        assert "§6" in text, name


def test_retired_doctrine_skills_stay_deleted() -> None:
    # 2026-07-19 catalog contraction (eval/FINDINGS.md "Catalog cuts v1.12"):
    # a retired body silently reappearing would re-grow the resident catalog.
    for name in (
        "fable-mode", "lean-execution", "plan-first-execute",
        "requirements-ledger", "standing-orders", "wayfinder",
        "self-improvement-loops",
    ):
        assert not (ROOT / "skills" / name).exists(), name


TESTS = [value for name, value in sorted(globals().items()) if name.startswith("test_")]


def main() -> int:
    failed = 0
    for test in TESTS:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")
    print(f"{len(TESTS) - failed}/{len(TESTS)} passed")
    return failed


if __name__ == "__main__":
    sys.exit(main())
