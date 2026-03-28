"""Tests for the TaskPlanner CLI frontend.

Uses Click's CliRunner and mocks httpx responses so no real server is needed.
"""

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from click.testing import CliRunner

from client_cli.cli import cli


@pytest.fixture
def runner():
    return CliRunner()


# --- Helpers to build mock httpx responses ---


def mock_response(status_code=200, json_data=None):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = json.dumps(json_data or {})
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


SAMPLE_USER = {"id": 1, "external_id": "alice", "username": "alice", "display_name": "Alice"}
USERS_LIST = [SAMPLE_USER]


def mock_get_with_users(status_code=200, data=None):
    """Mock httpx.get that returns users list for resolve_assignee."""

    def side_effect(url, *args, **kwargs):
        if "/api/v1/users" in url:
            return mock_response(200, USERS_LIST)
        return mock_response(status_code, data)

    return side_effect


SAMPLE_TASK = {
    "id": 1,
    "title": "Fix login bug",
    "assignee_id": 1,
    "assignee_name": "Alice",
    "assignee_username": "alice",
    "description": "The login page crashes on submit",
    "importance": 85,
    "estimated_effort": 3,
    "created_time": 1700000000.0,
    "status": "NEW",
    "tags": ["backend", "urgent"],
    "blockers": [2],
    "parent_task_id": None,
}
SAMPLE_TASK_MINIMAL = {
    "id": 2,
    "title": "Write docs",
    "assignee_id": None,
    "assignee_name": None,
    "assignee_username": None,
    "description": "",
    "importance": 10,
    "estimated_effort": 1,
    "created_time": 1700001000.0,
    "status": "STARTED",
    "tags": [],
    "blockers": [],
    "parent_task_id": None,
}
SAMPLE_COMMENT = {
    "id": 1,
    "task_id": 1,
    "content": "This is a comment",
    "created_time": 1700002000.0,
}
SAMPLE_BOARD = {
    "id": 1,
    "name": "Project Alpha",
    "description": "Main project board",
    "created_time": 1700000000.0,
}
SAMPLE_BOARD_2 = {
    "id": 2,
    "name": "Sprint Beta",
    "description": "",
    "created_time": 1700001000.0,
}


# --- Board commands ---


class TestCreateBoard:
    @patch("client_cli.cli.httpx.post")
    def test_create_board_success(self, mock_post, runner):
        mock_post.return_value = mock_response(200, SAMPLE_BOARD)
        result = runner.invoke(
            cli, ["create-board", "--name", "Project Alpha", "--description", "Main project board"]
        )
        assert result.exit_code == 0
        assert "Project Alpha" in result.output
        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        assert "/api/v1/boards/new" in call_url

    @patch("client_cli.cli.httpx.post")
    def test_create_board_no_description(self, mock_post, runner):
        mock_post.return_value = mock_response(200, SAMPLE_BOARD)
        result = runner.invoke(cli, ["create-board", "--name", "Project Alpha"])
        assert result.exit_code == 0

    @patch("client_cli.cli.httpx.post")
    def test_create_board_missing_name(self, mock_post, runner):
        result = runner.invoke(cli, ["create-board"])
        assert result.exit_code != 0


class TestListBoards:
    @patch("client_cli.cli.httpx.get")
    def test_list_boards_success(self, mock_get, runner):
        mock_get.return_value = mock_response(200, [SAMPLE_BOARD, SAMPLE_BOARD_2])
        result = runner.invoke(cli, ["list-boards"])
        assert result.exit_code == 0
        assert "Project Alpha" in result.output
        assert "Sprint Beta" in result.output
        call_url = mock_get.call_args[0][0]
        assert "/api/v1/boards" in call_url

    @patch("client_cli.cli.httpx.get")
    def test_list_boards_empty(self, mock_get, runner):
        mock_get.return_value = mock_response(200, [])
        result = runner.invoke(cli, ["list-boards"])
        assert result.exit_code == 0
        assert "No boards" in result.output


class TestShowBoard:
    @patch("client_cli.cli.httpx.get")
    def test_show_board_success(self, mock_get, runner):
        mock_get.return_value = mock_response(200, SAMPLE_BOARD)
        result = runner.invoke(cli, ["show-board", "1"])
        assert result.exit_code == 0
        assert "Project Alpha" in result.output
        call_url = mock_get.call_args[0][0]
        assert "/api/v1/board/1" in call_url


# --- Board flag on task commands ---


class TestBoardFlagRequired:
    """Task commands must require --board / -b or .env TASKPLANNER_BOARD_ID."""

    @patch("client_cli.cli._find_env_board_id", return_value=None)
    def test_list_requires_board(self, mock_env, runner):
        result = runner.invoke(cli, ["list"])
        assert result.exit_code != 0
        assert "board" in result.output.lower() or "board" in (result.stderr or "").lower()

    @patch("client_cli.cli._find_env_board_id", return_value=None)
    def test_add_task_requires_board(self, mock_env, runner):
        result = runner.invoke(cli, ["add-task", "--title", "Test"])
        assert result.exit_code != 0

    @patch("client_cli.cli._find_env_board_id", return_value=None)
    def test_show_task_requires_board(self, mock_env, runner):
        result = runner.invoke(cli, ["show-task", "1"])
        assert result.exit_code != 0

    @patch("client_cli.cli._find_env_board_id", return_value=None)
    def test_edit_status_requires_board(self, mock_env, runner):
        result = runner.invoke(cli, ["edit", "1", "--status", "STARTED"])
        assert result.exit_code != 0

    @patch("client_cli.cli._find_env_board_id", return_value=None)
    def test_edit_title_requires_board(self, mock_env, runner):
        result = runner.invoke(cli, ["edit", "1", "--title", "X"])
        assert result.exit_code != 0

    @patch("client_cli.cli._find_env_board_id", return_value=None)
    def test_edit_assignee_requires_board(self, mock_env, runner):
        result = runner.invoke(cli, ["edit", "1", "--assignee", "alice"])
        assert result.exit_code != 0

    @patch("client_cli.cli._find_env_board_id", return_value=None)
    def test_add_comment_requires_board(self, mock_env, runner):
        result = runner.invoke(cli, ["add-comment", "1", "-m", "hi"])
        assert result.exit_code != 0


class TestBoardFromEnvFile:
    """TASKPLANNER_BOARD_ID in .env file should provide the board ID."""

    @patch("client_cli.cli._find_env_board_id", return_value=5)
    @patch("client_cli.cli.httpx.get")
    def test_list_uses_env_file_board(self, mock_get, mock_env, runner):
        mock_get.return_value = mock_response(200, [SAMPLE_TASK])
        result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        call_url = mock_get.call_args[0][0]
        assert "/api/v1/board/5/tasks" in call_url


# --- add-user (global, no board needed) ---


class TestAddUser:
    @patch("client_cli.cli.httpx.post")
    def test_add_user_success(self, mock_post, runner):
        mock_post.return_value = mock_response(200, SAMPLE_USER)
        result = runner.invoke(
            cli,
            [
                "add-user",
                "--external-id",
                "alice",
                "--username",
                "alice",
                "--display-name",
                "Alice",
            ],
        )
        assert result.exit_code == 0
        assert "alice" in result.output or "Alice" in result.output
        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        assert "/api/v1/users/new" in call_url

    @patch("client_cli.cli.httpx.post")
    def test_add_user_missing_args(self, mock_post, runner):
        result = runner.invoke(cli, ["add-user"])
        assert result.exit_code != 0


# --- add-task (with -b flag) ---


class TestAddTask:
    @patch("client_cli.cli.httpx.get")
    @patch("client_cli.cli.httpx.post")
    def test_add_task_success(self, mock_post, mock_get, runner):
        mock_get.side_effect = mock_get_with_users()
        mock_post.return_value = mock_response(200, SAMPLE_TASK)
        result = runner.invoke(
            cli,
            [
                "-b",
                "1",
                "add-task",
                "--title",
                "Fix login bug",
                "--description",
                "The login page crashes on submit",
                "--importance",
                "85",
                "--effort",
                "3",
                "--tags",
                "backend,urgent",
                "--blockers",
                "2",
            ],
            env={"TASKPLANNER_USERNAME": "alice"},
        )
        assert result.exit_code == 0
        assert "1" in result.output  # task ID
        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        assert "/api/v1/board/1/tasks/new" in call_url

    @patch("client_cli.cli.httpx.get")
    @patch("client_cli.cli.httpx.post")
    def test_add_task_with_assignee(self, mock_post, mock_get, runner):
        mock_get.side_effect = mock_get_with_users()
        mock_post.return_value = mock_response(200, SAMPLE_TASK)
        result = runner.invoke(
            cli,
            [
                "-b",
                "1",
                "add-task",
                "--title",
                "Test",
                "--assignee",
                "alice",
            ],
            env={"TASKPLANNER_USERNAME": "alice"},
        )
        assert result.exit_code == 0, f"output: {result.output}"

    @patch("client_cli.cli.httpx.post")
    def test_add_task_missing_title(self, mock_post, runner):
        result = runner.invoke(cli, ["-b", "1", "add-task"])
        assert result.exit_code != 0


# --- list (with -b flag) ---


class TestListTasks:
    @patch("client_cli.cli.httpx.get")
    def test_list_table_format(self, mock_get, runner):
        mock_get.return_value = mock_response(200, [SAMPLE_TASK, SAMPLE_TASK_MINIMAL])
        result = runner.invoke(cli, ["-b", "1", "list"])
        assert result.exit_code == 0
        assert "Fix login bug" in result.output
        assert "Write docs" in result.output
        call_url = mock_get.call_args[0][0]
        assert "/api/v1/board/1/tasks" in call_url

    @patch("client_cli.cli.httpx.get")
    def test_list_json_format(self, mock_get, runner):
        mock_get.return_value = mock_response(200, [SAMPLE_TASK])
        result = runner.invoke(cli, ["-b", "1", "list", "--format", "json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)
        assert parsed[0]["title"] == "Fix login bug"

    @patch("client_cli.cli.httpx.get")
    def test_list_with_filter(self, mock_get, runner):
        mock_get.return_value = mock_response(200, [SAMPLE_TASK])
        result = runner.invoke(cli, ["-b", "1", "list", "--filter", "STATUS=NEW,IMPORTANCE>=80"])
        assert result.exit_code == 0
        call_url = mock_get.call_args[0][0]
        assert "filter=" in call_url or mock_get.call_args[1].get("params", {}).get("filter")

    @patch("client_cli.cli.httpx.get")
    def test_list_with_template(self, mock_get, runner):
        mock_get.return_value = mock_response(200, [SAMPLE_TASK])
        result = runner.invoke(cli, ["-b", "1", "list", "-T", "{ID}: {TITLE} [{STATUS}]"])
        assert result.exit_code == 0
        assert "1: Fix login bug [NEW]" in result.output


# --- show-task (with -b flag) ---


class TestShowTask:
    @patch("client_cli.cli.httpx.get")
    def test_show_task_colored_output(self, mock_get, runner):
        def side_effect(url, *args, **kwargs):
            # Subtask, attachment, and comment list URLs return lists
            if "params" in kwargs or "/attachments" in url or "/comments" in url:
                return mock_response(200, [])
            if url.endswith("/tasks") or "/tasks?" in url:
                return mock_response(200, [])
            return mock_response(200, SAMPLE_TASK)
        mock_get.side_effect = side_effect
        result = runner.invoke(cli, ["-b", "1", "show-task", "1"])
        assert result.exit_code == 0
        assert "Fix login bug" in result.output
        assert "NEW" in result.output
        assert "85" in result.output

    @patch("client_cli.cli.httpx.get")
    def test_show_task_with_template(self, mock_get, runner):
        mock_get.return_value = mock_response(200, SAMPLE_TASK)
        result = runner.invoke(cli, ["-b", "1", "show-task", "1", "-T", "{ID}: {TITLE} [{STATUS}]"])
        assert result.exit_code == 0
        assert "1: Fix login bug [NEW]" in result.output

    @patch("client_cli.cli.httpx.get")
    def test_show_task_not_found(self, mock_get, runner):
        mock_get.return_value = mock_response(404, {"detail": "Not found"})
        result = runner.invoke(cli, ["-b", "1", "show-task", "999"])
        assert (
            result.exit_code != 0
            or "not found" in result.output.lower()
            or "error" in result.output.lower()
        )


# --- edit (unified) ---


class TestEdit:
    @patch("client_cli.cli.httpx.get")
    @patch("client_cli.cli.httpx.post")
    def test_edit_status(self, mock_post, mock_get, runner):
        mock_get.side_effect = mock_get_with_users()
        updated = {**SAMPLE_TASK, "status": "STARTED"}
        mock_post.return_value = mock_response(200, updated)
        result = runner.invoke(
            cli,
            ["-b", "1", "edit", "1", "--status", "STARTED"],
            env={"TASKPLANNER_USERNAME": "alice"},
        )
        assert result.exit_code == 0
        call_url = mock_post.call_args[0][0]
        assert "/api/v1/board/1/tasks/1/edit" in call_url
        body = mock_post.call_args[1].get("json", {})
        assert body.get("status") == "STARTED"

    @patch("client_cli.cli.httpx.get")
    @patch("client_cli.cli.httpx.post")
    def test_edit_properties(self, mock_post, mock_get, runner):
        mock_get.side_effect = mock_get_with_users()
        updated = {**SAMPLE_TASK, "title": "New title", "importance": 50}
        mock_post.return_value = mock_response(200, updated)
        result = runner.invoke(
            cli,
            [
                "-b",
                "1",
                "edit",
                "1",
                "--title",
                "New title",
                "--importance",
                "50",
            ],
            env={"TASKPLANNER_USERNAME": "alice"},
        )
        assert result.exit_code == 0

    @patch("client_cli.cli.httpx.get")
    @patch("client_cli.cli.httpx.post")
    def test_edit_assignee(self, mock_post, mock_get, runner):
        mock_get.side_effect = mock_get_with_users()
        updated = {**SAMPLE_TASK, "assignee_id": 1, "assignee_name": "Alice"}
        mock_post.return_value = mock_response(200, updated)
        result = runner.invoke(
            cli,
            ["-b", "1", "edit", "1", "--assignee", "alice"],
            env={"TASKPLANNER_USERNAME": "alice"},
        )
        assert result.exit_code == 0
        body = mock_post.call_args[1].get("json", {})
        assert body.get("assignee") == "alice"

    @patch("client_cli.cli.httpx.get")
    @patch("client_cli.cli.httpx.post")
    def test_edit_multiple(self, mock_post, mock_get, runner):
        mock_get.side_effect = mock_get_with_users()
        updated = {**SAMPLE_TASK, "status": "STARTED", "assignee_id": 1, "importance": 90}
        mock_post.return_value = mock_response(200, updated)
        result = runner.invoke(
            cli,
            [
                "-b",
                "1",
                "edit",
                "1",
                "--status",
                "STARTED",
                "--assignee",
                "alice",
                "--importance",
                "90",
            ],
            env={"TASKPLANNER_USERNAME": "alice"},
        )
        assert result.exit_code == 0


# --- add-comment (with -b flag) ---


class TestAddComment:
    @patch("client_cli.cli.httpx.get")
    @patch("client_cli.cli.httpx.post")
    def test_add_comment_success(self, mock_post, mock_get, runner):
        mock_get.side_effect = mock_get_with_users()
        mock_post.return_value = mock_response(200, SAMPLE_COMMENT)
        result = runner.invoke(
            cli,
            ["-b", "1", "add-comment", "1", "-m", "This is a comment"],
            env={"TASKPLANNER_USERNAME": "alice"},
        )
        assert result.exit_code == 0
        call_url = mock_post.call_args[0][0]
        assert "/api/v1/board/1/tasks/1/new_comment" in call_url


# --- list-users (global, no board needed) ---


class TestListUsers:
    @patch("client_cli.cli.httpx.get")
    def test_list_users(self, mock_get, runner):
        mock_get.return_value = mock_response(200, [SAMPLE_USER])
        result = runner.invoke(cli, ["list-users"])
        assert result.exit_code == 0
        assert "Alice" in result.output


# --- Template rendering ---


class TestTemplateRendering:
    def test_simple_interpolation(self):
        from client_cli.cli import render_template

        result = render_template("{ID}: {TITLE}", {"ID": 1, "TITLE": "Test"})
        assert result == "1: Test"

    def test_conditional_present(self):
        from client_cli.cli import render_template

        result = render_template(
            "{TITLE}{?ASSIGNEE_NAME} (assigned to {ASSIGNEE_NAME}){/ASSIGNEE_NAME}",
            {"TITLE": "Task", "ASSIGNEE_NAME": "Alice"},
        )
        assert result == "Task (assigned to Alice)"

    def test_conditional_absent(self):
        from client_cli.cli import render_template

        result = render_template(
            "{TITLE}{?ASSIGNEE_NAME} (assigned to {ASSIGNEE_NAME}){/ASSIGNEE_NAME}",
            {"TITLE": "Task", "ASSIGNEE_NAME": None},
        )
        assert result == "Task"

    def test_escaped_braces(self):
        from client_cli.cli import render_template

        result = render_template("{{not a field}} {TITLE}", {"TITLE": "Test"})
        assert result == "{not a field} Test"

    def test_list_field_joins(self):
        from client_cli.cli import render_template

        result = render_template("Tags: {TAGS}", {"TAGS": ["a", "b", "c"]})
        assert result == "Tags: a, b, c"


# --- Error handling ---


class TestErrorHandling:
    def test_invalid_subcommand(self, runner):
        result = runner.invoke(cli, ["nonexistent"])
        assert result.exit_code != 0

    @patch("client_cli.cli.httpx.get")
    def test_server_connection_error(self, mock_get, runner):
        mock_get.side_effect = httpx.ConnectError("Connection refused")
        result = runner.invoke(cli, ["-b", "1", "list"])
        assert (
            result.exit_code != 0
            or "error" in result.output.lower()
            or "connect" in result.output.lower()
        )


# serve command removed — server is now a separate entry point (TaskPlannerServer)


# --- Global options ---


class TestGlobalOptions:
    @patch("client_cli.cli.httpx.get")
    def test_custom_server_url(self, mock_get, runner):
        mock_get.return_value = mock_response(200, [])
        result = runner.invoke(cli, ["-s", "http://myserver:9000", "-b", "1", "list"])
        assert result.exit_code == 0
        call_url = mock_get.call_args[0][0]
        assert call_url.startswith("http://myserver:9000")

    @patch.dict("os.environ", {"TASKPLANNER_SERVER": "http://envserver:7000"})
    @patch("client_cli.cli.httpx.get")
    def test_server_url_from_env(self, mock_get, runner):
        mock_get.return_value = mock_response(200, [])
        result = runner.invoke(cli, ["-b", "1", "list"])
        assert result.exit_code == 0
        call_url = mock_get.call_args[0][0]
        assert call_url.startswith("http://envserver:7000")
