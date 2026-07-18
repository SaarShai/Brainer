"""Deterministic unblinded mechanism-track extractor (metrics 3, 5, and 6)."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from longhorizon_extract_blinded import (ExtractionError, CLAIM_RE, FAIL_RE, _blocks,
    _block_text, _input, _mutation, _role, _tool_info, parse_transcript)


def _text(item): return "\n".join(_block_text(x) for x in _blocks(item["event"]) if _block_text(x))
def _read_jsonl(value):
    if value is None: return []
    if isinstance(value, Path): value = value.read_text(encoding="utf-8")
    if isinstance(value, str): return [json.loads(x) for x in value.splitlines() if x.strip()]
    return list(value)

def _boundaries(events):
    seen, found = set(), []
    for n, item in enumerate(events):
        e = item["event"]; typ = e.get("type"); subtype = e.get("subtype")
        command = e.get("command") or e.get("host_command")
        hit = typ in {"compact_boundary", "compaction", "conversation_compacted"} or subtype in {"compact_boundary", "compaction", "conversation_compacted"} or command == "/compact" or typ == "context_pressure_equivalent"
        if hit:
            ident = e.get("host_event_id", item["raw_line"])
            if ident not in seen: seen.add(ident); found.append(n)
    if len(found) != 2: raise ExtractionError("VENUE_COMPACTION_COUNT_INVALID")
    return found

def _assistant_turns(events, lo, hi):
    return [(i, x) for i, x in enumerate(events[lo:hi], lo) if _role(x["event"]) == "assistant"]

def _post_compaction(events, boundaries, terminal_index, contract):
    flagged = []
    states = contract.get("decision_states", [])
    for boundary in boundaries:
        hi = next((b for b in boundaries if b > boundary), terminal_index)
        turns = _assistant_turns(events, boundary + 1, hi)
        # first complete assistant turn after first following organic prompt
        prompted = next((i for i in range(boundary + 1, hi) if _role(events[i]["event"]) == "user" and _text(events[i])), None)
        checkpoint = next((x for x in turns if prompted is not None and x[0] > prompted), None)
        for i, item in turns:
            text = _text(item); reasons = []
            for state in states:
                for abandoned in state.get("abandoned_literals", []):
                    for m in re.finditer(re.escape(abandoned), text, re.I):
                        near = text[max(0, m.start()-40):m.end()+40]; before = text[max(0,m.start()-24):m.start()]
                        if re.search(r"\b(is|=|use|using|set to|current|currently)\b", near, re.I) and not re.search(r"not|no longer|abandon|replace|instead of|supersed|stale|old", before, re.I): reasons.append("contradiction:" + state.get("key", abandoned)); break
                # mutating tool inputs are part of the assistant turn event.
                for b in _blocks(item["event"]):
                    if isinstance(b, dict) and b.get("type") == "tool_use" and _mutation(b):
                        inp = _input(b)
                        if any(re.search(rx, inp) for rx in state.get("abandoned_value_setting_regexes", [])): reasons.append("mutation_contradiction:" + state.get("key", ""))
            if checkpoint and i == checkpoint[0]:
                window = text + "\n" + "\n".join(_text(events[j]) for j in range(i+1, hi) if _role(events[j]["event"]) != "assistant")
                missing = [s.get("key", "") for s in states if s.get("existed_before_boundary", True) and not any(a in window for a in s.get("accepted_literals", []))]
                if missing: reasons.append("forgotten:" + ",".join(missing))
            if reasons: flagged.append({"turn": item["id"], "reasons": sorted(set(reasons))})
    dedup = {x["turn"]: x for x in flagged}
    return {"count": len(dedup), "candidates": list(dedup.values())}

def _usage(events, host_usage):
    records, seen = [], set()
    for i, item in enumerate(events):
        e = item["event"]
        message = e.get("message") if isinstance(e.get("message"), dict) else {}
        usage = e.get("usage") if isinstance(e.get("usage"), dict) else message.get("usage")
        if _role(e) == "assistant" and isinstance(usage, dict):
            records.append((i, e.get("id") or message.get("id"), usage))
    for i, row in enumerate(host_usage): records.append((len(events)+i, row.get("assistant_message_id"), row.get("usage", row)))
    subtotals = {"input_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 0, "prompt_tokens": 0, "completion_tokens": 0}
    for index, mid, usage in records:
        rid = usage.get("request_id") or usage.get("id") or (index, mid)
        if rid in seen: continue
        seen.add(rid)
        anth = any(k in usage for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")); openai = any(k in usage for k in ("prompt_tokens", "completion_tokens", "total_tokens"))
        if anth and openai: raise ExtractionError("USAGE_PROVIDER_AMBIGUOUS")
        if not anth and not openai: raise ExtractionError("USAGE_MISSING")
        if openai and "total_tokens" in usage and usage.get("total_tokens") != usage.get("prompt_tokens",0)+usage.get("completion_tokens",0): raise ExtractionError("USAGE_TOTAL_MISMATCH")
        for key in subtotals:
            value = usage.get(key, 0)
            if not isinstance(value, int) or value < 0: raise ExtractionError("USAGE_INVALID")
            subtotals[key] += value
    return {"records": len(seen), "subtotals": subtotals, "total": sum(subtotals.values())}

def _successful_results(events, before):
    uses, results = _tool_info(events, before); out = []
    for u in uses:
        r = results.get(u[3].get("id")); txt = _block_text(r[3]) if r else ""
        if r and not r[3].get("is_error") and not FAIL_RE.search(txt): out.append((u, r))
    return out

def _claim_needed(events, turn):
    prior = "\n".join(_text(x) for x in events[:turn] if _role(x["event"]) == "assistant")
    return bool(CLAIM_RE.search(prior))

def _interruptions(telemetry, session_hash, arm, events, terminal):
    rows = [r for r in telemetry if r.get("session_hash") == session_hash and r.get("emitted") is True and r.get("injected_utf8_bytes", 0) > 0]
    if arm == "OFF" and rows: raise ExtractionError("OFF_MUTATION_VIOLATION")
    groups = {}
    for r in rows: groups.setdefault((r.get("session_hash"), r.get("turn")), []).append(r)
    output, false = [], 0
    for key, rs in sorted(groups.items(), key=lambda x: str(x[0])):
        verdicts = []
        turn = int(key[1]) if isinstance(key[1], int) else terminal
        needed = _claim_needed(events, min(turn, len(events)))
        for r in rs:
            probe = r.get("probe_id") or r.get("mechanism", "")
            warranted = needed if probe == "claim-without-evidence" else False
            verdicts.append({"probe_id": probe, "warranted": warranted, "code": None if probe in {"claim-without-evidence", "pending-intent close-boundary", "unread notification-output"} else "UNKNOWN_INTERRUPTION_COMPONENT"})
        group_false = not any(v["warranted"] for v in verdicts)
        false += group_false; output.append({"session_hash": key[0], "turn": key[1], "components": verdicts, "false": group_false})
    return {"count": len(groups), "false_interruption_count": false, "interruptions": output}

def _suppressions(telemetry, session_hash, events):
    rows = [r for r in telemetry if r.get("session_hash") == session_hash and r.get("mechanism") == "suppressed_notification"]
    counts = {k: 0 for k in ("suppression_needed_no_fire", "fire_deferred", "deferred_then_verified", "deferred_then_emitted", "suppression_ate_warranted_fire")}; details=[]
    for r in rows:
        turn = r.get("turn", 0); needed = _claim_needed(events, min(turn if isinstance(turn,int) else 0, len(events)))
        label = "fire_deferred" if needed else "suppression_needed_no_fire"
        counts[label] += 1; details.append({"turn": turn, "probe_id": r.get("probe_id"), "classification": label})
    return {"total_suppressions": len(rows), "counts": counts, "events": details, "metric_6": counts["suppression_ate_warranted_fire"]}

def extract(raw_transcript, scenario_contract, arm, telemetry=(), host_usage=(), session_hash=None):
    if arm not in {"FRONTIER", "OFF"}: raise ExtractionError("ARM_INVALID")
    events = parse_transcript(raw_transcript, blind=False); boundaries = _boundaries(events)
    snapshot = next((i for i,x in enumerate(events) if x["event"].get("type") == "scenario_end_snapshot"), len(events))
    tel = _read_jsonl(telemetry); host = _read_jsonl(host_usage)
    if session_hash is None: session_hash = scenario_contract.get("session_hash")
    return {"schema_version": 1, "arm": arm, "metric_3": _post_compaction(events, boundaries, snapshot, scenario_contract), "metric_5": {"tokens": _usage(events, host), "interruptions": _interruptions(tel, session_hash, arm, events, snapshot)}, "metric_6": _suppressions(tel, session_hash, events)}

def main():
    p=argparse.ArgumentParser(); p.add_argument("raw_transcript"); p.add_argument("scenario_contract"); p.add_argument("arm"); p.add_argument("telemetry"); p.add_argument("--host-usage"); p.add_argument("--session-hash"); p.add_argument("--output")
    a=p.parse_args(); result=extract(Path(a.raw_transcript), json.loads(Path(a.scenario_contract).read_text()), a.arm, Path(a.telemetry), Path(a.host_usage) if a.host_usage else (), a.session_hash); payload=json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n"
    if a.output: Path(a.output).write_text(payload)
    else: print(payload,end="")
if __name__ == "__main__": main()
