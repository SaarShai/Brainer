#!/usr/bin/env python3
"""Deterministic tests for native-plugin/project-hook precedence."""
from __future__ import annotations

import importlib.util
import json
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
ROUTER_PATH = REPO / "hooks" / "project_hook_precedence.py"
SPEC = importlib.util.spec_from_file_location("project_hook_precedence", ROUTER_PATH)
assert SPEC and SPEC.loader
router = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(router)


HANDLERS = {
    "UserPromptSubmit": ".claude/skills/compliance-canary/tools/hook.sh",
    "PreCompact": ".claude/skills/context-keeper/tools/hook.sh",
    "SessionEnd": ".claude/skills/context-keeper/tools/archive.sh",
}


def write_executable(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/usr/bin/env bash\nset -eu\n" + body, encoding="utf-8")
    path.chmod(0o755)


def settings_for(project: Path, events: dict[str, str]) -> None:
    hooks: dict[str, list] = {}
    for index, (event, relative) in enumerate(events.items()):
        if index % 2:
            handler = {"type": "command", "command": "bash", "args": [relative]}
        else:
            handler = {"type": "command", "command": f'bash "${{CLAUDE_PROJECT_DIR:-$PWD}}/{relative}"'}
        hooks[event] = [{"matcher": "*", "hooks": [handler]}]
    path = project / ".claude" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"hooks": hooks}), encoding="utf-8")


class PluginHookPrecedenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="plugin-hook-precedence-")
        self.root = Path(self.tmp.name)
        self.project = self.root / "project"
        self.other_cwd = self.root / "elsewhere"
        self.project.mkdir()
        self.other_cwd.mkdir()
        self.plugin_capture = self.root / "plugin.stdin"
        self.plugin_effect = self.root / "plugin.effects"
        self.plugin_cwd = self.root / "plugin.cwd"
        self.plugin_project_env = self.root / "plugin.project-env"
        self.plugin_handler = self.root / "plugin.sh"
        self.user_settings = self.root / "user-settings.json"
        write_executable(
            self.plugin_handler,
            f"cat > {shlex.quote(str(self.plugin_capture))}\n"
            f"printf 'plugin\\n' >> {shlex.quote(str(self.plugin_effect))}\n"
            f"pwd > {shlex.quote(str(self.plugin_cwd))}\n"
            f"printf '%s' \"$CLAUDE_PROJECT_DIR\" > "
            f"{shlex.quote(str(self.plugin_project_env))}\n",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def payload(self, cwd: Path | None = None) -> bytes:
        value = {"session_id": "s", "prompt": "héllo\nworld"}
        if cwd is not None:
            value["cwd"] = str(cwd)
        return (json.dumps(value, ensure_ascii=False) + "\n").encode("utf-8")

    def route(self, raw: bytes, event: str, relative: str, **kwargs) -> int:
        return router.route(
            raw, event, relative, self.plugin_handler,
            user_settings=self.user_settings, **kwargs)

    def test_plugin_only_preserves_stdin_and_uses_payload_project_cwd(self) -> None:
        raw = self.payload(self.project)
        rc = self.route(
            raw, "UserPromptSubmit", HANDLERS["UserPromptSubmit"],
            env={"CLAUDE_PROJECT_DIR": str(self.root / "wrong-project")},
            process_cwd=self.other_cwd,
        )
        self.assertEqual(0, rc)
        self.assertEqual(raw, self.plugin_capture.read_bytes())
        self.assertEqual("plugin\n", self.plugin_effect.read_text())
        self.assertEqual(str(self.project.resolve()), self.plugin_cwd.read_text().strip())
        self.assertEqual(str(self.project), self.plugin_project_env.read_text())

    def test_mixed_project_and_plugin_configuration_has_one_effect_per_event(self) -> None:
        project_effect = self.root / "project.effects"
        for event, relative in HANDLERS.items():
            write_executable(
                self.project / relative,
                f"printf {shlex.quote(event + chr(10))} >> {shlex.quote(str(project_effect))}\n",
            )
        settings_for(self.project, HANDLERS)
        raw = self.payload(self.project)
        for event, relative in HANDLERS.items():
            subprocess.run(["bash", str(self.project / relative)], input=raw,
                           cwd=self.project, check=True)
            self.assertEqual(
                0, self.route(raw, event, relative,
                              process_cwd=self.other_cwd))
        self.assertEqual(set(HANDLERS), set(project_effect.read_text().splitlines()))
        self.assertFalse(self.plugin_effect.exists())

    def test_corrupt_project_settings_fails_open_to_plugin(self) -> None:
        target = self.project / HANDLERS["UserPromptSubmit"]
        write_executable(target, "exit 0\n")
        settings = self.project / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text("{not-json", encoding="utf-8")
        raw = self.payload(self.project)
        self.assertEqual(
            0, self.route(raw, "UserPromptSubmit", HANDLERS["UserPromptSubmit"]))
        self.assertEqual(raw, self.plugin_capture.read_bytes())

    def test_configured_but_non_executable_project_target_fails_open(self) -> None:
        target = self.project / HANDLERS["PreCompact"]
        write_executable(target, "exit 0\n")
        target.chmod(0o644)
        settings_for(self.project, {"PreCompact": HANDLERS["PreCompact"]})
        raw = self.payload(self.project)
        self.assertEqual(
            0, self.route(raw, "PreCompact", HANDLERS["PreCompact"]))
        self.assertEqual(raw, self.plugin_capture.read_bytes())

    def test_configured_but_missing_project_target_fails_open(self) -> None:
        settings_for(self.project, {"SessionEnd": HANDLERS["SessionEnd"]})
        raw = self.payload(self.project)
        self.assertEqual(
            0, self.route(raw, "SessionEnd", HANDLERS["SessionEnd"]))
        self.assertEqual(raw, self.plugin_capture.read_bytes())

    def test_valid_settings_wins_even_when_other_settings_file_is_corrupt(self) -> None:
        relative = HANDLERS["UserPromptSubmit"]
        write_executable(self.project / relative, "exit 0\n")
        settings_for(self.project, {"UserPromptSubmit": relative})
        (self.project / ".claude" / "settings.local.json").write_text(
            "{not-json", encoding="utf-8")
        raw = self.payload(self.project)
        self.assertEqual(
            0, self.route(raw, "UserPromptSubmit", relative))
        self.assertFalse(self.plugin_effect.exists())

    def test_settings_local_is_an_active_project_hook_surface(self) -> None:
        relative = HANDLERS["SessionEnd"]
        write_executable(self.project / relative, "exit 0\n")
        settings_for(self.project, {"SessionEnd": relative})
        source = self.project / ".claude" / "settings.json"
        source.replace(self.project / ".claude" / "settings.local.json")
        raw = self.payload(self.project)
        self.assertEqual(
            0, self.route(raw, "SessionEnd", relative))
        self.assertFalse(self.plugin_effect.exists())

    def test_conditional_project_hook_does_not_suppress_plugin(self) -> None:
        relative = HANDLERS["PreCompact"]
        write_executable(self.project / relative, "exit 0\n")
        settings_for(self.project, {"PreCompact": relative})
        settings = self.project / ".claude" / "settings.json"
        data = json.loads(settings.read_text(encoding="utf-8"))
        data["hooks"]["PreCompact"][0]["matcher"] = "manual"
        settings.write_text(json.dumps(data), encoding="utf-8")

        raw = self.payload(self.project)
        self.assertEqual(0, self.route(raw, "PreCompact", relative))
        self.assertEqual("plugin\n", self.plugin_effect.read_text())

    def test_unconditional_user_hook_suppresses_plugin(self) -> None:
        relative = HANDLERS["UserPromptSubmit"]
        write_executable(self.project / relative, "exit 0\n")
        settings_for(self.project, {"UserPromptSubmit": relative})
        project_settings = self.project / ".claude" / "settings.json"
        project_settings.replace(self.user_settings)

        raw = self.payload(self.project)
        self.assertEqual(0, self.route(raw, "UserPromptSubmit", relative))
        self.assertFalse(self.plugin_effect.exists())

    def test_plugin_only_install_exports_canary_skills_root(self) -> None:
        """Regression guard (2026-07-19 adversarial finding): a plugin-only
        consumer install (no repo checkout, no .claude/skills anywhere under
        the project) must still let the compliance-canary hook discover its
        probes. The fallback dispatch set CLAUDE_PROJECT_DIR for the child
        process but never COMPLIANCE_CANARY_SKILLS_ROOT, so the hook's
        skills_root() defaulted to the (nonexistent) <project>/.claude/skills
        and the always-on drift watcher silently ran with probe_count=0."""
        hook_path = REPO / "skills" / "compliance-canary" / "tools" / "hook.py"
        probe_count_file = self.root / "probe-count"
        canary_root_file = self.root / "canary-root"
        probe_script = self.root / "count_probes.py"
        probe_script.write_text(
            "import importlib.util\n"
            f"spec = importlib.util.spec_from_file_location('canary_hook', {str(hook_path)!r})\n"
            "mod = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(mod)\n"
            "probes = mod.discover_probes(mod.skills_root())\n"
            f"open({str(probe_count_file)!r}, 'w').write(str(len(probes)))\n"
            f"open({str(canary_root_file)!r}, 'w').write(str(mod.skills_root()))\n",
            encoding="utf-8",
        )
        write_executable(
            self.plugin_handler,
            f"{shlex.quote(sys.executable)} {shlex.quote(str(probe_script))}\n",
        )
        raw = self.payload(self.project)
        self.assertEqual(
            0, self.route(raw, "UserPromptSubmit", HANDLERS["UserPromptSubmit"]))
        self.assertEqual(str(router.PLUGIN_ROOT / "skills"), canary_root_file.read_text())
        self.assertGreater(int(probe_count_file.read_text()), 0)

    def test_active_project_fallback_order(self) -> None:
        raw = self.payload(self.project)
        self.assertEqual(
            self.project,
            router.active_project(
                raw, {"CLAUDE_PROJECT_DIR": str(self.root / "env-project")},
                self.other_cwd),
        )
        env_project = self.root / "env-project"
        self.assertEqual(
            env_project,
            router.active_project(b"{}", {"CLAUDE_PROJECT_DIR": str(env_project)},
                                  self.other_cwd),
        )
        self.assertEqual(
            self.other_cwd,
            router.active_project(b"not-json", {}, self.other_cwd),
        )


if __name__ == "__main__":
    unittest.main()
