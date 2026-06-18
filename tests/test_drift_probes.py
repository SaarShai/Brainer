import scripts.check_drift_probes as probes


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
