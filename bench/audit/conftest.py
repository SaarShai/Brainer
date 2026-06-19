"""Local pytest config for the audit performance benchmarks.

Registers the ``slow`` marker so the benchmark module can self-mark without
emitting an "unknown mark" warning. This conftest only applies under
``bench/audit/`` and is never loaded by ``make test`` (whose ``testpaths`` is
``["tests"]`` per the repo ``pyproject.toml``), so these benchmarks stay out of
the default fast gate. Run them explicitly:

    python3 -m pytest bench/audit/bench_audit_perf.py -v -s
    # or, with no pytest dependency at all:
    python3 bench/audit/bench_audit_perf.py
"""
from __future__ import annotations


def pytest_configure(config):  # noqa: D401
    config.addinivalue_line(
        "markers",
        "slow: perf/efficiency benchmark; excluded from the default fast gate.",
    )
