"""Gate/probe spec liveness.

Every machine-readable gate/probe spec under ``skills/*/`` must parse and carry
its minimal top-level shape. Motivation:
docs/brainer-learning-failures-2026-07-06.md failure 5 (B5) — the gate
substrate (``tools/verify/specs.yaml`` in the old framework) sat silently
unparseable for three days and every gate consuming it went inert while looking
healthy. A spec that does not parse must fail loudly here, not at gate time.

JSON specs (``*probes*.json``, ``*gate*.json``) are always checked. YAML specs
(``specs.yaml`` and similar), when present, FAIL the run if PyYAML is not
importable — per B5 above, YAML is exactly the file class that rotted silently,
so a missing parser must be loud, not a skip. When no YAML specs exist the YAML
parametrization is empty and JSON coverage never depends on the YAML extra.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SKILLS = Path(__file__).resolve().parents[1] / "skills"

JSON_PATTERNS = ("*probes*.json", "*gate*.json")
YAML_PATTERNS = ("*.yaml", "*.yml")


def _collect(patterns: tuple[str, ...]) -> list[Path]:
    found: set[Path] = set()
    for pattern in patterns:
        found.update(SKILLS.glob(f"*/{pattern}"))
    return sorted(found)


JSON_SPECS = _collect(JSON_PATTERNS)
YAML_SPECS = _collect(YAML_PATTERNS)


def _spec_id(path: Path) -> str:
    return path.relative_to(SKILLS).as_posix()


def _assert_minimal_shape(data: object, path: Path) -> None:
    """Minimal expected top-level shape: a non-empty mapping, or a non-empty
    list of mappings (probe lists). Anything else means the gate reading this
    file would go inert or crash."""
    assert isinstance(data, (dict, list)), (
        f"{_spec_id(path)}: top level must be an object or a list of objects, "
        f"got {type(data).__name__}"
    )
    assert data, f"{_spec_id(path)}: spec is empty"
    if isinstance(data, list):
        for index, item in enumerate(data):
            assert isinstance(item, dict), (
                f"{_spec_id(path)}: entry {index} must be an object, "
                f"got {type(item).__name__}"
            )


def test_json_gate_probe_specs_exist():
    assert JSON_SPECS, (
        "no gate/probe JSON specs found under skills/*/ — catalog drift or a "
        "broken glob; the liveness check itself would be inert"
    )


@pytest.mark.parametrize("path", JSON_SPECS, ids=_spec_id)
def test_json_gate_probe_spec_parses(path: Path):
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    _assert_minimal_shape(data, path)
    if "probes" in path.name:
        assert isinstance(data, list), (
            f"{_spec_id(path)}: probe specs are lists of probe objects"
        )


@pytest.mark.parametrize("path", YAML_SPECS, ids=_spec_id)
def test_yaml_gate_spec_parses(path: Path):
    if importlib.util.find_spec("yaml") is None:
        pytest.fail(
            "PyYAML not installed but YAML gate specs exist under skills/*/ — "
            "install pyyaml (e.g. `pip install pyyaml`). Skipping here is how "
            "the old specs.yaml rotted silently for three days (B5); a YAML "
            "spec that cannot be parsed must fail loudly, not at gate time."
        )
    import yaml

    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    _assert_minimal_shape(data, path)
