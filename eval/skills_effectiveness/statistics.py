"""Dependency-free preregistered paired statistics and trigger gates."""
from __future__ import annotations

import math
import random


def wilson_upper_one_sided(successes: int, total: int, confidence: float = 0.95) -> float:
    if total <= 0:
        raise ValueError("total must be positive")
    if confidence != 0.95:
        raise ValueError("only the preregistered 95% bound is supported")
    z = 1.6448536269514722
    p = successes / total
    den = 1 + z * z / total
    centre = p + z * z / (2 * total)
    radius = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    return min(1.0, (centre + radius) / den)


def trigger_metrics(expected: list[bool], fired: list[bool]) -> dict:
    if len(expected) != len(fired) or not expected:
        raise ValueError("expected and fired must be equally sized and non-empty")
    tp = sum(w and got for w, got in zip(expected, fired))
    fp = sum((not w) and got for w, got in zip(expected, fired))
    fn = sum(w and not got for w, got in zip(expected, fired))
    tn = sum((not w) and not got for w, got in zip(expected, fired))
    precision = tp / (tp + fp) if tp + fp else 0.0
    negatives = fp + tn
    upper = wilson_upper_one_sided(fp, negatives)
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "reviewed_precision": precision,
            "false_injection_rate": fp / negatives if negatives else None,
            "false_injection_upper_95_one_sided": upper,
            "gates": {"precision_ge_95pct": precision >= 0.95,
                      "false_injection_below_1pct": bool(negatives) and fp / negatives < 0.01,
                      "false_injection_upper_below_1pct": upper < 0.01}}


def exact_mcnemar(a_pass: list[bool], b_pass: list[bool]) -> dict:
    if len(a_pass) != len(b_pass) or not a_pass:
        raise ValueError("paired inputs must be equally sized and non-empty")
    a_only = sum(a and not b for a, b in zip(a_pass, b_pass))
    b_only = sum(b and not a for a, b in zip(a_pass, b_pass))
    n = a_only + b_only
    if n == 0:
        p = 1.0
    else:
        tail = sum(math.comb(n, k) for k in range(0, min(a_only, b_only) + 1)) / (2 ** n)
        p = min(1.0, 2 * tail)
    return {"a_only": a_only, "b_only": b_only, "discordant": n, "p_two_sided": p}


def paired_sign_test(a: list[float], b: list[float]) -> dict:
    if len(a) != len(b) or not a:
        raise ValueError("paired inputs must be equally sized and non-empty")
    positive = sum(y > x for x, y in zip(a, b))
    negative = sum(y < x for x, y in zip(a, b))
    n = positive + negative
    if n == 0:
        p = 1.0
    else:
        tail = sum(math.comb(n, k) for k in range(min(positive, negative) + 1)) / (2 ** n)
        p = min(1.0, 2 * tail)
    return {"positive": positive, "negative": negative, "ties": len(a) - n,
            "p_two_sided": p}


def paired_bootstrap_delta(a: list[float], b: list[float], *, samples: int = 10_000,
                           seed: int = 20260716) -> dict:
    if len(a) != len(b) or not a:
        raise ValueError("paired inputs must be equally sized and non-empty")
    rng = random.Random(seed)
    diffs = [y - x for x, y in zip(a, b)]
    means = []
    for _ in range(samples):
        means.append(sum(diffs[rng.randrange(len(diffs))] for _ in diffs) / len(diffs))
    means.sort()
    return {"delta": sum(diffs) / len(diffs),
            "ci95": [means[int(samples * 0.025)], means[min(samples - 1, int(samples * 0.975))]],
            "samples": samples, "seed": seed}
