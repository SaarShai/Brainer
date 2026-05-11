from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from token_economy.cli import main, next_relay_session_name, relay_session_name
from token_economy.code_map import code_map
from token_economy.config import detect_agent
from token_economy.codex_app_server import codex_fresh_thread_plan, default_codex_fresh_model
from token_economy.context import checkpoint, fresh_launch_commands, host_context_controls, lint_handoff, meter
from token_economy.docs import audit as docs_audit
from token_economy.delegate import classify, documentation_lifecycle_packet, personal_assistant_packet, strip_pa_prefix
from token_economy.output_filter import filter_text, load_rules
from token_economy.tokens import estimate_tokens
from token_economy.wiki import WikiStore


REPO = Path(__file__).resolve().parents[1]


class UniversalFrameworkTests(unittest.TestCase):
    def test_active_docs_do_not_reintroduce_global_or_app_setup(self):
        active_paths = [
            REPO / "AGENT_ONBOARDING.md",
            REPO / "INSTALL.md",
            REPO / "README.md",
            REPO / "start.md",
            REPO / "HANDOFF.md",
            REPO / "ROADMAP.md",
            REPO / "L0_rules.md",
            REPO / "stable/AGENT_PROMPT.md",
            REPO / "stable/INSTALL.sh",
            REPO / "stable/README.md",
            REPO / "schema.md",
            REPO / "skills/token-economy-external-adoption/SKILL.md",
            REPO / "token_economy/wiki.py",
            REPO / "token_economy/delegate.py",
            REPO / "projects/wiki-search/README.md",
            REPO / "projects/agents-triage/SKILL.md",
            REPO / "projects/agents-triage/install.sh",
            REPO / "projects/agents-triage/classify.py",
            REPO / "projects/agents-triage/agents/wiki-note.md",
        ]
        forbidden = ("obsidian", "vault", "~/.claude", "--scope user", "scope user")
        for path in active_paths:
            text = path.read_text(encoding="utf-8", errors="replace").lower()
            for needle in forbidden:
                self.assertNotIn(needle, text, f"{needle!r} found in {path.relative_to(REPO)}")

    def test_setup_prompt_allows_fresh_folder_clear_only(self):
        text = (REPO / "stable/AGENT_PROMPT.md").read_text(encoding="utf-8")
        self.assertIn("explicit permission to clear the current folder", text)
        self.assertIn("find . -mindepth 1 -maxdepth 1 -exec rm -rf {} +", text)
        self.assertIn("git clone --depth 1 --filter=blob:none --sparse https://github.com/SaarShai/token-economy.git .", text)
        self.assertIn("git sparse-checkout set --no-cone", text)
        self.assertIn("rm -rf .git", text)
        self.assertIn("git init", text)
        self.assertIn("Do not delete anything outside the current folder", text)
        self.assertNotIn("git restore --source origin/main", text)
        self.assertNotIn("git reset --hard", text)

    def test_start_and_adapters_stay_lean(self):
        start = (REPO / "start.md").read_text(encoding="utf-8")
        self.assertIn("no softening", start)
        self.assertLessEqual(estimate_tokens(start), 1500)
        for adapter in [
            REPO / "adapters/claude/CLAUDE.md",
            REPO / "adapters/codex/AGENTS.md",
            REPO / "adapters/gemini/GEMINI.md",
            REPO / "adapters/cursor/token-economy.mdc",
            REPO / "CLAUDE.md",
            REPO / "AGENTS.md",
            REPO / "GEMINI.md",
            REPO / ".cursor/rules/token-economy.mdc",
        ]:
            combined = start + "\n" + adapter.read_text(encoding="utf-8")
            self.assertLessEqual(estimate_tokens(combined), 2500)

    def test_relay_successor_names_version_old_session_title(self):
        self.assertEqual(relay_session_name("screenery relay"), "screenery relay v2")
        self.assertEqual(relay_session_name("screenery relay v2"), "screenery relay v3")
        self.assertEqual(relay_session_name("screenery relay_v9"), "screenery relay v10")
        self.assertEqual(next_relay_session_name(previous="farey-g3-h1-relay v7", fallback="ignored"), "farey-g3-h1-relay v8")
        self.assertEqual(next_relay_session_name(previous=None, fallback="fallback relay"), "fallback relay v2")

    def test_wiki_progressive_retrieval(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            wiki = WikiStore(root)
            wiki.init()
            note = root / "concepts" / "context-refresh.md"
            note.write_text(
                """---
type: concept
axis: cross_session_memory
tags: [context-refresh]
confidence: high
evidence_count: 1
---

# Context Refresh

Use fresh session packets at 20 percent context to avoid context rot. Links to [[patterns/progressive-retrieval]].
""",
                encoding="utf-8",
            )
            linked = root / "patterns" / "progressive-retrieval.md"
            linked.write_text(
                """---
type: pattern
axis: knowledge_org
tags: [retrieval]
confidence: med
evidence_count: 1
---

# Progressive Retrieval

Search first, timeline second, fetch last.
""",
                encoding="utf-8",
            )
            alias = root / "concepts" / "alias-link.md"
            alias.write_text(
                """---
type: concept
axis: knowledge_org
tags: [retrieval]
confidence: med
evidence_count: 1
---

# Alias Link

Alias link to [[patterns/progressive-retrieval|progressive retrieval]].

```bash
if [[ "$path" == raw/* ]]; then
  echo skip
fi
```
""",
                encoding="utf-8",
            )
            result = wiki.index()
            self.assertGreaterEqual(result["indexed"], 2)
            hits = wiki.search("context refresh")
            self.assertTrue(hits)
            self.assertEqual(hits[0]["id"], "concepts/context-refresh")
            timeline = wiki.timeline("patterns/progressive-retrieval")
            self.assertTrue(timeline["backlinks"])
            fetched = wiki.fetch("concepts/context-refresh")
            self.assertIn("20 percent context", fetched["content"])
            lint = wiki.lint()
            self.assertEqual(lint["broken_links"], [])
            self.assertEqual(wiki.read_page(alias.resolve()).links, ["patterns/progressive-retrieval"])

    def test_wiki_context_loads_relevant_and_rejects_noise(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            wiki = WikiStore(root)
            wiki.init()
            (root / "concepts" / "new-retrieval.md").write_text(
                """---
schema_version: 2
title: "New Retrieval"
type: concept
domain: framework
tier: semantic
confidence: 0.9
created: 2026-04-25
updated: 2026-04-25
verified: 2026-04-25
sources: ["unit-test"]
supersedes: ["[[concepts/old-retrieval]]"]
superseded-by:
tags: [retrieval, context]
---

# New Retrieval

Progressive retrieval loads context by search, timeline, then fetch. Related: [[schema]]
""",
                encoding="utf-8",
            )
            (root / "concepts" / "old-retrieval.md").write_text(
                """---
schema_version: 2
title: "Old Retrieval"
type: concept
domain: framework
tier: semantic
confidence: 0.3
created: 2026-01-01
updated: 2026-01-01
verified: 2026-01-01
sources: ["unit-test"]
supersedes: []
superseded-by: [[concepts/new-retrieval]]
tags: [retrieval, context]
---

# Old Retrieval

Superseded progressive retrieval note.
""",
                encoding="utf-8",
            )
            (root / "raw" / "2026-04-25-context-dump.md").write_text(
                """---
schema_version: 2
title: "Context Dump"
type: raw
domain: external-source
tier: episodic
confidence: 0.6
created: 2026-04-25
updated: 2026-04-25
verified: 2026-04-25
sources: ["unit-test"]
supersedes: []
superseded-by:
tags: [retrieval, context]
---

# Context Dump

Raw context retrieval archive distractor.
""",
                encoding="utf-8",
            )
            wiki.index()
            packet = wiki.context("progressive retrieval context", max_pages=5, max_tokens=1200)
            self.assertIn("concepts/new-retrieval", packet["fetch_plan"])
            self.assertLessEqual(len(packet["loaded"]), 5)
            self.assertLessEqual(packet["token_estimate"], 1200)
            self.assertNotIn("raw/2026-04-25-context-dump", packet["fetch_plan"])
            rejected = {row["id"]: row for row in packet["rejected"]}
            self.assertEqual(rejected["concepts/old-retrieval"]["reason"], "superseded")

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main(["--repo", str(root), "wiki", "context", "progressive retrieval context", "--max-pages", "5", "--max-tokens", "1200"]), 0)
            cli_packet = json.loads(buf.getvalue())
            self.assertEqual(cli_packet["fetch_plan"], packet["fetch_plan"])

    def test_wiki_lint_warns_on_stale_index_and_quality_gaps(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            wiki = WikiStore(root)
            wiki.init()
            page = root / "concepts" / "quality-gap.md"
            page.write_text(
                """---
schema_version: 2
title: "Quality Gap"
type: concept
domain: framework
tier: semantic
confidence: 0.5
created: 2026-04-25
updated: 2026-04-25
verified: 2026-04-25
sources: []
supersedes: []
superseded-by:
tags: [quality]
---

# Quality Gap

Missing provenance and backlinks on purpose.
""",
                encoding="utf-8",
            )
            wiki.index()
            index_mtime = (root / "L1_index.md").stat().st_mtime
            os.utime(page, (index_mtime + 3, index_mtime + 3))
            lint = wiki.lint_pages(strict=True)
            self.assertIn("L1_index.md", lint["stale_indexes"])
            self.assertIn("concepts/quality-gap", lint["missing_provenance"])
            self.assertIn("concepts/quality-gap", lint["missing_backlinks"])
            self.assertEqual(lint["errors"], [])

    def test_code_map_extracts_compact_symbols_and_cli(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            package = root / "pkg"
            package.mkdir()
            (root / "token-economy.yaml").write_text("wiki_root: .\n", encoding="utf-8")
            (package / "worker.py").write_text(
                """import json
from pathlib import Path


class Worker:
    def run(self, path: Path):
        return json.dumps({"path": str(path)})


def helper(value):
    return value
""",
                encoding="utf-8",
            )
            (package / "ui.ts").write_text(
                """import { readFileSync } from "fs";

export function renderPanel() {
  return readFileSync("x", "utf8");
}
""",
                encoding="utf-8",
            )
            mapped = code_map(root, query="worker run", max_files=5, max_symbols=20)
            self.assertEqual(mapped["matched_files"], 1)
            self.assertEqual(mapped["files"][0]["path"], "pkg/worker.py")
            names = {symbol["name"] for symbol in mapped["files"][0]["symbols"]}
            self.assertIn("Worker", names)
            self.assertIn("run", names)
            self.assertIn("json", mapped["files"][0]["imports"])

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main(["--repo", str(root), "code", "map", "renderPanel"]), 0)
            cli_map = json.loads(buf.getvalue())
            self.assertEqual(cli_map["files"][0]["path"], "pkg/ui.ts")
            self.assertEqual(cli_map["files"][0]["symbols"][0]["name"], "renderPanel")

    def test_checkpoint_packet_is_small_and_plan_mode(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "L1_index.md").write_text("# L1\n\n- x -> `x.md`\n", encoding="utf-8")
            transcript = root / "transcript.txt"
            transcript.write_text(
                "command: pytest tests/test_x.py\nERROR failed assertion\nTouched /tmp/example.py\n",
                encoding="utf-8",
            )
            result = checkpoint(root, goal="finish framework", plan="verify tests", transcript=transcript)
            self.assertLessEqual(result["tokens"], 2000)
            self.assertIn("Start in plan mode", result["packet"])
            self.assertIn("pytest tests/test_x.py", result["packet"])

    def test_delegate_prefers_cheapest_capable_worker(self):
        route = classify("summarize this markdown wiki note and document the result")
        self.assertEqual(route.tier, "simple")
        self.assertEqual(route.model_class, "lightweight")
        self.assertEqual(route.worker, "wiki-documenter")

        repo_route = classify("commit and push verified changes to the GitHub repo")
        self.assertEqual(repo_route.model_class, "lightweight")
        self.assertEqual(repo_route.worker, "repo-maintainer")

    def test_documentation_lifecycle_routes_only_verified_evidence(self):
        routed = documentation_lifecycle_packet(
            "document important wiki results",
            "pytest tests/test_universal_framework.py passed; updated token_economy/wiki.py",
            verified=True,
        )
        self.assertEqual(routed["action"], "route")
        self.assertEqual(routed["worker"], "wiki-documenter")
        self.assertEqual(routed["model_class"], "lightweight")
        self.assertIn("verified evidence", routed["context_policy"])

        skipped = documentation_lifecycle_packet("document plan", "planned but not executed", verified=False)
        self.assertEqual(skipped["action"], "skip")
        self.assertFalse(skipped["persist"])

    def test_personal_assistant_prompt_bypass(self):
        invoked, clean = strip_pa_prefix("/pa summarize this wiki note")
        self.assertTrue(invoked)
        self.assertEqual(clean, "summarize this wiki note")
        self.assertEqual(strip_pa_prefix("/btw: extract file paths")[1], "extract file paths")

        packet = personal_assistant_packet("/pa summarize this wiki note")
        self.assertEqual(packet["mode"], "personal_assistant")
        self.assertTrue(packet["bypass_context"])
        self.assertEqual(packet["router"]["model_class"], "lightweight")
        self.assertEqual(packet["handler"]["model_class"], "lightweight")
        self.assertFalse(packet["context_bundle"]["include_full_transcript"])
        self.assertTrue(packet["context_bundle"]["include_l1_index"])
        self.assertIn("Do not answer", packet["main_model_instruction"])

    def test_cli_pa_and_hook_route(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(main(["pa", "/pa summarize this wiki note"]), 0)
        packet = json.loads(buf.getvalue())
        self.assertEqual(packet["mode"], "personal_assistant")

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(main(["pa", "--directive", "/btw", "summarize", "this"]), 0)
        self.assertIn("[token-economy:/pa]", buf.getvalue())
        self.assertIn("Do not answer directly", buf.getvalue())

        proc = subprocess.run(
            ["bash", str(REPO / "hooks/user-prompt-submit.sh")],
            input=json.dumps({"prompt": "/pa summarize this"}),
            text=True,
            cwd=REPO,
            capture_output=True,
            check=True,
        )
        self.assertIn("[token-economy:/pa]", proc.stdout)

        quiet = subprocess.run(
            ["bash", str(REPO / "hooks/user-prompt-submit.sh")],
            input=json.dumps({"prompt": "normal prompt"}),
            text=True,
            cwd=REPO,
            capture_output=True,
            check=True,
        )
        self.assertEqual(quiet.stdout, "")

    def test_context_keeper_v2_memory_api(self):
        memory_dir = REPO / "projects" / "context-keeper-v2"
        sys.path.insert(0, str(memory_dir))
        try:
            from memory_api import ck_fetch, ck_query, ck_recent

            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                (root / "L2_facts").mkdir()
                (root / "L3_sops").mkdir()
                (root / "L4_archive").mkdir()
                (root / "L1_index.md").write_text("- routing -> `L2_facts/routing.md`\n", encoding="utf-8")
                (root / "L2_facts" / "routing.md").write_text("cheap models first for routing\n", encoding="utf-8")
                (root / "L4_archive" / "session.md").write_text("archive\n", encoding="utf-8")
                self.assertTrue(ck_query("routing", root=root))
                fetched = ck_fetch("L2", "routing", root=root)
                self.assertIn("cheap models", fetched["content"])
                self.assertTrue(ck_recent(root=root))
        finally:
            sys.path.remove(str(memory_dir))

    def test_skill_crystallizer_v1_writes_sop_only_after_verified_work(self):
        skill_dir = REPO / "projects" / "skill-crystallizer"
        sys.path.insert(0, str(skill_dir))
        try:
            from detector import crystallize_task

            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                events = [
                    "User asked to harden wiki context retrieval",
                    "apply_patch updated token_economy/wiki.py",
                    "apply_patch updated tests/test_universal_framework.py",
                    "python3 -m unittest tests.test_universal_framework passed OK",
                    "done",
                ]
                result = crystallize_task(events, root=root, task="Harden wiki context retrieval")
                self.assertEqual(result["action"], "created")
                self.assertTrue((root / result["path"]).exists())
                self.assertTrue((root / "L1_index.md").exists())

                skipped = crystallize_task(["read start.md", "looked at index"], root=root, task="Read docs")
                self.assertEqual(skipped["action"], "skip")
        finally:
            sys.path.remove(str(skill_dir))

    def test_cli_wiki_init_and_delegate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main(["--repo", str(root), "wiki", "init"]), 0)
            self.assertIn("wiki_root", json.loads(buf.getvalue()))
            self.assertTrue((root / "schema.md").exists())

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main(["--repo", str(root), "delegate", "classify", "one-line typo fix"]), 0)
            route = json.loads(buf.getvalue())
            self.assertEqual(route["tier"], "simple")

    def test_wiki_new_v2_page_and_strict_lint(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            wiki = WikiStore(root)
            wiki.init()
            # Copy templates into temp wiki to emulate repo install.
            (root / "templates").mkdir(exist_ok=True)
            for name in ("page.template.md", "decision.template.md", "source-summary.template.md", "import-manifest.template.md"):
                (root / "templates" / name).write_text((REPO / "templates" / name).read_text(encoding="utf-8"), encoding="utf-8")
            created = wiki.new_page("page", "Progressive Retrieval", "framework")
            self.assertTrue((root / created["created"]).exists())
            manifest = wiki.new_page("import-manifest", "Import Manifest", "project")
            self.assertTrue((root / manifest["created"]).exists())
            lint = wiki.lint_pages(strict=True)
            self.assertEqual(lint["errors"], [])

    def test_wiki_import_audit_validates_self_contained_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            wiki = WikiStore(root)
            wiki.init()
            project = root / "projects" / "example.md"
            project.write_text(
                """---
schema_version: 2
title: "Example Project"
type: project
domain: project
tier: working
confidence: 0.8
created: 2026-04-26
updated: 2026-04-26
verified: 2026-04-26
sources: ["[[raw/2026-04-26-import-manifest]]"]
supersedes: []
superseded-by:
tags: [imported]
---

# Example Project

Local rewritten project facts. Related: [[index]].
""",
                encoding="utf-8",
            )
            sop = root / "L3_sops" / "runbook.md"
            sop.write_text(
                """---
schema_version: 2
title: "Runbook"
type: sop
domain: project
tier: procedural
confidence: 0.8
created: 2026-04-26
updated: 2026-04-26
verified: 2026-04-26
sources: ["[[raw/2026-04-26-import-manifest]]"]
supersedes: []
superseded-by:
tags: [runbook]
---

# Runbook

Run the local smoke test. Related: [[projects/example]].
""",
                encoding="utf-8",
            )
            manifest = root / "raw" / "2026-04-26-import-manifest.md"
            manifest.write_text(
                """# Import Manifest

Source provenance may mention the original wiki and absolute paths here.

| Original page/path | Summary | Target local page | Status | Rationale | Provenance |
|---|---|---|---|---|---|
| /Users/saar/OldWiki/Home.md | Project state | projects/example.md | adapted | Rewritten into local project page | full_summ section 4 |
| /Users/saar/OldWiki/Runbook.md | Runbook | L3_sops/runbook.md | adapted | Rewritten as local SOP | full_summ section 4 |
| /Users/saar/OldWiki/Noise.md | Duplicate chatter |  | discarded | Duplicative transcript noise | full_summ section 10 |
""",
                encoding="utf-8",
            )
            (root / "index.md").write_text("- [[projects/example]]\n", encoding="utf-8")
            (root / "L1_index.md").write_text("- projects/example -> `projects/example.md`\n", encoding="utf-8")

            audit = wiki.import_audit("raw/2026-04-26-import-manifest.md")
            self.assertTrue(audit["ok"], audit)
            self.assertEqual(audit["rows"], 3)

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main(["--repo", str(root), "wiki", "import-audit", "--manifest", "raw/2026-04-26-import-manifest.md"]), 0)
            self.assertTrue(json.loads(buf.getvalue())["ok"])

            missing = manifest.read_text(encoding="utf-8").replace("L3_sops/runbook.md", "L3_sops/missing.md")
            manifest.write_text(missing, encoding="utf-8")
            audit = wiki.import_audit(manifest)
            self.assertFalse(audit["ok"])
            self.assertIn("target_page_missing", {error["code"] for error in audit["errors"]})

            manifest.write_text(missing.replace("L3_sops/missing.md", "L3_sops/runbook.md"), encoding="utf-8")
            project.write_text(project.read_text(encoding="utf-8") + "\nUse the original wiki for details.\n", encoding="utf-8")
            audit = wiki.import_audit(manifest)
            self.assertFalse(audit["ok"])
            self.assertIn("forbidden_external_wiki_reference", {error["code"] for error in audit["errors"]})

    def test_context_meter_env_threshold_and_handoff_lint(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            transcript = root / "transcript.txt"
            transcript.write_text("x" * 200, encoding="utf-8")
            old_refresh = os.environ.get("REFRESH_AT_PCT")
            old_warn = os.environ.get("WARN_AT_PCT")
            old_max = os.environ.get("TOKEN_ECONOMY_CONTEXT_MAX")
            os.environ["REFRESH_AT_PCT"] = "20"
            os.environ["WARN_AT_PCT"] = "15"
            os.environ["TOKEN_ECONOMY_CONTEXT_MAX"] = "250"
            try:
                status = meter(transcript, model="test")
                self.assertEqual(status["action"], "refresh")
            finally:
                for key, value in (("REFRESH_AT_PCT", old_refresh), ("WARN_AT_PCT", old_warn), ("TOKEN_ECONOMY_CONTEXT_MAX", old_max)):
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
            packet = checkpoint(root, goal="meter test", plan="verify", transcript=transcript)
            self.assertTrue(lint_handoff(Path(packet["path"]))["ok"])
            try:
                os.environ["REFRESH_AT_PCT"] = "0.20"
                self.assertEqual(meter(transcript, model="test", max_tokens=250)["refresh_threshold"], 0.20)
            finally:
                if old_refresh is None:
                    os.environ.pop("REFRESH_AT_PCT", None)
                else:
                    os.environ["REFRESH_AT_PCT"] = old_refresh
            self.assertEqual(meter(model="gemini-flash")["max_tokens"], 1_000_000)
            self.assertEqual(meter(model="claude-sonnet")["max_tokens"], 200_000)

    def test_delegate_plan_contract(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(main(["delegate", "plan", "extract two symbols from code"]), 0)
        plan = json.loads(buf.getvalue())
        self.assertNotEqual(plan["chosen_tier"], "reasoning_top")
        self.assertIn("Orchestrator does not delegate final synthesis", plan["orchestrator_rule"])
        self.assertIn("sources", plan["result_contract"])

    def test_output_filter_preserves_errors(self):
        proc = subprocess.run(
            ["bash", str(REPO / "hooks/output-filter/filter.sh")],
            input="same\nsame\nERROR exact failure\nsame\n",
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("ERROR exact failure", proc.stdout)
        self.assertIn("deduped", proc.stdout)

    def test_output_filter_archives_stats_and_rewinds(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "token-economy.yaml").write_text("wiki_root: .\noutput_filter_archive: true\n", encoding="utf-8")
            payload = ("same\n" * 20) + "ERROR exact failure\n50%\n"
            buf = io.StringIO()
            old_stdin = sys.stdin
            try:
                sys.stdin = io.StringIO(payload)
                with contextlib.redirect_stdout(buf):
                    self.assertEqual(main(["--repo", str(root), "output-filter", "filter"]), 0)
            finally:
                sys.stdin = old_stdin
            self.assertIn("ERROR exact failure", buf.getvalue())
            self.assertNotIn("50%", buf.getvalue())

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main(["--repo", str(root), "output-filter", "stats"]), 0)
            stats = json.loads(buf.getvalue())
            self.assertEqual(stats["events"], 1)
            self.assertGreater(stats["char_savings"], 0)
            self.assertEqual(stats["last_id"].endswith("-default"), True)

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main(["--repo", str(root), "output-filter", "rewind"]), 0)
            self.assertEqual(buf.getvalue(), payload)

    def test_output_filter_custom_rules_and_session_awareness(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            rules_path = root / "rules.txt"
            rules_path.write_text("drop:^noise$\nkeep:^noise important$\n", encoding="utf-8")
            seen_path = root / "seen.txt"
            rules = load_rules(rules_path)
            first, first_stats = filter_text("noise\nnoise important\nrepeat\n", rules=rules, session_aware=True, seen_path=seen_path)
            self.assertNotIn("noise\n", first)
            self.assertIn("noise important", first)
            self.assertEqual(first_stats["dropped_lines"], 1)
            second, second_stats = filter_text("repeat\nnoise important\n", rules=rules, session_aware=True, seen_path=seen_path)
            self.assertNotIn("repeat", second)
            self.assertIn("noise important", second)
            self.assertEqual(second_stats["session_suppressed_lines"], 1)

    def test_turboquant_adoption_review_and_smoke_harness(self):
        review = (REPO / "raw/2026-04-25-turboquant-adoption-review.md").read_text(encoding="utf-8")
        concept = (REPO / "concepts/turboquant-kv-cache.md").read_text(encoding="utf-8")
        local_setup = (REPO / "concepts/local-model-setup.md").read_text(encoding="utf-8")
        agent = (REPO / "projects/agents-triage/agents/turboquant-local.md").read_text(encoding="utf-8")
        devices = (REPO / "concepts/devices-inventory.md").read_text(encoding="utf-8")

        self.assertIn("Workflow compliance", review)
        self.assertIn("pattern-reimplementation", review)
        self.assertIn("TheTom/llama-cpp-turboquant", review)
        self.assertIn("quantumaikr/quant.cpp", review)
        self.assertIn("arozanov/turboquant-mlx", review)
        self.assertIn("Q4_K_M GGUF + `K=q8_0`, `V=turbo4`", review)
        self.assertIn("direct `llama-server`", review)

        self.assertIn("2026-04-25 adoption review", concept)
        self.assertIn("scripts/turboquant_smoke.py --json", concept)
        self.assertIn("NO AUTO-INSTALL", concept)
        self.assertIn("not running", devices)
        self.assertIn("Do not auto-install", devices)
        self.assertIn("task-capable peer", devices)
        self.assertIn("same models as M1", devices)
        self.assertIn("M1B should not be treated as worker-only", local_setup)
        self.assertIn("./te bench run --suite framework-smoke", local_setup)
        self.assertIn("./INSTALL.sh --scope project", local_setup)
        self.assertIn("launchctl setenv OLLAMA_KEEP_ALIVE 24h", local_setup)
        self.assertIn("ollama pull qwen3.5:35b", local_setup)
        self.assertIn("wrong llama-server build", agent)

        with tempfile.TemporaryDirectory() as td:
            help_file = Path(td) / "llama-help.txt"
            help_file.write_text("--cache-type-k q8_0 --cache-type-v turbo4\n", encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(REPO / "scripts/turboquant_smoke.py"), "--help-text-file", str(help_file), "--json"],
                cwd=REPO,
                capture_output=True,
                text=True,
                check=True,
            )
            report = json.loads(proc.stdout)
            self.assertTrue(report["cache_flags_supported"])
            self.assertEqual(report["safe_q4km_default"], "-ctk q8_0 -ctv turbo4")

    def test_token_economy_external_adoption_skill_is_project_scoped(self):
        skill_path = REPO / "skills/token-economy-external-adoption/SKILL.md"
        self.assertTrue(skill_path.exists())
        skill = skill_path.read_text(encoding="utf-8")
        start = (REPO / "start.md").read_text(encoding="utf-8")
        onboarding = (REPO / "AGENT_ONBOARDING.md").read_text(encoding="utf-8")
        index = (REPO / "index.md").read_text(encoding="utf-8")
        l1 = (REPO / "L1_index.md").read_text(encoding="utf-8")

        self.assertIn("Default target project comes from the user prompt", start)
        self.assertNotIn("TE repo external adoption", start)
        self.assertNotIn("skills/token-economy-external-adoption/SKILL.md", start)
        self.assertNotIn("project-maintenance only, not a downstream user rule", onboarding)
        self.assertNotIn("skills/token-economy-external-adoption/SKILL", index)
        self.assertNotIn("skills/token-economy-external-adoption", l1)
        self.assertNotIn("finish with verification, a commit, and a clean working tree", onboarding)
        self.assertNotIn("ROADMAP", l1)
        self.assertNotIn("projects/compound-compression-pipeline", l1)

        required = [
            "Token Economy framework maintenance only",
            "not for normal framework users",
            "Source inspection",
            "repo URL",
            "commit SHA or tag",
            "license",
            ".token-economy/external-src",
            "docs, implementation, and tests",
            "public interfaces",
            "failure modes",
            "security-sensitive behavior",
            "repo-local operation",
            "model-agnostic design",
            "measured claims only",
            "cite-only",
            "pattern-reimplementation",
            "native-adapter",
            "direct-code-copy",
            "vendored-subtree",
            "external-dependency",
            "compatible license",
            "clear provenance",
            "Contradiction and overlap check",
            "duplicate existing tools",
            "global agent settings",
            "unsafe secret handling",
            "Framework integration",
            "provenance links from operational dependencies",
            "Verification loop",
            "Add local tests",
            "./te doctor",
            "Do not claim adoption is complete",
            "Documentation",
            "inspected files",
            "residual risk",
        ]
        for needle in required:
            self.assertIn(needle, skill)

    def test_install_dry_run_and_bench(self):
        proc = subprocess.run(["bash", str(REPO / "INSTALL.sh"), "--dry-run"], cwd=REPO, check=True, capture_output=True, text=True)
        self.assertIn("[5/7] agents-triage", proc.stdout)
        self.assertIn("[6/7] context-keeper", proc.stdout)
        self.assertIn("[7/7] semdiff", proc.stdout)
        blocked = subprocess.run(["bash", str(REPO / "INSTALL.sh"), "--scope", "user", "--dry-run"], cwd=REPO, capture_output=True, text=True)
        self.assertNotEqual(blocked.returncode, 0)
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                main(["start", "--scope", "user"])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(main(["bench", "run", "--suite", "framework-smoke"]), 0)
        self.assertTrue(json.loads(buf.getvalue())["ok"])

    def test_downstream_runtime_subset_installs_without_framework_projects(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            files = [
                ".gitignore",
                "AGENTS.md",
                "CLAUDE.md",
                "GEMINI.md",
                "INSTALL.sh",
                "L0_rules.md",
                "L1_index.md",
                "LICENSE",
                "index.md",
                "models.yaml",
                "schema.md",
                "start.md",
                "te",
                "token-economy.yaml",
            ]
            dirs = [
                "token_economy",
                "adapters",
                "hooks",
                "prompts",
                "templates",
                "skills/caveman-ultra",
                "skills/context-refresh",
                "skills/personal-assistant",
                "skills/plan-first-execute",
                "skills/subagent-orchestrator",
                "skills/verification-before-completion",
                "skills/wiki-retrieve",
                "skills/wiki-write",
            ]
            for rel in files:
                target = root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(REPO / rel, target)
            for rel in dirs:
                shutil.copytree(REPO / rel, root / rel)

            subprocess.run(["bash", str(root / "INSTALL.sh"), "--scope", "project", "--agent", "auto"], cwd=root, check=True, capture_output=True, text=True)
            doctor = subprocess.run([str(root / "te"), "doctor"], cwd=root, check=True, capture_output=True, text=True)
            hooks = subprocess.run([str(root / "te"), "hooks", "doctor"], cwd=root, check=True, capture_output=True, text=True)

            self.assertTrue(json.loads(doctor.stdout)["ok"])
            self.assertTrue(json.loads(hooks.stdout)["ok"])
            self.assertFalse((root / "ROADMAP.md").exists())
            self.assertFalse((root / "projects/compound-compression-pipeline").exists())
            self.assertFalse((root / "skills/token-economy-external-adoption").exists())

    def test_local_model_installers_cover_triage_context_and_semdiff(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            shutil.copytree(REPO / "projects/agents-triage", root / "projects/agents-triage")
            shutil.copytree(REPO / "projects/context-keeper", root / "projects/context-keeper")
            shutil.copytree(REPO / "projects/semdiff", root / "projects/semdiff")
            (root / ".claude").mkdir()
            (root / ".claude/settings.json").write_text(
                json.dumps({"hooks": {"UserPromptSubmit": [{"matcher": "existing", "hooks": [{"type": "command", "command": "echo keep"}]}]}}),
                encoding="utf-8",
            )

            subprocess.run(["bash", str(root / "projects/agents-triage/install.sh"), "--project"], cwd=root, check=True, capture_output=True, text=True)
            subprocess.run(["bash", str(root / "projects/context-keeper/install.sh"), "--project"], cwd=root, check=True, capture_output=True, text=True)
            semdiff = subprocess.run(["bash", str(root / "projects/semdiff/install.sh"), "--dry-run"], cwd=root, check=True, capture_output=True, text=True)

            self.assertTrue((root / ".claude/agents/kaggle-feeder.md").exists())
            self.assertTrue((root / ".claude/skills/context-keeper").is_symlink())

            settings = json.loads((root / ".claude/settings.json").read_text(encoding="utf-8"))
            user_submit = settings["hooks"]["UserPromptSubmit"]
            precompact = settings["hooks"]["PreCompact"]
            self.assertTrue(any(rule["matcher"] == "existing" for rule in user_submit))
            self.assertTrue(any("bash" in hook["command"] and "agents-triage/hook.sh" in hook["command"] for rule in user_submit for hook in rule["hooks"]))
            self.assertTrue(any(hook["command"] == "bash ./.claude/skills/context-keeper/hook.sh" for rule in precompact for hook in rule["hooks"]))
            self.assertIn("claude plugin install", semdiff.stdout)
            self.assertIn("claude mcp add semdiff", semdiff.stdout)

    def test_docs_audit_targets_startup_surface_only(self):
        rows = docs_audit(REPO)
        paths = {row["path"] for row in rows}
        self.assertIn("start.md", paths)
        self.assertIn("L1_index.md", paths)
        self.assertNotIn("README.md", paths)
        self.assertTrue(all(row["recommendation"] == "startup-safe" for row in rows if row["status"] == "lean"))
        self.assertTrue((REPO / "prompts/subagents/repo-maintainer.prompt.md").exists())
        self.assertTrue((REPO / "prompts/subagents/lifecycle.prompt.md").exists())
        self.assertTrue((REPO / "prompts/summ.md").exists())
        self.assertTrue((REPO / "prompts/summ-experiments.md").exists())
        self.assertFalse((REPO / "prompts/summ-codex-manual.md").exists(),
            "summ-codex-manual.md should be archived under L4_archive/")
        self.assertTrue((REPO / "L4_archive/2026-04-24-summ-codex-manual.md").exists())
        self.assertTrue((REPO / "prompts/manual-summ-document-and-handoff.md").exists())
        self.assertTrue((REPO / "prompts/manual-fresh-session-from-handoff.md").exists())
        self.assertTrue((REPO / "prompts/complete-migrate-export.md").exists())
        self.assertTrue((REPO / "prompts/complete-migrate-import.md").exists())
        legacy_export = "manual-" + "full-summ.md"
        legacy_import = "manual-" + "import-full-summ.md"
        self.assertFalse((REPO / "prompts" / legacy_export).exists())
        self.assertFalse((REPO / "prompts" / legacy_import).exists())
        self.assertTrue((REPO / "templates/import-manifest.template.md").exists())
        self.assertTrue((REPO / "concepts/superpowers-skills.md").exists())
        self.assertTrue((REPO / "skills/verification-before-completion/SKILL.md").exists())
        self.assertTrue((REPO / "prompts/subagents/wiki-documenter.prompt.md").exists())
        self.assertTrue((REPO / "projects/context-keeper/SKILL.md").exists())
        self.assertTrue((REPO / "projects/context-keeper/install.sh").exists())
        self.assertTrue((REPO / "projects/context-keeper/hook.sh").exists())
        self.assertTrue((REPO / "projects/semdiff/install.sh").exists())
        lifecycle = (REPO / "prompts/subagents/lifecycle.prompt.md").read_text(encoding="utf-8")
        self.assertIn("Close a subagent only", lifecycle)
        self.assertIn("result packet has been read", lifecycle)
        self.assertIn("wiki-documenter", (REPO / "skills/context-refresh/SKILL.md").read_text(encoding="utf-8"))
        self.assertIn("kaggle-feeder", (REPO / "projects/agents-triage/SKILL.md").read_text(encoding="utf-8"))
        caveman = (REPO / "skills/caveman-ultra/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Do not add softeners", caveman)
        self.assertIn("explicitly asks for normal prose", caveman)
        self.assertNotIn("Auto-soften", caveman)
        superpowers = (REPO / "concepts/superpowers-skills.md").read_text(encoding="utf-8")
        self.assertIn("mandatory skill checks before action", superpowers)
        self.assertIn("Verification claims need fresh evidence", superpowers)
        verify_skill = (REPO / "skills/verification-before-completion/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("evidence before claims", verify_skill)
        self.assertIn("If verification is impossible", verify_skill)
        summ = (REPO / "prompts/summ.md").read_text(encoding="utf-8")
        self.assertIn("only `start.md` plus the handoff", summ)
        self.assertIn("codex-fresh-thread", summ)
        self.assertIn("manual-summ-document-and-handoff", summ)
        self.assertIn("clear or bypass old context", summ)
        self.assertIn("do not claim same-thread clearing is solved", summ)
        self.assertIn("session_handoff.md", summ)
        self.assertNotIn("Stop new task work immediately", summ)
        self.assertNotIn("FRESH CONTEXT PACKET READY - STOP HERE", summ)
        self.assertNotIn("Do not assume you can execute host slash commands", summ)
        old_manual = (REPO / "prompts/manual-summ-document-and-handoff.md").read_text(encoding="utf-8")
        self.assertIn("session_handoff.md", old_manual)
        self.assertIn("wiki-documenter", old_manual)
        self.assertIn("cheap/smaller-model", old_manual)
        self.assertIn("lint-handoff session_handoff.md", old_manual)
        self.assertNotIn("FRESH CONTEXT PACKET READY - STOP HERE", old_manual)
        self.assertNotIn("If durable wiki memory exists", old_manual)
        fresh_manual = (REPO / "prompts/manual-fresh-session-from-handoff.md").read_text(encoding="utf-8")
        self.assertIn("Read only `start.md` and `session_handoff.md`", fresh_manual)
        self.assertIn("retrieval is needed", fresh_manual)
        self.assertIn("Start in plan mode", fresh_manual)
        export_prompt = (REPO / "prompts/complete-migrate-export.md").read_text(encoding="utf-8")
        self.assertIn("[project-name]_complete_migrate_export.md", export_prompt)
        self.assertIn("Source Location Index", export_prompt)
        self.assertIn("Transfer Manifest", export_prompt)
        self.assertIn("Obsidian/wiki pages", export_prompt)
        self.assertIn("Raw API keys/secrets are explicitly authorized", export_prompt)
        self.assertIn("context rot", export_prompt)
        self.assertIn("Think carefully, step by step, and devise a plan for the following, then execute the plan.", export_prompt)
        self.assertIn("Write `[project-name]_complete_migrate_export.md`", export_prompt)
        self.assertIn("Use smaller/lightweight subagents", export_prompt)
        self.assertIn("prompts/subagents/lifecycle.prompt.md", export_prompt)
        self.assertIn("compact result packet", export_prompt)
        self.assertIn("Do not delegate final synthesis", export_prompt)
        self.assertIn("Provenance", export_prompt)
        self.assertIn("complete original-wiki coverage map", export_prompt)
        self.assertIn("target Token Economy category", export_prompt)
        self.assertIn("`secret-local`", export_prompt)
        import_prompt = (REPO / "prompts/complete-migrate-import.md").read_text(encoding="utf-8")
        self.assertIn("Complete-migrate export file", import_prompt)
        self.assertIn("the uploaded file", import_prompt)
        self.assertIn("self-contained", import_prompt)
        self.assertIn("Use the export's `Source Location Index` and `Transfer Manifest`", import_prompt)
        self.assertIn("Use smaller/lightweight subagents", import_prompt)
        self.assertIn("Safe file copying", import_prompt)
        self.assertIn("Old-path reference search", import_prompt)
        self.assertIn("git clone --depth 1 --filter=blob:none --sparse https://github.com/SaarShai/token-economy.git .", import_prompt)
        self.assertIn("git sparse-checkout set --no-cone", import_prompt)
        self.assertIn("rm -rf .git", import_prompt)
        self.assertIn("git init", import_prompt)
        # Structural check: verify the sparse-checkout list covers the
        # verified-to-work components, not the exact glob form. Patterns
        # like /path/*, /path/**, or /path/ are all equivalent here.
        sparse_block = import_prompt.split("git sparse-checkout set --no-cone", 1)[1].split("rm -rf .git", 1)[0]
        required_under_sparse = [
            "token_economy",
            "projects/compound-compression-pipeline",
            "projects/context-keeper",
            "projects/semdiff",
            "stable",
        ]
        for needle in required_under_sparse:
            self.assertIn(needle, sparse_block,
                f"sparse-checkout in complete-migrate-import.md must cover {needle}")
        self.assertNotIn("ROADMAP", import_prompt)
        self.assertIn("./INSTALL.sh --dry-run", import_prompt)
        self.assertIn("./INSTALL.sh --scope project --agent auto", import_prompt)
        self.assertIn("./stable/INSTALL.sh", import_prompt)
        self.assertIn("start.md", import_prompt)
        self.assertIn("token-economy.yaml", import_prompt)
        self.assertIn("Do not overwrite Token Economy framework paths", import_prompt)
        self.assertIn("raw/imported-source/", import_prompt)
        self.assertIn("old absolute paths to the new working folder", import_prompt)
        self.assertIn("sealed provenance", import_prompt)
        self.assertIn("Put source summaries and imported source evidence under `raw/`", import_prompt)
        self.assertIn("Put verified durable facts under `L2_facts/`", import_prompt)
        self.assertIn("wiki transplant", import_prompt)
        self.assertIn("raw/YYYY-MM-DD-import-manifest.md", import_prompt)
        self.assertIn("cover every original wiki item", import_prompt)
        self.assertIn("source evidence only", import_prompt)
        self.assertIn("Never leave synthesized pages", import_prompt)
        self.assertIn("./te wiki import-audit --manifest raw/YYYY-MM-DD-import-manifest.md", import_prompt)
        self.assertIn("Create or update `README.md` for the imported target project", import_prompt)
        self.assertIn("The MCP install step is required, not optional", import_prompt)
        self.assertIn("ComCom", import_prompt)
        self.assertIn("semdiff", import_prompt)
        self.assertIn("context-keeper", import_prompt)
        self.assertNotIn("commit the uploaded file", import_prompt)
        self.assertNotIn("git status --short", import_prompt)
        self.assertIn("./te wiki lint --strict", import_prompt)
        self.assertIn("./te doctor", import_prompt)
        self.assertIn("Run `rg` checks for the old project root and old source-wiki root", import_prompt)
        self.assertIn("remaining old-path hits are provenance-only", import_prompt)
        self.assertIn("copied/adapted instructions point to the new working folder", import_prompt)
        self.assertEqual(host_context_controls("codex")["clear"], "/clear")
        self.assertEqual(host_context_controls("codex")["strategy"], "fresh-successor-workaround-current-clear-unsolved")
        self.assertIn("experimental", " ".join(host_context_controls("codex")["notes"]))
        self.assertEqual(host_context_controls("claude")["strategy"], "native-clear-or-compact")
        self.assertEqual(host_context_controls("gemini")["compact"], "/compress")
        self.assertIn("universal_protocol", host_context_controls("generic"))
        self.assertIn("completion_test", host_context_controls("codex"))
        self.assertIn("codex-fresh-thread", fresh_launch_commands("codex", REPO, REPO / "handoff.md")["preferred"])
        plan = codex_fresh_thread_plan(REPO, REPO / "handoff.md")
        self.assertEqual(plan["model"], default_codex_fresh_model())
        self.assertEqual(plan["persistence"], "persistent")
        self.assertIn("thread/started", " ".join(plan["success_test"]))
        self.assertIn("turns: []", " ".join(plan["success_test"]))

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(main(["context", "host-controls", "--agent", "claude"]), 0)
        self.assertEqual(json.loads(buf.getvalue())["clear"], "/clear")

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(main(["context", "fresh-command", "--agent", "codex", "--handoff", "handoff.md"]), 0)
        self.assertIn("fresh successor", json.loads(buf.getvalue())["note"])

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(main(["context", "codex-fresh-thread", "--handoff", "handoff.md", "--model", "gpt-5.3-codex-spark"]), 0)
        self.assertEqual(json.loads(buf.getvalue())["mode"], "app-server-fresh-thread")
        self.assertIn("thread_persistent", (REPO / "prompts/summ.md").read_text(encoding="utf-8"))
        self.assertIn("clean continuation", (REPO / "README.md").read_text(encoding="utf-8"))

    def test_agent_detection_ignores_provider_api_keys(self):
        original = os.environ.copy()
        try:
            os.environ.clear()
            os.environ["ANTHROPIC_API_KEY"] = "secret"
            self.assertEqual(detect_agent(), "codex")
            os.environ["CLAUDE_CODE_SESSION"] = "1"
            self.assertEqual(detect_agent(), "claude")
        finally:
            os.environ.clear()
            os.environ.update(original)


if __name__ == "__main__":
    unittest.main()
