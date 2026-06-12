#!/usr/bin/env python3
"""
Brainer transcript miner.
Reads JSONL session files from ~/.claude/projects/-Users-za-Documents-Brainer/
and produces aggregate stats + transcript_report.json.

Schema verified on 3+ sample lines:
- type='assistant': message.content[] has {type, id, name, input, caller} for tool_use
  and {type, text} for text; message.usage has output_tokens; message.model
- type='user': message.content[] has {type:'tool_result', tool_use_id, is_error, content}
  or {type:'text', text}
- type='attachment': attachment.{type, hookName, hookEvent, stdout, content, exitCode, ...}
  attachment types: hook_success, hook_additional_context, task_reminder, skill_listing, etc.
- type='system': subtype, hookInfos[], hookErrors[], hookAdditionalContext[], preventedContinuation
- type='last-prompt', 'queue-operation', 'mode': misc control events
- NO compaction/summary events found in these 8 sessions.
"""

import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

TRANSCRIPTS_DIR = Path.home() / ".claude/projects/-Users-za-Documents-Brainer"
OUTPUT_PATH = Path("/Users/za/Documents/Brainer/scratch/transcript_report.json")
CHECKPOINTS_DIR = Path("/Users/za/Documents/Brainer/.brainer/checkpoints")
SESSIONS_DIR = Path("/Users/za/Documents/Brainer/.brainer/sessions")

# ─── helpers ────────────────────────────────────────────────────────────────

def content_text(content):
    """Flatten a tool_result content field to a string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(item.get("text", item.get("content", str(item))))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)


def iter_events(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        for lineno, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            yield lineno, obj


# ─── per-session analysis ────────────────────────────────────────────────────

def analyze_session(path):
    fname = path.name
    session_id = fname.replace(".jsonl", "")

    # 1. Tool call histogram + error tracking
    tool_calls = defaultdict(int)          # tool_name -> count
    tool_errors = defaultdict(int)         # tool_name -> error count
    pending_tool_calls = {}                # tool_use_id -> tool_name

    # 2. Error signatures
    error_signatures = defaultdict(int)    # first-100-chars -> count

    # 3. Prompt-triage decisions
    triage_decisions = []

    # 4. Same-file re-reads
    file_reads = defaultdict(int)          # file_path -> count

    # 5. Search chain detection (state machine)
    search_chain_tools = {"Grep", "Glob", "Read", "mcp__search", "WebSearch"}
    search_chain_count = 0
    current_chain = 0

    # 6. Bash result sizes
    bash_result_sizes = []                 # list of (size_bytes, snippet)

    # 7. Compaction events
    compaction_count = 0

    # 8. User interruptions
    interruption_count = 0

    # 9. Subagent usage
    subagent_calls = []                    # list of {tool, model, subagent_type}

    # 10. Output tokens
    output_tokens_total = 0

    # 11. Prompt-cache accounting (ccmeter-lite; token-based, no $$ — prices
    # drift and hardcoding unverified prices is a recorded anti-pattern).
    # A large cache_creation event after the session's first means a prefix
    # segment re-keyed (bust) — each one paid a write where a read was hoped.
    cache_read_total = 0
    cache_creation_total = 0
    input_tokens_total = 0
    cache_creation_events = []             # (lineno, creation_tokens)

    # For triage: capture the most recent user prompt text before each triage
    last_user_prompt = ""

    events = list(iter_events(path))

    # Build an ordered list of tool actions for chain detection
    tool_sequence = []  # list of tool names in order

    for lineno, obj in events:
        etype = obj.get("type", "")

        # ── ASSISTANT events ──────────────────────────────────────────────
        if etype == "assistant":
            msg = obj.get("message", {})

            # usage
            usage = msg.get("usage", {})
            output_tokens_total += usage.get("output_tokens", 0)
            cr = usage.get("cache_read_input_tokens", 0) or 0
            cc = usage.get("cache_creation_input_tokens", 0) or 0
            cache_read_total += cr
            cache_creation_total += cc
            input_tokens_total += usage.get("input_tokens", 0) or 0
            if cc > 1024:
                cache_creation_events.append((lineno, cc))

            model = msg.get("model", "")
            content = msg.get("content", [])
            if isinstance(content, list):
                for c in content:
                    if not isinstance(c, dict):
                        continue
                    ctype = c.get("type", "")
                    if ctype == "tool_use":
                        tname = c.get("name", "unknown")
                        tid = c.get("id", "")
                        tool_calls[tname] += 1
                        if tid:
                            pending_tool_calls[tid] = tname
                        tool_sequence.append(tname)

                        # Subagent detection: Task/Agent tool
                        if tname in ("Task", "Agent", "mcp_task", "SubAgent"):
                            inp = c.get("input", {})
                            subagent_calls.append({
                                "tool": tname,
                                "model": inp.get("model", model),
                                "subagent_type": inp.get("type", inp.get("subagent_type", "")),
                                "description": str(inp.get("description", inp.get("prompt", "")))[:100],
                            })

                        # Track Read calls for file re-reads
                        if tname == "Read":
                            inp = c.get("input", {})
                            fpath_val = inp.get("file_path", inp.get("path", ""))
                            if fpath_val:
                                file_reads[fpath_val] += 1

        # ── USER events ──────────────────────────────────────────────────
        elif etype == "user":
            msg = obj.get("message", {})
            content = msg.get("content", [])
            if isinstance(content, str):
                last_user_prompt = content[:500]
            elif isinstance(content, list):
                for c in content:
                    if not isinstance(c, dict):
                        continue
                    ctype = c.get("type", "")

                    if ctype == "text":
                        txt = c.get("text", "")
                        if txt and not txt.startswith("<system-reminder"):
                            last_user_prompt = txt[:500]

                    elif ctype == "tool_result":
                        tid = c.get("tool_use_id", "")
                        is_error = c.get("is_error", False)
                        raw_content = content_text(c.get("content", ""))
                        tname = pending_tool_calls.get(tid, "unknown")

                        if is_error:
                            tool_errors[tname] += 1
                            sig = raw_content[:100].strip()
                            if sig:
                                error_signatures[sig] += 1

                        # Check for user interruption / denial
                        lower_content = raw_content.lower()
                        denial_phrases = [
                            "doesn't want to proceed",
                            "denied",
                            "rejected",
                            "permission denied",
                            "cancelled",
                            "interrupted",
                        ]
                        for phrase in denial_phrases:
                            if phrase in lower_content:
                                interruption_count += 1
                                break

                        # Bash result sizes
                        if tname == "Bash":
                            size = len(raw_content.encode("utf-8"))
                            bash_result_sizes.append((size, raw_content[:80]))

        # ── ATTACHMENT events (hook output) ──────────────────────────────
        elif etype == "attachment":
            attach = obj.get("attachment", {})
            atype = attach.get("type", "")
            hookname = attach.get("hookName", "")
            hookevent = attach.get("hookEvent", "")

            # Triage decisions in hook_success for UserPromptSubmit
            if atype == "hook_success" and hookevent == "UserPromptSubmit":
                stdout = attach.get("stdout", "") or ""
                # Extract JSON triage block
                # Pattern: {"tier": ..., "agent": ..., "model": ..., "confidence": ..., ...}
                matches = re.findall(r'\{[^{}]*"tier"[^{}]*"confidence"[^{}]*\}', stdout)
                if not matches:
                    # Also try multiline-ish: find the JSON after "Task classified:"
                    m = re.search(r'\{.*?"tier".*?\}', stdout, re.DOTALL)
                    if m:
                        matches = [m.group(0)]

                for m in matches:
                    try:
                        decision = json.loads(m)
                        decision["_prompt_prefix"] = last_user_prompt[:150]
                        decision["_session"] = session_id[:8]
                        triage_decisions.append(decision)
                    except json.JSONDecodeError:
                        pass

        # ── SYSTEM events ────────────────────────────────────────────────
        elif etype == "system":
            # No compaction/summary events found; keep counter at 0
            pass

    # ── Search chain detection ────────────────────────────────────────────
    # Run over tool_sequence; count runs of >= 4 consecutive search-type calls
    run = 0
    for tname in tool_sequence:
        if tname in search_chain_tools:
            run += 1
            if run == 4:
                search_chain_count += 1
        else:
            run = 0
    # Also catch chains still active at end if >= 4
    # (already counted when run hit exactly 4)

    # ── Bash result sizes summary ─────────────────────────────────────────
    over_5kb = [(sz, snip) for sz, snip in bash_result_sizes if sz > 5120]
    top10_bash = sorted(bash_result_sizes, key=lambda x: -x[0])[:10]

    # ── File re-reads ─────────────────────────────────────────────────────
    multi_reads = {fp: cnt for fp, cnt in file_reads.items() if cnt >= 3}

    return {
        "session_id": session_id,
        "tool_calls": dict(tool_calls),
        "tool_errors": dict(tool_errors),
        "error_signatures": dict(error_signatures),
        "triage_decisions": triage_decisions,
        "multi_reads": multi_reads,
        "search_chain_count": search_chain_count,
        "bash_over_5kb_count": len(over_5kb),
        "top10_bash_bytes": [(sz, snip) for sz, snip in top10_bash],
        "compaction_count": compaction_count,
        "interruption_count": interruption_count,
        "subagent_calls": subagent_calls,
        "output_tokens_total": output_tokens_total,
        "cache": {
            "read_tokens": cache_read_total,
            "creation_tokens": cache_creation_total,
            "uncached_input_tokens": input_tokens_total,
            "hit_ratio": round(
                cache_read_total / (cache_read_total + cache_creation_total + input_tokens_total), 4
            ) if (cache_read_total + cache_creation_total + input_tokens_total) else None,
            "bust_events_gt1k": len(cache_creation_events),
            "top3_creations": sorted(cache_creation_events, key=lambda x: -x[1])[:3],
        },
    }


# ─── aggregate ───────────────────────────────────────────────────────────────

def aggregate(sessions):
    agg_tools = defaultdict(int)
    agg_errors = defaultdict(int)
    agg_error_sigs = defaultdict(int)
    agg_triage = []
    agg_multi_reads = defaultdict(lambda: defaultdict(int))  # session -> path -> count
    agg_search_chains = 0
    agg_bash_over_5kb = 0
    agg_bash_top_sizes = []
    agg_compaction = 0
    agg_interruptions = 0
    agg_subagents = []
    agg_output_tokens = 0

    session_summaries = []

    for s in sessions:
        for k, v in s["tool_calls"].items():
            agg_tools[k] += v
        for k, v in s["tool_errors"].items():
            agg_errors[k] += v
        for k, v in s["error_signatures"].items():
            agg_error_sigs[k] += v
        agg_triage.extend(s["triage_decisions"])
        for fp, cnt in s["multi_reads"].items():
            agg_multi_reads[s["session_id"][:8]][fp] = cnt
        agg_search_chains += s["search_chain_count"]
        agg_bash_over_5kb += s["bash_over_5kb_count"]
        agg_bash_top_sizes.extend(s["top10_bash_bytes"])
        agg_compaction += s["compaction_count"]
        agg_interruptions += s["interruption_count"]
        agg_subagents.extend(s["subagent_calls"])
        agg_output_tokens += s["output_tokens_total"]

        session_summaries.append({
            "session_id": s["session_id"][:8],
            "total_tool_calls": sum(s["tool_calls"].values()),
            "total_errors": sum(s["tool_errors"].values()),
            "triage_count": len(s["triage_decisions"]),
            "search_chain_occurrences": s["search_chain_count"],
            "bash_over_5kb": s["bash_over_5kb_count"],
            "compaction_events": s["compaction_count"],
            "interruptions": s["interruption_count"],
            "subagent_calls": len(s["subagent_calls"]),
            "output_tokens": s["output_tokens_total"],
            "multi_read_files": list(s["multi_reads"].keys()),
        })

    # Tool error rates
    tool_error_rates = {}
    for tname, ecnt in agg_errors.items():
        total = agg_tools.get(tname, 0)
        tool_error_rates[tname] = {
            "errors": ecnt,
            "total": total,
            "error_rate": round(ecnt / total, 3) if total > 0 else 1.0,
        }

    # Triage analysis
    triage_tier_dist = defaultdict(int)
    triage_source_dist = defaultdict(int)
    triage_low_confidence = []
    for d in agg_triage:
        triage_tier_dist[d.get("tier", "unknown")] += 1
        triage_source_dist[d.get("source", "unknown")] += 1
        conf = d.get("confidence", 1.0)
        if conf < 0.7:
            triage_low_confidence.append({
                "tier": d.get("tier"),
                "agent": d.get("agent"),
                "model": d.get("model"),
                "confidence": conf,
                "reason": d.get("reason", ""),
                "source": d.get("source", ""),
                "session": d.get("_session", ""),
                "prompt_prefix": d.get("_prompt_prefix", ""),
            })

    # Bash top 10 by size
    bash_top10_global = sorted(agg_bash_top_sizes, key=lambda x: -x[0])[:10]

    # Multi-reads flattened
    all_multi_reads = []
    for sess, reads in agg_multi_reads.items():
        for fp, cnt in reads.items():
            all_multi_reads.append({"session": sess, "file": fp, "reads": cnt})
    all_multi_reads.sort(key=lambda x: -x["reads"])

    # Check context-keeper sidecars
    ckpt_exists = CHECKPOINTS_DIR.exists()
    sess_exists = SESSIONS_DIR.exists()
    ckpt_files = list(CHECKPOINTS_DIR.glob("*")) if ckpt_exists else []
    sess_files = list(SESSIONS_DIR.glob("*")) if sess_exists else []

    # Subagent model distribution
    subagent_models = defaultdict(int)
    for sa in agg_subagents:
        subagent_models[sa.get("model", "unknown")] += 1

    return {
        "meta": {
            "sessions_analyzed": len(sessions),
            "context_keeper_checkpoints_dir_exists": ckpt_exists,
            "context_keeper_sessions_dir_exists": sess_exists,
            "context_keeper_checkpoint_files": len(ckpt_files),
            "context_keeper_session_files": len(sess_files),
        },
        "tool_histogram": dict(sorted(agg_tools.items(), key=lambda x: -x[1])),
        "tool_error_rates": dict(sorted(tool_error_rates.items(), key=lambda x: -x[1]["errors"])),
        "error_signatures_repeated_3plus": {
            sig: cnt for sig, cnt in agg_error_sigs.items() if cnt >= 3
        },
        "all_error_signatures": dict(sorted(agg_error_sigs.items(), key=lambda x: -x[1])),
        "triage": {
            "total_decisions": len(agg_triage),
            "tier_distribution": dict(triage_tier_dist),
            "source_distribution": dict(triage_source_dist),
            "low_confidence_decisions": triage_low_confidence,
        },
        "multi_reads": all_multi_reads,
        "search_chain_occurrences_total": agg_search_chains,
        "bash_results_over_5kb_total": agg_bash_over_5kb,
        "bash_top10_sizes": [{"bytes": sz, "snippet": snip} for sz, snip in bash_top10_global],
        "compaction_events_total": agg_compaction,
        "interruptions_total": agg_interruptions,
        "subagent_calls_total": len(agg_subagents),
        "subagent_model_distribution": dict(subagent_models),
        "subagent_calls_detail": agg_subagents[:20],
        "output_tokens_total": agg_output_tokens,
        "output_tokens_per_session": {s["session_id"]: s["output_tokens"] for s in session_summaries},
        "session_summaries": session_summaries,
    }


# ─── interpretation ──────────────────────────────────────────────────────────

def interpret(agg):
    issues = []

    # 1. Search chains (index-first violations)
    chains = agg["search_chain_occurrences_total"]
    multi = agg["multi_reads"]
    multi_count = len(multi)
    if chains > 0 or multi_count > 0:
        example = None
        if multi:
            example = f"File '{multi[0]['file']}' read {multi[0]['reads']}x in session {multi[0]['session']}"
        issues.append({
            "rank": 1,
            "issue": "Search-chain / repeated-read sprawl",
            "description": (
                f"{chains} search-chain occurrences (≥4 consecutive Grep/Glob/Read calls); "
                f"{multi_count} file(s) read ≥3 times in one session."
            ),
            "evidence_count": chains + multi_count,
            "example": example or "no multi-reads",
            "classification": "[suite-failing: index-first + semantic-diff should fire]",
        })

    # 2. Triage misrouting (low-confidence)
    low_conf = agg["triage"]["low_confidence_decisions"]
    all_triage = agg["triage"]["total_decisions"]
    if low_conf:
        ex = low_conf[0]
        issues.append({
            "rank": 2,
            "issue": "Prompt-triage low-confidence decisions",
            "description": (
                f"{len(low_conf)}/{all_triage} triage decisions below 0.7 confidence. "
                f"All low-conf decisions use source '{ex.get('source')}', "
                f"routing to tier='{ex.get('tier')}' / model='{ex.get('model')}'."
            ),
            "evidence_count": len(low_conf),
            "example": (
                f"confidence={ex['confidence']}, reason='{ex['reason']}', "
                f"prompt='{ex['prompt_prefix'][:100]}'"
            ),
            "classification": "[suite-failing: prompt-triage confidence calibration]",
        })

    # 3. Triage source bias (all regex-low-conf?)
    source_dist = agg["triage"]["source_distribution"]
    dominant_source = max(source_dist, key=lambda k: source_dist[k]) if source_dist else None
    if dominant_source and source_dist.get(dominant_source, 0) == all_triage and all_triage > 2:
        issues.append({
            "rank": 3,
            "issue": f"Triage always fires from single source '{dominant_source}'",
            "description": (
                f"100% of {all_triage} triage decisions come from source='{dominant_source}'. "
                "No semantic/LLM-backed triage path observed — all regex-pattern routing."
            ),
            "evidence_count": all_triage,
            "example": f"All {all_triage} decisions: source='{dominant_source}'",
            "classification": "[suite-missing: no LLM-backed triage path wired]",
        })

    # 4. Triage tier concentration
    tier_dist = agg["triage"]["tier_distribution"]
    if tier_dist:
        dominant_tier = max(tier_dist, key=lambda k: tier_dist[k])
        dominant_count = tier_dist[dominant_tier]
        if all_triage > 0 and dominant_count / all_triage > 0.8:
            issues.append({
                "rank": 4,
                "issue": f"Triage classifies {round(dominant_count/all_triage*100)}% of tasks as tier='{dominant_tier}'",
                "description": (
                    f"{dominant_count}/{all_triage} tasks routed to '{dominant_tier}'. "
                    "If the tier is 'simple' this suggests the triage regex is too aggressive "
                    "and may be sending complex tasks to underpowered agents."
                ),
                "evidence_count": dominant_count,
                "example": f"tier_distribution={dict(tier_dist)}",
                "classification": "[suite-failing: prompt-triage tier calibration]",
            })

    # 5. Large Bash outputs (output-filter)
    over5kb = agg["bash_results_over_5kb_total"]
    top10 = agg["bash_top10_sizes"]
    if over5kb > 0:
        ex = top10[0] if top10 else {}
        issues.append({
            "rank": 5,
            "issue": "Unfiltered large Bash outputs",
            "description": (
                f"{over5kb} Bash tool results exceed 5KB total across all sessions. "
                f"Top result: {ex.get('bytes', 0):,} bytes."
            ),
            "evidence_count": over5kb,
            "example": f"Largest: {ex.get('bytes', 0):,} bytes — '{ex.get('snippet', '')[:60]}'",
            "classification": "[suite-failing: output-filter should intercept]",
        })

    # 6. Tool errors
    error_rates = agg["tool_error_rates"]
    high_error_tools = [(k, v) for k, v in error_rates.items() if v["errors"] >= 2]
    high_error_tools.sort(key=lambda x: -x[1]["errors"])
    if high_error_tools:
        top_tool, top_stats = high_error_tools[0]
        # Get a sample error signature for this tool
        sigs = agg["all_error_signatures"]
        sample_sig = next(iter(sigs), "n/a") if sigs else "n/a"
        issues.append({
            "rank": 6,
            "issue": "Repeated tool errors",
            "description": (
                f"{len(high_error_tools)} tool(s) with ≥2 errors. "
                f"Top: '{top_tool}' with {top_stats['errors']} errors "
                f"({round(top_stats['error_rate']*100)}% error rate)."
            ),
            "evidence_count": sum(v["errors"] for _, v in high_error_tools),
            "example": f"Sample error: '{sample_sig[:100]}'",
            "classification": "[suite-missing: no retry/escalation hook for tool errors]",
        })

    # 7. Zero compaction sidecars
    ckpt_count = agg["meta"]["context_keeper_checkpoint_files"]
    if ckpt_count == 0:
        issues.append({
            "rank": 7,
            "issue": "No context-keeper sidecars found",
            "description": (
                "0 compaction events in all 8 sessions AND "
                f"context-keeper checkpoint directory has {ckpt_count} files. "
                "Either sessions never compacted, or context-keeper PreCompact hook is not wired."
            ),
            "evidence_count": 0,
            "example": (
                f"CHECKPOINTS_DIR exists={agg['meta']['context_keeper_checkpoints_dir_exists']}, "
                f"SESSIONS_DIR exists={agg['meta']['context_keeper_sessions_dir_exists']}"
            ),
            "classification": "[suite-failing: context-keeper PreCompact hook may not be wired]",
        })

    # 8. Subagent usage
    total_subagents = agg["subagent_calls_total"]
    model_dist = agg["subagent_model_distribution"]
    if total_subagents > 0:
        issues.append({
            "rank": 8,
            "issue": "Subagent/Task tool usage",
            "description": (
                f"{total_subagents} Task/Agent tool calls across sessions. "
                f"Model distribution: {dict(model_dist)}."
            ),
            "evidence_count": total_subagents,
            "example": str(agg["subagent_calls_detail"][:2]),
            "classification": "[working-as-designed: delegation is expected]",
        })

    # Sort by evidence_count descending (preserve manual ranks for ties)
    issues.sort(key=lambda x: (-x["evidence_count"], x["rank"]))
    for i, issue in enumerate(issues, 1):
        issue["rank"] = i

    return issues


# ─── main ────────────────────────────────────────────────────────────────────

def main():
    jsonl_files = sorted(TRANSCRIPTS_DIR.glob("*.jsonl"))
    if not jsonl_files:
        print(f"ERROR: No JSONL files found in {TRANSCRIPTS_DIR}", file=sys.stderr)
        sys.exit(1)

    print(f"Analyzing {len(jsonl_files)} session(s)...", file=sys.stderr)

    sessions = []
    for fpath in jsonl_files:
        print(f"  {fpath.name}...", file=sys.stderr)
        s = analyze_session(fpath)
        sessions.append(s)

    print("Aggregating...", file=sys.stderr)
    agg = aggregate(sessions)

    print("Interpreting...", file=sys.stderr)
    issues = interpret(agg)

    cache_rows = [
        {"session": s["session_id"][:8], **s["cache"]}
        for s in sessions if s.get("cache")
    ]
    tot_read = sum(r["read_tokens"] for r in cache_rows)
    tot_create = sum(r["creation_tokens"] for r in cache_rows)
    tot_uncached = sum(r["uncached_input_tokens"] for r in cache_rows)
    denom = tot_read + tot_create + tot_uncached
    report = {
        "aggregate": agg,
        "cache": {
            "per_session": cache_rows,
            "total_read": tot_read,
            "total_creation": tot_create,
            "total_uncached_input": tot_uncached,
            "overall_hit_ratio": round(tot_read / denom, 4) if denom else None,
        },
        "top_issues": issues,
    }
    print("\nCACHE (read / creation / uncached / hit-ratio / busts>1k):", file=sys.stderr)
    for r in cache_rows:
        print(f"  {r['session']}: {r['read_tokens']:,} / {r['creation_tokens']:,} / "
              f"{r['uncached_input_tokens']:,} / {r['hit_ratio']} / {r['bust_events_gt1k']}",
              file=sys.stderr)
    if denom:
        print(f"  OVERALL hit ratio: {report['cache']['overall_hit_ratio']}", file=sys.stderr)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"\nReport written to {OUTPUT_PATH}", file=sys.stderr)
    return report


if __name__ == "__main__":
    report = main()
    agg = report["aggregate"]
    issues = report["top_issues"]

    print("\n" + "="*70)
    print("AGGREGATE STATS")
    print("="*70)
    print(f"Sessions: {agg['meta']['sessions_analyzed']}")
    print(f"Total tool calls: {sum(agg['tool_histogram'].values())}")
    print(f"Tool histogram (top 15):")
    for k, v in list(agg["tool_histogram"].items())[:15]:
        err = agg["tool_error_rates"].get(k, {})
        err_str = f" (errors={err.get('errors',0)}, rate={err.get('error_rate',0):.1%})" if err else ""
        print(f"  {k}: {v}{err_str}")
    print(f"\nSearch chain occurrences (≥4 consecutive): {agg['search_chain_occurrences_total']}")
    print(f"Files read ≥3x in one session: {len(agg['multi_reads'])}")
    for mr in agg["multi_reads"][:5]:
        print(f"  {mr['file']} — {mr['reads']}x in session {mr['session']}")
    print(f"\nBash results >5KB: {agg['bash_results_over_5kb_total']}")
    print(f"Top bash sizes (bytes): {[x['bytes'] for x in agg['bash_top10_sizes'][:5]]}")
    print(f"\nCompaction events: {agg['compaction_events_total']}")
    print(f"Context-keeper checkpoints: {agg['meta']['context_keeper_checkpoint_files']}")
    print(f"\nInterruptions/denials: {agg['interruptions_total']}")
    print(f"Subagent calls: {agg['subagent_calls_total']}")
    print(f"  Model distribution: {agg['subagent_model_distribution']}")
    print(f"\nOutput tokens total: {agg['output_tokens_total']:,}")
    print(f"Output tokens per session:")
    for sess, toks in sorted(agg["output_tokens_per_session"].items(), key=lambda x: -x[1]):
        print(f"  {sess[:8]}: {toks:,}")

    print(f"\n\nTRIAGE DECISIONS")
    print("-"*60)
    print(f"Total: {agg['triage']['total_decisions']}")
    print(f"Tier distribution: {agg['triage']['tier_distribution']}")
    print(f"Source distribution: {agg['triage']['source_distribution']}")
    lc = agg["triage"]["low_confidence_decisions"]
    print(f"Low confidence (<0.7): {len(lc)}")
    for d in lc:
        print(f"  [{d['session']}] conf={d['confidence']} tier={d['tier']} model={d['model']}")
        print(f"    reason: {d['reason']}")
        print(f"    prompt: {d['prompt_prefix'][:120]}")

    print(f"\n\nERROR SIGNATURES (all)")
    print("-"*60)
    for sig, cnt in sorted(agg["all_error_signatures"].items(), key=lambda x: -x[1]):
        print(f"  [{cnt}x] {sig[:100]}")
    if not agg["all_error_signatures"]:
        print("  (none)")

    print(f"\n\nTOP ISSUES")
    print("="*70)
    for issue in issues:
        print(f"\n#{issue['rank']} [{issue['evidence_count']} occurrences] {issue['issue']}")
        print(f"  {issue['description']}")
        print(f"  Example: {issue['example']}")
        print(f"  {issue['classification']}")
