#!/usr/bin/env python3
"""Performance / efficiency benchmarks for the Brainer audit system.

PURPOSE
    Regression protection + documented baselines for the audit hot paths. The
    gates here are deliberately GENEROUS (several multiples of the measured
    baseline) so they protect against order-of-magnitude regressions WITHOUT
    flaking on a busy CI box. Each benchmark prints the measured numbers so a
    human can see the real baseline next to the gate.

WHAT IS MEASURED
    1. Hook no-marker overhead      -- the cheap path: no marker present, hook
                                       must write zero files and return fast.
    2. Hook active-marker overhead  -- marker armed, one event appended per
                                       invocation; per-event wall time.
    3. Append integrity under load  -- many concurrent processes invoke the
                                       hook against ONE marker; the resulting
                                       JSONL must contain EXACTLY the expected
                                       number of valid, parseable lines (no
                                       torn / interleaved writes).
    4. Inspector/detector runtime   -- load_events + run_detectors over large
                                       synthetic JSONL (1k and 10k events).
    5. Sidecar scan cost            -- synthetic artifact dir with many files;
                                       the ``max_files`` cap must be respected
                                       and the scan must be bounded.

SAFETY / DETERMINISM
    * All synthetic data is generated inside a fresh tempdir; the real
      ``.brainer/`` is never read or mutated. The tempdir lives OUTSIDE the
      repo, so the ``BRAINER_CHECK_NO_WRITE`` repo guard never suppresses the
      writes we are trying to measure.
    * Content is generated from a fixed seed (``random.Random(SEED)``); no
      wall-clock randomness feeds the payload bodies.

USAGE
    # Standalone (no pytest needed) -- prints baselines, asserts gates, exits
    # non-zero on failure:
        python3 bench/audit/bench_audit_perf.py

    # Under pytest (slow-marked, NOT collected by ``make test`` because
    # pyproject testpaths == ["tests"]); -s shows the printed baselines:
        python3 -m pytest bench/audit/bench_audit_perf.py -v -s
"""
from __future__ import annotations

import json
import os
import random
import statistics
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Tuple

# ---------------------------------------------------------------------------
# Locate the audit tools relative to this file (bench/audit/ -> repo root).
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS = REPO_ROOT / "skills" / "brainer-audit" / "tools"
HOOK_PY = TOOLS / "hook.py"

# Import detector + sidecar helpers directly (in-process timing, no subprocess
# overhead for tasks 4 & 5).
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(REPO_ROOT / "skills" / "_shared"))
from detectors import load_events, run_detectors  # noqa: E402
from watch_artifacts import artifact_events, build_sidecar_events  # noqa: E402

SEED = 1234567

# ---------------------------------------------------------------------------
# Generous gates. Measured baselines on the dev box (arm64, py3.9) recorded as
# comments; gates are multiples chosen to catch order-of-magnitude regressions
# without flaking. Override via env if a slow CI box needs headroom.
# ---------------------------------------------------------------------------
# Per-invocation cost includes Python interpreter cold start (~20-40ms), so the
# gates below are dominated by process spawn, not audit logic. They are tagged
# "subprocess" to make that explicit.
GATE_NO_MARKER_P95_S = float(os.environ.get("BENCH_NO_MARKER_P95_S", "2.0"))      # measured ~0.03-0.06s/call
GATE_ACTIVE_MARKER_P95_S = float(os.environ.get("BENCH_ACTIVE_MARKER_P95_S", "2.0"))  # measured ~0.03-0.06s/call
GATE_DETECT_1K_S = float(os.environ.get("BENCH_DETECT_1K_S", "5.0"))             # measured ~0.05-0.15s
GATE_DETECT_10K_S = float(os.environ.get("BENCH_DETECT_10K_S", "30.0"))          # measured ~0.5-2.0s
GATE_SIDECAR_S = float(os.environ.get("BENCH_SIDECAR_S", "10.0"))               # measured ~0.05-0.3s

# Iteration counts kept modest so the whole file runs in a few seconds.
N_NO_MARKER = int(os.environ.get("BENCH_N_NO_MARKER", "40"))
N_ACTIVE_MARKER = int(os.environ.get("BENCH_N_ACTIVE_MARKER", "40"))
N_CONCURRENCY = int(os.environ.get("BENCH_N_CONCURRENCY", "60"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _p95(samples: List[float]) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    # nearest-rank p95
    idx = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
    return ordered[idx]


def _summary(samples: List[float]) -> str:
    return (
        f"n={len(samples)} "
        f"min={min(samples) * 1000:.2f}ms "
        f"median={statistics.median(samples) * 1000:.2f}ms "
        f"p95={_p95(samples) * 1000:.2f}ms "
        f"max={max(samples) * 1000:.2f}ms"
    )


def _arm_marker(root: Path, *, events_name: str = "events.jsonl") -> Path:
    """Create a brainer-audit marker under ``root`` and return the events path.

    ``events_path`` is stored relative so the hook resolves it under
    ``.brainer/brainer-audit/`` (path-confinement honored).
    """
    base = root / ".brainer" / "brainer-audit"
    base.mkdir(parents=True, exist_ok=True)
    (base / "current.json").write_text(
        json.dumps({"events_path": events_name}), encoding="utf-8"
    )
    return base / events_name


def _run_hook(root: Path, payload: Dict[str, Any], *, event: str = "UserPromptSubmit") -> float:
    """Invoke hook.py as a subprocess (the real entrypoint hosts use).

    Returns wall time in seconds. ``BRAINER_CHECK_NO_WRITE`` is explicitly unset
    in the child so the repo guard cannot interfere (tmp root is outside the
    repo anyway, but be defensive).
    """
    env = dict(os.environ)
    env.pop("BRAINER_CHECK_NO_WRITE", None)
    data = json.dumps(payload).encode("utf-8")
    start = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, str(HOOK_PY), "--host", "claude", "--event", event, "--root", str(root)],
        input=data,
        capture_output=True,
        env=env,
    )
    elapsed = time.perf_counter() - start
    if proc.returncode != 0:
        raise AssertionError(
            f"hook.py exited {proc.returncode}: {proc.stderr.decode('utf-8', 'replace')[:400]}"
        )
    return elapsed


def _gen_payloads(n: int) -> List[Dict[str, Any]]:
    """Deterministic typical UserPromptSubmit payloads (fixed seed)."""
    rng = random.Random(SEED)
    verbs = ["fix", "refactor", "add", "investigate", "audit", "benchmark"]
    nouns = ["the hook", "the detector", "this module", "the sidecar", "the marker path"]
    out: List[Dict[str, Any]] = []
    for i in range(n):
        prompt = f"please {rng.choice(verbs)} {rng.choice(nouns)} and run the tests (#{i})"
        out.append({"prompt": prompt, "session_id": f"bench-{i % 7}", "turn_id": str(i)})
    return out


def _gen_events_jsonl(path: Path, n: int) -> None:
    """Write n deterministic, detector-exercising events to a JSONL file.

    Mixes event kinds so several detectors actually do work (completion claims,
    noisy tool_results, user_prompt requirements, file_changes) rather than
    short-circuiting on a uniform stream.
    """
    rng = random.Random(SEED)
    path.parent.mkdir(parents=True, exist_ok=True)
    kinds = ["assistant_message", "tool_result", "user_prompt", "tool_call", "file_change"]
    with path.open("w", encoding="utf-8") as fh:
        for i in range(n):
            kind = kinds[i % len(kinds)]
            ev: Dict[str, Any] = {
                "schema_version": 1,
                "mode": "brainer-audit",
                "session_id": f"s{i % 11}",
                "host": "claude",
                "project_path": "/tmp/bench",
                "event": kind,
                "timestamp": f"2026-01-01T00:{(i // 60) % 60:02d}:{i % 60:02d}Z",
            }
            if kind == "assistant_message":
                ev["content_summary"] = (
                    "done, tests passed and committed" if i % 9 == 0
                    else f"working on step {i} of the task with details {rng.random():.4f}"
                )
            elif kind == "tool_result":
                ev["command"] = "pytest -q" if i % 5 == 0 else f"echo step {i}"
                ev["exit_code"] = 0
                if i % 13 == 0:
                    ev["content_summary"] = "\x1b[31m" + ("progress " * 80)  # noisy
                    ev["output_bytes"] = 20000
                    ev["line_count"] = 300
                else:
                    ev["content_summary"] = f"ok {rng.random():.4f}"
            elif kind == "user_prompt":
                ev["content_summary"] = f"user asks for thing {i}"
                if i % 7 == 0:
                    ev["requirements"] = [f"requirement-{i}-a", f"requirement-{i}-b"]
            elif kind == "tool_call":
                ev["tool"] = "Bash"
                ev["command"] = f"ls -la dir{i}"
            else:  # file_change
                ev["path"] = f"src/module_{i}.py" if i % 4 else f"wiki/page_{i}.md"
                ev["content_summary"] = f"M\tsrc/module_{i}.py"
            fh.write(json.dumps(ev, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------
# Benchmark bodies (each returns a (label, ok, detail) tuple for the runner).
# ---------------------------------------------------------------------------
def bench_no_marker_overhead() -> Tuple[str, bool, str]:
    with tempfile.TemporaryDirectory(prefix="brnr_nomark_") as td:
        root = Path(td)
        payloads = _gen_payloads(N_NO_MARKER)
        samples = [_run_hook(root, p) for p in payloads]
        files = list((root / ".brainer").rglob("*")) if (root / ".brainer").exists() else []
        wrote_nothing = len([f for f in files if f.is_file()]) == 0
        p95 = _p95(samples)
        detail = (
            f"NO-MARKER: {_summary(samples)} | files_written={len([f for f in files if f.is_file()])} "
            f"| gate p95<{GATE_NO_MARKER_P95_S * 1000:.0f}ms"
        )
        ok = wrote_nothing and p95 < GATE_NO_MARKER_P95_S
        assert wrote_nothing, f"no-marker path wrote files: {files}"
        assert p95 < GATE_NO_MARKER_P95_S, f"no-marker p95 {p95:.4f}s exceeds gate {GATE_NO_MARKER_P95_S}s"
        return ("no_marker_overhead", ok, detail)


def bench_active_marker_overhead() -> Tuple[str, bool, str]:
    with tempfile.TemporaryDirectory(prefix="brnr_active_") as td:
        root = Path(td)
        events_path = _arm_marker(root)
        payloads = _gen_payloads(N_ACTIVE_MARKER)
        samples = [_run_hook(root, p) for p in payloads]
        lines = events_path.read_text(encoding="utf-8").splitlines()
        # exactly one event appended per invocation
        exactly_one_each = len(lines) == N_ACTIVE_MARKER
        all_parse = all(isinstance(json.loads(ln), dict) for ln in lines if ln.strip())
        p95 = _p95(samples)
        detail = (
            f"ACTIVE-MARKER: {_summary(samples)} | lines={len(lines)} (expected {N_ACTIVE_MARKER}) "
            f"| gate p95<{GATE_ACTIVE_MARKER_P95_S * 1000:.0f}ms"
        )
        ok = exactly_one_each and all_parse and p95 < GATE_ACTIVE_MARKER_P95_S
        assert exactly_one_each, f"expected {N_ACTIVE_MARKER} appended lines, got {len(lines)}"
        assert all_parse, "an appended line was not valid JSON"
        assert p95 < GATE_ACTIVE_MARKER_P95_S, f"active-marker p95 {p95:.4f}s exceeds gate {GATE_ACTIVE_MARKER_P95_S}s"
        return ("active_marker_overhead", ok, detail)


def bench_append_integrity_concurrency() -> Tuple[str, bool, str]:
    """Spawn many CONCURRENT hook subprocesses against one marker; the JSONL
    must end up with EXACTLY N valid lines (no torn / interleaved writes)."""
    with tempfile.TemporaryDirectory(prefix="brnr_conc_") as td:
        root = Path(td)
        events_path = _arm_marker(root)
        payloads = _gen_payloads(N_CONCURRENCY)

        env = dict(os.environ)
        env.pop("BRAINER_CHECK_NO_WRITE", None)

        def _spawn(p: Dict[str, Any]) -> int:
            proc = subprocess.run(
                [sys.executable, str(HOOK_PY), "--host", "claude",
                 "--event", "UserPromptSubmit", "--root", str(root)],
                input=json.dumps(p).encode("utf-8"),
                capture_output=True,
                env=env,
            )
            return proc.returncode

        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=min(16, N_CONCURRENCY)) as ex:
            rcs = list(ex.map(_spawn, payloads))
        elapsed = time.perf_counter() - start

        assert all(rc == 0 for rc in rcs), f"some hook subprocesses failed: {rcs}"

        raw_lines = events_path.read_text(encoding="utf-8").splitlines()
        valid = 0
        torn = 0
        for ln in raw_lines:
            if not ln.strip():
                continue
            try:
                obj = json.loads(ln)
            except json.JSONDecodeError:
                torn += 1
                continue
            if isinstance(obj, dict):
                valid += 1
            else:
                torn += 1
        ok = (valid == N_CONCURRENCY) and (torn == 0)
        detail = (
            f"CONCURRENCY: spawned={N_CONCURRENCY} valid_lines={valid} torn_lines={torn} "
            f"total_lines={len(raw_lines)} wall={elapsed:.3f}s "
            f"-> {'EXACT, no torn writes' if ok else 'MISMATCH'}"
        )
        assert torn == 0, f"found {torn} torn/invalid JSONL lines under concurrency"
        assert valid == N_CONCURRENCY, (
            f"expected exactly {N_CONCURRENCY} valid lines, got {valid} "
            f"(total raw lines {len(raw_lines)})"
        )
        return ("append_integrity_concurrency", ok, detail)


def _bench_detect_at(n: int, gate_s: float) -> Tuple[str, bool, str]:
    with tempfile.TemporaryDirectory(prefix=f"brnr_detect_{n}_") as td:
        events_path = Path(td) / "events.jsonl"
        _gen_events_jsonl(events_path, n)
        # time load + detect together (the full inspector hot path)
        start = time.perf_counter()
        events = load_events(events_path)
        findings = run_detectors(events)
        elapsed = time.perf_counter() - start
        assert len(events) == n, f"loaded {len(events)} events, expected {n}"
        ok = elapsed < gate_s
        detail = (
            f"DETECT {n}: load+run_detectors={elapsed * 1000:.1f}ms "
            f"events={len(events)} findings={len(findings)} | gate<{gate_s}s"
        )
        assert ok, f"detector runtime {elapsed:.3f}s over {n} events exceeds gate {gate_s}s"
        return (f"detector_runtime_{n}", ok, detail)


def bench_detector_runtime_1k() -> Tuple[str, bool, str]:
    return _bench_detect_at(1000, GATE_DETECT_1K_S)


def bench_detector_runtime_10k() -> Tuple[str, bool, str]:
    return _bench_detect_at(10000, GATE_DETECT_10K_S)


def bench_sidecar_scan_cap() -> Tuple[str, bool, str]:
    """Synthetic artifact dir with many nested files; the ``max_files`` cap must
    be respected and the scan bounded (no unbounded recursion)."""
    with tempfile.TemporaryDirectory(prefix="brnr_sidecar_") as td:
        root = Path(td)
        art = root / "artifacts"
        total_files = 500
        # spread across nested subdirs to exercise rglob recursion
        for i in range(total_files):
            sub = art / f"d{i % 10}" / f"e{i % 5}"
            sub.mkdir(parents=True, exist_ok=True)
            (sub / f"f{i}.log").write_text(f"line {i}\n", encoding="utf-8")

        cap = 50
        start = time.perf_counter()
        evs = artifact_events(root, "bench-sidecar", [str(art)], max_files=cap, include_content=False)
        elapsed = time.perf_counter() - start

        file_changes = [e for e in evs if e.get("event") == "file_change"]
        cap_respected = len(file_changes) <= cap
        # also confirm a smaller cap returns fewer events (cap is the binding limit)
        evs_small = artifact_events(root, "bench-sidecar", [str(art)], max_files=10, include_content=False)
        small_changes = [e for e in evs_small if e.get("event") == "file_change"]
        small_respected = len(small_changes) <= 10

        ok = cap_respected and small_respected and elapsed < GATE_SIDECAR_S
        detail = (
            f"SIDECAR: total_files={total_files} cap={cap} file_change_events={len(file_changes)} "
            f"(cap10 -> {len(small_changes)}) scan={elapsed * 1000:.1f}ms | gate<{GATE_SIDECAR_S}s"
        )
        assert cap_respected, f"max_files cap {cap} not respected: {len(file_changes)} file_change events"
        assert small_respected, f"cap=10 not respected: {len(small_changes)} events"
        assert elapsed < GATE_SIDECAR_S, f"sidecar scan {elapsed:.3f}s over {total_files} files exceeds gate"
        return ("sidecar_scan_cap", ok, detail)


ALL_BENCHES = [
    bench_no_marker_overhead,
    bench_active_marker_overhead,
    bench_append_integrity_concurrency,
    bench_detector_runtime_1k,
    bench_detector_runtime_10k,
    bench_sidecar_scan_cap,
]


# ---------------------------------------------------------------------------
# pytest entrypoints (slow-marked; NOT collected by ``make test``).
# ---------------------------------------------------------------------------
try:
    import pytest

    @pytest.mark.slow
    def test_no_marker_overhead():
        _, ok, detail = bench_no_marker_overhead()
        print(detail)
        assert ok

    @pytest.mark.slow
    def test_active_marker_overhead():
        _, ok, detail = bench_active_marker_overhead()
        print(detail)
        assert ok

    @pytest.mark.slow
    def test_append_integrity_concurrency():
        _, ok, detail = bench_append_integrity_concurrency()
        print(detail)
        assert ok

    @pytest.mark.slow
    def test_detector_runtime_1k():
        _, ok, detail = bench_detector_runtime_1k()
        print(detail)
        assert ok

    @pytest.mark.slow
    def test_detector_runtime_10k():
        _, ok, detail = bench_detector_runtime_10k()
        print(detail)
        assert ok

    @pytest.mark.slow
    def test_sidecar_scan_cap():
        _, ok, detail = bench_sidecar_scan_cap()
        print(detail)
        assert ok
except ImportError:  # pragma: no cover - pytest is optional for standalone runs
    pass


# ---------------------------------------------------------------------------
# Standalone runner (no pytest required).
# ---------------------------------------------------------------------------
def main() -> int:
    print("=" * 78)
    print("Brainer audit performance benchmarks (generous regression gates)")
    print(f"python={sys.version.split()[0]}  hook={HOOK_PY}")
    print("=" * 78)
    failures = 0
    for fn in ALL_BENCHES:
        try:
            label, ok, detail = fn()
        except AssertionError as exc:
            failures += 1
            print(f"[FAIL] {fn.__name__}: {exc}")
            continue
        except Exception as exc:  # pragma: no cover
            failures += 1
            print(f"[ERROR] {fn.__name__}: {type(exc).__name__}: {exc}")
            continue
        status = "PASS" if ok else "FAIL"
        if not ok:
            failures += 1
        print(f"[{status}] {label}")
        print(f"       {detail}")
    print("=" * 78)
    print(f"benchmarks: {len(ALL_BENCHES)}  failures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
