"""Shared utilities for skill-simulation harnesses.

Designed for the 4 sim shapes:
  - CALIBRATION: classifier-style skills (write-gate, prompt-triage). Labeled
    pos/neg corpus → accuracy/precision/recall/F1.
  - FUZZ: parser / file-handling skills (cache-lint, wiki-memory). Malformed
    inputs → crash rate + correctness checks.
  - SCALE: batch-processing skills (memory-decay). N=10/100/1k/10k → linear?
  - INTEGRATION: cross-skill end-to-end pipelines.

Each sim should:
  1. Use `repo_root()` to find /Users/za/Documents/brainer/ regardless of cwd.
  2. Use `import_skill_module(name, module)` to load skill code without sys.path hacks.
  3. Use `Report` to collect results and `write_report(name, report)` to save JSON.
  4. Use `print_report(name, report)` for a consistent console summary.
  5. Return 0 / 1 based on report.passed.

Conventions:
  - sim filename: eval/sims/<skill>_<shape>.py (e.g. write_gate_corpus.py)
  - result JSON:  eval/sims/results/<skill>_<shape>.json
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def repo_root() -> Path:
    """Find the project root (the one containing skills/ and eval/)."""
    p = Path(__file__).resolve()
    while p != p.parent:
        if (p / "skills").is_dir() and (p / "eval").is_dir():
            return p
        p = p.parent
    raise RuntimeError("could not find repo root")


REPO = repo_root()


def import_skill_module(skill: str, module: str):
    """Import a Python module from skills/<skill>/tools/<module>.py.

    Returns the loaded module. Adds tools/ to sys.path the first time it's called
    for a given skill so within-package imports keep working.
    """
    tools_dir = REPO / "skills" / skill / "tools"
    if not tools_dir.is_dir():
        raise FileNotFoundError(f"no tools dir for skill {skill!r}: {tools_dir}")
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    import importlib
    return importlib.import_module(module)


@dataclass
class Report:
    """Common shape across sim types — flexible payload, fixed metadata."""
    skill: str
    shape: str                   # "calibration" / "fuzz" / "scale" / "integration"
    summary: dict[str, Any] = field(default_factory=dict)
    findings: list[dict[str, Any]] = field(default_factory=list)
    elapsed_s: float = 0.0
    passed: bool = True

    def finding(self, **kwargs) -> None:
        self.findings.append(kwargs)


def write_report(report: Report) -> Path:
    out_dir = REPO / "eval/sims/results"
    name = f"{report.skill}_{report.shape}.json"
    path = out_dir / name
    if os.environ.get("BRAINER_CHECK_NO_WRITE") == "1":
        return path
    out_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "skill": report.skill,
        "shape": report.shape,
        "elapsed_s": report.elapsed_s,
        "passed": report.passed,
        "summary": report.summary,
        "findings": report.findings,
    }, indent=2, default=str))
    return path


def print_report(report: Report) -> None:
    head = f"=== {report.skill} · {report.shape} sim ({report.elapsed_s:.2f}s) ==="
    print(head)
    for k, v in report.summary.items():
        print(f"  {k}: {v}")
    if not report.passed:
        print(f"  STATUS: FAILED")


class Timer:
    def __init__(self) -> None:
        self.t0 = time.time()

    def elapsed(self) -> float:
        return time.time() - self.t0


# --- Calibration helpers (classifier sims) ------------------------------

@dataclass
class LabeledCase:
    label: str            # short slug for identification
    inputs: tuple         # whatever the classifier takes
    expected: Any         # ground truth


def calibration_metrics(rows: list[dict]) -> dict:
    """Compute accuracy/precision/recall/F1 from rows with {'correct': bool,
    'expected': bool, 'actual': bool}. Binary case only — multi-class harnesses
    should compute their own confusion matrix."""
    n = len(rows)
    if not n:
        return {"n": 0}
    tp = sum(1 for r in rows if r["expected"] and r["actual"])
    tn = sum(1 for r in rows if not r["expected"] and not r["actual"])
    fp = sum(1 for r in rows if not r["expected"] and r["actual"])
    fn = sum(1 for r in rows if r["expected"] and not r["actual"])
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    return {
        "n": n,
        "accuracy": round((tp + tn) / n, 3),
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(2 * precision * recall / max(1e-9, precision + recall), 3),
        "tp": tp, "tn": tn, "fp": fp, "fn": fn,
    }


# --- Fuzz helpers (parser/file sims) ------------------------------------

def common_fuzz_payloads() -> dict[str, bytes | str]:
    """Returns a set of generally-evil inputs that any file-handling code should
    survive without crashing. Skill-specific fuzz sims should EXTEND this."""
    import random
    return {
        "empty": "",
        "whitespace": "   \n\n\t\n",
        "bom_utf8": "﻿" + "hello\nworld\n",
        "crlf": "hello\r\nworld\r\n",
        "latin1": "café résumé naïve " * 50,
        "cjk_rtl": "テスト 中文 العربية " * 50,
        "huge_1mb": "x" * 1_000_000,
        "binary_garbage": bytes(random.randint(0, 255) for _ in range(2000)),
        "long_line_no_nl": "x" * 50_000,
        "many_short_lines": "a\n" * 5_000,
        "dos_substitutions": "$(date) " * 5_000,
        "nul_bytes": "a\x00b\x00c" * 100,
    }


# --- Scale helpers (batch sims) ----------------------------------------

DEFAULT_SCALE_SIZES = (10, 100, 1000, 10000)


def assert_linear_scaling(times_per_item: list[float], threshold: float = 5.0) -> bool:
    """Per-item time should stay within `threshold`× across the size sweep.
    Small N is filesystem-bound; large N exposes algorithmic issues."""
    if not times_per_item:
        return True
    return max(times_per_item) / max(1e-9, min(times_per_item)) < threshold
