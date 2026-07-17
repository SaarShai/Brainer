#!/usr/bin/env python3
"""Deterministic contracts for the frontier-default skill surface."""
from __future__ import annotations

import json
import re
import sys
from math import ceil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.prune_optin_hooks import prune  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
MANUAL_SKILLS = (
    "caveman-ultra",
    "fable-mode",
    "learn-skill",
    "lean-execution",
    "loop-engineering",
    "plan-first-execute",
    "prompt-triage",
    "requirements-ledger",
    "standing-orders",
    "task-retrospective",
    "team-lead",
    "think",
    "verify-before-completion",
    "wayfinder",
)
ROLE_FILES = (
    ROOT / ".claude/agents/builder.md",
    ROOT / ".claude/agents/verifier.md",
    ROOT / ".claude/agents/research-lite.md",
)


def frontmatter(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), path
    return text.split("---", 2)[1]


def body(path: Path) -> str:
    return path.read_text(encoding="utf-8").split("---", 2)[2]


def token_estimate(text: str) -> int:
    return ceil(len(text) / 4) + text.count("\n")


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
