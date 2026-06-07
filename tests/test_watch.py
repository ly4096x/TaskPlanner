"""Tests for TaskPlanner watch — specifically the parent-exit watchdog.

The watch loop uses a daemon thread that polls os.getppid(); if the
parent process dies (kernel reparents us to init / a subreaper) the
ppid changes and the watcher exits via os._exit(0).
"""

import os
import signal
import subprocess
import sys
import textwrap
import time

import pytest


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def test_watch_exits_when_parent_dies():
    """Parent process dies → watch detects ppid change and exits within a few seconds."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Intermediate Python process: spawn TaskPlanner watch, print its pid, then sleep.
    # Watch is pointed at an unreachable server so the SSE loop is harmless (it'll
    # retry forever), but the parent-exit watchdog runs independently of that.
    parent_script = textwrap.dedent(f"""
        import os, subprocess, sys, time
        sys.path.insert(0, {repo_root!r})
        env = os.environ.copy()
        env["TASKPLANNER_SERVER"] = "http://127.0.0.1:1"
        env["TASKPLANNER_BOARD_ID"] = "1"
        env["TASKPLANNER_USER_ACCESS_TOKEN"] = "x"
        p = subprocess.Popen(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, {repo_root!r}); "
             "from client_cli.cli import main; main()",
             "watch", "--session-id", "test-pp"],
            env=env,
        )
        print(p.pid, flush=True)
        time.sleep(60)
    """)

    parent = subprocess.Popen(
        [sys.executable, "-c", parent_script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert parent.stdout is not None and parent.stderr is not None
    try:
        line = parent.stdout.readline()
        assert line, f"intermediate parent failed to launch: {parent.stderr.read()!r}"
        child_pid = int(line.strip())

        # Give the watchdog thread a moment to capture initial_ppid.
        time.sleep(1)
        assert _is_alive(child_pid), "watch process died before parent was killed"

        # Kill the intermediate parent; the watchdog should notice within 2s.
        parent.kill()
        parent.wait(timeout=5)

        deadline = time.time() + 10
        while time.time() < deadline:
            if not _is_alive(child_pid):
                return  # watch exited as expected
            time.sleep(0.2)

        os.kill(child_pid, signal.SIGKILL)
        pytest.fail(f"watch (pid {child_pid}) did not exit within 10s of parent death")
    finally:
        if parent.poll() is None:
            parent.kill()
