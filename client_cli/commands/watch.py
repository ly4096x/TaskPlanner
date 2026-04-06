"""Watch command: SSE watcher for new actionable tasks."""

import click
import httpx

# Import get_board_id from cli (not helpers) so tests can patch client_cli.cli._find_env_board_id
from client_cli.cli import get_board_id
from client_cli.helpers import (
    _authed_get,
    _authed_post,
    get_server_url,
)


def register(cli):
    """Register the watch command with the CLI group."""
    cli.add_command(watch)


@click.command("watch")
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
            resp = _authed_post(ctx, f"{url}/api/v1/board/{board}/watch/stop", params=params, timeout=5)
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
        users_resp = _authed_get(ctx, f"{url}/api/v1/users")
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
        tasks_resp = _authed_get(ctx,
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
            verify_resp = _authed_get(ctx,
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

    token = ctx.obj.get("token", "")
    path = f"/api/v1/board/{board}/events?token={token}"

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
