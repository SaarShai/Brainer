import importlib.util
from pathlib import Path

import scripts.check_drift_probes as probes

HOOK_PATH = Path(__file__).resolve().parents[1] / "skills" / "compliance-canary" / "tools" / "hook.py"
HOOK_SPEC = importlib.util.spec_from_file_location("compliance_canary_hook", HOOK_PATH)
assert HOOK_SPEC and HOOK_SPEC.loader
hook = importlib.util.module_from_spec(HOOK_SPEC)
HOOK_SPEC.loader.exec_module(hook)


def test_drift_probe_checker_passes():
    errors = []
    for path in sorted(probes.SKILLS.glob("*/drift_probes.json")):
        errors.extend(probes.validate_file(path))
    assert not errors


def test_unknown_probe_kind_is_rejected():
    errors = probes.validate_probe(
        {"id": "bad", "kind": "madeup", "message": "bad"},
        "fixture/drift_probes.json",
        set(),
    )
    assert any("unknown kind" in error for error in errors)


def test_invalid_probe_regex_is_rejected():
    errors = probes.validate_probe(
        {"id": "bad-regex", "kind": "forbidden_regex", "pattern": "(", "message": "bad"},
        "fixture/drift_probes.json",
        set(),
    )
    assert any("invalid regex" in error for error in errors)


def test_invalid_unless_pattern_is_rejected():
    errors = probes.validate_probe(
        {
            "id": "bad-unless",
            "kind": "forbidden_regex",
            "pattern": "drift",
            "unless_pattern": "(",
            "message": "bad",
        },
        "fixture/drift_probes.json",
        set(),
    )
    assert any("invalid regex in unless_pattern" in error for error in errors)


def test_forbidden_regex_unless_pattern_suppresses_match():
    result = hook.detect_forbidden_regex(
        {
            "id": "style",
            "kind": "forbidden_regex",
            "pattern": "(?i)prompt-only",
            "unless_pattern": "(?i)test artifact",
        },
        [{"text": "This is a prompt-only test artifact."}],
        [],
    )
    assert result is None
