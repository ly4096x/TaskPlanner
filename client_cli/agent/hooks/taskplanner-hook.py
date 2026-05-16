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

    # Stop and StopWatch must short-circuit when the harness is already in a stop-hook
    # cycle, otherwise asyncRewake re-fires Stop indefinitely.
    if event in ("Stop", "StopWatch"):
        try:
            if json.loads(stdin_data or "{}").get("stop_hook_active"):
                sys.exit(0)
        except (ValueError, TypeError):
            pass

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
