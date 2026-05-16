#!/usr/bin/env python3
"""Thin wrapper that delegates to `TaskPlanner claude-hook <event>`.

All hook logic lives in the CLI itself (client_cli/cli.py).
This script just forwards stdin/stdout and maps hook modes to event names.
"""

import os
import subprocess
import sys

CLI = os.path.expanduser("~/.local/bin/TaskPlanner")

# Map hook invocation modes to claude-hook event names
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

    try:
        result = subprocess.run(
            [CLI, "claude-hook", event],
            input=sys.stdin.read(),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.stdout.strip():
            print(result.stdout.strip())
        if result.returncode != 0 and result.returncode != 2:
            # Non-zero non-2 exit: silently pass through (server down, etc.)
            pass
        sys.exit(result.returncode)
    except Exception:
        # CLI not found or timeout — silently pass through
        pass


if __name__ == "__main__":
    main()
