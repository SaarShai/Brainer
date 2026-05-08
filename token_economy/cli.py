from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any

from .config import detect_agent, load_config
from .bench import run_framework_smoke
from .code_map import code_map
from .codex_app_server import codex_compact_thread_plan, codex_fresh_thread_plan, run_codex_ask_old_thread, run_codex_compact_thread, run_codex_fresh_thread
from .context import ask_old_session_plan, checkpoint, current_codex_transcript, fresh_launch_commands, host_context_controls, lint_handoff, meter, should_auto_relay, status_for_files, write_pending_relay
from .delegate import delegation_plan, documentation_lifecycle_packet, dumps, load_models, classify, personal_assistant_directive, personal_assistant_packet
from .docs import audit as docs_audit, split_plan
from .hooks import doctor as hooks_doctor
from .output_filter import rewind as output_filter_rewind, stats as output_filter_stats
from .output_filter import cmd_filter as output_filter_cmd_filter, cmd_rules as output_filter_cmd_rules
from .profile import set_profile, show as show_profile
from .tokens import estimate_tokens
from .wiki import WikiStore


RELAY_NAME_RE = re.compile(r"^Relay\[(?P<version>\d+)\]:\s*(?P<name>.+)$")


def relay_session_name(name: str | None = None, version: str = "01") -> str:
    session = name or "auto-context-refresh"
    if session.startswith("Relay["):
        return session
    return f"Relay[{version}]: {session}"


def next_relay_session_name(previous: str | None = None, fallback: str | None = None, version: str = "01") -> str:
    source = (previous or fallback or "auto-context-refresh").strip()
    match = RELAY_NAME_RE.match(source)
    if match:
        next_version = int(match.group("version")) + 1
        return f"Relay[{next_version:02d}]: {match.group('name')}"
    if fallback and fallback != source:
        return relay_session_name(fallback, version)
    return relay_session_name(source, version)


def codex_thread_title(thread_id: str | None) -> str | None:
    if not thread_id:
        return None
    db = Path.home() / ".codex" / "state_5.sqlite"
    if not db.exists():
        return None
    try:
        with sqlite3.connect(db) as con:
            row = con.execute("SELECT title FROM threads WHERE id = ?", (thread_id,)).fetchone()
    except sqlite3.Error:
        return None
    title = row[0] if row else None
    return title.strip() if isinstance(title, str) and title.strip() else None


def codex_thread_id_from_transcript(transcript: Path | None) -> str | None:
    if not transcript:
        return None
    match = re.search(r"rollout-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}-(?P<id>[0-9a-f-]{36})\.jsonl$", transcript.name)
    return match.group("id") if match else None


def codex_previous_thread_title(transcript: Path | None) -> str | None:
    return codex_thread_title(codex_thread_id_from_transcript(transcript) or None)


def print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True))


def cmd_doctor(args: argparse.Namespace) -> int:
    cfg = load_config(args.repo)
    required = {
        "config",
        "start_md",
        "wiki_root_exists",
    }
    checks = {
        "repo_root": str(cfg.repo_root),
        "config": (cfg.repo_root / "token-economy.yaml").exists(),
        "start_md": (cfg.repo_root / "start.md").exists(),
        "wiki_root": str(cfg.wiki_root),
        "wiki_root_exists": cfg.wiki_root.exists(),
        "refresh_threshold": cfg.refresh_threshold,
        "comcom_mcp": (cfg.repo_root / "projects/compound-compression-pipeline/comcom_mcp/server.py").exists(),
        "semdiff_mcp": (cfg.repo_root / "projects/semdiff/semdiff_mcp/server.py").exists(),
        "context_keeper": (cfg.repo_root / "projects/context-keeper").exists(),
        "python": sys.version.split()[0],
    }
    checks["ok"] = all(bool(checks[k]) for k in required)
    checks["extensions"] = {
        "comcom_mcp": checks["comcom_mcp"],
        "semdiff_mcp": checks["semdiff_mcp"],
        "context_keeper": checks["context_keeper"],
    }
    print_json(checks)
    return 0 if checks["ok"] else 1


def adapter_target(repo_root: Path, agent: str) -> Path:
    if agent == "claude":
        return repo_root / "CLAUDE.md"
    if agent == "gemini":
        return repo_root / "GEMINI.md"
    if agent == "cursor":
        return repo_root / ".cursor" / "rules" / "token-economy.mdc"
    return repo_root / "AGENTS.md"


def cmd_start(args: argparse.Namespace) -> int:
    cfg = load_config(args.repo)
    if args.scope != "project":
        raise SystemExit("Token Economy installs project-locally only; use --scope project.")
    agent = detect_agent() if args.agent == "auto" else args.agent
    src_name = "token-economy.mdc" if agent == "cursor" else {"claude": "CLAUDE.md", "gemini": "GEMINI.md"}.get(agent, "AGENTS.md")
    src = cfg.repo_root / "adapters" / agent / src_name
    if not src.exists():
        raise SystemExit(f"unknown adapter: {agent}")
    target = adapter_target(cfg.repo_root, agent)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and "Token Economy Adapter" not in target.read_text(encoding="utf-8", errors="replace"):
        sidecar = target.with_name(target.name + ".token-economy")
        shutil.copyfile(src, sidecar)
        print_json({"agent": agent, "scope": args.scope, "installed": str(sidecar), "note": f"existing {target.name} left untouched"})
        return 0
    shutil.copyfile(src, target)
    print_json({"agent": agent, "scope": args.scope, "installed": str(target)})
    return 0


def cmd_wiki(args: argparse.Namespace) -> int:
    cfg = load_config(args.repo)
    wiki = WikiStore(cfg.wiki_root)
    if args.wiki_cmd == "init":
        print_json(wiki.init())
    elif args.wiki_cmd == "index":
        print_json(wiki.index())
    elif args.wiki_cmd == "search":
        print_json(wiki.search(args.query, args.k))
    elif args.wiki_cmd == "fetch":
        print_json(wiki.fetch(args.id))
    elif args.wiki_cmd == "timeline":
        print_json(wiki.timeline(args.id, args.window))
    elif args.wiki_cmd == "context":
        print_json(wiki.context(args.task, max_pages=args.max_pages, max_tokens=args.max_tokens, k=args.k))
    elif args.wiki_cmd == "lint":
        result = wiki.lint_pages(strict=args.strict)
        print_json(result)
        if args.fail_on_error and result.get("errors"):
            return 1
    elif args.wiki_cmd == "import-audit":
        result = wiki.import_audit(args.manifest)
        print_json(result)
        return 0 if result["ok"] else 1
    elif args.wiki_cmd == "ingest":
        print_json(wiki.ingest(args.source, args.title))
    elif args.wiki_cmd == "new":
        print_json(wiki.new_page(args.template, args.title, args.domain, args.slug))
    elif args.wiki_cmd == "query":
        hits = wiki.search(args.query, args.k)
        print_json({"query": args.query, "hits": hits, "next": "Use `te wiki timeline <id>` then `te wiki fetch <id>` for relevant hits only."})
    return 0


def cmd_docs(args: argparse.Namespace) -> int:
    cfg = load_config(args.repo)
    if args.docs_cmd == "audit":
        print_json(docs_audit(cfg.repo_root, args.limit))
    elif args.docs_cmd == "split":
        path = Path(args.path)
        if not path.is_absolute():
            path = cfg.repo_root / path
        print_json(split_plan(cfg.repo_root, path))
    elif args.docs_cmd == "load":
        path = Path(args.path)
        if not path.is_absolute():
            path = cfg.repo_root / path
        text = path.read_text(encoding="utf-8", errors="replace")
        print(text)
    return 0


def cmd_code(args: argparse.Namespace) -> int:
    cfg = load_config(args.repo)
    if args.code_cmd == "map":
        print_json(code_map(cfg.repo_root, query=args.query or "", max_files=args.max_files, max_symbols=args.max_symbols))
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    cfg = load_config(args.repo)
    if args.context_cmd == "status":
        files = [cfg.repo_root / "start.md"]
        for rel in ("L0_rules.md", "L1_index.md"):
            files.append(cfg.wiki_root / rel)
        result = status_for_files(files, cfg.context_max_tokens, cfg.refresh_threshold)
        print_json(result)
    elif args.context_cmd == "meter":
        transcript = Path(args.transcript).expanduser() if args.transcript else current_codex_transcript()
        print_json(meter(transcript=transcript, model=args.model, max_tokens=cfg.context_max_tokens, threshold=cfg.refresh_threshold))
    elif args.context_cmd == "checkpoint":
        transcript = Path(args.transcript).expanduser() if args.transcript else None
        context_pct = "unknown"
        if transcript and transcript.exists():
            context_pct = str(meter(transcript=transcript, max_tokens=cfg.context_max_tokens, threshold=cfg.refresh_threshold)["pct"])
        result = checkpoint(cfg.repo_root, goal=args.goal or "", plan=args.plan or "", transcript=transcript, max_packet_tokens=args.max_tokens, context_pct=context_pct)
        if args.print_packet:
            print(result["packet"])
        else:
            print_json({k: v for k, v in result.items() if k != "packet"})
    elif args.context_cmd == "fresh-start":
        result = checkpoint(cfg.repo_root, goal=args.goal or "", plan=args.plan or "", max_packet_tokens=args.max_tokens)
        print(result["packet"])
        print(f"\nFresh packet written: {result['path']}")
        print("Open a fresh session with this packet if the host cannot clear context programmatically.")
    elif args.context_cmd == "current-transcript":
        transcript = current_codex_transcript(args.thread_id)
        if transcript:
            print(transcript)
        else:
            return 1
    elif args.context_cmd == "lint-handoff":
        print_json(lint_handoff(Path(args.path).expanduser(), max_tokens=args.max_tokens))
    elif args.context_cmd == "ask-old":
        handoff = Path(args.handoff).expanduser()
        if not handoff.is_absolute():
            handoff = cfg.repo_root / handoff
        plan = ask_old_session_plan(cfg.repo_root, handoff, args.question, execute=args.execute)
        if args.execute and plan.get("mode") == "codex-old-thread":
            print_json(run_codex_ask_old_thread(cfg.repo_root, str(plan["thread_id"]), args.question, model=args.model if args.model != "auto" else None, timeout=args.timeout))
        else:
            print_json(plan)
    elif args.context_cmd == "host-controls":
        agent = detect_agent() if args.agent == "auto" else args.agent
        print_json(host_context_controls(agent))
    elif args.context_cmd == "fresh-command":
        agent = detect_agent() if args.agent == "auto" else args.agent
        handoff = Path(args.handoff).expanduser() if args.handoff else None
        if handoff and not handoff.is_absolute():
            handoff = cfg.repo_root / handoff
        print_json(fresh_launch_commands(agent, cfg.repo_root, handoff))
    elif args.context_cmd == "codex-fresh-thread":
        handoff = Path(args.handoff).expanduser()
        if not handoff.is_absolute():
            handoff = cfg.repo_root / handoff
        session_name = relay_session_name(args.name, args.version) if args.name else None
        if args.execute:
            print_json(run_codex_fresh_thread(cfg.repo_root, handoff, model=args.model, timeout=args.timeout, ephemeral=args.ephemeral, session_name=session_name, continue_work=args.continue_work))
        else:
            print_json(codex_fresh_thread_plan(cfg.repo_root, handoff, model=args.model, ephemeral=args.ephemeral, session_name=session_name, continue_work=args.continue_work))
    elif args.context_cmd == "relay":
        transcript = Path(args.transcript).expanduser() if args.transcript else current_codex_transcript()
        status = meter(transcript=transcript, model=args.model, max_tokens=cfg.context_max_tokens, threshold=cfg.refresh_threshold)
        old_title = codex_previous_thread_title(transcript)
        relay_name = next_relay_session_name(old_title, fallback=args.name, version=args.version)
        packet = checkpoint(
            cfg.repo_root,
            goal=args.goal or f"Automatic context relay for {relay_name}",
            plan="Fresh successor should continue from this handoff with start.md only.",
            transcript=transcript,
            max_packet_tokens=args.max_tokens,
            context_pct=status["pct"],
        )
        handoff = Path(packet["path"])
        result: dict[str, Any] = {
            "agent": "codex",
            "mode": "relay",
            "session_name": relay_name,
            "previous_session_name": old_title,
            "threshold": cfg.refresh_threshold,
            "meter": status,
            "handoff": str(handoff),
            "handoff_tokens": packet["tokens"],
            "execute": args.execute,
        }
        if args.execute:
            result["successor"] = run_codex_fresh_thread(
                cfg.repo_root,
                handoff,
                model=args.model if args.model != "auto" else None,
                timeout=args.timeout,
                ephemeral=args.ephemeral,
                session_name=relay_name,
                continue_work=True,
            )
            result["ok"] = bool(result["successor"].get("ok"))
        else:
            result["successor"] = codex_fresh_thread_plan(
                cfg.repo_root,
                handoff,
                model=args.model if args.model != "auto" else None,
                ephemeral=args.ephemeral,
                session_name=relay_name,
                continue_work=True,
            )
            result["ok"] = True
        print_json(result)
    elif args.context_cmd == "auto-relay":
        transcript = Path(args.transcript).expanduser() if args.transcript else current_codex_transcript()
        status = meter(transcript=transcript, model=args.model, max_tokens=cfg.context_max_tokens, threshold=args.threshold if args.threshold is not None else cfg.refresh_threshold)
        decision = should_auto_relay(cfg.repo_root, transcript, status, cooldown_seconds=args.cooldown)
        result: dict[str, Any] = {
            "agent": "codex",
            "mode": "auto-relay",
            "meter": status,
            "transcript": str(transcript) if transcript else None,
            **decision,
        }
        if decision.get("should_relay"):
            state = write_pending_relay(cfg.repo_root, dict(decision["payload"]))
            result["state"] = state
            if args.execute:
                old_title = codex_previous_thread_title(transcript)
                relay_name = next_relay_session_name(old_title, fallback=args.name, version=args.version)
                packet = checkpoint(
                    cfg.repo_root,
                    goal=args.goal or f"Automatic context relay for {relay_name}",
                    plan="Fresh successor should continue from this handoff with start.md only.",
                    transcript=transcript,
                    max_packet_tokens=args.max_tokens,
                    context_pct=status["pct"],
                )
                handoff = Path(packet["path"])
                result["handoff"] = str(handoff)
                result["handoff_tokens"] = packet["tokens"]
                result["session_name"] = relay_name
                result["previous_session_name"] = old_title
                result["successor"] = run_codex_fresh_thread(
                    cfg.repo_root,
                    handoff,
                    model=args.model if args.model != "auto" else None,
                    timeout=args.timeout,
                    ephemeral=args.ephemeral,
                    session_name=relay_name,
                    continue_work=True,
                )
                result["ok"] = bool(result["successor"].get("ok"))
            else:
                result["ok"] = True
        else:
            result["ok"] = True
        print_json(result)
    elif args.context_cmd == "codex-compact-thread":
        handoff = Path(args.handoff).expanduser() if args.handoff else None
        if handoff and not handoff.is_absolute():
            handoff = cfg.repo_root / handoff
        thread_id = None if args.current else args.thread_id
        if args.execute:
            print_json(run_codex_compact_thread(cfg.repo_root, thread_id=thread_id, handoff=handoff, model=args.model, timeout=args.timeout))
        else:
            print_json(codex_compact_thread_plan(cfg.repo_root, thread_id=thread_id, handoff=handoff, model=args.model))
    return 0


def cmd_delegate(args: argparse.Namespace) -> int:
    cfg = load_config(args.repo)
    registry = load_models(cfg.model_registry)
    if args.delegate_cmd == "models":
        print_json(registry)
    elif args.delegate_cmd == "classify":
        print(dumps(classify(args.task, registry).as_dict()))
    elif args.delegate_cmd == "plan":
        print_json(delegation_plan(args.task, registry))
    elif args.delegate_cmd == "document":
        print_json(documentation_lifecycle_packet(args.task, args.evidence, args.verified, registry))
    return 0


def cmd_pa(args: argparse.Namespace) -> int:
    cfg = load_config(args.repo)
    registry = load_models(cfg.model_registry)
    prompt = " ".join(args.prompt).strip()
    if not prompt:
        raise SystemExit("te pa requires a prompt, usually starting with /pa or /btw")
    packet = personal_assistant_packet(prompt, registry)
    if args.directive:
        print(personal_assistant_directive(packet))
    else:
        print_json(packet)
    return 0


def cmd_hooks(args: argparse.Namespace) -> int:
    cfg = load_config(args.repo)
    if args.hooks_cmd == "doctor":
        result = hooks_doctor(cfg.repo_root)
        print_json(result)
        return 0 if result["ok"] else 1
    return 0


def cmd_output_filter(args: argparse.Namespace) -> int:
    cfg = load_config(args.repo)
    if args.output_filter_cmd == "filter":
        return output_filter_cmd_filter(args)
    if args.output_filter_cmd == "stats":
        print_json(output_filter_stats(cfg.repo_root, limit=args.limit))
    elif args.output_filter_cmd == "rewind":
        print(output_filter_rewind(cfg.repo_root, args.id), end="")
    elif args.output_filter_cmd == "rules":
        return output_filter_cmd_rules(args)
    return 0


def cmd_profile(args: argparse.Namespace) -> int:
    cfg = load_config(args.repo)
    if args.profile_cmd == "show":
        print_json(show_profile(cfg.repo_root))
    elif args.profile_cmd == "set":
        print_json(set_profile(cfg.repo_root, args.name))
    return 0


def cmd_bench(args: argparse.Namespace) -> int:
    cfg = load_config(args.repo)
    if args.bench_cmd == "run":
        if args.suite != "framework-smoke":
            raise SystemExit(f"unknown suite: {args.suite}")
        result = run_framework_smoke(cfg.repo_root)
        print_json(result)
        return 0 if result["ok"] else 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="te", description="Token Economy universal agent framework CLI")
    p.add_argument("--repo", default=None, help="Repo root or child path")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("doctor")
    d.set_defaults(func=cmd_doctor)

    s = sub.add_parser("start")
    s.add_argument("--agent", choices=["auto", "claude", "codex", "gemini", "cursor"], default="auto")
    s.add_argument("--scope", choices=["project"], default="project")
    s.set_defaults(func=cmd_start)

    w = sub.add_parser("wiki")
    wsub = w.add_subparsers(dest="wiki_cmd", required=True)
    wsub.add_parser("init").set_defaults(func=cmd_wiki)
    wsub.add_parser("index").set_defaults(func=cmd_wiki)
    ws = wsub.add_parser("search")
    ws.add_argument("query")
    ws.add_argument("-k", type=int, default=10)
    ws.set_defaults(func=cmd_wiki)
    wf = wsub.add_parser("fetch")
    wf.add_argument("id")
    wf.set_defaults(func=cmd_wiki)
    wt = wsub.add_parser("timeline")
    wt.add_argument("id")
    wt.add_argument("--window", type=int, default=3)
    wt.set_defaults(func=cmd_wiki)
    wc = wsub.add_parser("context", help="Plan and load bounded task context from the wiki")
    wc.add_argument("task")
    wc.add_argument("--max-pages", type=int, default=5)
    wc.add_argument("--max-tokens", type=int, default=4000)
    wc.add_argument("-k", type=int, default=12)
    wc.set_defaults(func=cmd_wiki)
    wl = wsub.add_parser("lint")
    wl.add_argument("--strict", action="store_true")
    wl.add_argument("--fail-on-error", action="store_true")
    wl.set_defaults(func=cmd_wiki)
    wa = wsub.add_parser("import-audit", help="Validate self-contained wiki import coverage")
    wa.add_argument("--manifest", required=True)
    wa.set_defaults(func=cmd_wiki)
    wi = wsub.add_parser("ingest")
    wi.add_argument("source")
    wi.add_argument("--title")
    wi.set_defaults(func=cmd_wiki)
    wn = wsub.add_parser("new")
    wn.add_argument("--template", choices=["page", "decision", "source-summary", "import-manifest"], default="page")
    wn.add_argument("--title", required=True)
    wn.add_argument("--domain", default="framework")
    wn.add_argument("--slug")
    wn.set_defaults(func=cmd_wiki)
    wq = wsub.add_parser("query")
    wq.add_argument("query")
    wq.add_argument("-k", type=int, default=10)
    wq.set_defaults(func=cmd_wiki)

    docs = sub.add_parser("docs")
    dsub = docs.add_subparsers(dest="docs_cmd", required=True)
    da = dsub.add_parser("audit")
    da.add_argument("--limit", type=int, default=1500)
    da.set_defaults(func=cmd_docs)
    ds = dsub.add_parser("split")
    ds.add_argument("path")
    ds.set_defaults(func=cmd_docs)
    dl = dsub.add_parser("load")
    dl.add_argument("path")
    dl.set_defaults(func=cmd_docs)

    code = sub.add_parser("code")
    codesub = code.add_subparsers(dest="code_cmd", required=True)
    cdm = codesub.add_parser("map", help="Build a compact structural code map")
    cdm.add_argument("query", nargs="?", default="")
    cdm.add_argument("--max-files", type=int, default=20)
    cdm.add_argument("--max-symbols", type=int, default=200)
    cdm.set_defaults(func=cmd_code)

    ctx = sub.add_parser("context")
    csub = ctx.add_subparsers(dest="context_cmd", required=True)
    csub.add_parser("status").set_defaults(func=cmd_context)
    cm = csub.add_parser("meter")
    cm.add_argument("--model", default="auto")
    cm.add_argument("--transcript")
    cm.set_defaults(func=cmd_context)
    cc = csub.add_parser("checkpoint")
    cc.add_argument("--goal")
    cc.add_argument("--plan")
    cc.add_argument("--transcript")
    cc.add_argument("--max-tokens", type=int, default=2000)
    cc.add_argument("--print-packet", action="store_true")
    cc.add_argument("--handoff-template", action="store_true")
    cc.set_defaults(func=cmd_context)
    cf = csub.add_parser("fresh-start")
    cf.add_argument("--goal")
    cf.add_argument("--plan")
    cf.add_argument("--max-tokens", type=int, default=2000)
    cf.set_defaults(func=cmd_context)
    ct = csub.add_parser("current-transcript", help="Print the current Codex transcript path when CODEX_THREAD_ID is available")
    ct.add_argument("--thread-id")
    ct.set_defaults(func=cmd_context)
    cl = csub.add_parser("lint-handoff")
    cl.add_argument("path")
    cl.add_argument("--max-tokens", type=int, default=2000)
    cl.set_defaults(func=cmd_context)
    cao = csub.add_parser("ask-old", help="Ask an explicit bounded follow-up of the old relay session")
    cao.add_argument("--handoff", required=True)
    cao.add_argument("--question", required=True)
    cao.add_argument("--model", default="auto")
    cao.add_argument("--execute", action="store_true", help="Actually query an old Codex thread when old-thread-id is available")
    cao.add_argument("--timeout", type=int, default=120)
    cao.set_defaults(func=cmd_context)
    ch = csub.add_parser("host-controls")
    ch.add_argument("--agent", choices=["auto", "claude", "codex", "gemini", "cursor", "generic"], default="auto")
    ch.set_defaults(func=cmd_context)
    fc = csub.add_parser("fresh-command")
    fc.add_argument("--agent", choices=["auto", "claude", "codex", "gemini", "cursor", "generic"], default="auto")
    fc.add_argument("--handoff")
    fc.set_defaults(func=cmd_context)
    cft = csub.add_parser("codex-fresh-thread")
    cft.add_argument("--handoff", required=True)
    cft.add_argument("--model")
    cft.add_argument("--name", default=None, help='Name/label for the fresh successor, e.g. "Relay[01]: sessions-relay"')
    cft.add_argument("--version", default="01", help='Relay version used when --name is a suffix, e.g. Relay[01]: sessions-relay')
    cft.add_argument("--continue-work", action="store_true", help="Tell the successor to verify the handoff and continue instead of stopping")
    cft.add_argument("--execute", action="store_true", help="Actually launch Codex App Server and start a fresh successor thread")
    cft.add_argument("--ephemeral", action="store_true", help="Use an in-memory throwaway thread instead of the default persistent project thread")
    cft.add_argument("--timeout", type=int, default=120)
    cft.set_defaults(func=cmd_context)
    cct = csub.add_parser("codex-compact-thread", help="EXPERIMENTAL: Codex current-thread compact; current-thread clear is unsolved in tested Desktop/App Server")
    cct.add_argument("--thread-id")
    cct.add_argument("--current", action="store_true", help="Use CODEX_THREAD_ID from the current Codex session")
    cct.add_argument("--handoff")
    cct.add_argument("--model")
    cct.add_argument("--execute", action="store_true", help="Actually ask Codex App Server to compact the target thread")
    cct.add_argument("--timeout", type=int, default=120)
    cct.set_defaults(func=cmd_context)
    cr = csub.add_parser("relay", help="Write a handoff and launch or plan a fresh Codex relay successor")
    cr.add_argument("--transcript")
    cr.add_argument("--goal")
    cr.add_argument("--name", default=None, help='Relay session label suffix; defaults to "auto-context-refresh"')
    cr.add_argument("--version", default="01", help='Relay version used in the generated name, e.g. Relay[01]: auto-context-refresh')
    cr.add_argument("--model", default="auto")
    cr.add_argument("--max-tokens", type=int, default=2000)
    cr.add_argument("--execute", action="store_true")
    cr.add_argument("--ephemeral", action="store_true")
    cr.add_argument("--timeout", type=int, default=120)
    cr.set_defaults(func=cmd_context)
    car = csub.add_parser("auto-relay", help="Check current context and launch or schedule relay when threshold is crossed")
    car.add_argument("--transcript")
    car.add_argument("--goal")
    car.add_argument("--name", default=None)
    car.add_argument("--version", default="01")
    car.add_argument("--model", default="auto")
    car.add_argument("--threshold", type=float)
    car.add_argument("--cooldown", type=int, default=1800)
    car.add_argument("--max-tokens", type=int, default=2000)
    car.add_argument("--execute", action="store_true", help="Launch the fresh successor immediately when relay is due")
    car.add_argument("--ephemeral", action="store_true")
    car.add_argument("--timeout", type=int, default=120)
    car.set_defaults(func=cmd_context)

    de = sub.add_parser("delegate")
    desub = de.add_subparsers(dest="delegate_cmd", required=True)
    desub.add_parser("models").set_defaults(func=cmd_delegate)
    dc = desub.add_parser("classify")
    dc.add_argument("task")
    dc.set_defaults(func=cmd_delegate)
    dp = desub.add_parser("plan")
    dp.add_argument("task")
    dp.set_defaults(func=cmd_delegate)
    dd = desub.add_parser("document", help="Route verified durable evidence to a lightweight wiki-documenter")
    dd.add_argument("--task", required=True)
    dd.add_argument("--evidence", required=True)
    dd.add_argument("--verified", action="store_true")
    dd.set_defaults(func=cmd_delegate)

    pa = sub.add_parser("pa", help="Route /pa or /btw prompts through the personal-assistant router")
    pa.add_argument("--directive", action="store_true", help="Print hook-friendly routing instructions")
    pa.add_argument("prompt", nargs=argparse.REMAINDER)
    pa.set_defaults(func=cmd_pa)

    hk = sub.add_parser("hooks")
    hksub = hk.add_subparsers(dest="hooks_cmd", required=True)
    hksub.add_parser("doctor").set_defaults(func=cmd_hooks)

    of = sub.add_parser("output-filter", help="Filter noisy tool output with raw-output recovery")
    ofsub = of.add_subparsers(dest="output_filter_cmd", required=True)
    off = ofsub.add_parser("filter")
    off.add_argument("--no-archive", action="store_true")
    off.add_argument("--session-aware", action="store_true")
    off.set_defaults(func=cmd_output_filter)
    ofs = ofsub.add_parser("stats")
    ofs.add_argument("--limit", type=int)
    ofs.set_defaults(func=cmd_output_filter)
    ofr = ofsub.add_parser("rewind")
    ofr.add_argument("id", nargs="?", default="last")
    ofr.set_defaults(func=cmd_output_filter)
    ofrules = ofsub.add_parser("rules")
    ofrules.add_argument("--init", action="store_true")
    ofrules.set_defaults(func=cmd_output_filter)

    pr = sub.add_parser("profile")
    prsub = pr.add_subparsers(dest="profile_cmd", required=True)
    prsub.add_parser("show").set_defaults(func=cmd_profile)
    ps = prsub.add_parser("set")
    ps.add_argument("name")
    ps.set_defaults(func=cmd_profile)

    be = sub.add_parser("bench")
    besub = be.add_subparsers(dest="bench_cmd", required=True)
    br = besub.add_parser("run")
    br.add_argument("--suite", default="framework-smoke")
    br.set_defaults(func=cmd_bench)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
