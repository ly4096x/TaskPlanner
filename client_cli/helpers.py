"""Shared helpers for the TaskPlanner CLI."""

import os
import re

import click
import httpx

# --- Template renderer ---


def render_template(template: str, data: dict) -> str:
    """Render a template string with field interpolation."""
    result = template

    def replace_conditional(m):
        field = m.group(1)
        body = m.group(2)
        value = data.get(field)
        if value is not None and value != "" and value != [] and value != 0:
            return render_template(body, data)
        return ""

    result = re.sub(r"\{\?(\w+)\}(.*?)\{/\1\}", replace_conditional, result, flags=re.DOTALL)

    def replace_field(m):
        field = m.group(1)
        value = data.get(field, "")
        if isinstance(value, list):
            return ", ".join(str(v) for v in value)
        return str(value) if value is not None else ""

    result = re.sub(r"\{(\w+)\}", replace_field, result)
    result = result.replace("{{", "{").replace("}}", "}")
    return result


def task_to_template_data(task: dict) -> dict:
    """Convert a task API response dict to template-friendly keys."""
    return {
        "ID": task.get("id", ""),
        "TITLE": task.get("title", ""),
        "STATUS": task.get("status", ""),
        "DESCRIPTION": task.get("description", ""),
        "ASSIGNEE": task.get("assignee_name") or "",
        "ASSIGNEE_NAME": task.get("assignee_name") or "",
        "ASSIGNEE_ID": task.get("assignee_id") or "",
        "IMPORTANCE": task.get("importance", 0),
        "ESTIMATED_EFFORT": task.get("estimated_effort", 0),
        "CREATED_TIME": task.get("created_time", ""),
        "TAGS": task.get("tags", []),
        "BLOCKERS": task.get("blockers", []),
        "PARENT": task.get("parent_task_id") or "",
        "PARENT_TITLE": task.get("parent_title") or "",
    }


# --- URL / Board / Auth helpers ---


def get_server_url(ctx: click.Context) -> str:
    return ctx.obj["server"]


def _find_env_board_id() -> int | None:
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


def resolve_assignee(url: str, assignee: str, headers: dict | None = None) -> int:
    try:
        resp = httpx.get(f"{url}/api/v1/users", headers=headers or {})
        resp.raise_for_status()
        users = resp.json()
        for u in users:
            if u.get("username") == assignee:
                return u["id"]
    except (httpx.ConnectError, httpx.HTTPStatusError):
        pass
    click.echo(click.style(f"Error: User '{assignee}' not found.", fg="red"), err=True)
    raise SystemExit(1)


def get_auth_headers(ctx: click.Context) -> dict:
    token = ctx.obj.get("token")
    if not token:
        click.echo(
            click.style(
                "Error: set TASKPLANNER_USER_ACCESS_TOKEN env var or use --user-access-token/-u",
                fg="red",
            ),
            err=True,
        )
        raise SystemExit(1)
    return {"Authorization": f"Bearer {token}"}


def _authed_get(ctx, url, **kwargs):
    kwargs.setdefault("headers", {}).update(get_auth_headers(ctx))
    return httpx.get(url, **kwargs)


def _authed_post(ctx, url, **kwargs):
    kwargs.setdefault("headers", {}).update(get_auth_headers(ctx))
    return httpx.post(url, **kwargs)


def handle_request_error(e: Exception):
    if isinstance(e, httpx.ConnectError):
        click.echo(
            click.style("Error: Could not connect to server. Is it running?", fg="red"), err=True
        )
    elif isinstance(e, httpx.HTTPStatusError):
        try:
            detail = e.response.json().get("detail", str(e))
        except Exception:
            detail = e.response.text or str(e)
        click.echo(click.style(f"Error: {detail}", fg="red"), err=True)
    else:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
    raise SystemExit(1)


def make_agent_identity(session_id: str, subagent_id: str | None = None):
    safe_session = session_id.lower().replace("-", "_")
    session_short = session_id.replace("-", "")[:6]
    if subagent_id:
        safe_subagent = subagent_id.lower().replace("-", "_")
        subagent_short = subagent_id.replace("-", "")[:4]
        username = f"agent_{safe_session}_sub_{safe_subagent}"
        display_name = f"Agent {session_short}_{subagent_short}"
        ext_id = f"agent:{session_id}:{subagent_id}"
    else:
        username = f"agent_{safe_session}"
        display_name = f"Agent {session_short}"
        ext_id = f"agent:{session_id}"
    return username, display_name, ext_id
