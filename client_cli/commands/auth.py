"""Auth commands: whoami, create-token, list-tokens, revoke-token, set-role."""

from datetime import datetime

import click
import httpx

from client_cli.helpers import (
    _authed_get,
    _authed_post,
    get_auth_headers,
    get_server_url,
    handle_request_error,
    resolve_assignee,
)


def register(cli):
    """Register auth commands with the CLI group."""
    cli.add_command(whoami)
    cli.add_command(create_token)
    cli.add_command(list_tokens)
    cli.add_command(revoke_token)
    cli.add_command(set_role)


@click.command("whoami")
@click.pass_context
def whoami(ctx):
    """Show current authenticated user."""
    url = get_server_url(ctx)
    try:
        resp = _authed_get(ctx, f"{url}/api/v1/auth/me")
        resp.raise_for_status()
        user = resp.json()
        click.echo(f"Username: {user['username']}")
        click.echo(f"Display name: {user['display_name']}")
        click.echo(f"Role: {user.get('role') or 'member'}")
        click.echo(f"ID: {user['id']}")
    except (httpx.ConnectError, httpx.HTTPStatusError) as e:
        handle_request_error(e)


@click.command("create-token")
@click.option("--label", default="", help="Token label")
@click.option("--for-user", "for_user", default=None, help="Create token for another user (admin only)")
@click.pass_context
def create_token(ctx, label, for_user):
    """Create a new access token."""
    url = get_server_url(ctx)
    try:
        # Get current user ID
        me_resp = _authed_get(ctx, f"{url}/api/v1/auth/me")
        me_resp.raise_for_status()
        user_id = me_resp.json()["id"]

        if for_user:
            # Resolve target user
            target_id = resolve_assignee(url, for_user, get_auth_headers(ctx))
            user_id = target_id

        resp = _authed_post(ctx, f"{url}/api/v1/users/{user_id}/tokens", json={"label": label})
        resp.raise_for_status()
        data = resp.json()
        click.echo(f"Token created: {data['token']}")
        if label:
            click.echo(f"Label: {label}")
    except (httpx.ConnectError, httpx.HTTPStatusError) as e:
        handle_request_error(e)


@click.command("list-tokens")
@click.option("--user", "for_user", default=None, help="List tokens for user (admin only)")
@click.pass_context
def list_tokens(ctx, for_user):
    """List access tokens."""
    url = get_server_url(ctx)
    try:
        me_resp = _authed_get(ctx, f"{url}/api/v1/auth/me")
        me_resp.raise_for_status()
        user_id = me_resp.json()["id"]

        if for_user:
            user_id = resolve_assignee(url, for_user, get_auth_headers(ctx))

        resp = _authed_get(ctx, f"{url}/api/v1/users/{user_id}/tokens")
        resp.raise_for_status()
        tokens = resp.json()
        if not tokens:
            click.echo("No tokens found.")
            return
        for t in tokens:
            last_used = t.get("last_used_time")
            last_str = datetime.fromtimestamp(last_used).strftime("%Y-%m-%d %H:%M") if last_used else "never"
            click.echo(f"  #{t['id']}: label={t['label'] or '(none)'}, last_used={last_str}")
    except (httpx.ConnectError, httpx.HTTPStatusError) as e:
        handle_request_error(e)


@click.command("revoke-token")
@click.argument("token_id", type=int)
@click.pass_context
def revoke_token(ctx, token_id):
    """Revoke an access token."""
    url = get_server_url(ctx)
    try:
        me_resp = _authed_get(ctx, f"{url}/api/v1/auth/me")
        me_resp.raise_for_status()
        user_id = me_resp.json()["id"]

        resp = _authed_post(ctx, f"{url}/api/v1/users/{user_id}/tokens/{token_id}/revoke")
        resp.raise_for_status()
        click.echo(f"Token #{token_id} revoked.")
    except (httpx.ConnectError, httpx.HTTPStatusError) as e:
        handle_request_error(e)


@click.command("set-role")
@click.argument("username")
@click.argument("role", type=click.Choice(["admin", "member", "viewer"]))
@click.pass_context
def set_role(ctx, username, role):
    """Set a user's role (admin only)."""
    url = get_server_url(ctx)
    try:
        user_id = resolve_assignee(url, username, get_auth_headers(ctx))
        resp = _authed_post(ctx, f"{url}/api/v1/users/{user_id}", json={"role": role})
        resp.raise_for_status()
        click.echo(f"Set {username} role to {role}")
    except (httpx.ConnectError, httpx.HTTPStatusError) as e:
        handle_request_error(e)
