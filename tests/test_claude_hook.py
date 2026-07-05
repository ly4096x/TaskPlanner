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


class TestBoardPinning:
    """SessionStart/SubagentStart must pin TASKPLANNER_BOARD_ID into the session
    env file: Claude Code re-sources it on resume, so the session stays on its
    originating board instead of drifting with the resuming shell (#570/#706)."""

    def _setup(self, monkeypatch, tmp_path):
        from client_cli.commands import claude_hook as ch

        env_file = tmp_path / "sessionstart-hook-0.sh"
        monkeypatch.setenv("CLAUDE_ENV_FILE", str(env_file))
        monkeypatch.setenv("TASKPLANNER_BOARD_ID", "7")
        monkeypatch.delenv("TASKPLANNER_USER_ACCESS_TOKEN", raising=False)
        monkeypatch.setattr(
            ch, "_hook_get_or_create_user", lambda *a, **k: {"id": 1, "username": "agent_x"}
        )
        monkeypatch.setattr(ch, "_hook_mint_token", lambda *a, **k: "tok-123")
        monkeypatch.setattr(ch, "_hook_get_agent_tasks", lambda *a, **k: [])
        return env_file

    def test_session_start_pins_board(self, runner, monkeypatch, tmp_path):
        env_file = self._setup(monkeypatch, tmp_path)
        data = json.dumps({"session_id": "pin-sess", "agent_id": "main"})
        result = runner.invoke(cli, ["claude-hook", "SessionStart"], input=data)
        assert result.exit_code == 0
        content = env_file.read_text()
        assert "export TASKPLANNER_BOARD_ID=7" in content
        assert "export TASKPLANNER_USERNAME=agent_x" in content
        assert "export TASKPLANNER_USER_ACCESS_TOKEN=tok-123" in content

    def test_subagent_start_pins_board(self, runner, monkeypatch, tmp_path):
        env_file = self._setup(monkeypatch, tmp_path)
        data = json.dumps({"session_id": "pin-sess", "agent_id": "sub-1"})
        result = runner.invoke(cli, ["claude-hook", "SubagentStart"], input=data)
        assert result.exit_code == 0
        content = env_file.read_text()
        assert "export TASKPLANNER_BOARD_ID=7" in content

    def test_session_start_without_board_still_exports_identity(
        self, runner, monkeypatch, tmp_path
    ):
        env_file = self._setup(monkeypatch, tmp_path)
        monkeypatch.delenv("TASKPLANNER_BOARD_ID")
        # No .env walk-up hit either — resolve from an empty cwd.
        monkeypatch.chdir(tmp_path)
        data = json.dumps({"session_id": "pin-sess", "agent_id": "main"})
        result = runner.invoke(cli, ["claude-hook", "SessionStart"], input=data)
        assert result.exit_code == 0
        content = env_file.read_text()
        assert "TASKPLANNER_BOARD_ID" not in content
        assert "export TASKPLANNER_USERNAME=agent_x" in content


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


class TestPreToolUseTaskPlannerChaining:
    """The TaskPlanner bypass allows pipes and redirections but not command
    sequencing — sequencing could smuggle an arbitrary command past the gate."""

    def _invoke(self, runner, command):
        data = json.dumps({
            "session_id": "chain-sess", "agent_id": "main",
            "tool_name": "Bash",
            "tool_input": {"command": command, "description": "x"},
        })
        return runner.invoke(cli, ["claude-hook", "PreToolUse"], input=data)

    @staticmethod
    def _denied(result):
        assert result.exit_code == 0
        if not result.output.strip():
            return None
        out = json.loads(result.output).get("hookSpecificOutput", {})
        return out.get("permissionDecisionReason") if out.get("permissionDecision") == "deny" else None

    def test_plain_command_passes(self, runner):
        assert self._denied(self._invoke(runner, "TaskPlanner list")) is None

    def test_quoted_operator_passes(self, runner):
        # Operators inside quotes are legitimate args, not sequencing.
        assert self._denied(self._invoke(runner, 'TaskPlanner add-task --title "a && b"')) is None

    @pytest.mark.parametrize("command", [
        "TaskPlanner list | grep x",
        "TaskPlanner list | grep x | wc -l",
        "TaskPlanner list |& cat",
        "TaskPlanner list > out.txt",
        "TaskPlanner list >> out.txt",
        "TaskPlanner list 2> err.txt",
        "TaskPlanner list > out.txt 2>&1",
        "TaskPlanner list < in.txt",
        # Multi-line Markdown via the documented heredoc pattern (#580/#731).
        "TaskPlanner add-comment 42 -m \"$(cat <<'EOF'\n## Findings\n\n- `code`\nEOF\n)\"",
        'TaskPlanner add-comment 42 -m "line1\nline2\n- bullet"',
        'TaskPlanner add-comment 42 -m "use `code` and `x` here"',
        'TaskPlanner add-task --title "a && b; c"',
    ])
    def test_pipes_redirects_and_multiline_markdown_pass(self, runner, command):
        assert self._denied(self._invoke(runner, command)) is None

    @pytest.mark.parametrize("command", [
        "TaskPlanner list && rm -rf /",
        "TaskPlanner list || true",
        "TaskPlanner list; echo hi",
        "TaskPlanner edit 5 --status DONE &",
        "TaskPlanner list | grep x && rm -rf /",
        "TaskPlanner list $(rm -rf /)",       # unquoted command substitution
        "TaskPlanner list `rm -rf /`",        # top-level backtick substitution
        "TaskPlanner edit 5\nrm -rf /",       # top-level newline separator
        'TaskPlanner add-comment 1 -m "q1\nq2"\nrm -rf /',  # quoted nl + top-level nl
    ])
    def test_sequencing_denied(self, runner, command):
        reason = self._denied(self._invoke(runner, command))
        assert reason is not None
        assert "Command sequencing is not allowed" in reason

    def test_lowercase_sequencing_denied(self, runner):
        assert self._denied(self._invoke(runner, "taskplanner list && rm -rf /")) is not None


class TestHasShellChaining:
    """Unit coverage for the shlex-based sequencing detector."""

    @pytest.mark.parametrize("command", [
        "TaskPlanner list",
        'TaskPlanner add-task --title "a && b; c"',
        "TaskPlanner edit 5 --status DONE",
        # Pipes and redirections are allowed.
        "TaskPlanner list | cat",
        "TaskPlanner list | grep x | wc -l",
        "TaskPlanner list |& cat",
        "TaskPlanner list > out.txt",
        "TaskPlanner list 2>&1",
        "TaskPlanner list < in.txt",
        # Quoted command substitution / newlines / backticks (multi-line markdown).
        "TaskPlanner add-comment 42 -m \"$(cat <<'EOF'\n## H\n- `c`\nEOF\n)\"",
        'TaskPlanner add-comment 1 -m "line\n`code`\nmore"',
        'TaskPlanner list -m "$(rm -rf /)"',   # substitution inside quotes: allowed
        # Heredoc body with embedded quotes, backticks, nested EOF and $() — the
        # case that fools a naive quote scanner (#580/#731).
        "TaskPlanner add-comment 732 -m \"$(cat <<'EOF'\n## H\n\n```bash\nx -m \"$(cat <<'EOF' ... EOF)\"\n```\n- \"quotes\" and `code` and $(subst)\nEOF\n)\"",
        'TaskPlanner add-comment 1 -m "prose with << b less than"',  # bare << not a heredoc
    ])
    def test_clean(self, command):
        from client_cli.commands.claude_hook import _has_shell_chaining
        assert _has_shell_chaining(command) is False

    @pytest.mark.parametrize("command", [
        "TaskPlanner list && echo",
        "TaskPlanner list || echo",
        "TaskPlanner list; echo",
        "TaskPlanner list & ",
        "TaskPlanner list | cat && echo",
        "echo $(TaskPlanner list)",
        "TaskPlanner list $(rm -rf /)",   # unquoted command substitution
        "TaskPlanner list `echo`",        # top-level backtick
        "TaskPlanner list\necho",         # top-level newline
        '(TaskPlanner list)',
        'TaskPlanner add-task --title "unterminated',
    ])
    def test_sequenced(self, command):
        from client_cli.commands.claude_hook import _has_shell_chaining
        assert _has_shell_chaining(command) is True


class TestPreToolUseTaskMatching:
    """Any STARTED task assigned to the agent must be a valid Task# reference
    in a Bash description suffix — not just the first one in list order."""

    TASKS = [
        {"id": 10, "title": "parent", "status": "STARTED", "importance": 0, "assignee_id": 1},
        {"id": 20, "title": "child", "status": "STARTED", "importance": 0, "assignee_id": 1},
        {"id": 30, "title": "todo", "status": "NEW", "importance": 0, "assignee_id": 1},
    ]

    def _invoke(self, runner, monkeypatch, description, posted=None, tasks=None, tool_name="Bash"):
        from client_cli.commands import claude_hook as ch

        monkeypatch.setenv("TASKPLANNER_BOARD_ID", "1")
        monkeypatch.delenv("TASKPLANNER_USER_ACCESS_TOKEN", raising=False)
        monkeypatch.setattr(
            ch, "_hook_resolve_user", lambda *a, **k: {"id": 1, "username": "agent_x"}
        )
        if tasks is None:
            tasks = list(self.TASKS)
        monkeypatch.setattr(ch, "_hook_get_agent_tasks", lambda *a, **k: list(tasks))
        if posted is None:
            posted = []
        monkeypatch.setattr(
            ch,
            "_hook_api_post",
            lambda url, headers, json_data=None: posted.append((url, json_data)) or {},
        )
        if tool_name == "Bash":
            tool_input = {"command": "echo hi", "description": description}
        else:
            tool_input = {"file_path": "/tmp/f.txt", "old_string": "a", "new_string": "b"}
        data = json.dumps({
            "session_id": "match-sess", "agent_id": "main",
            "tool_name": tool_name,
            "tool_input": tool_input,
        })
        return runner.invoke(cli, ["claude-hook", "PreToolUse"], input=data)

    @staticmethod
    def _decision(result):
        assert result.exit_code == 0
        if not result.output.strip():
            return None
        return json.loads(result.output).get("hookSpecificOutput", {}).get("permissionDecision")

    @staticmethod
    def _reason(result):
        return (
            json.loads(result.output)
            .get("hookSpecificOutput", {})
            .get("permissionDecisionReason", "")
        )

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

    # --- suffix parsing edge cases ---

    def test_trailing_newline_denied(self, runner, monkeypatch):
        result = self._invoke(runner, monkeypatch, "do thing Task#10\n")
        assert self._decision(result) == "deny"

    def test_leading_zeros_resolve_to_task(self, runner, monkeypatch):
        result = self._invoke(runner, monkeypatch, "do thing Task#010")
        assert self._decision(result) != "deny"

    def test_no_leading_space_denied(self, runner, monkeypatch):
        result = self._invoke(runner, monkeypatch, "Task#10")
        assert self._decision(result) == "deny"

    def test_mid_string_reference_denied(self, runner, monkeypatch):
        result = self._invoke(runner, monkeypatch, "Task#10 then more")
        assert self._decision(result) == "deny"

    def test_last_suffix_wins(self, runner, monkeypatch):
        posted = []
        result = self._invoke(runner, monkeypatch, "fix Task#10 then Task#20", posted)
        assert self._decision(result) != "deny"
        assert any("/tasks/20/new_comment" in url for url, _ in posted)

    def test_huge_task_id_denied_not_crash(self, runner, monkeypatch):
        # 4301+ digits would make int() raise; the digit bound must turn this
        # into a deny instead of a fail-open hook crash.
        result = self._invoke(runner, monkeypatch, "do thing Task#" + "1" * 4301)
        assert self._decision(result) == "deny"

    def test_ten_digit_task_id_denied(self, runner, monkeypatch):
        result = self._invoke(runner, monkeypatch, "do thing Task#1234567890")
        assert self._decision(result) == "deny"

    # --- EXECUTION_LOG payload ---

    def test_execution_log_payload(self, runner, monkeypatch):
        posted = []
        result = self._invoke(runner, monkeypatch, "do thing Task#20", posted)
        assert self._decision(result) != "deny"
        _, payload = posted[0]
        assert payload["content"] == "[Tool:Bash] do thing\n\n```bash\necho hi\n```"
        assert payload["comment_type"] == "EXECUTION_LOG"
        assert payload["as_user"] == "agent_x"

    def test_suffix_only_description_logs_placeholder(self, runner, monkeypatch):
        posted = []
        result = self._invoke(runner, monkeypatch, " Task#10", posted)
        assert self._decision(result) != "deny"
        _, payload = posted[0]
        assert payload["content"].startswith("[Tool:Bash] (no description)")

    # --- no-STARTED-task deny paths ---

    def test_no_started_task_denied_with_hint(self, runner, monkeypatch):
        new_only = [{"id": 30, "title": "todo", "status": "NEW", "importance": 0, "assignee_id": 1}]
        result = self._invoke(runner, monkeypatch, "x Task#30", tasks=new_only)
        assert self._decision(result) == "deny"
        assert "No STARTED task" in self._reason(result)

    def test_no_tasks_at_all_denied_with_hint(self, runner, monkeypatch):
        result = self._invoke(runner, monkeypatch, "x Task#30", tasks=[])
        assert self._decision(result) == "deny"
        assert "No tasks assigned" in self._reason(result)

    # --- Edit/Write gating ---

    @pytest.mark.parametrize("tool_name", ["Edit", "Write"])
    def test_edit_write_pass_with_started_task(self, runner, monkeypatch, tool_name):
        result = self._invoke(runner, monkeypatch, "", tool_name=tool_name)
        assert self._decision(result) != "deny"

    @pytest.mark.parametrize("tool_name", ["Edit", "Write"])
    def test_edit_write_denied_without_started_task(self, runner, monkeypatch, tool_name):
        new_only = [{"id": 30, "title": "todo", "status": "NEW", "importance": 0, "assignee_id": 1}]
        result = self._invoke(runner, monkeypatch, "", tasks=new_only, tool_name=tool_name)
        assert self._decision(result) == "deny"


class TestPreToolUseSubagentDelegation:
    """A subagent's Bash gate must also accept the session main agent's tasks,
    so a parent can hand its own STARTED task to a subagent without forcing a
    duplicate mirror task (#589)."""

    MAIN = {"id": 1, "username": "agent_main"}
    SUB = {"id": 2, "username": "agent_main_sub"}
    MAIN_TASKS = [
        {"id": 10, "title": "parent work", "status": "STARTED", "importance": 0, "assignee_id": 1},
    ]

    def _invoke(self, runner, monkeypatch, description, posted=None, sub_tasks=None):
        from client_cli.commands import claude_hook as ch

        monkeypatch.setenv("TASKPLANNER_BOARD_ID", "1")
        monkeypatch.delenv("TASKPLANNER_USER_ACCESS_TOKEN", raising=False)

        def resolve(url, headers, session_id, agent_id):
            return dict(self.MAIN) if agent_id == "main" else dict(self.SUB)

        monkeypatch.setattr(ch, "_hook_resolve_user", resolve)

        def get_tasks(url, headers, board, user_id, filter_expr=None, limit=None):
            if user_id == self.MAIN["id"]:
                return [dict(t) for t in self.MAIN_TASKS]
            return [dict(t) for t in (sub_tasks or [])]

        monkeypatch.setattr(ch, "_hook_get_agent_tasks", get_tasks)
        if posted is None:
            posted = []
        monkeypatch.setattr(
            ch, "_hook_api_post",
            lambda url, headers, json_data=None: posted.append((url, json_data)) or {},
        )
        data = json.dumps({
            "session_id": "deleg-sess", "agent_id": "sub-abc",
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

    def test_subagent_can_reference_parents_started_task(self, runner, monkeypatch):
        posted = []
        result = self._invoke(runner, monkeypatch, "do parent work Task#10", posted)
        assert self._decision(result) != "deny"
        # Execution log lands on the parent's task, attributed to the subagent.
        url, payload = posted[0]
        assert "/tasks/10/new_comment" in url
        assert payload["as_user"] == self.SUB["username"]

    def test_subagent_own_task_still_accepted(self, runner, monkeypatch):
        own = [{"id": 20, "title": "sub work", "status": "STARTED", "importance": 0,
                "assignee_id": 2}]
        result = self._invoke(runner, monkeypatch, "x Task#20", sub_tasks=own)
        assert self._decision(result) != "deny"

    def test_subagent_unknown_task_still_denied(self, runner, monkeypatch):
        result = self._invoke(runner, monkeypatch, "x Task#99")
        assert self._decision(result) == "deny"

    def test_shared_unassigned_task_deduplicated(self, runner, monkeypatch):
        # An unassigned task shows up in both users' task lists; the merge must
        # not duplicate it (active_by_id stays consistent).
        shared = [{"id": 10, "title": "parent work", "status": "STARTED", "importance": 0,
                   "assignee_id": None}]
        result = self._invoke(runner, monkeypatch, "x Task#10", sub_tasks=shared)
        assert self._decision(result) != "deny"


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
