#!/usr/bin/env python3
"""TaskPlanner-backed progress tracker hook for Claude Code.

Uses the TaskPlanner CLI to track tasks. Requires:
  - TaskPlanner server running (default http://localhost:8000)
  - ~/.local/bin/TaskPlanner in PATH

Hooks:
  start — SessionStart: create agent user, export TASKPLANNER_USERNAME, show pending tasks
  pre   — PreToolUse: require active (STARTED) task before Bash/Edit/Write
  stop  — Stop: block if agent has unresolved tasks

Agent user is created once in SessionStart and exported as TASKPLANNER_USERNAME
via CLAUDE_ENV_FILE. PreToolUse and Stop read it from the environment or fall
back to show-user lookup.

Escape hatches:
  - Say "THIS_IS_AN_EMERGENCY_SOMETHING_WENT_WRONG_I_NEED_TO_STOP" to bypass Stop hook
  - TaskPlanner CLI commands always pass through PreToolUse
  - Non-Bash/Edit/Write tools always pass through PreToolUse
  - If TaskPlanner CLI fails (server down), hooks silently pass through
"""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
from hook_options import (
    ALLOW_STOP_HOOK_BYPASS,
    ALLOW_TOOL_USE_HOOK_BYPASS,
    DISABLE_STOP_WATCH,
    DISABLE_TOOL_USE_HOOK,
    HUMAN_USERNAME,
)

ESCAPE_HATCH = "THIS_IS_AN_EMERGENCY_SOMETHING_WENT_WRONG_I_NEED_TO_STOP"

CLI = os.path.expanduser("~/.local/bin/TaskPlanner")


def run_cli(*args, parse_json=False, timeout: int | None = 5):
    """Run TaskPlanner CLI and return output. Returns None on failure.
    Board ID is resolved from .env file by the CLI itself."""
    try:
        cmd = [CLI] + list(args)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            return None
        output = result.stdout.strip()
        if parse_json:
            return json.loads(output)
        return output
    except Exception:
        return None


def run_cli_global(*args):
    """Run TaskPlanner CLI without board scope (for user commands)."""
    try:
        cmd = [CLI] + list(args)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            return None
        return result.stdout.strip()
    except Exception:
        return None


def get_agent_id(hook_data):
    return hook_data.get("agent_id") or "main"


def get_session_id(hook_data):
    return hook_data.get("session_id") or ""


def _identity_args(session_id, agent_id):
    """Build CLI args for --agent-session-id [--subagent-id]."""
    args = ["--agent-session-id", session_id]
    if agent_id != "main":
        args += ["--subagent-id", agent_id]
    return args


def _show_user_json(cli_args, *fields):
    """Run show-user with a JSON template and parse the result. Returns dict or None."""
    tpl_fields = ", ".join(f'"{f}": "{{{f}}}"' for f in fields)
    tpl = "{{" + tpl_fields + "}}"
    output = run_cli_global("show-user", *cli_args, "--template", tpl)
    if output:
        try:
            return json.loads(output.strip())
        except (json.JSONDecodeError, ValueError):
            pass
    return None


def get_or_create_agent_user(session_id, agent_id):
    """Create agent user if needed, return username or None. Called from SessionStart."""
    id_args = _identity_args(session_id, agent_id)

    data = _show_user_json(id_args, "username")
    if data:
        return data["username"]

    # For subagents, find the main agent's username and set report_to
    create_args = list(id_args)
    if agent_id != "main":
        main_data = _show_user_json(_identity_args(session_id, "main"), "username")
        if main_data:
            create_args += ["--report-to", main_data["username"]]

    run_cli_global("add-user", *create_args)

    data = _show_user_json(id_args, "username")
    if data:
        return data["username"]

    return None


def lookup_agent_username(session_id, agent_id):
    """Look up existing agent username. Returns username or None. No creation."""
    id_args = _identity_args(session_id, agent_id)
    data = _show_user_json(id_args, "username")
    return data["username"] if data else None


def resolve_user_id(username):
    """Resolve username to numeric user ID. Returns int or None."""
    data = _show_user_json(["--username", username], "id")
    if data:
        try:
            return int(data["id"])
        except (ValueError, TypeError):
            pass
    return None


def get_agent_tasks(username, filter_expr=None, limit=None):
    """Get tasks assigned to this agent (by username) or unassigned. Returns list or None."""
    args = ["list", "--format", "json"]
    if filter_expr is not None:
        args += ["--filter", filter_expr]
    if limit is not None:
        args += ["--limit", str(limit)]
    output = run_cli(*args)
    if output is None:
        return None
    try:
        tasks = json.loads(output)
        user_id = resolve_user_id(username)
        return [t for t in tasks if t.get("assignee_id") is None or t.get("assignee_id") == user_id]
    except (json.JSONDecodeError, TypeError):
        return None


def is_taskplanner_cmd(command):
    """Check if the command is a TaskPlanner CLI command."""
    cmd = command.strip()
    return cmd.startswith("TaskPlanner ") or cmd.startswith("taskplanner ")


def format_task_list(tasks):
    """Format tasks sorted by importance desc, with importance shown."""
    sorted_tasks = sorted(tasks, key=lambda t: t.get("importance", 0), reverse=True)
    return "\n".join(
        f"  #{t['id']}: [{t['status']}] {t['title']} (importance:{t.get('importance', 0)})"
        for t in sorted_tasks
    )


def deny(reason):
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


def handle_pre_tool(data):
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})
    session_id = get_session_id(data)
    agent_id = get_agent_id(data)

    # Gate Bash and file-editing tools
    if tool_name not in ("Bash", "Edit", "Write"):
        return

    command = tool_input.get("command", "")
    description = tool_input.get("description", "")

    if DISABLE_TOOL_USE_HOOK or ALLOW_TOOL_USE_HOOK_BYPASS and description.endswith("09sduf09q7we"):
        return

    # Always allow TaskPlanner CLI commands through (escape hatch)
    if tool_name == "Bash" and is_taskplanner_cmd(command):
        return

    # Look up agent user (created in SessionStart)
    username = lookup_agent_username(session_id, agent_id)
    if username is None:
        # User not yet created — silently pass through
        return
    # Ensure TASKPLANNER_USERNAME is set for run_cli subprocesses
    os.environ["TASKPLANNER_USERNAME"] = username

    # Get agent's tasks
    agent_tasks = get_agent_tasks(username, limit=0)
    if agent_tasks is None:
        deny("Cannot fetch task list from TaskPlanner. Is the server running?")
        return

    # Find active task (STARTED status)
    active = [t for t in agent_tasks if t["status"] == "STARTED"]
    if not active:
        pending = [t for t in agent_tasks if t["status"] in ("NEW", "STARTED")]
        if pending:
            task_list = format_task_list(pending)
            deny(
                f"No STARTED task. Your tasks:\n{task_list}\n\n"
                "Start a task:\n"
                "  $ TaskPlanner edit <id> --status STARTED"
            )
        else:
            deny(
                f"No tasks assigned to you. Create one first:\n"
                f'  $ TaskPlanner add-task [--start] --title "your task" --assignee {username}'
            )
        return

    # For Edit/Write, just having an active task is enough
    if tool_name in ("Edit", "Write"):
        return

    # For Bash: require description to reference the active task
    current_task = active[0]
    ct_tag = f" Task#{current_task['id']}"
    if not description.endswith(ct_tag):
        deny(
            'Command description must reference the active task.\nAdd suffix to your description: " Task#<task_id>"'
        )
        return

    # Log as comment on the task
    reason = description.split(ct_tag)[0].strip() or "(no description)"
    run_cli(
        "add-comment",
        str(current_task["id"]),
        "-m",
        f"[Tool:Bash] {reason}\n\n```bash\n{command}\n```",
        "-t",
        "EXECUTION_LOG",
    )


def get_stop_blocking_tasks(data):
    last_msg = data.get("last_assistant_message", "")

    # Escape hatch
    if ALLOW_STOP_HOOK_BYPASS and ESCAPE_HATCH in last_msg:
        return

    session_id = get_session_id(data)
    agent_id = get_agent_id(data)

    username = lookup_agent_username(session_id, agent_id)
    if username is None:
        return  # User not found, pass through
    os.environ["TASKPLANNER_USERNAME"] = username

    # TODO: also include BLOCKED state tasks that all blockers are already DONE/CANCELLED/NOT_REPRODUCIBLE
    agent_tasks = get_agent_tasks(
        username, f"(STATUS=NEW OR STATUS=STARTED),(ASSIGNEE={username} OR ASSIGNEE=)"
    )
    if agent_tasks is None:
        return  # CLI issue, pass through

    # Find non-terminal tasks
    incomplete = [t for t in agent_tasks if t["status"] in ("NEW", "STARTED")]

    return incomplete


def handle_stop(data):
    blocking_tasks = get_stop_blocking_tasks(data)
    if blocking_tasks:
        task_list = format_task_list(blocking_tasks)
        print(
            json.dumps(
                {
                    "decision": "block",
                    "reason": (
                        f"You have {len(blocking_tasks)} unresolved task(s):\n{task_list}"
                        "\nResolve with:"
                        "\n  $ TaskPlanner edit <id> --status DONE|BLOCKED|CANCELLED|WAITING_FOR_COMMAND_EXECUTION"
                        f"\nNeed more info from the user? Post what you need as a comment for the task, then set status to NEW and assign to {HUMAN_USERNAME}:"
                        f"\n  $ TaskPlanner edit <id> --status NEW --assignee {HUMAN_USERNAME}"
                    )
                    + (f"\nOr say {ESCAPE_HATCH} to force stop." if ALLOW_STOP_HOOK_BYPASS else ""),
                }
            )
        )


def handle_stop_watch(data):
    if DISABLE_STOP_WATCH:
        return

    if get_stop_blocking_tasks(data):
        return

    session_id = get_session_id(data)

    # Kill any existing watcher before starting a new one
    stop_args = ["watch", "--stop"]
    if session_id:
        stop_args += ["--session-id", session_id]
    run_cli(*stop_args, timeout=10)

    watch_cmd = [CLI, "watch"]
    if session_id:
        watch_cmd += ["--session-id", session_id]
    try:
        result = subprocess.run(watch_cmd, capture_output=True, text=True)
        if result.returncode == 2:
            # Exit code 2 = actionable task found — propagate to asyncRewake
            msg = result.stdout.strip() or "TaskPlanner watch returned 2 without stdout"
            print(msg)
            sys.exit(2)
    except Exception:
        pass


def export_env(data, username=None):
    """Write session metadata to CLAUDE_ENV_FILE so Bash calls can access it.
    Deduplicates by reading existing content and only writing new/changed vars."""
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    if not env_file:
        return
    session_id = data.get("session_id", "")
    new_vars = {
        "EDITOR": "cat_and_exit_1.sh",
        "PAGER": "cat",
    }
    if session_id:
        new_vars["AGENT_SESSION_ID"] = session_id
    if username:
        new_vars["TASKPLANNER_USERNAME"] = username
    if not new_vars:
        return

    # Read existing lines, dedup by var name
    existing = {}
    other_lines = []
    try:
        with open(env_file, "r") as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("export ") and "=" in stripped:
                    var = stripped.split("=", 1)[0].removeprefix("export ").strip()
                    existing[var] = stripped
                elif stripped:
                    other_lines.append(stripped)
    except FileNotFoundError:
        pass

    # Merge: new values override existing
    for var, val in new_vars.items():
        existing[var] = f"export {var}={val}"

    with open(env_file, "w") as f:
        for line in other_lines:
            f.write(line + "\n")
        for line in existing.values():
            f.write(line + "\n")


def handle_session_start(data):
    session_id = data.get("session_id", "")
    agent_id = get_agent_id(data)

    # Create agent user (the only place this happens)
    username = get_or_create_agent_user(session_id, agent_id)

    # Export env vars (session ID + username)
    export_env(data, username)

    if username is None:
        return

    agent_tasks = get_agent_tasks(username)
    if agent_tasks is None:
        return

    # Find tasks needing attention
    started = [t for t in agent_tasks if t["status"] == "STARTED"]
    new = [t for t in agent_tasks if t["status"] == "NEW"]
    waiting = [t for t in agent_tasks if t["status"] == "WAITING_FOR_COMMAND_EXECUTION"]

    lines = []
    if started:
        lines.append("Active tasks:")
        lines.append(format_task_list(started))
    if new:
        lines.append("Pending tasks:")
        lines.append(format_task_list(new))
    if waiting:
        lines.append("Waiting tasks:")
        lines.append(format_task_list(waiting))

    if lines:
        msg = (
            "TaskPlanner — your tasks:\n"
            + "\n".join(lines)
            + "\n\nStart a task:"
            + "\n  $ TaskPlanner edit <id> --status STARTED"
            + "\nCreate a task:"
            + f'\n  $ TaskPlanner add-task --title "desc" --assignee {username}'
        )
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": msg,
                    }
                }
            )
        )


def handle_subagent_start(data):
    """Create agent user for a subagent. Called from SubagentStart hook (runs on main thread)."""
    session_id = get_session_id(data)
    agent_id = get_agent_id(data)

    get_or_create_agent_user(session_id, agent_id)


def main():
    if len(sys.argv) < 2:
        print("Usage: taskplanner-hook.py <pre|stop|start|SubagentStart>", file=sys.stderr)
        sys.exit(1)

    mode = sys.argv[1]
    data = json.load(sys.stdin)

    if mode == "pre":
        handle_pre_tool(data)
    elif mode == "stop":
        handle_stop(data)
    elif mode == "start":
        handle_session_start(data)
    elif mode == "watch":
        handle_stop_watch(data)
    elif mode == "SubagentStart":
        handle_subagent_start(data)


if __name__ == "__main__":
    main()
