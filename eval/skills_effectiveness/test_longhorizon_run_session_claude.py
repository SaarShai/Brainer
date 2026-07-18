import json
import tempfile
import unittest
from pathlib import Path

try:
    from .longhorizon_run_session_claude import (
        RunnerResult, arm_profile, parse_scripted_turns, run_session,
    )
except ImportError:
    from longhorizon_run_session_claude import (
        RunnerResult, arm_profile, parse_scripted_turns, run_session,
    )

HERE = Path(__file__).resolve().parent
SCENARIO_01 = HERE / "scenarios" / "scenario-01.md"


class FakeRunner:
    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on

    def __call__(self, command, env, output_path, cwd=None):
        turn = len(self.calls) + 1
        self.calls.append((command, env.copy(), output_path, cwd))
        output_path.write_text(
            json.dumps({"type": "system", "session_id": "session-123"}) + "\n",
            encoding="utf-8",
        )
        return RunnerResult(7 if turn == self.fail_on else 0, "session-123")


def scenario(path, name="sample", count=3, compact_at=None):
    lines = [
        f"# {name}",
        "",
        f"Fixture root: `longhorizon-work/{name}/`",
        "",
    ]
    lines.extend(
        f"T{index:02d} — `{'/compact' if index == compact_at else f'message {index}'}`"
        for index in range(1, count + 1)
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class LongHorizonRunSessionClaudeTests(unittest.TestCase):
    def test_parse_scenario_01(self):
        turns = parse_scripted_turns(SCENARIO_01)
        self.assertEqual(44, len(turns))
        self.assertEqual((1, turns[0][1]), turns[0])
        self.assertEqual([14, 31], [index for index, text in turns if text == "/compact"])

    def test_manifest_writing_and_command_shape(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            venue = root / "venue"
            venue.mkdir()
            source = root / "sample.md"
            scenario(source, count=2, compact_at=2)
            runner = FakeRunner()
            manifest = run_session(
                source, "frontier", venue, root / "out", runner=runner,
                version_getter=lambda: "claude-code test",
                git_state_getter=lambda unused: "clean\n",
            )
            written = json.loads((root / "out" / "manifest.json").read_text())
            self.assertEqual(manifest, written)
            self.assertEqual(1, written["schema_version"])
            self.assertEqual("frontier", written["environment"]["COMPLIANCE_CANARY_PROFILE"])
            self.assertEqual("claude-code", written["environment"]["host"])
            self.assertEqual("claude-code test", written["environment"]["host_version"])
            self.assertNotIn("codex_version", written["environment"])
            self.assertEqual([1, 2], [record["turn_index"] for record in written["turns"]])
            self.assertEqual(
                [{"turn_index": 2, "mechanism": "claude-native-compact"}],
                written["forced_compactions"],
            )
            self.assertEqual(
                ["claude", "-p", "--output-format", "stream-json", "--verbose",
                 "--dangerously-skip-permissions", "message 1"],
                runner.calls[0][0],
            )
            self.assertEqual(venue.resolve(), runner.calls[0][3])
            self.assertEqual("--resume", runner.calls[1][0][6])
            self.assertEqual("session-123", runner.calls[1][0][7])
            self.assertEqual("/compact", runner.calls[1][0][8])
            self.assertEqual("frontier", runner.calls[0][1]["COMPLIANCE_CANARY_PROFILE"])

    def test_resume_from_continues_without_reset(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            venue = root / "venue"
            fixture = venue / "longhorizon-work" / "sample"
            fixture.mkdir(parents=True)
            source = root / "sample.md"
            scenario(source, count=3)
            first = FakeRunner(fail_on=2)
            with self.assertRaisesRegex(RuntimeError, "turn 02 failed"):
                run_session(
                    source, "off", venue, root / "out", runner=first,
                    version_getter=lambda: "claude-code test",
                    git_state_getter=lambda unused: "state\n",
                )
            marker = fixture / "keep.txt"
            fixture.mkdir(parents=True)
            marker.write_text("resume must not reset", encoding="utf-8")
            second = FakeRunner()
            resumed = run_session(
                source, "off", venue, root / "out", resume_from=2, runner=second,
                version_getter=lambda: "unused",
                git_state_getter=lambda unused: self.fail("git state should not run on resume"),
            )
            self.assertTrue(marker.exists())
            self.assertEqual([1, 2, 3], [record["turn_index"] for record in resumed["turns"]])
            self.assertEqual("--resume", second.calls[0][0][6])

    def test_arm_environment_mapping(self):
        self.assertEqual("frontier", arm_profile("frontier"))
        self.assertEqual("off", arm_profile("off"))
        with self.assertRaises(ValueError):
            arm_profile("shadow")


if __name__ == "__main__":
    unittest.main()
