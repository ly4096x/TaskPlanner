#!/usr/bin/env python3
"""Thin wrapper that delegates to `TaskPlanner claude-hook <event>`.

All hook logic lives in the CLI itself (client_cli/cli.py).
This script just forwards stdin/stdout/stderr and maps hook modes to event names.
"""

import json
import os
import subprocess
import sys

CLI = os.path.expanduser("~/.local/bin/TaskPlanner")
CRED_FILE = os.path.expanduser("~/.claude/taskplanner.env")

MODE_MAP = {
    "start": "SessionStart",
    "pre": "PreToolUse",
    "stop": "Stop",
    "watch": "StopWatch",
    "SubagentStart": "SubagentStart",
}


def load_admin_credential():
    """Backfill the privileged token from ~/.claude/taskplanner.env.

    `TaskPlanner claude-hook` needs an admin token to create agent users and mint
    their per-agent tokens. Claude Code's hook subprocess inherits the launch
    environment, which may not carry TASKPLANNER_USER_ACCESS_TOKEN; read it from
    the credentials file so the hook works regardless of how Claude Code was
    launched. The token stays in this hook subprocess only — claude-hook writes
    the agent's own (non-admin) token to CLAUDE_ENV_FILE, never the admin token."""
    if os.environ.get("TASKPLANNER_USER_ACCESS_TOKEN"):
        return
    try:
        with open(CRED_FILE) as f:
            for line in f:
                s = line.strip()
                if s.startswith("export TASKPLANNER_USER_ACCESS_TOKEN="):
                    val = s.split("=", 1)[1].strip().strip('"').strip("'")
                    if val:
                        os.environ["TASKPLANNER_USER_ACCESS_TOKEN"] = val
                    break
    except OSError:
        pass


def main():
    if len(sys.argv) < 2:
        print("Usage: taskplanner-hook.py <pre|stop|start|watch|SubagentStart>", file=sys.stderr)
        sys.exit(1)

    mode = sys.argv[1]
    event = MODE_MAP.get(mode, mode)
    stdin_data = sys.stdin.read()
    try:
        payload = json.loads(stdin_data or "{}")
    except (ValueError, TypeError):
        payload = {}

    # Claude Code's hook subprocess env doesn't include AGENT_SESSION_ID, but the
    # JSON does. Copy session_id into env so the CLI's session-env-file token
    # fallback can find it.
    sid = payload.get("session_id")
    if sid and not os.environ.get("AGENT_SESSION_ID"):
        os.environ["AGENT_SESSION_ID"] = sid

    # Ensure an admin token is present so claude-hook can create users / mint tokens.
    load_admin_credential()

    # Stop and StopWatch must short-circuit when the harness is already in a stop-hook
    # cycle, otherwise asyncRewake re-fires Stop indefinitely.
    if event in ("Stop", "StopWatch") and payload.get("stop_hook_active"):
        sys.exit(0)

    # The watch loop is long-running (SSE) so it must NOT go through claude-hook's
    # 30s subprocess timeout. Invoke `TaskPlanner watch` directly with the current
    # session id; it exits with code 2 when an actionable task arrives (signaling
    # asyncRewake) or 0 when stopped.
    if event == "StopWatch":
        session_id = payload.get("session_id") or ""
        # Replace any prior watcher for this session before starting a new one.
        if session_id:
            try:
                subprocess.run(
                    [CLI, "watch", "--stop", "--session-id", session_id],
                    capture_output=True, text=True, timeout=10,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
        args = [CLI, "watch"]
        if session_id:
            args += ["--session-id", session_id]
        try:
            os.execvp(args[0], args)
        except FileNotFoundError:
            print(f"taskplanner-hook: CLI not found at {CLI}", file=sys.stderr)
            sys.exit(0)

    try:
        result = subprocess.run(
            [CLI, "claude-hook", event],
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        print(f"taskplanner-hook: CLI not found at {CLI}", file=sys.stderr)
        sys.exit(0)  # pass through, do not block
    except subprocess.TimeoutExpired:
        print(f"taskplanner-hook: {event} timed out after 30s", file=sys.stderr)
        sys.exit(0)

    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
