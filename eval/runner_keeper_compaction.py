#!/usr/bin/env python3
"""End-to-end compaction test for context-keeper.

Question: when an LLM summarizes a long Claude Code transcript the way
PreCompact compaction would, does the hook's pointer survive into the summary,
and can a downstream agent recover facts that the summary would otherwise drop?

Method:
  1. Take a real transcript JSONL.
  2. Run the context-keeper hook on it -> checkpoint + pointer text.
  3. Build a "transcript text" representation capped at N tokens.
  4. Summarize via local Ollama under two arms:
       A (control): just the transcript
       B (with hook): pointer prepended as "additional compaction context
                       to preserve verbatim" + transcript
  5. Measure:
       a) Does the checkpoint path appear verbatim in each summary?
       b) For each held-out fact (Q1..QN), does the LLM, given ONLY the summary
          (no transcript), recall the answer? B has the option of reading the
          checkpoint file if its path was preserved.
  6. Print a comparison report.

Usage:
  python3 eval/runner_keeper_compaction.py <transcript.jsonl> \
      [--model gemma4:26b] [--summary-tokens 600] [--input-tokens 20000]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

OLLAMA = "http://127.0.0.1:11434/api/generate"


def iter_events(path):
    with open(path) as f:
        for line in f:
            try:
                yield json.loads(line)
            except Exception:
                continue


def flatten_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if not isinstance(b, dict):
                parts.append(str(b))
                continue
            if "text" in b:
                parts.append(b["text"])
            elif b.get("type") == "tool_use":
                inp = json.dumps(b.get("input", {}))[:400]
                parts.append(f"[tool:{b.get('name','?')} {inp}]")
            elif b.get("type") == "tool_result":
                c = b.get("content", "")
                if isinstance(c, list):
                    parts.extend(x.get("text", "")[:600] for x in c if isinstance(x, dict))
                else:
                    parts.append(str(c)[:600])
        return "\n".join(parts)
    return str(content)


def transcript_text(path: str, max_chars: int) -> str:
    parts = []
    for ev in iter_events(path):
        t = ev.get("type", "")
        if t not in ("user", "assistant"):
            continue
        msg = ev.get("message") or {}
        content = msg.get("content") if isinstance(msg, dict) else ev.get("content")
        body = flatten_content(content)
        if not body:
            continue
        parts.append(f"[{t}] {body[:1500]}")
    full = "\n\n".join(parts)
    if len(full) <= max_chars:
        return full
    head = full[: max_chars // 2]
    tail = full[-max_chars // 2 :]
    return head + "\n\n[...transcript truncated for prompt budget...]\n\n" + tail


def ollama_call(model: str, prompt: str, max_tokens: int) -> str:
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "options": {"num_predict": max_tokens, "temperature": 0.0},
    }).encode()
    req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        out = json.loads(r.read())
    return out.get("response", "")


def run_hook(transcript: str) -> tuple[str, Path | None]:
    """Invoke the hook the way Claude Code would; return (pointer_stdout, checkpoint_path)."""
    sid = Path(transcript).stem
    payload = json.dumps({
        "session_id": sid,
        "transcript_path": transcript,
        "hook_event_name": "PreCompact",
        "trigger": "auto",
    })
    repo = Path(__file__).resolve().parents[1]
    hook = repo / "skills" / "context-keeper" / "tools" / "hook.sh"
    proc = subprocess.run(
        ["bash", str(hook)], input=payload, capture_output=True, text=True, timeout=60,
    )
    stdout = proc.stdout.strip()
    # Parse the checkpoint path from the pointer text
    m = re.search(r"saved → (\S+\.md)", stdout)
    checkpoint = Path(m.group(1)) if m else None
    return stdout, checkpoint


def summary_prompt(transcript_text: str, hook_pointer: str | None) -> str:
    intro = (
        "You are the compaction summarizer for a long Claude Code session. "
        "Produce a faithful summary in under 500 words that preserves the user's goals, "
        "key files touched, decisions made, commands run, and errors encountered. "
        "Use compact bullets. Do not invent details.\n\n"
    )
    if hook_pointer:
        intro += (
            "ADDITIONAL CONTEXT FROM A PreCompact HOOK — you MUST include this block verbatim "
            "in your output so the next agent can locate the checkpoint:\n"
            f"<<<HOOK_OUTPUT>>>\n{hook_pointer}\n<<<END_HOOK_OUTPUT>>>\n\n"
        )
    return intro + "TRANSCRIPT:\n" + transcript_text + "\n\nSUMMARY:\n"


def qa_prompt(summary: str, question: str, checkpoint_path: Path | None) -> str:
    base = (
        "You are continuing a Claude Code session after compaction. The summary below "
        "is all you remember of the prior conversation. Answer the question concisely. "
        "If the answer is not in the summary, say UNKNOWN.\n\n"
    )
    if checkpoint_path is not None:
        base += (
            f"If the summary references a checkpoint file at {checkpoint_path}, you may treat "
            "the following as its contents (it is grep-able structured memory of the prior session):\n"
            "<<<CHECKPOINT>>>\n"
            + checkpoint_path.read_text()[:8000]
            + "\n<<<END_CHECKPOINT>>>\n\n"
        )
    return base + f"SUMMARY:\n{summary}\n\nQUESTION: {question}\nANSWER:"


def judge(question: str, expected_substrings: list[str], answer: str) -> bool:
    a = answer.lower()
    return all(s.lower() in a for s in expected_substrings)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("--model", default="gemma4:26b")
    ap.add_argument("--summary-tokens", type=int, default=700)
    ap.add_argument("--input-chars", type=int, default=24000)
    ap.add_argument("--out", default="eval/results/keeper_compaction.json")
    args = ap.parse_args()

    # 1. Run hook
    print("== running hook against transcript ==", file=sys.stderr)
    pointer, checkpoint = run_hook(args.transcript)
    print(pointer, file=sys.stderr)
    if not checkpoint or not checkpoint.exists():
        print("ABORT: hook did not produce a checkpoint", file=sys.stderr)
        sys.exit(2)

    # 2. Build transcript text
    text = transcript_text(args.transcript, args.input_chars)
    print(f"== transcript text: {len(text)} chars ==", file=sys.stderr)

    # 3. Two summaries
    print("== ARM A: summary without hook ==", file=sys.stderr)
    t0 = time.time()
    sum_a = ollama_call(args.model, summary_prompt(text, None), args.summary_tokens)
    t_a = time.time() - t0
    print(sum_a[:400], file=sys.stderr)

    print("\n== ARM B: summary WITH hook pointer ==", file=sys.stderr)
    t0 = time.time()
    sum_b = ollama_call(args.model, summary_prompt(text, pointer), args.summary_tokens)
    t_b = time.time() - t0
    print(sum_b[:400], file=sys.stderr)

    # 4. Pointer-survival check
    path_str = str(checkpoint)
    survived_a = path_str in sum_a
    survived_b = path_str in sum_b

    # 5. Fact-recovery questions — these answers are known to be in the 893-line transcript.
    # Each question has a list of substrings that an acceptable answer must contain.
    QUESTIONS = [
        ("What is the secrets file path that holds MIMO_API_KEY?",
            [".brainer/secrets.env"]),
        ("Which SKILL.md frontmatter value caused the host to fail to resolve a model?",
            ["model: any"]),
        ("Which Kaggle API endpoint returned 'Unauthorized' during exploration?",
            ["kaggle.com/api/v1/kernels/list"]),
        ("What env var name held the Kaggle API token?",
            ["KAGGLE_API_TOKEN"]),
        ("Which Python module was missing on Kaggle (ModuleNotFoundError)?",
            ["datasets"]),
    ]

    results = []
    for q, expected in QUESTIONS:
        ans_a = ollama_call(args.model, qa_prompt(sum_a, q, None), 200).strip()
        # ARM B can also read the checkpoint file if its path was in the summary
        cp_for_b = checkpoint if survived_b else None
        ans_b = ollama_call(args.model, qa_prompt(sum_b, q, cp_for_b), 200).strip()
        results.append({
            "question": q,
            "expected": expected,
            "arm_a": {"answer": ans_a[:300], "correct": judge(q, expected, ans_a)},
            "arm_b": {"answer": ans_b[:300], "correct": judge(q, expected, ans_b)},
        })

    correct_a = sum(1 for r in results if r["arm_a"]["correct"])
    correct_b = sum(1 for r in results if r["arm_b"]["correct"])

    report = {
        "transcript": args.transcript,
        "model": args.model,
        "checkpoint": str(checkpoint),
        "pointer_chars": len(pointer),
        "summary_a_chars": len(sum_a),
        "summary_b_chars": len(sum_b),
        "summary_a_seconds": round(t_a, 1),
        "summary_b_seconds": round(t_b, 1),
        "pointer_survived_arm_a": survived_a,
        "pointer_survived_arm_b": survived_b,
        "n_questions": len(QUESTIONS),
        "correct_arm_a": correct_a,
        "correct_arm_b": correct_b,
        "questions": results,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2))

    print("\n=== RESULTS ===")
    print(f"  pointer survived: A={survived_a}  B={survived_b}")
    print(f"  fact recall:      A={correct_a}/{len(QUESTIONS)}  B={correct_b}/{len(QUESTIONS)}")
    print(f"  summary times:    A={t_a:.1f}s  B={t_b:.1f}s")
    print(f"  full report:      {args.out}")


if __name__ == "__main__":
    main()
