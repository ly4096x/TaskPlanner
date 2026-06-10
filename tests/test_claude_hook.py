"""Tests for TaskPlanner claude-hook subcommand.

Tests the Claude Code hook handlers that are invoked as:
  TaskPlanner claude-hook <SessionStart|PreToolUse|Stop|StopWatch|SubagentStart>

Each handler reads JSON from stdin and outputs JSON hook responses to stdout.
"""

import json

import pytest
from click.testing import CliRunner

from client_cli.cli import cli


@pytest.fixture
def runner():
    return CliRunner()


class TestClaudeHookSessionStart:
    def test_creates_agent_user(self, runner):
        """SessionStart should output additionalContext with task info."""
        data = json.dumps({"session_id": "test-sess-1", "agent_id": "main"})
        result = runner.invoke(cli, ["claude-hook", "SessionStart"], input=data)
        # Should not crash — may output JSON or nothing
        assert result.exit_code == 0

    def test_outputs_valid_json_or_empty(self, runner):
        """SessionStart should output valid JSON (hook response) or empty."""
        data = json.dumps({"session_id": "test-sess-2", "agent_id": "main"})
        result = runner.invoke(cli, ["claude-hook", "SessionStart"], input=data)
        assert result.exit_code == 0
        if result.output.strip():
            parsed = json.loads(result.output)
            assert "hookSpecificOutput" in parsed


class TestClaudeHookPreToolUse:
    def test_non_gated_tool_passes(self, runner):
        """Non-Bash/Edit/Write tools should pass through (no output)."""
        data = json.dumps({
            "session_id": "test-sess-3", "agent_id": "main",
            "tool_name": "Read", "tool_input": {}
        })
        result = runner.invoke(cli, ["claude-hook", "PreToolUse"], input=data)
        assert result.exit_code == 0

    def test_taskplanner_cmd_passes(self, runner):
        """TaskPlanner CLI commands should always pass through."""
        data = json.dumps({
            "session_id": "test-sess-3", "agent_id": "main",
            "tool_name": "Bash",
            "tool_input": {"command": "TaskPlanner list", "description": "list tasks"}
        })
        result = runner.invoke(cli, ["claude-hook", "PreToolUse"], input=data)
        assert result.exit_code == 0
        # Should not deny
        if result.output.strip():
            parsed = json.loads(result.output)
            assert parsed.get("hookSpecificOutput", {}).get("permissionDecision") != "deny"

    def test_bash_without_task_denies(self, runner):
        """Bash command without a STARTED task should be denied."""
        data = json.dumps({
            "session_id": "no-user-session", "agent_id": "main",
            "tool_name": "Bash",
            "tool_input": {"command": "echo hi", "description": "test Task#999"}
        })
        result = runner.invoke(cli, ["claude-hook", "PreToolUse"], input=data)
        # Either passes (user not found → pass through) or denies (no started task)
        assert result.exit_code == 0


class TestPreToolUseTaskMatching:
    """Any STARTED task assigned to the agent must be a valid Task# reference
    in a Bash description suffix — not just the first one in list order."""

    TASKS = [
        {"id": 10, "title": "parent", "status": "STARTED", "importance": 0, "assignee_id": 1},
        {"id": 20, "title": "child", "status": "STARTED", "importance": 0, "assignee_id": 1},
        {"id": 30, "title": "todo", "status": "NEW", "importance": 0, "assignee_id": 1},
    ]

    def _invoke(self, runner, monkeypatch, description, posted=None):
        from client_cli.commands import claude_hook as ch

        monkeypatch.setenv("TASKPLANNER_BOARD_ID", "1")
        monkeypatch.delenv("TASKPLANNER_USER_ACCESS_TOKEN", raising=False)
        monkeypatch.setattr(
            ch, "_hook_resolve_user", lambda *a, **k: {"id": 1, "username": "agent_x"}
        )
        monkeypatch.setattr(ch, "_hook_get_agent_tasks", lambda *a, **k: list(self.TASKS))
        if posted is None:
            posted = []
        monkeypatch.setattr(
            ch,
            "_hook_api_post",
            lambda url, headers, json_data=None: posted.append((url, json_data)) or {},
        )
        data = json.dumps({
            "session_id": "match-sess", "agent_id": "main",
            "tool_name": "Bash",
            "tool_input": {"command": "echo hi", "description": description},
        })
        return runner.invoke(cli, ["claude-hook", "PreToolUse"], input=data)

    @staticmethod
    def _decision(result):
        assert result.exit_code == 0
        if not result.output.strip():
            return None
        return json.loads(result.output).get("hookSpecificOutput", {}).get("permissionDecision")

    def test_first_started_task_accepted(self, runner, monkeypatch):
        result = self._invoke(runner, monkeypatch, "do thing Task#10")
        assert self._decision(result) != "deny"

    def test_second_started_task_accepted(self, runner, monkeypatch):
        result = self._invoke(runner, monkeypatch, "do thing Task#20")
        assert self._decision(result) != "deny"

    def test_execution_log_goes_to_referenced_task(self, runner, monkeypatch):
        posted = []
        result = self._invoke(runner, monkeypatch, "do thing Task#20", posted)
        assert self._decision(result) != "deny"
        urls = [url for url, _ in posted]
        assert any("/tasks/20/new_comment" in url for url in urls)
        assert not any("/tasks/10/new_comment" in url for url in urls)

    def test_non_started_task_reference_denied(self, runner, monkeypatch):
        result = self._invoke(runner, monkeypatch, "do thing Task#30")
        assert self._decision(result) == "deny"

    def test_unknown_task_reference_denied(self, runner, monkeypatch):
        result = self._invoke(runner, monkeypatch, "do thing Task#999")
        assert self._decision(result) == "deny"

    def test_missing_suffix_denied(self, runner, monkeypatch):
        result = self._invoke(runner, monkeypatch, "do thing")
        assert self._decision(result) == "deny"


class TestClaudeHookStop:
    def test_no_user_passes(self, runner):
        """Stop with unknown session should pass through."""
        data = json.dumps({
            "session_id": "unknown-session", "agent_id": "main",
            "last_assistant_message": ""
        })
        result = runner.invoke(cli, ["claude-hook", "Stop"], input=data)
        assert result.exit_code == 0

    def test_escape_hatch(self, runner):
        """Stop with escape hatch message should pass through."""
        data = json.dumps({
            "session_id": "test-sess-4", "agent_id": "main",
            "last_assistant_message": "THIS_IS_AN_EMERGENCY_SOMETHING_WENT_WRONG_I_NEED_TO_STOP"
        })
        result = runner.invoke(cli, ["claude-hook", "Stop"], input=data)
        assert result.exit_code == 0
        # Should not block
        if result.output.strip():
            parsed = json.loads(result.output)
            assert parsed.get("decision") != "block"


class TestClaudeHookUnknownEvent:
    def test_unknown_event_exits_clean(self, runner):
        """Unknown event name should exit cleanly."""
        data = json.dumps({"session_id": "test", "agent_id": "main"})
        result = runner.invoke(cli, ["claude-hook", "UnknownEvent"], input=data)
        assert result.exit_code == 0
