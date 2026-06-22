"""Claude Code hook command and helper functions."""

import json
import os
import re
import shlex
from pathlib import Path

import click
import httpx

# Import get_board_id from cli (not helpers) so tests can patch client_cli.cli._find_env_board_id
from client_cli.cli import get_board_id
from client_cli.helpers import (
    get_server_url,
)


def _hook_export_env(pairs: dict) -> None:
    """Append/replace export lines in CLAUDE_ENV_FILE so the agent's shell inherits them."""
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    if not env_file or not pairs:
        return
    path = Path(env_file)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        existing: dict[str, str] = {}
        order: list[str] = []
        if path.exists():
            for raw in path.read_text().splitlines():
                line = raw.strip()
                if line.startswith("export ") and "=" in line:
                    key = line.removeprefix("export ").split("=", 1)[0].strip()
                    if key not in existing:
                        order.append(key)
                    existing[key] = line
        for k, v in pairs.items():
            if k not in existing:
                order.append(k)
            existing[k] = f"export {k}={v}"
        path.write_text("\n".join(existing[k] for k in order) + "\n")
    except OSError:
        pass


def register(cli):
    """Register the claude-hook command with the CLI group."""
    cli.add_command(claude_hook)


# --- Hook helpers ---


def _hook_output(data):
    """Print hook JSON response to stdout."""
    click.echo(json.dumps(data))


def _hook_deny(reason):
    """Output a PreToolUse deny response."""
    _hook_output({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    })


def _hook_get_auth_headers(ctx):
    """Get auth headers for hook — returns empty dict if no token (graceful)."""
    token = ctx.obj.get("token")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def _hook_api_get(url, headers):
    """GET with error handling — returns response or None."""
    try:
        resp = httpx.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def _hook_api_post(url, headers, json_data=None):
    """POST with error handling — returns response or None."""
    try:
        resp = httpx.post(url, headers=headers, json=json_data, timeout=5)
        if resp.status_code in (200, 201):
            return resp.json()
    except Exception:
        pass
    return None


def _hook_make_agent_identity(session_id, subagent_id=None):
    """Build (username, display_name, external_id) from session/subagent IDs."""
    session_clean = session_id.replace("-", "_")
    if subagent_id and subagent_id != "main":
        sub_clean = subagent_id.replace("-", "_")
        username = f"agent_{session_clean}_{sub_clean}"
        short = f"Agent {session_clean[:6]}_{sub_clean[:4]}"
        ext_id = f"agent:{session_id}:{subagent_id}"
    else:
        username = f"agent_{session_clean}"
        short = f"Agent {session_clean[:6]}"
        ext_id = f"agent:{session_id}"
    return username, short, ext_id


def _hook_resolve_user(url, headers, session_id, agent_id):
    """Look up agent user by external_id pattern. Returns user dict or None."""
    users = _hook_api_get(f"{url}/api/v1/users", headers)
    if not users:
        return None
    _, _, ext_id = _hook_make_agent_identity(session_id, agent_id if agent_id != "main" else None)
    for u in users:
        if u.get("external_id") == ext_id:
            return u
    return None


def _hook_mint_token(url, headers, user_id, label):
    """Mint a fresh access token for user_id. Returns raw token string or None."""
    resp = _hook_api_post(f"{url}/api/v1/users/{user_id}/tokens", headers, {"label": label})
    if resp and "token" in resp:
        return resp["token"]
    return None


def _hook_get_or_create_user(url, headers, session_id, agent_id):
    """Get or create agent user. Returns user dict or None.

    Newly created agent users are assigned the built-in 'member' role so their
    minted tokens can actually access boards. If the role doesn't exist or the
    assignment endpoint isn't authorized, the user is still created.
    """
    user = _hook_resolve_user(url, headers, session_id, agent_id)
    if user:
        return user
    # Create
    username, display_name, ext_id = _hook_make_agent_identity(
        session_id, agent_id if agent_id != "main" else None
    )
    body = {"username": username, "display_name": display_name, "external_id": ext_id}
    # Set report_to for subagents
    if agent_id != "main":
        main_user = _hook_resolve_user(url, headers, session_id, "main")
        if main_user:
            body["report_to"] = main_user["username"]
    created = _hook_api_post(f"{url}/api/v1/users", headers, body)
    if created and not created.get("role_id"):
        role = _hook_ensure_agent_role(url, headers)
        if role:
            _hook_api_post(
                f"{url}/api/v1/users/{created['id']}", headers,
                {"role": role["name"], "role_id": role["id"]},
            )
            refreshed = _hook_api_get(f"{url}/api/v1/users/{created['id']}", headers)
            if refreshed:
                created = refreshed
    return created


def _hook_ensure_agent_role(url, headers):
    """Find or create the 'agent' role (member-equivalent) used for hook-created users."""
    roles = _hook_api_get(f"{url}/api/v1/roles", headers) or []
    role = next((r for r in roles if r.get("name") == "agent"), None)
    if role:
        return role
    return _hook_api_post(
        f"{url}/api/v1/roles", headers,
        {
            "name": "agent",
            "description": "Auto-assigned to Claude Code agent users",
            "permissions": [
                "boards.read", "boards.write",
                "tasks.read", "tasks.create", "tasks.edit", "tasks.post_comment",
            ],
        },
    )


def _hook_get_agent_tasks(url, headers, board_id, user_id, filter_expr=None, limit=None):
    """Get tasks for agent. Returns list or None."""
    params = {}
    if filter_expr:
        params["filter"] = filter_expr
    if limit is not None and limit > 0:
        params["limit"] = str(limit)
    try:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        full_url = f"{url}/api/v1/board/{board_id}/tasks" + (f"?{qs}" if qs else "")
        tasks = _hook_api_get(full_url, headers)
        if tasks is None:
            return None
        return [t for t in tasks if t.get("assignee_id") is None or t.get("assignee_id") == user_id]
    except Exception:
        return None


def _hook_format_task_list(tasks):
    """Format tasks sorted by importance desc."""
    sorted_tasks = sorted(tasks, key=lambda t: t.get("importance", 0), reverse=True)
    return "\n".join(
        f"  #{t['id']}: [{t['status']}] {t['title']} (importance:{t.get('importance', 0)})"
        for t in sorted_tasks
    )


HOOK_ESCAPE_HATCH = "THIS_IS_AN_EMERGENCY_SOMETHING_WENT_WRONG_I_NEED_TO_STOP"


@click.command("claude-hook")
@click.argument("event")
@click.pass_context
def claude_hook(ctx, event):
    """Handle Claude Code hook events. Reads JSON from stdin."""
    data = json.loads(click.get_text_stream("stdin").read())
    url = get_server_url(ctx)
    headers = _hook_get_auth_headers(ctx)
    session_id = data.get("session_id", "")
    agent_id = data.get("agent_id") or "main"

    if event == "SessionStart":
        _handle_session_start(ctx, url, headers, data, session_id, agent_id)
    elif event == "PreToolUse":
        _handle_pre_tool_use(ctx, url, headers, data, session_id, agent_id)
    elif event == "Stop":
        _handle_stop(ctx, url, headers, data, session_id, agent_id)
    elif event == "SubagentStart":
        user = _hook_get_or_create_user(url, headers, session_id, agent_id)
        if user:
            exports = {"TASKPLANNER_USERNAME": user["username"]}
            existing_token = os.environ.get("TASKPLANNER_USER_ACCESS_TOKEN")
            reuse = False
            if existing_token:
                me = _hook_api_get(
                    f"{url}/api/v1/auth/me",
                    {"Authorization": f"Bearer {existing_token}"},
                )
                if me and me.get("id") == user["id"]:
                    exports["TASKPLANNER_USER_ACCESS_TOKEN"] = existing_token
                    reuse = True
            if not reuse:
                tok = _hook_mint_token(url, headers, user["id"], f"hook:{session_id[:8]}:{agent_id}")
                if tok:
                    exports["TASKPLANNER_USER_ACCESS_TOKEN"] = tok
            _hook_export_env(exports)
    # Unknown events silently pass through


def _handle_session_start(ctx, url, headers, data, session_id, agent_id):
    """SessionStart: create agent user, export username + token, show pending tasks."""
    user = _hook_get_or_create_user(url, headers, session_id, agent_id)
    if not user:
        return

    username = user.get("username", "")
    exports = {"TASKPLANNER_USERNAME": username}
    # If the env already has a working token, reuse it (task #323) — avoids
    # accumulating per-session tokens when the user supplied a long-lived one.
    existing_token = os.environ.get("TASKPLANNER_USER_ACCESS_TOKEN")
    reuse = False
    if existing_token:
        me = _hook_api_get(f"{url}/api/v1/auth/me", {"Authorization": f"Bearer {existing_token}"})
        if me and me.get("id") == user["id"]:
            exports["TASKPLANNER_USER_ACCESS_TOKEN"] = existing_token
            reuse = True
    if not reuse:
        tok = _hook_mint_token(url, headers, user["id"], f"hook:{session_id[:8]}:{agent_id}")
        if tok:
            exports["TASKPLANNER_USER_ACCESS_TOKEN"] = tok
    _hook_export_env(exports)

    board = ctx.obj.get("board")
    if not board:
        try:
            board = get_board_id(ctx)
        except SystemExit:
            return

    tasks = _hook_get_agent_tasks(url, headers, board, user["id"])
    if not tasks:
        return

    started = [t for t in tasks if t["status"] == "STARTED"]
    new = [t for t in tasks if t["status"] == "NEW"]
    waiting = [t for t in tasks if t["status"] == "WAITING_FOR_COMMAND_EXECUTION"]

    lines = []
    if started:
        lines.append("Active tasks:")
        lines.append(_hook_format_task_list(started))
    if new:
        lines.append("Pending tasks:")
        lines.append(_hook_format_task_list(new))
    if waiting:
        lines.append("Waiting tasks:")
        lines.append(_hook_format_task_list(waiting))

    if lines:
        msg = (
            "TaskPlanner — your tasks:\n"
            + "\n".join(lines)
            + "\n\nStart a task:"
            + "\n  $ TaskPlanner edit <id> --status STARTED"
            + "\nCreate a task:"
            + f'\n  $ TaskPlanner add-task --title "desc" --assignee {username}'
        )
        _hook_output({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": msg,
            }
        })


# Shell operators that chain or compose additional commands. shlex with
# punctuation_chars isolates runs of these into their own tokens; newlines and
# backticks are checked separately since shlex treats them as whitespace / word
# characters respectively rather than as punctuation.
_SHELL_CHAIN_CHARS = ";&|<>()"


def _has_shell_chaining(command):
    """True if `command` chains or composes commands via shell operators.

    Used to stop the TaskPlanner bypass from being abused to smuggle an
    arbitrary command past the task gate (e.g. ``TaskPlanner list && rm -rf``).
    Operators inside quotes (a legitimate ``--title "a && b"``) are ignored.
    """
    # Newlines, backticks and command substitution stay live even inside double
    # quotes, so shlex (which strips quotes / treats newlines as whitespace)
    # can't see them — check the raw string for those.
    if any(s in command for s in ("\n", "\r", "`", "$(")):
        return True
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        # Unbalanced quotes etc. — can't reason about it safely; treat as chained.
        return True
    # punctuation_chars isolates runs of operators into their own tokens, so a
    # chaining operator is a token made up *entirely* of operator characters.
    # A quoted arg keeps its other characters, so it never looks like one.
    chars = set(_SHELL_CHAIN_CHARS)
    return any(tok and set(tok) <= chars for tok in tokens)


def _handle_pre_tool_use(ctx, url, headers, data, session_id, agent_id):
    """PreToolUse: require active task for Bash/Edit/Write."""
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    if tool_name not in ("Bash", "Edit", "Write"):
        return

    command = tool_input.get("command", "")

    # Always allow TaskPlanner CLI commands — but only a single, un-chained
    # invocation. Chaining (e.g. `TaskPlanner list && rm -rf /`) would smuggle
    # an arbitrary command past the task gate, so deny it instead of bypassing.
    if tool_name == "Bash" and (
        command.strip().startswith("TaskPlanner ") or command.strip().startswith("taskplanner ")
    ):
        if _has_shell_chaining(command):
            _hook_deny(
                "Chaining is not allowed for TaskPlanner commands. Run TaskPlanner "
                "as a single command with no shell operators (; && || | & redirections, "
                "command substitution, backticks, or newlines). Split chained commands "
                "into separate Bash calls."
            )
        return

    # Look up agent user
    user = _hook_resolve_user(url, headers, session_id, agent_id)
    if not user:
        return  # User not found — pass through

    board = ctx.obj.get("board")
    if not board:
        try:
            board = get_board_id(ctx)
        except SystemExit:
            return

    tasks = _hook_get_agent_tasks(url, headers, board, user["id"], limit=0)
    if tasks is None:
        _hook_deny("Cannot fetch task list from TaskPlanner. Is the server running?")
        return

    active = [t for t in tasks if t["status"] == "STARTED"]
    if not active:
        pending = [t for t in tasks if t["status"] in ("NEW", "STARTED")]
        if pending:
            task_list = _hook_format_task_list(pending)
            _hook_deny(
                f"No STARTED task. Your tasks:\n{task_list}\n\n"
                "Start a task:\n"
                "  $ TaskPlanner edit <id> --status STARTED"
            )
        else:
            _hook_deny(
                "No tasks assigned to you. Create one first:\n"
                f'  $ TaskPlanner add-task [--start-now] --title "your task" --assignee {user["username"]}'
            )
        return

    if tool_name in ("Edit", "Write"):
        return

    # For Bash: require description to reference one of the agent's STARTED tasks.
    # \Z (not $) so a trailing newline doesn't count as end-of-suffix; digits are
    # bounded so int() can't hit Python's 4300-digit conversion limit and crash
    # the hook (a crashed PreToolUse hook fails open in Claude Code).
    description = tool_input.get("description", "")
    match = re.search(r" Task#(\d{1,9})\Z", description)
    active_by_id = {t["id"]: t for t in active}
    current_task = active_by_id.get(int(match.group(1))) if match else None
    if match is None or current_task is None:
        task_list = _hook_format_task_list(active)
        _hook_deny(
            "Command description must reference one of your STARTED tasks:\n"
            f"{task_list}\n\n"
            'Add suffix to your description: " Task#<task_id>"'
        )
        return

    # Log as comment. The hook's headers carry the admin token (the wrapper
    # backfills it from taskplanner.env when Claude Code's hook subprocess
    # env doesn't have a token); use as_user so the comment is attributed
    # to the agent, not the admin who owns the backfilled token.
    reason = description[: match.start()].strip() or "(no description)"
    _hook_api_post(
        f"{url}/api/v1/board/{board}/tasks/{current_task['id']}/new_comment",
        headers,
        {
            "content": f"[Tool:Bash] {reason}\n\n```bash\n{command}\n```",
            "comment_type": "EXECUTION_LOG",
            "as_user": user["username"],
        },
    )


def _handle_stop(ctx, url, headers, data, session_id, agent_id):
    """Stop: block if agent has unresolved tasks."""
    last_msg = data.get("last_assistant_message", "")
    if HOOK_ESCAPE_HATCH in last_msg:
        return

    user = _hook_resolve_user(url, headers, session_id, agent_id)
    if not user:
        return

    board = ctx.obj.get("board")
    if not board:
        try:
            board = get_board_id(ctx)
        except SystemExit:
            return

    username = user["username"]
    tasks = _hook_get_agent_tasks(
        url, headers, board, user["id"],
        filter_expr=f"(STATUS=NEW OR STATUS=STARTED),(ASSIGNEE={username} OR ASSIGNEE=)",
    )
    if not tasks:
        return

    incomplete = [t for t in tasks if t["status"] in ("NEW", "STARTED")]
    if incomplete:
        task_list = _hook_format_task_list(incomplete)
        _hook_output({
            "decision": "block",
            "reason": (
                f"You have {len(incomplete)} unresolved task(s):\n{task_list}"
                "\nResolve with:"
                "\n  $ TaskPlanner edit <id> --status DONE|BLOCKED|CANCELLED|WAITING_FOR_COMMAND_EXECUTION"
                f"\nNeed more info from the user? Post what you need as a comment for the task, then set status to NEW and assign to the user:"
                f"\n  $ TaskPlanner edit <id> --status NEW --assignee <username>"
            ),
        })
