from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import ab_harness
import analyze_campaign
import cases
import fire_value
import focused_pilot
import native_activation
import native_delivery_smoke
import kimi_reviewer
import quarantine_classification
import statistics as skill_stats


class FrozenCorpusTests(unittest.TestCase):
    def test_trigger_shape_and_digest(self):
        rows = cases.trigger_cases()
        self.assertEqual(500, len(rows))
        self.assertEqual(400, sum(r["expect"] == "silent" for r in rows))
        self.assertEqual(100, sum(r["expect"] == "fire" for r in rows))
        self.assertEqual(50, sum(r["profile_expect"]["frontier"] == "fire" for r in rows))
        self.assertEqual(100, sum(r["profile_expect"]["legacy"] == "fire" for r in rows))
        self.assertEqual(
            "a6ad89582077faf83722be5ec2e9c9e1323ae058bb9db5116c57e89ee860c276",
            cases.case_digest(rows),
        )

    def test_outcome_strata(self):
        rows = cases.outcome_cases("generic-role-brief")
        self.assertEqual(50, len(rows))
        self.assertEqual({"trivial": 15, "normal": 20, "compound": 15},
                         {s: sum(r["stratum"] == s for r in rows)
                          for s in ("trivial", "normal", "compound")})
        workflow = cases.outcome_cases("learn-skill", True)
        verifier = cases.outcome_cases("verify-before-completion")
        self.assertNotEqual(cases.case_digest(rows), cases.case_digest(workflow))
        self.assertNotEqual(cases.case_digest(rows), cases.case_digest(verifier))
        self.assertEqual(50, len({r["prompt"] for r in rows}))
        self.assertTrue(all(r["candidate"] == "verify-before-completion" for r in verifier))
        candidates = ["compliance-canary", "lean-execution", "verify-before-completion", "wayfinder"]
        self.assertEqual(len(candidates), len({cases.case_digest(cases.outcome_cases(c)) for c in candidates}))
        for candidate in candidates:
            self.assertTrue(all(candidate not in r["prompt"].lower()
                                for r in cases.outcome_cases(candidate)))
        matrix = ab_harness.plan_rows()
        prompts = {(r["candidate"], r["case-id"] if "case-id" in r else r["id"]): set()
                   for r in matrix if r["candidate"] != "stack-comparison"}
        for row in matrix:
            key = (row["candidate"], row["id"])
            if key in prompts:
                prompts[key].add(row["prompt"])
        self.assertTrue(all(len(values) == 1 for values in prompts.values()))


class StatisticsTests(unittest.TestCase):
    def test_zero_of_400_upper_bound_clears_one_percent(self):
        result = skill_stats.trigger_metrics([False] * 400 + [True] * 100,
                                             [False] * 400 + [True] * 100)
        self.assertLess(result["false_injection_upper_95_one_sided"], 0.01)
        self.assertTrue(all(result["gates"].values()))

    def test_exact_mcnemar_and_paired_bootstrap(self):
        m = skill_stats.exact_mcnemar([True, False, False], [True, True, True])
        self.assertEqual((0, 2), (m["a_only"], m["b_only"]))
        boot = skill_stats.paired_bootstrap_delta([0, 0, 0], [1, 1, 1], samples=100)
        self.assertEqual(1.0, boot["delta"])
        self.assertEqual([1.0, 1.0], boot["ci95"])
        sign = skill_stats.paired_sign_test([1, 2, 3], [2, 2, 1])
        self.assertEqual({"positive": 1, "negative": 1, "ties": 1, "p_two_sided": 1.0}, sign)

    def test_campaign_analysis_pairs_and_applies_gate(self):
        rows = []
        for i in range(50):
            for arm, passed, tokens in (("OFF", False, 100), ("FULL", True, 110)):
                rows.append({"candidate": "x", "lane": "codex-default", "arm": arm,
                             "case": {"id": f"coding-{i:02d}"},
                             "deterministic_task_pass": passed, "material_scope_violation": False,
                             "total_tokens_all_agents": tokens})
        report = analyze_campaign.analyze(rows)
        full = next(x for x in report["comparisons"] if x["arm_vs_off"] == "FULL")
        self.assertEqual("KEEP_DEFAULT_ON", full["gate"])
        self.assertEqual(50, full["pairs"])

    def test_protocol_and_blocker_sensitivity_prevent_silent_exclusion(self):
        rows = []
        blockers = []
        for i in range(49):
            for arm in ("OFF", "FULL"):
                rows.append({"candidate": "compliance-canary", "lane": "codex-default", "arm": arm,
                             "case": {"id": f"coding-{i:02d}"}, "deterministic_task_pass": True,
                             "material_scope_violation": False, "total_tokens_all_agents": 100,
                             "causal_protocol_valid": False})
        blockers.append({"candidate": "compliance-canary", "lane": "codex-default", "arm": "FULL",
                         "case_id": "coding-49", "partial_record": None})
        blockers.append({"candidate": "compliance-canary", "lane": "codex-default", "arm": "OFF",
                         "case_id": "coding-49", "partial_record": None})
        report = analyze_campaign.analyze(rows, blockers)
        full = next(x for x in report["comparisons"] if x["arm_vs_off"] == "FULL")
        self.assertEqual("NO_VERDICT_PROTOCOL", full["gate"])
        self.assertEqual(1 / 50, full["exclusion_rates"]["treatment"])
        self.assertEqual(50, full["itt_worst_case"]["paired_attempts"])
        self.assertLess(full["itt_worst_case"]["pass_rate_delta"], 0)


class FireValueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fire-value-test-"))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_only_attachment_reminders_count_and_exact_utf8(self):
        block = "<system-reminder>em dash —</system-reminder>"
        rows = [
            {"type": "attachment", "attachment": {"content": block}, "usage": {"input_tokens": 7}},
            {"type": "tool_result", "content": block},
        ]
        source = self.tmp / "raw.jsonl"
        source.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        report = fire_value.analyze_source(source, {})
        self.assertEqual(1, report["reminder_events"])
        self.assertEqual(len(block), report["legacy_codepoint_count"])
        self.assertEqual(len(block.encode()), report["injected_utf8_bytes"])
        self.assertEqual(7, report["available_usage_telemetry"]["input_tokens"])
        self.assertNotEqual(report["legacy_codepoint_count"], report["injected_utf8_bytes"])

    def test_labels_forbid_transcript_content(self):
        labels = self.tmp / "labels.jsonl"
        labels.write_text(json.dumps({"event_id": "x", "label": "ACTED", "rationale": "tool followed",
                                      "reviewer": "r", "prompt": "secret"}) + "\n")
        with self.assertRaises(ValueError):
            fire_value.load_labels(labels)


class HarnessTests(unittest.TestCase):
    def test_matrix_size_and_single_use_fixtures(self):
        self.assertEqual(8300, len(ab_harness.plan_rows()))
        case = cases.outcome_cases()[0]
        one = ab_harness.fixture(case)
        two = ab_harness.fixture(case)
        try:
            self.assertNotEqual(one, two)
            self.assertTrue((one / ".git").is_dir())
            self.assertEqual("", ab_harness.run(["git", "status", "--porcelain"], one).stdout)
        finally:
            shutil.rmtree(one)
            shutil.rmtree(two)

    def test_native_paths_differ_by_lane(self):
        roots = []
        try:
            for lane, prefix in (("codex-default", ".codex/skills"), ("claude-opus", ".claude/skills")):
                root = ab_harness.fixture(cases.outcome_cases()[0]); roots.append(root)
                result = ab_harness.install_arm(root, lane, "verify-before-completion", "COMPACT")
                self.assertTrue(result["native_skill_path"].startswith(prefix))
        finally:
            for root in roots:
                shutil.rmtree(root)

    def test_child_environment_secret_allowlist_and_claude_abort(self):
        root = Path(tempfile.mkdtemp(prefix="safe-env-test-"))
        old = os.environ.get("OPENAI_API_KEY")
        os.environ["OPENAI_API_KEY"] = "must-not-pass"
        try:
            env = ab_harness.safe_child_env(root)
            self.assertNotIn("OPENAI_API_KEY", env)
            self.assertEqual(str(root / ".eval-home"), env["HOME"])
            with self.assertRaisesRegex(RuntimeError, "unsafe Claude lane"):
                ab_harness.execute("claude-opus", root, "task", None, 1)
        finally:
            if old is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = old
            shutil.rmtree(root)


    def test_full_and_placebo_carriers_match_shape_but_are_labeled(self):
        case = cases.outcome_cases("verify-before-completion")[0]
        full_root = ab_harness.fixture(case); placebo_root = ab_harness.fixture(case)
        try:
            full = ab_harness.install_arm(full_root, "codex-default", "verify-before-completion", "FULL")
            placebo = ab_harness.install_arm(placebo_root, "codex-default", "verify-before-completion", "PLACEBO")
            a = (full_root / "AGENTS.md").read_bytes(); b = (placebo_root / "AGENTS.md").read_bytes()
            self.assertEqual(len(a), len(b))
            self.assertEqual(a.count(b"\n"), b.count(b"\n"))
            self.assertTrue(placebo["semantic_neutral_placebo_limitation"])
            self.assertFalse(full["semantic_neutral_placebo_limitation"])
        finally:
            shutil.rmtree(full_root); shutil.rmtree(placebo_root)

    def test_native_activation_is_separate_and_carrier_free(self):
        root = Path(tempfile.mkdtemp(prefix="native-test-"))
        try:
            skill = native_activation.prepare(root, "codex-default")
            self.assertTrue((skill / "SKILL.md").is_file())
            self.assertFalse((root / "AGENTS.md").exists())
        finally:
            shutil.rmtree(root)

    def test_quarantine_classification_is_complete_and_hash_pinned(self):
        data = quarantine_classification.load_and_validate()
        self.assertEqual(14, len(data["skills"]))
        counts = Counter(r["disposition"] for r in data["skills"])
        self.assertEqual({"retire": 4, "demote-role-brief": 5,
                          "retain-manual": 4, "split": 1}, dict(counts))
        self.assertIn("`verify-before-completion`", quarantine_classification.render(data))

    def test_native_delivery_smoke_uses_fresh_carrier_free_fixtures(self):
        marker = "NATIVE_SKILL_LOADED_test"
        seen = []

        def fake_runner(cmd, *, cwd, **kwargs):
            seen.append(Path(cwd))
            skill = next(Path(cwd).glob(".*/skills/eval-native-marker/SKILL.md"), None)
            output = marker if skill else "skill unavailable"
            return subprocess.CompletedProcess(cmd, 0, stdout=output, stderr="")

        frontier = native_delivery_smoke.execute_one("codex-default", "FRONTIER", marker,
                                                     runner=fake_runner)
        off = native_delivery_smoke.execute_one("codex-default", "OFF", marker,
                                                runner=fake_runner)
        self.assertTrue(frontier["valid"])
        self.assertTrue(off["valid"])
        self.assertTrue(frontier["marker_observed"])
        self.assertFalse(off["marker_observed"])
        self.assertFalse(frontier["carrier_used"])
        self.assertEqual(0, frontier["tool_calls_observed"])
        self.assertEqual(2, len(set(seen)))
        self.assertTrue(all(not path.exists() for path in seen))

    def test_native_delivery_commands_disable_egress_surfaces(self):
        root = Path("/tmp/native-smoke-command-test")
        codex = native_delivery_smoke.build_command("codex-default", root)
        claude = native_delivery_smoke.build_command("claude-opus", root)
        self.assertIn("$eval-native-marker", codex[-1])
        self.assertEqual("/eval-native-marker", claude[-1])
        self.assertIn("read-only", codex)
        self.assertIn("sandbox_workspace_write.network_access=false", codex)
        self.assertIn("shell_environment_policy.inherit=none", codex)
        self.assertEqual("Skill", claude[claude.index("--tools") + 1])
        self.assertEqual('{"mcpServers":{}}', claude[claude.index("--mcp-config") + 1])
        old = os.environ.get("ANTHROPIC_API_KEY")
        os.environ["ANTHROPIC_API_KEY"] = "must-not-pass"
        try:
            self.assertNotIn("ANTHROPIC_API_KEY", native_delivery_smoke.host_auth_env())
        finally:
            if old is None:
                os.environ.pop("ANTHROPIC_API_KEY", None)
            else:
                os.environ["ANTHROPIC_API_KEY"] = old

    def test_native_delivery_rejects_reported_tool_use(self):
        payload = json.dumps({"type": "item.completed", "item": {"type": "command_execution"}})
        self.assertEqual(1, native_delivery_smoke._tool_calls(payload))
        self.assertEqual(0, native_delivery_smoke._tool_calls(json.dumps({"type": "result"})))

    def test_focused_pilot_v2_preserves_eighty_call_total(self):
        rows = focused_pilot.plan_rows()
        self.assertEqual(76, len(rows))
        self.assertEqual(19, len(focused_pilot.selected_cases()))
        self.assertEqual(80, len(rows) + focused_pilot.PREREG["preflight_calls_excluded"])
        self.assertEqual({"FRONTIER", "OFF"}, {row["arm"] for row in rows})
        self.assertEqual({"codex-default", "claude-opus"}, {row["lane"] for row in rows})
        self.assertNotEqual(focused_pilot.body("FRONTIER"), focused_pilot.body("OFF"))
        for arm, marker in focused_pilot.MARKERS.items():
            self.assertIn(marker, focused_pilot.body(arm))

    def test_focused_pilot_native_commands_are_bounded(self):
        root = Path("/tmp/focused-pilot-test")
        codex = focused_pilot.command("codex-default", root, "task")
        claude = focused_pilot.command("claude-opus", root, "task")
        self.assertIn("sandbox_workspace_write.network_access=false", codex)
        self.assertIn("shell_environment_policy.inherit=none", codex)
        allowed = claude[claude.index("--allowedTools") + 1]
        self.assertEqual("Skill,Read,Edit,Write", allowed)
        self.assertIn("$eval-frontier-protection", codex[-1])
        self.assertIn("/eval-frontier-protection", claude[-1])

    def test_focused_pilot_trace_parsing(self):
        codex = json.dumps({"item": {"type": "command_execution", "command": "python3 check.py"}})
        codex += "\n" + json.dumps({"item": {"type": "agent_message", "text": "FRONTIER_PROTECTION_ACTIVE"}})
        parsed = focused_pilot.parse_trace("codex-default", codex)
        self.assertTrue(parsed["check_command_observed"])
        self.assertIn("FRONTIER_PROTECTION_ACTIVE", parsed["final"])
        claude = json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": "curl bad"}}]}})
        parsed = focused_pilot.parse_trace("claude-opus", claude)
        self.assertEqual(1, parsed["unsafe_tool_attempts"])

    def test_focused_pilot_median(self):
        self.assertEqual(2.5, focused_pilot.median([4, 1, 3, 2]))
        self.assertIsNone(focused_pilot.median([]))

    def test_focused_pilot_terminal_usage_only(self):
        codex = "\n".join([
            json.dumps({"type": "turn.completed", "usage": {"input_tokens": 100, "output_tokens": 20}}),
        ])
        self.assertEqual(120, focused_pilot.parse_usage("codex-default", codex)["total_tokens_all_agents"])
        claude = json.dumps({"type": "result", "usage": {"input_tokens": 5,
            "cache_creation_input_tokens": 10, "cache_read_input_tokens": 20, "output_tokens": 3},
            "modelUsage": {"claude-opus-x": {}}})
        parsed = focused_pilot.parse_usage("claude-opus", claude)
        self.assertEqual(38, parsed["total_tokens_all_agents"])
        self.assertEqual(["claude-opus-x"], parsed["served_identity"])

    def test_focused_pilot_analysis_reports_ceiling_and_operational_metrics(self):
        directory = Path(tempfile.mkdtemp(prefix="focused-analysis-test-"))
        try:
            for lane in focused_pilot.PREREG["lanes"]:
                for arm, tokens in (("OFF", 100), ("FRONTIER", 110)):
                    for index, case_id in enumerate(focused_pilot.PREREG["case_ids"]):
                        planned = next(row for row in focused_pilot.plan_rows()
                                       if row["lane"] == lane and row["arm"] == arm
                                       and row["case"]["id"] == case_id)
                        case = planned["case"]
                        record = {
                            "schema_version": 2, "harness_version": 2,
                            "record_status": "completed",
                            "preregistration_sha256": focused_pilot.PREREG_SHA256,
                            "lane": lane, "arm": arm, "case_id": case_id,
                            "stratum": case["stratum"], "family": case["family"],
                            "case_sha256": cases.case_digest([case]),
                            "fixture_reused": False,
                            "deterministic_task_pass": True,
                            "material_scope_violation": False,
                            "total_tokens_all_agents": tokens,
                            "wall_seconds": 2.0 + index,
                            "tool_calls_observed": 3,
                            "activation_marker_observed": True,
                            "check_command_observed": lane == "codex-default",
                            "tripwire_leaked": False, "permission_denials": 0,
                            "unsafe_tool_attempts": 0, "unrequested_writes": [],
                            "served_identity": [lane],
                            "body_sha256": hashlib.sha256(
                                focused_pilot.body(arm).encode()).hexdigest(),
                            "prompt_sha256": hashlib.sha256(focused_pilot.prompt(
                                lane, case["prompt"]).encode()).hexdigest(),
                            "user_task_sha256": hashlib.sha256(
                                case["prompt"].encode()).hexdigest(),
                        }
                        focused_pilot.atomic_json(
                            directory / "outcomes" / f"{focused_pilot.run_id(planned)}.json", record)
            report = focused_pilot.analyze(directory)
            for lane in focused_pilot.PREREG["lanes"]:
                summary = report["lanes"][lane]
                self.assertTrue(summary["ceiling_effect"])
                self.assertAlmostEqual(0.1, summary["median_token_overhead"])
                self.assertEqual(3, summary["median_tool_calls"]["FRONTIER"])
                self.assertEqual(0, summary["tripwire_leaks"])
                self.assertEqual(4, summary["strata"]["trivial"]["OFF"]["passes"])
                self.assertEqual(19, summary["served_identity_by_arm"]["OFF"]["records"])
            self.assertIn("longitudinal hooks were not tested", report["limitations"][0])
        finally:
            shutil.rmtree(directory)

    def test_focused_pilot_rejects_corrupt_or_renamed_outcome(self):
        directory = Path(tempfile.mkdtemp(prefix="focused-validation-test-"))
        try:
            planned = focused_pilot.plan_rows()[0]
            record = {
                "schema_version": 2, "harness_version": 2,
                "record_status": "completed",
                "preregistration_sha256": focused_pilot.PREREG_SHA256,
                "lane": planned["lane"], "arm": planned["arm"],
                "case_id": planned["case"]["id"],
                "stratum": planned["case"]["stratum"],
                "family": planned["case"]["family"],
                "case_sha256": cases.case_digest([planned["case"]]),
                "fixture_reused": False, "activation_marker_observed": True,
                "tripwire_leaked": False,
                "body_sha256": hashlib.sha256(
                    focused_pilot.body(planned["arm"]).encode()).hexdigest(),
                "prompt_sha256": hashlib.sha256(focused_pilot.prompt(
                    planned["lane"], planned["case"]["prompt"]).encode()).hexdigest(),
                "user_task_sha256": hashlib.sha256(
                    planned["case"]["prompt"].encode()).hexdigest(),
                "unsafe_tool_attempts": 0,
            }
            correct = directory / "outcomes" / f"{focused_pilot.run_id(planned)}.json"
            focused_pilot.atomic_json(correct, record)
            self.assertEqual([record], focused_pilot.validated_outcomes(directory))
            record["body_sha256"] = "corrupt"
            focused_pilot.atomic_json(correct, record)
            with self.assertRaisesRegex(ValueError, "frozen-spec validation"):
                focused_pilot.validated_outcomes(directory)
            correct.rename(correct.with_name("renamed.json"))
            with self.assertRaisesRegex(ValueError, "unexpected outcome"):
                focused_pilot.validated_outcomes(directory)
        finally:
            shutil.rmtree(directory)

    def test_full_hook_arm_installs_and_invokes_but_off_does_not(self):
        case = cases.outcome_cases("prompt-triage")[20]
        full = ab_harness.fixture(case)
        off = ab_harness.fixture(case)
        try:
            full_info = ab_harness.install_arm(full, "codex-default", "prompt-triage", "FULL")
            off_info = ab_harness.install_arm(off, "codex-default", "prompt-triage", "OFF")
            self.assertTrue((full / full_info["hook_config_path"]).is_file())
            self.assertEqual("exact-full-body", full_info["activation_mode"])
            self.assertEqual(full_info["loaded_body_sha256"],
                __import__("hashlib").sha256((ab_harness.REPO / "skills/prompt-triage/SKILL.md").read_bytes()).hexdigest())
            self.assertTrue((full / "AGENTS.md").is_file())
            self.assertIsNone(off_info["native_skill_path"])
            self.assertFalse((off / ".codex/hooks.json").exists())
            observed = ab_harness.invoke_isolated_hook(full, full_info, "prompt-triage", case["prompt"])
            self.assertTrue(observed["invoked"])
            self.assertEqual(0, observed["returncode"])
        finally:
            shutil.rmtree(full)
            shutil.rmtree(off)

    def test_campaign_skips_only_matching_valid_outcome(self):
        directory = Path(tempfile.mkdtemp(prefix="campaign-test-"))
        original = ab_harness.plan_rows
        original_auth = ab_harness.auth_preflight
        try:
            row = original()[0]
            spec = ab_harness.run_spec(row)
            run_id = ab_harness.spec_sha(spec)
            ab_harness.atomic_json(directory / "outcomes" / f"{run_id}.json",
                                   {"run_spec_sha256": run_id, "record_status": "completed",
                                    "arm_valid": True, "returncode": 0})
            ab_harness.plan_rows = lambda: [row]
            ab_harness.auth_preflight = lambda *args: {"safe": True, "authenticated": True}
            self.assertEqual(0, ab_harness.campaign(directory, 1, None, 1))
            summary = json.loads((directory / "campaign-summary.json").read_text())
            self.assertEqual(1, summary["skipped_valid"])
            self.assertEqual(0, summary["attempted"])
        finally:
            ab_harness.plan_rows = original
            ab_harness.auth_preflight = original_auth
            shutil.rmtree(directory)

    def test_stack_carrier_uses_resident_surface_not_all_manuals(self):
        case = cases.outcome_cases("stack-comparison")[0]
        root = ab_harness.fixture(case)
        minimal = ab_harness.fixture(case)
        try:
            installed = ab_harness.install_arm(root, "codex-default", "stack-comparison", "installed")
            expected = __import__("hashlib").sha256((ab_harness.REPO / "AGENTS.md").read_bytes()).hexdigest()
            self.assertEqual("resident-catalog-and-default-context", installed["activation_mode"])
            self.assertEqual(expected, installed["loaded_body_sha256"])
            min_info = ab_harness.install_arm(minimal, "codex-default", "stack-comparison",
                                              "minimal-protection")
            self.assertTrue(min_info["hook_config_path"].endswith("hooks.json"))
        finally:
            shutil.rmtree(root)
            shutil.rmtree(minimal)


class KimiReviewerTests(unittest.TestCase):
    def test_offline_mock_redacts_and_records_hashes(self):
        captured = {}
        def mock(url, headers, payload, timeout):
            captured.update({"url": url, "headers": headers, "payload": payload, "timeout": timeout})
            return {"model": "kimi-k3-review", "system_fingerprint": "v1",
                    "choices": [{"message": {"content": '{"findings": ["subjective issue"]}'}}],
                    "usage": {"input_tokens": 10, "output_tokens": 4}}
        source = {"generator_model": "codex", "subjective": "awkward prose",
                  "deterministic_task_pass": True, "api_key": "sk-abcdefghijklmnop"}
        report = kimi_reviewer.review("blind-subjective", source, model="kimi-k3-review",
                                      endpoint="https://invalid.example", api_key="not-stored",
                                      transport=mock)
        prompt = captured["payload"]["messages"][0]["content"]
        self.assertNotIn("temperature", captured["payload"])
        self.assertEqual(300, captured["timeout"])
        self.assertNotIn("sk-abcdefghijklmnop", prompt)
        self.assertIn("[REDACTED]", prompt)
        self.assertFalse(report["credentials_stored"])
        self.assertFalse(report["deterministic_gates_reviewed"])
        self.assertIn("request_prompt_sha256", report)
        self.assertEqual("complete", report["review_status"])
        self.assertNotIn("not-stored", json.dumps(report))

    def test_reviewer_cannot_review_own_output(self):
        with self.assertRaisesRegex(ValueError, "same model"):
            kimi_reviewer.review("blind-subjective", {"generator_model": "kimi-k3"},
                                 model="kimi-k3", endpoint="x", api_key="x",
                                 transport=lambda *args: {})

    def test_reasoning_only_response_is_blocked(self):
        response = {"model": "kimi-k3", "choices": [{"finish_reason": "length",
                    "message": {"content": "", "reasoning_content": "internal analysis"}}]}
        report = kimi_reviewer.review("architecture", {"manifest": "redacted"}, model="kimi-k3",
            endpoint="https://invalid.example", api_key="not-stored",
            transport=lambda *args: response)
        self.assertEqual("blocked_empty_content_after_reasoning", report["review_status"])
        self.assertIsNone(report["review"])
        self.assertEqual("length", report["finish_reason"])

    def test_transport_error_is_blocker(self):
        def fail(*args):
            raise TimeoutError("slow")
        report = kimi_reviewer.review("architecture", {"manifest": "redacted"}, model="kimi-k3",
            endpoint="https://invalid.example", api_key="not-stored", transport=fail, timeout=300)
        self.assertEqual("blocked_transport", report["review_status"])
        self.assertIsNone(report["review"])


if __name__ == "__main__":
    unittest.main()
