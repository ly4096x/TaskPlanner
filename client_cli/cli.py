"""TaskPlanner CLI frontend.

Talks to the FastAPI server via HTTP using httpx.
Entry point: client_cli.cli:main (registered as TaskPlanner script).
"""

import os

import click
import httpx  # noqa: F401 — tests patch client_cli.cli.httpx

from client_cli.helpers import (  # noqa: F401
    _authed_get,
    _authed_post,
    get_auth_headers,
    get_server_url,
    handle_request_error,
    make_agent_identity,
    render_template,
    resolve_assignee,
    task_to_template_data,
)

# --- Board ID resolution (re-defined here so tests can patch client_cli.cli._find_env_board_id) ---


def _find_env_board_id() -> int | None:
    """Walk up from CWD looking for .env with TASKPLANNER_BOARD_ID=."""
    from pathlib import Path

    d = Path.cwd().resolve()
    while True:
        env_file = d / ".env"
        if env_file.is_file():
            try:
                for line in env_file.read_text().splitlines():
                    line = line.strip()
                    if line.startswith("TASKPLANNER_BOARD_ID=") and not line.startswith("#"):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        return int(val)
            except (ValueError, OSError):
                pass
        parent = d.parent
        if parent == d:
            break
        d = parent
    return None


def get_board_id(ctx: click.Context) -> int:
    """Get board ID from --board flag, TASKPLANNER_BOARD_ID env var, or .env file."""
    board = ctx.obj.get("board")
    if board is None:
        env_board = os.environ.get("TASKPLANNER_BOARD_ID")
        if env_board:
            try:
                board = int(env_board)
            except ValueError:
                pass
    if board is None:
        board = _find_env_board_id()
    if board is None:
        click.echo(
            click.style(
                "Error: --board/-b option, TASKPLANNER_BOARD_ID env var, or TASKPLANNER_BOARD_ID in .env is required.",
                fg="red",
            ),
            err=True,
        )
        raise SystemExit(1)
    return board


# --- CLI group ---


@click.group()
@click.option("--server", "-s", default=None, help="Server URL (default: http://localhost:8000)")
@click.option(
    "--board", "-b", type=int, default=None, help="Board ID (or set TASKPLANNER_BOARD_ID in .env)"
)
@click.option(
    "--user-access-token", "-u", default=None, help="Access token (or set TASKPLANNER_USER_ACCESS_TOKEN)"
)
@click.pass_context
def cli(ctx, server, board, user_access_token):
    """TaskPlanner -- task management CLI."""
    ctx.ensure_object(dict)
    url = server or os.environ.get("TASKPLANNER_SERVER", "http://localhost:8000")
    ctx.obj["server"] = url.rstrip("/")
    ctx.obj["board"] = board
    token = user_access_token or os.environ.get("TASKPLANNER_USER_ACCESS_TOKEN")
    ctx.obj["token"] = token
    ctx.obj["user"] = None  # deprecated, kept for compat


# Register all command modules
from client_cli.commands import auth, boards, claude_hook, tasks, users, watch  # noqa: E402

boards.register(cli)
users.register(cli)
tasks.register(cli)
auth.register(cli)
watch.register(cli)
claude_hook.register(cli)


# --- Entry point ---


def main():
    cli()


if __name__ == "__main__":
    main()
