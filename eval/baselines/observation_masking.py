#!/usr/bin/env python3
"""observation-masking baseline — the required control for any compaction skill.

FINDINGS.md lists observation-masking as a control that compaction skills MUST beat, but
it was only *cited* (arXiv 2508.21433: replacing past tool outputs with a placeholder
halves cost and matches LLM summarization on SWE-bench). This makes it *runnable*, so the
claim becomes measured.

Masking policy (the paper's): keep user/assistant TEXT and tool-CALL args; replace each
tool-RESULT body with `[output suppressed: N chars]`. Then measure, on the SAME transcript
and with the SAME ground-truth probes as `runner_keeper.py`:
  * compression ratio  — masked_chars / raw_chars
  * recall per category — files / cmds / errors / urls / nums that survive in the masked text

The head-to-head vs context-keeper falls straight out: masking keeps call args (so cmds
survive) but DROPS tool outputs — so any file / number / error / url that lives ONLY in a
tool result is lost. context-keeper extracts those, so it should win on output-embedded
recall while also compressing far harder (sidecar vs whole masked transcript).

Usage:
  python3 eval/baselines/observation_masking.py <transcript.jsonl> [--out path]
  # head-to-head (runs context-keeper extract on the same transcript too):
  python3 eval/baselines/observation_masking.py <transcript.jsonl> --vs-context-keeper
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = EVAL_DIR.parent
sys.path.insert(0, str(EVAL_DIR))
# Reuse the EXACT ground-truth + recall machinery context-keeper was scored with.
from runner_keeper import ground_truth, extracted_recall, iter_events, extract_text  # noqa: E402


def mask_transcript(jsonl_path: Path) -> dict:
    """Produce the observation-masked view: keep text + tool-call args, suppress outputs."""
    parts: list[str] = []
    suppressed_chars = 0
    n_results = 0
    n_tool_use = 0
    for ev in iter_events(jsonl_path):
        msg = ev.get("message") or ev
        content = msg.get("content", "") if isinstance(msg, dict) else ""
        if isinstance(content, str):
            parts.append(content)
            continue
        if not isinstance(content, list):
            continue
        for b in content:
            if not isinstance(b, dict):
                continue
            if "text" in b:
                parts.append(b["text"])
            elif b.get("type") == "tool_use":
                # KEEP the call args (this is what masking preserves — same shape as
                # extract_text, so a Bash command in the args still counts as recalled)
                parts.append(f"TOOL:{b.get('name','?')} INPUT:{json.dumps(b.get('input', {}))[:500]}")
                n_tool_use += 1
            elif b.get("type") == "tool_result":
                # SUPPRESS the output body — the defining move of observation-masking
                body = extract_text(b.get("content", ""))
                suppressed_chars += len(body)
                n_results += 1
                parts.append(f"[output suppressed: {len(body)} chars]")
    return {
        "masked_text": "\n".join(parts),
        "suppressed_chars": suppressed_chars,
        "n_tool_results_masked": n_results,
        "n_tool_use_kept": n_tool_use,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("--out", default=str(EVAL_DIR / "results" / "observation-masking.json"))
    ap.add_argument("--vs-context-keeper", action="store_true",
                    help="also run context-keeper extract.py on the same transcript and compare")
    args = ap.parse_args()

    transcript = Path(args.transcript)
    if not transcript.exists():
        print(f"not found: {transcript}", file=sys.stderr)
        return 2

    print(f"[1/3] ground truth from {transcript.name}")
    gt = ground_truth(transcript)
    print(f"      events={gt['events']} raw_chars={gt['raw_chars']} "
          f"files={len(gt['files'])} cmds={len(gt['cmds'])} errors={len(gt['errors'])} "
          f"urls={len(gt['urls'])} nums={len(gt['nums'])}")

    print("[2/3] observation-masking")
    t0 = time.time()
    masked = mask_transcript(transcript)
    mask_ms = int((time.time() - t0) * 1000)
    masked_text = masked["masked_text"]
    masked_chars = len(masked_text)
    mask_recall = extracted_recall(masked_text, gt)
    comp = round(masked_chars / max(gt["raw_chars"], 1), 4)
    print(f"      masked {masked_chars} chars ({comp*100:.1f}% of raw) in {mask_ms} ms; "
          f"suppressed {masked['n_tool_results_masked']} tool results "
          f"({masked['suppressed_chars']} chars)")
    for k, v in mask_recall.items():
        print(f"      {k}: {v:.1%}")

    summary = {
        "baseline": "observation-masking",
        "source": "arXiv 2508.21433",
        "transcript": str(transcript),
        "mask_ms": mask_ms,
        "raw_chars": gt["raw_chars"],
        "masked_chars": masked_chars,
        "compression_ratio": comp,
        "suppressed_chars": masked["suppressed_chars"],
        "n_tool_results_masked": masked["n_tool_results_masked"],
        "n_tool_use_kept": masked["n_tool_use_kept"],
        "events": gt["events"],
        "counts": {k: len(gt[k]) for k in ("files", "cmds", "errors", "urls", "nums")},
        "recall": mask_recall,
    }

    if args.vs_context_keeper:
        print("[3/3] context-keeper extract.py on the same transcript")
        extract_script = REPO_ROOT / "skills/context-keeper/tools/extract.py"
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
            ck_out = Path(f.name)
        t0 = time.time()
        proc = subprocess.run([sys.executable, str(extract_script), str(transcript),
                               "--out", str(ck_out)], capture_output=True, text=True, timeout=600)
        ck_ms = int((time.time() - t0) * 1000)
        if proc.returncode != 0:
            print(f"      extract failed: {proc.stderr[:300]}", file=sys.stderr)
        else:
            ck_md = ck_out.read_text()
            ck_recall = extracted_recall(ck_md, gt)
            ck_comp = round(len(ck_md) / max(gt["raw_chars"], 1), 4)
            summary["context_keeper"] = {
                "extract_ms": ck_ms, "extracted_chars": len(ck_md),
                "compression_ratio": ck_comp, "recall": ck_recall,
            }
            # head-to-head verdict
            cats = ["files_recall", "cmds_recall", "errors_recall", "urls_recall", "nums_recall"]
            ck_wins = [c for c in cats if ck_recall[c] > mask_recall[c] + 1e-9]
            mask_wins = [c for c in cats if mask_recall[c] > ck_recall[c] + 1e-9]
            summary["head_to_head"] = {
                "masking_compression": comp, "context_keeper_compression": ck_comp,
                "context_keeper_smaller_by_x": round(comp / max(ck_comp, 1e-9), 1),
                "context_keeper_recall_wins": ck_wins,
                "masking_recall_wins": mask_wins,
                "headline": (
                    f"context-keeper is {round(comp/max(ck_comp,1e-9),1)}× smaller "
                    f"({ck_comp*100:.1f}% vs {comp*100:.1f}% of raw) AND wins recall on "
                    f"{ck_wins or 'none'}; masking wins on {mask_wins or 'none'}"),
            }
            print(f"      context-keeper: {len(ck_md)} chars ({ck_comp*100:.1f}% of raw)")
            for c in cats:
                mark = "<<" if ck_recall[c] > mask_recall[c] + 1e-9 else (
                    ">>" if mask_recall[c] > ck_recall[c] + 1e-9 else "==")
                print(f"        {c:<14} masking {mask_recall[c]:.1%}  {mark}  ck {ck_recall[c]:.1%}")
            print(f"\n  {summary['head_to_head']['headline']}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"\n  results: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
