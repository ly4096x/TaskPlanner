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

MODE_MAP = {
    "start": "SessionStart",
    "pre": "PreToolUse",
    "stop": "Stop",
    "watch": "StopWatch",
    "SubagentStart": "SubagentStart",
}


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
