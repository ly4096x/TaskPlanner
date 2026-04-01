"""TaskPlanner CLI frontend.

Talks to the FastAPI server via HTTP using httpx.
Entry point: client_cli.cli:main (registered as TaskPlanner script).
"""

import json
import os
import re
from datetime import datetime

import click
import httpx

# --- Template renderer (client-side, no server imports) ---


def render_template(template: str, data: dict) -> str:
    """Render a template string with field interpolation.

    Supports:
    - {FIELD} interpolation
    - {?FIELD}...{/FIELD} conditionals (render block if field is truthy/non-empty)
    - {{ / }} for literal braces
    - List fields are joined with ", "
    """
    result = template

    # Handle conditionals first: {?FIELD}...{/FIELD}
    def replace_conditional(m):
        field = m.group(1)
        body = m.group(2)
        value = data.get(field)
        if value is not None and value != "" and value != [] and value != 0:
            # Recursively render the body
            return render_template(body, data)
        return ""

    result = re.sub(r"\{\?(\w+)\}(.*?)\{/\1\}", replace_conditional, result, flags=re.DOTALL)

    # Handle field interpolation: {FIELD}
    def replace_field(m):
        field = m.group(1)
        value = data.get(field, "")
        if isinstance(value, list):
            return ", ".join(str(v) for v in value)
        return str(value) if value is not None else ""

    result = re.sub(r"\{(\w+)\}", replace_field, result)

    # Handle escaped braces
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


# --- Status colors ---

STATUS_COLORS = {
    "NEW": "green",
    "STARTED": "yellow",
    "WAITING_FOR_COMMAND_EXECUTION": "cyan",
    "DONE": "magenta",
    "BLOCKED": "bright_red",
    "NOT_REPRODUCIBLE": "bright_yellow",
    "CANCELLED": "red",
}

VALID_STATUSES = list(STATUS_COLORS.keys())


# --- Helpers ---


def get_server_url(ctx: click.Context) -> str:
    return ctx.obj["server"]


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


def resolve_assignee(url: str, assignee: str) -> int:
    """Resolve username to integer user ID."""
    # Look up by username
    try:
        resp = httpx.get(f"{url}/api/v1/users")
        resp.raise_for_status()
        users = resp.json()
        for u in users:
            if u.get("username") == assignee:
                return u["id"]
    except (httpx.ConnectError, httpx.HTTPStatusError):
        pass
    click.echo(click.style(f"Error: User '{assignee}' not found.", fg="red"), err=True)
    raise SystemExit(1)


def get_acting_user_id(ctx: click.Context) -> int:
    """Get acting user ID from TASKPLANNER_USERNAME env var. Required for mutation commands."""
    user = ctx.obj.get("user")
    if user is None:
        click.echo(
            click.style(
                "Error: set TASKPLANNER_USERNAME env var",
                fg="red",
            ),
            err=True,
        )
        raise SystemExit(1)
    url = get_server_url(ctx)
    return resolve_assignee(url, user)


def get_acting_username(ctx: click.Context) -> str:
    """Get acting username from TASKPLANNER_USERNAME env var."""
    user = ctx.obj.get("user")
    if user is None:
        click.echo(
            click.style(
                "Error: set TASKPLANNER_USERNAME env var",
                fg="red",
            ),
            err=True,
        )
        raise SystemExit(1)
    return user


def make_agent_identity(session_id: str, subagent_id: str | None = None):
    """Build (username, display_name, external_id) from agent session/subagent IDs.

    Main agent:  username=agent_<session>, display="Agent <first6>", ext=agent:<session>
    Subagent:    username=agent_<session>_sub_<subagent>, display="Agent <first6>_<first4>", ext=agent:<session>:<subagent>
    All IDs lowercased, hyphens replaced with underscores in username.
    """
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


def handle_request_error(e: Exception):
    """Print a friendly error message for connection/request errors."""
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


# --- CLI group ---


@click.group()
@click.option("--server", "-s", default=None, help="Server URL (default: http://localhost:8000)")
@click.option(
    "--board", "-b", type=int, default=None, help="Board ID (or set TASKPLANNER_BOARD_ID in .env)"
)
@click.pass_context
def cli(ctx, server, board):
    """TaskPlanner -- task management CLI."""
    ctx.ensure_object(dict)
    url = server or os.environ.get("TASKPLANNER_SERVER", "http://localhost:8000")
    ctx.obj["server"] = url.rstrip("/")
    ctx.obj["board"] = board
    ctx.obj["user"] = os.environ.get("TASKPLANNER_USERNAME")


# --- Board commands ---


@cli.command("create-board")
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
        resp = httpx.post(f"{url}/api/v1/boards/new", json=body)
        resp.raise_for_status()
        board = resp.json()
        click.echo(f"Created board {board['id']}: {board['name']}")
    except (httpx.ConnectError, httpx.HTTPStatusError) as e:
        handle_request_error(e)


@cli.command("list-boards")
@click.pass_context
def list_boards(ctx):
    """List all boards."""
    url = get_server_url(ctx)
    try:
        resp = httpx.get(f"{url}/api/v1/boards")
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


@cli.command("show-board")
@click.argument("board_id", type=int)
@click.pass_context
def show_board(ctx, board_id):
    """Show board details."""
    url = get_server_url(ctx)
    try:
        resp = httpx.get(f"{url}/api/v1/board/{board_id}")
        resp.raise_for_status()
        board = resp.json()
        click.echo(click.style(board["name"], bold=True))
        if board.get("description"):
            click.echo(f"  {board['description']}")
        click.echo(f"  ID: {board['id']}")
    except (httpx.ConnectError, httpx.HTTPStatusError) as e:
        handle_request_error(e)


# --- add-user (global) ---


@cli.command("add-user")
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
        resp = httpx.post(f"{url}/api/v1/users/new", json=body)
        resp.raise_for_status()
        user = resp.json()
        click.echo(
            f"Created user {user['username']}: {user['display_name']} ({user['external_id']})"
        )
    except (httpx.ConnectError, httpx.HTTPStatusError) as e:
        handle_request_error(e)


# --- list-users (global) ---


@cli.command("list-users")
@click.pass_context
def list_users(ctx):
    """List all users."""
    url = get_server_url(ctx)
    try:
        resp = httpx.get(f"{url}/api/v1/users")
        resp.raise_for_status()
        users = resp.json()
        if not users:
            click.echo("No users found.")
            return
        for u in users:
            click.echo(f"  {u['username']}: {u['display_name']} ({u['external_id']})")
    except (httpx.ConnectError, httpx.HTTPStatusError) as e:
        handle_request_error(e)


# --- show-user ---


@cli.command("show-user")
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
        resp = httpx.get(f"{url}/api/v1/users")
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


# --- add-task ---


@cli.command("add-task")
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
    get_acting_user_id(ctx)  # validate actor exists
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
        resp = httpx.post(f"{url}/api/v1/board/{board}/tasks/new", json=body)
        resp.raise_for_status()
        task = resp.json()
        click.echo(f"Created task {task['id']}: {task['title']}")
    except (httpx.ConnectError, httpx.HTTPStatusError) as e:
        handle_request_error(e)


# --- list ---


@cli.command("list")
@click.option(
    "--filter",
    "-f",
    "filter_expr",
    default=None,
    help="Filter expression, default filter shows open task for current user.",
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
        resp = httpx.get(f"{url}/api/v1/board/{board}/tasks", params=params)
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


# --- Task detail helpers ---



def print_task_detail(url: str, board: int, task: dict, show_attachments: bool = True) -> None:
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
            att_resp = httpx.get(f"{url}/api/v1/board/{board}/tasks/{task_id}/attachments")
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
        comments_resp = httpx.get(f"{url}/api/v1/board/{board}/tasks/{task_id}/comments")
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


# --- show-task ---


@cli.command("show-task")
@click.argument("task_id", type=int)
@click.option("--template", "-T", default=None, help="Custom output template")
@click.pass_context
def show_task(ctx, task_id, template):
    """Show task detail."""
    url = get_server_url(ctx)
    board = get_board_id(ctx)
    try:
        resp = httpx.get(f"{url}/api/v1/board/{board}/tasks/{task_id}")
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

    print_task_detail(url, board, task)


# --- edit (unified) ---


@cli.command("edit")
@click.argument("task_id", type=int)
@click.option("--status", default=None, type=click.Choice(VALID_STATUSES), help="Set status")
@click.option("--assignee", default=None, type=str, help="Assign to user (username)")
@click.option("--title", default=None, help="Set title")
@click.option("--description", default=None, help="Set description")
@click.option("--importance", default=None, type=int, help="Set importance 0-100")
@click.option("--effort", default=None, type=int, help="Set estimated effort")
@click.option("--parent", "parent_task_id", default=None, type=int, help="Set parent task ID (0 to clear)")
@click.pass_context
def edit_task_cmd(ctx, task_id, status, assignee, title, description, importance, effort, parent_task_id):
    """Edit a task (status, assignee, title, description, importance, effort, parent)."""
    url = get_server_url(ctx)
    board = get_board_id(ctx)
    actor_username = get_acting_username(ctx)
    body: dict = {}
    if status is not None:
        body["status"] = status
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
        resp = httpx.post(
            f"{url}/api/v1/board/{board}/tasks/{task_id}/edit",
            json=body,
            headers={"X-Actor-Username": actor_username},
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
            print_task_detail(url, board, task, show_attachments=False)
    except (httpx.ConnectError, httpx.HTTPStatusError) as e:
        handle_request_error(e)


# --- add-comment ---


@cli.command("add-comment")
@click.argument("task_id", type=int)
@click.option("--message", "-m", required=True, help="Comment text")
@click.option("--file", "-f", "files", multiple=True, type=click.Path(exists=True), help="File(s) to attach")
@click.option("--type", "-t", "comment_type", default="TEXT", type=click.Choice(["TEXT", "EXECUTION_LOG"], case_sensitive=False), help="Comment type")
@click.pass_context
def add_comment(ctx, task_id, message, files, comment_type):
    """Add comment to task, optionally uploading file attachments."""
    url = get_server_url(ctx)
    board = get_board_id(ctx)
    actor_username = get_acting_username(ctx)
    try:
        # Create comment first (with username)
        resp = httpx.post(
            f"{url}/api/v1/board/{board}/tasks/{task_id}/new_comment",
            json={"content": message, "commenter": actor_username, "comment_type": comment_type.upper()},
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
                resp = httpx.post(
                    f"{url}/api/v1/board/{board}/tasks/{task_id}/comments/{comment_id}/upload",
                    files={"file": (filename, fh)},
                )
            resp.raise_for_status()
            att = resp.json()
            click.echo(f"Uploaded {filename} (attachment #{att['id']})")

    except (httpx.ConnectError, httpx.HTTPStatusError) as e:
        handle_request_error(e)


# --- watch ---


@cli.command("watch")
@click.option("--agent-id", default="main", help="Agent identifier for filtering tasks")
@click.option(
    "--session-id", default=None, help="Session identifier, written to lock file for targeted kill"
)
@click.option("--stop", "stop_watch", is_flag=True, default=False, help="Stop any running watcher for this board")
@click.pass_context
def watch(ctx, agent_id, session_id, stop_watch):
    """Watch for new tasks via SSE. Exits with code 2 when an actionable task appears.

    Used by asyncRewake hooks to wake the agent when new work arrives.
    Only wakes for tasks that are:
    - NEW and unassigned (available for pickup)
    - NEW/STARTED and assigned to this agent

    Use --stop to send a stop signal to any running watcher on this board.
    """
    if stop_watch:
        url = get_server_url(ctx)
        board = get_board_id(ctx)
        try:
            params = {}
            if session_id:
                params["session_id"] = session_id
            resp = httpx.post(f"{url}/api/v1/board/{board}/watch/stop", params=params, timeout=5)
            resp.raise_for_status()
        except (httpx.ConnectError, httpx.HTTPStatusError):
            pass
        return
    import http.client
    import json as _json
    import sys as _sys
    import time
    import urllib.parse

    url = get_server_url(ctx)
    board = get_board_id(ctx)

    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 8000

    # Resolve agent's user ID

    agent_username = ctx.obj.get("user") or ("agent_" + agent_id.lower().replace("-", "_"))
    agent_user_id = None
    try:
        users_resp = httpx.get(f"{url}/api/v1/users")
        if users_resp.status_code == 200:
            for u in users_resp.json():
                if u.get("username") == agent_username:
                    agent_user_id = u["id"]
                    break
    except (httpx.ConnectError, httpx.HTTPStatusError):
        pass

    # Snapshot existing task IDs at watch start — ignore events for these
    known_task_ids = set()
    try:
        tasks_resp = httpx.get(
            f"{url}/api/v1/board/{board}/tasks",
            params={"limit": "1000"},
            timeout=5,
        )
        if tasks_resp.status_code == 200:
            known_task_ids = {t["id"] for t in tasks_resp.json()}
    except (httpx.ConnectError, httpx.HTTPStatusError):
        pass

    def is_actionable(task_id_from_event, event_type):
        """Re-fetch task from API to verify it's still actionable."""
        try:
            # Ignore task_created for tasks that existed before watch started
            if event_type == "task_created" and task_id_from_event in known_task_ids:
                return False

            time.sleep(5)  # debounce: let rapid status changes settle
            verify_resp = httpx.get(
                f"{url}/api/v1/board/{board}/tasks/{task_id_from_event}", timeout=5
            )
            if verify_resp.status_code != 200:
                return False
            task = verify_resp.json()
            status = task.get("status", "")
            assignee_id = task.get("assignee_id")
            if status == "NEW" and assignee_id is None:
                return True  # unassigned, available for pickup
            if status == "NEW" and agent_user_id and assignee_id == agent_user_id:
                return True  # new task assigned to this agent
            # For task_updated on existing tasks: STARTED assigned to agent means
            # someone assigned/reopened a task for this agent
            if (
                event_type == "task_updated"
                and status == "STARTED"
                and agent_user_id
                and assignee_id == agent_user_id
            ):
                return True
            return False
        except (httpx.ConnectError, httpx.HTTPStatusError):
            return False

    path = f"/api/v1/board/{board}/events"

    conn: http.client.HTTPConnection | None = None
    while True:
        try:
            conn = http.client.HTTPConnection(host, port, timeout=60)
            conn.request("GET", path, headers={"Accept": "text/event-stream"})
            resp = conn.getresponse()

            if resp.status != 200:
                click.echo(f"SSE connection failed: {resp.status}", err=True)
                time.sleep(5)
                continue

            buffer = ""
            while True:
                chunk = resp.read(1).decode("utf-8", errors="replace")
                if not chunk:
                    break  # connection closed
                buffer += chunk
                if buffer.endswith("\n\n"):
                    for line in buffer.strip().split("\n"):
                        if line.startswith("data: "):
                            data_str = line[6:]
                            try:
                                event = _json.loads(data_str)
                                etype = event.get("type", "")
                                edata = event.get("data", {})
                                if etype == "watch_stop":
                                    # Check if this stop targets our session
                                    stop_sid = edata.get("session_id")
                                    if stop_sid is None or stop_sid == session_id:
                                        _sys.exit(0)
                                elif etype in ("task_created", "task_updated"):
                                    task_id = edata.get("id")
                                    if task_id and is_actionable(task_id, etype):
                                        status = edata.get("status", "")
                                        from datetime import datetime as _dt

                                        click.echo(
                                            f"[{_dt.now().strftime('%H:%M:%S')}] New actionable task: #{task_id} [{status}]. Check `TaskPlanner show-task {task_id}` for details."
                                        )
                                        _sys.exit(2)
                            except _json.JSONDecodeError:
                                pass
                    buffer = ""

        except (ConnectionRefusedError, OSError, http.client.IncompleteRead):
            # Server not running, wait and retry
            time.sleep(10)
        except Exception as e:
            click.echo(f"Watch error: {e}", err=True)
            time.sleep(5)
        finally:
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass


# --- Entry point ---


def main():
    cli()


if __name__ == "__main__":
    main()
