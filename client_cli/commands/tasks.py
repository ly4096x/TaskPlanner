"""Task commands: add-task, list, show-task, edit, add-comment + print_task_detail helper."""

import json
import os
from datetime import datetime

import click
import httpx

# Import get_board_id from cli (not helpers) so tests can patch client_cli.cli._find_env_board_id
from client_cli.cli import get_board_id
from client_cli.helpers import (
    _authed_get,
    _authed_post,
    get_auth_headers,
    get_server_url,
    handle_request_error,
    render_template,
    task_to_template_data,
)
from server.schema import (  # pyright: ignore[reportMissingImports]
    STATUS_CLI_COLORS as STATUS_COLORS,
)
from server.schema import STATUSES as VALID_STATUSES  # pyright: ignore[reportMissingImports]


def register(cli):
    """Register task commands with the CLI group."""
    cli.add_command(add_task)
    cli.add_command(list_tasks)
    cli.add_command(show_task)
    cli.add_command(edit_task_cmd)
    cli.add_command(add_comment)


def print_task_detail(url: str, board: int, task: dict, show_attachments: bool = True, headers: dict | None = None) -> None:
    """Print full task detail with description, attachments, and recent comments."""
    task_id = task["id"]

    # Header
    title = task["title"] or "(no title)"
    click.echo(click.style(f"#{task_id}  {title}", bold=True))

    # Status
    status = task["status"]
    color = STATUS_COLORS.get(status, None)
    click.echo(f"  Status:     {click.style(status, fg=color) if color else status}")

    # Importance
    imp = task["importance"]
    if imp >= 80:
        imp_str = click.style(str(imp), fg="red")
    elif imp >= 50:
        imp_str = click.style(str(imp), fg="yellow")
    else:
        imp_str = str(imp)
    click.echo(f"  Importance: {imp_str}")
    click.echo(f"  Effort:     {task['estimated_effort']}")

    # Assignee
    assignee = task.get("assignee_name") or "unassigned"
    assignee_username = task.get("assignee_username")
    if assignee_username:
        click.echo(f"  Assignee:   {assignee} ({assignee_username})")
    else:
        click.echo(f"  Assignee:   {assignee}")

    # Created time
    ts = task.get("created_time")
    if ts:
        dt = datetime.fromtimestamp(ts)
        click.echo(click.style(f"  Created:    {dt.strftime('%Y-%m-%d %H:%M')}"))

    # Parent task
    parent_id = task.get("parent_task_id")
    if parent_id:
        click.echo(f"  Parent:     #{parent_id}")

    # Tags
    if task.get("tags"):
        click.echo(f"  Tags:       {', '.join(task['tags'])}")

    # Blockers
    if task.get("blockers"):
        blockers_str = ", ".join(f"#{b}" for b in task["blockers"])
        click.echo(f"  Blockers:   {blockers_str}")

    # Description
    desc = task.get("description")
    if desc:
        click.echo()
        click.echo(click.style("Description:"))
        for line in desc.split("\n"):
            click.echo(f"  {line}")

    # Subtasks
    try:
        subtasks_resp = httpx.get(
            f"{url}/api/v1/board/{board}/tasks",
            params={"filter": f"PARENT={task_id}"},
            headers=headers or {},
        )
        if subtasks_resp.status_code == 200:
            subtasks = subtasks_resp.json()
            if subtasks:
                click.echo()
                click.echo(click.style(f"  Subtasks ({len(subtasks)}):"))
                for st in subtasks:
                    st_status = st.get("status", "")
                    st_color = STATUS_COLORS.get(st_status)
                    st_status_str = click.style(st_status, fg=st_color) if st_color else st_status
                    click.echo(f"    #{st['id']} [{st_status_str}] {st['title']}")
    except (httpx.ConnectError, httpx.HTTPStatusError):
        pass

    # Attachments
    if show_attachments:
        try:
            att_resp = httpx.get(f"{url}/api/v1/board/{board}/tasks/{task_id}/attachments", headers=headers or {})
            if att_resp.status_code == 200:
                atts = att_resp.json()
                if atts:
                    click.echo()
                    click.echo(click.style(f"  Attachments ({len(atts)}):"))
                    for a in atts:
                        size = a.get("size", 0)
                        if size < 1024:
                            size_str = f"{size} B"
                        elif size < 1024 * 1024:
                            size_str = f"{size / 1024:.1f} KB"
                        else:
                            size_str = f"{size / (1024 * 1024):.1f} MB"
                        ctype = a.get("content_type", "") or "unknown"
                        click.echo(f"    [{a['id']}] {a['original_name']}  ({size_str}, {ctype})")
        except (httpx.ConnectError, httpx.HTTPStatusError):
            pass

    # Recent comments
    try:
        comments_resp = httpx.get(f"{url}/api/v1/board/{board}/tasks/{task_id}/comments", headers=headers or {})
        if comments_resp.status_code == 200:
            all_comments = comments_resp.json()
            if all_comments:
                regular_comments = [c for c in all_comments if c.get("comment_type", "TEXT") == "TEXT"]
                if regular_comments:
                    recent = regular_comments[-5:]
                    click.echo()
                    click.echo(
                        click.style(
                            f"  Comments ({len(regular_comments)} regular, {len(all_comments)} total):",
                        )
                    )
                    for c in recent:
                        c_ts = datetime.fromtimestamp(c["created_time"]).strftime("%m/%d %H:%M")
                        author = c.get("commenter_username") or c.get("commenter_name") or "Unknown"
                        content = c["content"][:200].replace("\n", " ")
                        click.echo(f"    [{c_ts}]<{click.style(author, bold=True)}>: {content}")
    except (httpx.ConnectError, httpx.HTTPStatusError):
        pass


@click.command("add-task")
@click.option("--title", required=True, help="Task title")
@click.option("--description", default="", help="Task description")
@click.option("--assignee", default=None, type=str, help="Assignee username")
@click.option("--importance", default=0, type=int, help="Importance 0-100")
@click.option("--effort", default=0, type=int, help="Estimated effort >= 0")
@click.option("--tags", default=None, help="Comma-separated tag names")
@click.option("--blockers", default=None, help="Comma-separated task IDs")
@click.option("--start-now", is_flag=True, default=False, help="Create with STARTED status")
@click.option("--parent", "parent_task_id", default=None, type=int, help="Parent task ID")
@click.pass_context
def add_task(ctx, title, description, assignee, importance, effort, tags, blockers, start_now, parent_task_id):
    """Create a task."""
    url = get_server_url(ctx)
    board = get_board_id(ctx)
    body: dict = {
        "title": title,
        "description": description,
        "importance": importance,
        "estimated_effort": effort,
    }
    if start_now:
        body["status"] = "STARTED"
    if assignee is not None:
        body["assignee"] = assignee
    if tags:
        body["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
    if blockers:
        body["blockers"] = [int(x.strip()) for x in blockers.split(",") if x.strip()]
    if parent_task_id is not None:
        body["parent_task_id"] = parent_task_id
    try:
        resp = _authed_post(ctx, f"{url}/api/v1/board/{board}/tasks/new", json=body)
        resp.raise_for_status()
        task = resp.json()
        click.echo(f"Created task {task['id']}: {task['title']}")
    except (httpx.ConnectError, httpx.HTTPStatusError) as e:
        handle_request_error(e)


@click.command("list")
@click.option(
    "--filter",
    "-f",
    "filter_expr",
    default=None,
    help="Filter expression (default excludes CANCELLED and NOT_REPRODUCIBLE).",
)
@click.option(
    "--limit", "-L", "limit", type=int, default=100, help="Max tasks to show, 0 to show all"
)
@click.option("--template", "-T", default=None, help="Custom output template")
@click.option(
    "--format", "fmt", default="table", type=click.Choice(["table", "json"]), help="Output format"
)
@click.pass_context
def list_tasks(ctx, filter_expr, limit, template, fmt):
    """List tasks."""
    url = get_server_url(ctx)
    board = get_board_id(ctx)

    # Build request params
    params = {}

    if filter_expr is None:
        filter_expr = "STATUS!=CANCELLED,STATUS!=NOT_REPRODUCIBLE"

    params["filter"] = filter_expr
    params["sort"] = "importance_desc"
    if limit > 0:
        params["limit"] = str(limit)

    try:
        resp = _authed_get(ctx, f"{url}/api/v1/board/{board}/tasks", params=params)
        resp.raise_for_status()
        tasks = resp.json()
    except (httpx.ConnectError, httpx.HTTPStatusError) as e:
        handle_request_error(e)
        return

    if fmt == "json":
        click.echo(json.dumps(tasks))
        return

    if template:
        for task in tasks:
            data = task_to_template_data(task)
            click.echo(render_template(template, data))
        return

    # Table format
    if not tasks:
        click.echo("No tasks found.")
        return

    # Header
    click.echo(f"{'ID':<5} {'Title':<30} {'Status':<12} {'Imp':>4} {'Assignee':<15}")
    click.echo("-" * 70)
    for t in tasks:
        status = t.get("status", "")
        color = STATUS_COLORS.get(status, None)
        status_str = click.style(status, fg=color) if color else status
        assignee = t.get("assignee_name") or "-"
        click.echo(
            f"{t['id']:<5} {t['title']:<30} {status_str:<12} {t['importance']:>4} {assignee:<15}"
        )


@click.command("show-task")
@click.argument("task_id", type=int)
@click.option("--template", "-T", default=None, help="Custom output template")
@click.pass_context
def show_task(ctx, task_id, template):
    """Show task detail."""
    url = get_server_url(ctx)
    board = get_board_id(ctx)
    try:
        resp = _authed_get(ctx, f"{url}/api/v1/board/{board}/tasks/{task_id}")
        resp.raise_for_status()
        task = resp.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            click.echo(click.style(f"Error: Task {task_id} not found.", fg="red"), err=True)
            raise SystemExit(1)
        handle_request_error(e)
        return
    except httpx.ConnectError as e:
        handle_request_error(e)
        return

    if template:
        data = task_to_template_data(task)
        click.echo(render_template(template, data))
        return

    print_task_detail(url, board, task, headers=get_auth_headers(ctx))


@click.command("edit")
@click.argument("task_id", type=int)
@click.option("--status", default=None, type=click.Choice(VALID_STATUSES), help="Set status")
@click.option("--reason", "status_reason", default=None, type=str,
              help="Status change comment (required for non-admin when setting DONE/WAITING_FOR_COMMAND_EXECUTION/NOT_REPRODUCIBLE/CANCELLED)")
@click.option("--assignee", default=None, type=str, help="Assign to user (username)")
@click.option("--title", default=None, help="Set title")
@click.option("--description", default=None, help="Set description")
@click.option("--importance", default=None, type=int, help="Set importance 0-100")
@click.option("--effort", default=None, type=int, help="Set estimated effort")
@click.option("--parent", "parent_task_id", default=None, type=int, help="Set parent task ID (0 to clear)")
@click.pass_context
def edit_task_cmd(ctx, task_id, status, status_reason, assignee, title, description, importance, effort, parent_task_id):
    """Edit a task (status, assignee, title, description, importance, effort, parent)."""
    url = get_server_url(ctx)
    board = get_board_id(ctx)
    body: dict = {}
    if status is not None:
        body["status"] = status
    if status_reason is not None:
        body["status_reason"] = status_reason
    if assignee is not None:
        body["assignee"] = assignee
    if title is not None:
        body["title"] = title
    if description is not None:
        body["description"] = description
    if importance is not None:
        body["importance"] = importance
    if effort is not None:
        body["estimated_effort"] = effort
    if parent_task_id is not None:
        body["parent_task_id"] = parent_task_id if parent_task_id != 0 else None
    if not body:
        click.echo(
            "No changes specified. Use --status, --assignee, --title, --description, --importance, --effort, or --parent."
        )
        raise SystemExit(1)
    try:
        resp = _authed_post(ctx,
            f"{url}/api/v1/board/{board}/tasks/{task_id}/edit",
            json=body,
                    )
        resp.raise_for_status()
        task = resp.json()
        changes = []
        if status:
            changes.append(f"status={status}")
        if assignee:
            changes.append(f"assignee={task.get('assignee_name', assignee)}")
        if title:
            changes.append("title updated")
        if description is not None:
            changes.append("description updated")
        if importance is not None:
            changes.append(f"importance={importance}")
        if effort is not None:
            changes.append(f"effort={effort}")
        if parent_task_id is not None:
            changes.append(f"parent={parent_task_id}")
        click.echo(f'Task#{task_id}: "{task.get("title", "")}" — {", ".join(changes)}')

        # When starting a task, show full task detail (without attachments)
        if status == "STARTED":
            print_task_detail(url, board, task, show_attachments=False, headers=get_auth_headers(ctx))
    except (httpx.ConnectError, httpx.HTTPStatusError) as e:
        handle_request_error(e)


@click.command("add-comment")
@click.argument("task_id", type=int)
@click.option("--message", "-m", required=True, help="Comment text")
@click.option("--file", "-f", "files", multiple=True, type=click.Path(exists=True), help="File(s) to attach")
@click.option("--type", "-t", "comment_type", default="TEXT", type=click.Choice(["TEXT", "EXECUTION_LOG"], case_sensitive=False), help="Comment type")
@click.pass_context
def add_comment(ctx, task_id, message, files, comment_type):
    """Add comment to task, optionally uploading file attachments."""
    url = get_server_url(ctx)
    board = get_board_id(ctx)
    try:
        resp = _authed_post(ctx,
            f"{url}/api/v1/board/{board}/tasks/{task_id}/new_comment",
            json={"content": message, "comment_type": comment_type.upper()},
        )
        resp.raise_for_status()
        comment = resp.json()
        comment_id = comment["id"]
        click.echo(f"Comment {comment_id} added to task {task_id}.")

        # Upload attachments to the comment
        for filepath in files:
            filepath = os.path.abspath(filepath)
            filename = os.path.basename(filepath)
            with open(filepath, "rb") as fh:
                resp = _authed_post(ctx,
                    f"{url}/api/v1/board/{board}/tasks/{task_id}/comments/{comment_id}/upload",
                    files={"file": (filename, fh)},
                )
            resp.raise_for_status()
            att = resp.json()
            click.echo(f"Uploaded {filename} (attachment #{att['id']})")

    except (httpx.ConnectError, httpx.HTTPStatusError) as e:
        handle_request_error(e)
