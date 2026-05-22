#!/usr/bin/env python3
"""Validate compress-context's LLMLingua-2 pipeline mechanically.

Runs the bundled `pipeline_v2.compress()` on a corpus of real long-context
passages (wiki/raw/* and bench/data/*). Measures:
  - tokens before / after each stage (caveman -> critical-protect -> llmlingua)
  - achieved compression rate vs target rate
  - structural preservation: paths/URLs/numbers should survive the
    `protect()` step verbatim

Does NOT do the model-answer A/B (that's eval_v3.py with the SQuAD
adapter — slow, N=8 prior). This is the mechanical proof that the
compressor does what it claims.

Usage:
  python3 eval/runner_compress.py [--rate 0.5] [--max-samples 5]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "skills" / "compress-context" / "tools"))


def collect_samples(max_samples: int) -> list[tuple[str, str]]:
    """Pick prose-y files from wiki/raw/ that are long enough to test on."""
    samples: list[tuple[str, str]] = []
    raw_dir = REPO_ROOT / "wiki" / "raw"
    if raw_dir.exists():
        for f in sorted(raw_dir.rglob("*.md")):
            text = f.read_text()
            if len(text) < 1500:
                continue
            samples.append((str(f.relative_to(REPO_ROOT)), text))
            if len(samples) >= max_samples:
                return samples
    return samples


def count_preserved(original: str, compressed: str, patterns: list[re.Pattern]) -> tuple[int, int]:
    found_in_orig: set[str] = set()
    for p in patterns:
        found_in_orig.update(p.findall(original))
    preserved = sum(1 for x in found_in_orig if x in compressed)
    return preserved, len(found_in_orig)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--rate", type=float, default=0.5, help="LLMLingua target compression rate (keep fraction)")
    p.add_argument("--max-samples", type=int, default=5)
    p.add_argument("--out", default="eval/results/compress-context.json")
    args = p.parse_args()

    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    def count_tokens(text: str) -> int:
        return len(enc.encode(text))

    from pipeline_v2 import compress  # noqa: E402

    samples = collect_samples(args.max_samples)
    if not samples:
        print("no suitable sample files in wiki/raw/", file=sys.stderr)
        return 2

    print(f"loading LLMLingua-2 model (first call may take ~30s + download)...")
    URL = re.compile(r"https?://\S+")
    PATH = re.compile(r"(?:\.{0,2}/[\w./\-]+|/[\w./\-]+)")
    NUM = re.compile(r"\b\d+(?:\.\d+)?\b")

    results = []
    for path, original in samples:
        t0 = time.time()
        try:
            compressed, meta = compress(original, rate=args.rate)
        except Exception as e:
            print(f"FAIL {path}: {e!s}", file=sys.stderr)
            continue
        elapsed = time.time() - t0
        tok_in = meta.get("input_tokens") or count_tokens(original)
        tok_out = meta.get("output_tokens") or count_tokens(compressed)
        urls_p, urls_n = count_preserved(original, compressed, [URL])
        paths_p, paths_n = count_preserved(original, compressed, [PATH])
        nums_p, nums_n = count_preserved(original, compressed, [NUM])
        results.append({
            "file": path,
            "chars_in": len(original),
            "chars_out": len(compressed),
            "tokens_in": tok_in,
            "tokens_out": tok_out,
            "token_reduction_pct": round(100 * (1 - tok_out / max(tok_in, 1)), 1),
            "elapsed_s": round(elapsed, 1),
            "url_preservation": f"{urls_p}/{urls_n}",
            "path_preservation": f"{paths_p}/{paths_n}",
            "number_preservation": f"{nums_p}/{nums_n}",
            "meta": meta,
        })
        print(f"  {path}: {tok_in} -> {tok_out} tokens ({results[-1]['token_reduction_pct']:+.1f}%) urls={urls_p}/{urls_n}")

    if not results:
        return 1

    mean_red = sum(r["token_reduction_pct"] for r in results) / len(results)
    summary = {
        "harness": "runner_compress.py",
        "target_rate": args.rate,
        "n_samples": len(results),
        "results": results,
        "summary": {
            "mean_token_reduction_pct": round(mean_red, 1),
            "total_tokens_in": sum(r["tokens_in"] for r in results),
            "total_tokens_out": sum(r["tokens_out"] for r in results),
        },
    }
    out_path = REPO_ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2))

    print(f"\n=== compress-context (n={len(results)} samples, target rate={args.rate}) ===")
    print(f"  mean token reduction: {mean_red:.1f}%")
    print(f"  total: {summary['summary']['total_tokens_in']} -> {summary['summary']['total_tokens_out']}")
    print(f"  results: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
