#!/usr/bin/env python3
"""Tests for the cross-host transcript normalizer."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import transcript_norm as tn  # noqa: E402


def test_claude_passthrough():
    claude = [
        {"type": "assistant", "timestamp": "t", "message": {"content": [
            {"type": "tool_use", "name": "Skill", "input": {"skill": "x"}}]}},
        {"type": "user", "message": {"content": [{"type": "text", "text": "ok"}]}},
    ]
    assert tn.is_codex(claude) is False
    assert tn.normalize(claude) == claude  # untouched
    print("ok test_claude_passthrough")


def test_codex_detection():
    codex = [{"type": "response_item", "payload": {"type": "message", "role": "user",
              "content": [{"type": "input_text", "text": "hi"}]}}]
    assert tn.is_codex(codex) is True
    print("ok test_codex_detection")


def test_codex_function_call_maps_to_tool_use():
    # a NON-shell function call passes its name + parsed args through unchanged
    codex = [{"type": "response_item", "timestamp": "t1", "payload": {
        "type": "function_call", "name": "apply_patch",
        "arguments": '{"path":"a.py"}', "call_id": "c1"}}]
    norm = tn.normalize(codex)
    assert len(norm) == 1, norm
    b = norm[0]["message"]["content"][0]
    assert norm[0]["type"] == "assistant"
    assert b["type"] == "tool_use" and b["name"] == "apply_patch"
    assert b["input"] == {"path": "a.py"}         # JSON-string arguments parsed
    print("ok test_codex_function_call_maps_to_tool_use")


def test_codex_shell_tool_maps_to_bash_with_command_key():
    codex = [{"type": "response_item", "payload": {
        "type": "function_call", "name": "exec_command",
        "arguments": '{"cmd":"rm -rf x","workdir":"/tmp"}'}}]
    b = tn.normalize(codex)[0]["message"]["content"][0]
    assert b["name"] == "Bash", b                       # name normalized
    assert b["input"]["command"] == "rm -rf x", b       # cmd -> command
    assert b["input"]["workdir"] == "/tmp", b           # other args preserved
    print("ok test_codex_shell_tool_maps_to_bash_with_command_key")


def test_codex_bad_arguments_dont_crash():
    codex = [{"type": "response_item", "payload": {
        "type": "function_call", "name": "x", "arguments": "not json"}}]
    b = tn.normalize(codex)[0]["message"]["content"][0]
    assert b["input"] == {"_raw": "not json"}
    print("ok test_codex_bad_arguments_dont_crash")


def test_codex_user_and_assistant_messages():
    codex = [
        {"type": "response_item", "payload": {"type": "message", "role": "user",
         "content": [{"type": "input_text", "text": "do it"}]}},
        {"type": "response_item", "payload": {"type": "message", "role": "assistant",
         "content": [{"type": "output_text", "text": "done"}]}},
        {"type": "response_item", "payload": {"type": "message", "role": "developer",
         "content": [{"type": "input_text", "text": "instructions"}]}},
    ]
    norm = tn.normalize(codex)
    roles = [e["type"] for e in norm]
    assert roles == ["user", "assistant"], roles      # developer dropped
    assert norm[0]["message"]["content"][0]["text"] == "do it"
    print("ok test_codex_user_and_assistant_messages")


def test_codex_slash_skill_synthesizes_skill_tool_use():
    codex = [{"type": "response_item", "payload": {"type": "message", "role": "user",
              "content": [{"type": "input_text", "text": "/learn how I did this"}]}}]
    norm = tn.normalize(codex)
    assert norm[0]["type"] == "user"
    assert norm[1]["type"] == "assistant"
    b = norm[1]["message"]["content"][0]
    assert b["name"] == "Skill" and b["input"]["skill"] == "learn-skill", norm
    # /think -> think, /retro -> task-retrospective
    for tok, name in (("/think x", "think"), ("/retro", "task-retrospective")):
        c = [{"type": "response_item", "payload": {"type": "message", "role": "user",
              "content": [{"type": "input_text", "text": tok}]}}]
        assert tn.normalize(c)[1]["message"]["content"][0]["input"]["skill"] == name
    print("ok test_codex_slash_skill_synthesizes_skill_tool_use")


def test_codex_non_slash_user_no_synthesis():
    codex = [{"type": "response_item", "payload": {"type": "message", "role": "user",
              "content": [{"type": "input_text", "text": "just a normal request"}]}}]
    norm = tn.normalize(codex)
    assert len(norm) == 1 and norm[0]["type"] == "user", norm
    print("ok test_codex_non_slash_user_no_synthesis")


if __name__ == "__main__":
    test_claude_passthrough()
    test_codex_detection()
    test_codex_function_call_maps_to_tool_use()
    test_codex_shell_tool_maps_to_bash_with_command_key()
    test_codex_bad_arguments_dont_crash()
    test_codex_user_and_assistant_messages()
    test_codex_slash_skill_synthesizes_skill_tool_use()
    test_codex_non_slash_user_no_synthesis()
    print("ALL 8 TESTS PASSED")
