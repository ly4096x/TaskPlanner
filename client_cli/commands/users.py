"""User commands: add-user, list-users, show-user."""

import click
import httpx

from client_cli.helpers import (
    _authed_get,
    _authed_post,
    get_server_url,
    handle_request_error,
    make_agent_identity,
    render_template,
)


def register(cli):
    """Register user commands with the CLI group."""
    cli.add_command(add_user)
    cli.add_command(list_users)
    cli.add_command(show_user)


@click.command("add-user")
@click.option("--username", default=None, help="Username (a-z only, min 3 chars)")
@click.option("--display-name", default=None, help="Display name")
@click.option("--external-id", default=None, help="External identifier")
@click.option(
    "--agent-session-id",
    default=None,
    help="Agent session ID (auto-generates username/display/external_id)",
)
@click.option("--subagent-id", default=None, help="Subagent ID (use with --agent-session-id)")
@click.option("--report-to", default=None, help="Username this user reports to")
@click.pass_context
def add_user(ctx, username, display_name, external_id, agent_session_id, subagent_id, report_to):
    """Create a user.

    Either provide --username (with --external-id and --display-name),
    or --agent-session-id (optionally with --subagent-id) to auto-generate fields.
    --display-name can override the auto-generated display name.
    """
    if agent_session_id:
        gen_username, gen_display, gen_ext = make_agent_identity(agent_session_id, subagent_id)
        username = username or gen_username
        display_name = display_name or gen_display
        external_id = external_id or gen_ext
    elif not username:
        click.echo(
            click.style("Error: provide --username or --agent-session-id", fg="red"), err=True
        )
        raise SystemExit(1)

    if not display_name or not external_id:
        click.echo(
            click.style(
                "Error: --display-name and --external-id are required when not using --agent-session-id",
                fg="red",
            ),
            err=True,
        )
        raise SystemExit(1)

    url = get_server_url(ctx)
    body = {"external_id": external_id, "username": username, "display_name": display_name}
    if report_to is not None:
        body["report_to"] = report_to
    try:
        resp = _authed_post(ctx, f"{url}/api/v1/users", json=body)
        resp.raise_for_status()
        user = resp.json()
        click.echo(
            f"Created user {user['username']}: {user['display_name']} ({user['external_id']})"
        )
    except (httpx.ConnectError, httpx.HTTPStatusError) as e:
        handle_request_error(e)


@click.command("list-users")
@click.pass_context
def list_users(ctx):
    """List all users."""
    url = get_server_url(ctx)
    try:
        resp = _authed_get(ctx, f"{url}/api/v1/users")
        resp.raise_for_status()
        users = resp.json()
        if not users:
            click.echo("No users found.")
            return
        for u in users:
            click.echo(f"  {u['username']}: {u['display_name']} ({u['external_id']})")
    except (httpx.ConnectError, httpx.HTTPStatusError) as e:
        handle_request_error(e)


@click.command("show-user")
@click.option("--username", default=None, help="Look up by username")
@click.option(
    "--agent-session-id", default=None, help="Look up by agent session ID (finds main agent user)"
)
@click.option("--subagent-id", default=None, help="Subagent ID (use with --agent-session-id)")
@click.option("--template", default=None, help="Output template (e.g. '{username} {display_name}')")
@click.pass_context
def show_user(ctx, username, agent_session_id, subagent_id, template):
    """Show a user's info by username or agent identity."""
    if not username and not agent_session_id:
        click.echo(
            click.style("Error: provide --username or --agent-session-id", fg="red"), err=True
        )
        raise SystemExit(1)
    if subagent_id and not agent_session_id:
        click.echo(
            click.style("Error: --subagent-id requires --agent-session-id", fg="red"), err=True
        )
        raise SystemExit(1)

    url = get_server_url(ctx)
    users = []
    try:
        resp = _authed_get(ctx, f"{url}/api/v1/users")
        resp.raise_for_status()
        users = resp.json()
    except (httpx.ConnectError, httpx.HTTPStatusError) as e:
        handle_request_error(e)

    match = None
    if username:
        for u in users:
            if u["username"] == username:
                match = u
                break
    elif agent_session_id:
        _, _, ext_id = make_agent_identity(agent_session_id, subagent_id)
        for u in users:
            if u["external_id"] == ext_id:
                match = u
                break

    if not match:
        click.echo(click.style("User not found.", fg="red"), err=True)
        raise SystemExit(1)

    if template:
        click.echo(render_template(template, match))
    else:
        click.echo(f"id: {match['id']}")
        click.echo(f"username: {match['username']}")
        click.echo(f"display_name: {match['display_name']}")
        click.echo(f"external_id: {match['external_id']}")
