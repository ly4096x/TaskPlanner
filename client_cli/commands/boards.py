"""Board commands: create-board, list-boards, show-board."""

import click
import httpx

from client_cli.helpers import (
    _authed_get,
    _authed_post,
    get_server_url,
    handle_request_error,
)


def register(cli):
    """Register board commands with the CLI group."""
    cli.add_command(create_board)
    cli.add_command(list_boards)
    cli.add_command(show_board)


@click.command("create-board")
@click.option("--name", required=True, help="Board name")
@click.option("--description", default="", help="Board description")
@click.pass_context
def create_board(ctx, name, description):
    """Create a new board."""
    url = get_server_url(ctx)
    body = {"name": name}
    if description:
        body["description"] = description
    try:
        resp = _authed_post(ctx, f"{url}/api/v1/boards/new", json=body)
        resp.raise_for_status()
        board = resp.json()
        click.echo(f"Created board {board['id']}: {board['name']}")
    except (httpx.ConnectError, httpx.HTTPStatusError) as e:
        handle_request_error(e)


@click.command("list-boards")
@click.pass_context
def list_boards(ctx):
    """List all boards."""
    url = get_server_url(ctx)
    try:
        resp = _authed_get(ctx, f"{url}/api/v1/boards")
        resp.raise_for_status()
        boards = resp.json()
        if not boards:
            click.echo("No boards found.")
            return
        for b in boards:
            desc = f" - {b['description']}" if b.get("description") else ""
            click.echo(f"  {b['id']}: {b['name']}{desc}")
    except (httpx.ConnectError, httpx.HTTPStatusError) as e:
        handle_request_error(e)


@click.command("show-board")
@click.argument("board_id", type=int)
@click.pass_context
def show_board(ctx, board_id):
    """Show board details."""
    url = get_server_url(ctx)
    try:
        resp = _authed_get(ctx, f"{url}/api/v1/board/{board_id}")
        resp.raise_for_status()
        board = resp.json()
        click.echo(click.style(board["name"], bold=True))
        if board.get("description"):
            click.echo(f"  {board['description']}")
        click.echo(f"  ID: {board['id']}")
    except (httpx.ConnectError, httpx.HTTPStatusError) as e:
        handle_request_error(e)
