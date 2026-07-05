#!/usr/bin/env python3
"""VCS hooks for jj/git workspaces.

WorktreeCreate: creates a jj workspace under ~/.vcs_workspaces/<name>
WorktreeRemove: removes the jj workspace and cleans up the directory
Stop/SubagentStop: blocks if cwd has uncommitted changes, UNLESS the latest
    assistant message has a line starting "I'm stopping with uncommitted
    changes because: <reason>" (case-insensitive, reason required) — an
    explicit opt-out to stop dirty.

If cwd is not a jj or git repo, worktree hooks exit with code 1.
"""

import json
import os
import re
import subprocess
import sys
import time

WORKSPACES_DIR = os.path.expanduser("~/.vcs_workspaces")

# Explicit opt-out: when the assistant's final message says this, allow the
# turn to end with an uncommitted (dirty) working tree. A reason is required
# (at least one non-space char after the colon).
#
# Anchored to the start of a line (MULTILINE) so the opt-out only fires when
# the assistant writes the directive as its own line — not when a message
# merely quotes or discusses the phrase, and not from this hook's own block
# message (which the harness echoes back into the chat). The apostrophe is
# matched loosely to tolerate a straight ' or a curly ’.
DIRTY_BYPASS_RE = re.compile(
    r"^\s*i['’]m stopping with uncommitted changes because:\s*\S",
    re.IGNORECASE | re.MULTILINE,
)


def scan_assistant(transcript_path):
    """Scan the transcript JSONL. Return (count, last_text): the number of
    assistant messages that carried text, and the most recent such text
    (or (0, '') if unavailable)."""
    if not transcript_path or not os.path.isfile(transcript_path):
        return 0, ""
    count, last_text = 0, ""
    try:
        with open(transcript_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    evt = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if evt.get("type") != "assistant":
                    continue
                content = evt.get("message", {}).get("content", [])
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    text = "\n".join(
                        b.get("text", "")
                        for b in content
                        if isinstance(b, dict) and b.get("type") == "text"
                    )
                else:
                    text = ""
                if text:
                    count += 1
                    last_text = text
    except OSError:
        return count, last_text
    return count, last_text


def resolve_final_assistant_text(transcript_path, settle=1.5, interval=0.1):
    """The Stop hook can fire before the turn's final assistant message has been
    flushed to the transcript, so a naive read returns the *previous* message
    and misses a just-written opt-out line. Wait briefly for the in-flight
    message to land: short-circuit the moment a bypass line is visible, else
    wait until a newer assistant message appears (or `settle` elapses) and use
    that. On a genuine block this only costs the time until the final message
    flushes (usually well under `settle`)."""
    count0, text = scan_assistant(transcript_path)
    if DIRTY_BYPASS_RE.search(text):
        return text
    deadline = time.monotonic() + settle
    while time.monotonic() < deadline:
        time.sleep(interval)
        count, latest = scan_assistant(transcript_path)
        if count != count0:
            return latest
        text = latest
    return text


def dirty_bypass_requested(data):
    """True if the assistant explicitly opted out of the clean-tree check."""
    return bool(
        DIRTY_BYPASS_RE.search(resolve_final_assistant_text(data.get("transcript_path")))
    )


def is_jj_repo(path):
    """Check if path is inside a jj repo."""
    while path != "/":
        if os.path.isdir(os.path.join(path, ".jj")):
            return True
        path = os.path.dirname(path)
    return False


def is_git_repo(path):
    """Check if path is inside a git repo (non-jj)."""
    while path != "/":
        git_path = os.path.join(path, ".git")
        if os.path.isdir(git_path) or os.path.isfile(git_path):
            return True
        path = os.path.dirname(path)
    return False


def jj_repo_root(path):
    """Find the jj repo root."""
    while path != "/":
        if os.path.isdir(os.path.join(path, ".jj")):
            return path
        path = os.path.dirname(path)
    return None


def git_repo_root(path):
    """Find the git repo root."""
    while path != "/":
        git_path = os.path.join(path, ".git")
        if os.path.isdir(git_path) or os.path.isfile(git_path):
            return path
        path = os.path.dirname(path)
    return None


def has_uncommitted_changes(cwd):
    """Check if cwd has uncommitted changes. Returns (bool, str) — (dirty, description)."""
    if is_jj_repo(cwd):
        result = subprocess.run(
            ["jj", "diff", "--summary"],
            cwd=cwd,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().splitlines()
            if len(lines):
                return True, f"jj has uncommitted changes:\n{result.stdout.strip()}"
        return False, ""

    if is_git_repo(cwd):
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return True, f"git has uncommitted changes:\n{result.stdout.strip()}"
        return False, ""

    return False, ""


def block_stop_without_commit(data):
    """Block subagent if cwd has uncommitted changes in jj/git."""
    cwd = data.get("cwd")
    if not cwd:
        return

    if not is_jj_repo(cwd) and not is_git_repo(cwd):
        return

    dirty, description = has_uncommitted_changes(cwd)
    if dirty:
        if dirty_bypass_requested(data):
            # Assistant said "Leaving workspace dirty because: <reason>" —
            # honor the explicit opt-out and allow the turn to end.
            return
        print(
            json.dumps(
                {
                    "decision": "block",
                    "reason": (
                        f"{description}\n\n"
                        "You have uncommitted work. Before stopping:\n"
                        "1. Restart your task (TaskPlanner edit <id> --status STARTED)\n"
                        "2. Commit your changes (jj commit -m '...' or git add -A && git commit -m '...')\n"
                        "\n"
                        "Or, if leaving the tree dirty is intentional, include a line "
                        "starting with:\n"
                        "    I'm stopping with uncommitted changes because: <reason>\n"
                        "and this check will be skipped.\n"
                    ),
                }
            )
        )


def handle_create(data):
    cwd = data.get("cwd")
    # Use provided name, or generate from session+agent IDs
    name = data.get("name")
    if not name:
        session_id = data.get("session_id", "unknown")
        agent_id = data.get("agent_id", "main")
        name = f"agent.{session_id}.{agent_id}"

    # Only support jj repos; ignore non-VCS dirs and pure git repos
    if not is_jj_repo(cwd):
        if is_git_repo(cwd):
            # Let the built-in git worktree handling take over
            # (this hook shouldn't have been called for git repos, but just in case)
            print("Not a jj repo, skipping", file=sys.stderr)
        else:
            print("Not a jj or git repo, skipping", file=sys.stderr)
        sys.exit(1)

    repo_root = jj_repo_root(cwd)
    workspace_path = os.path.join(WORKSPACES_DIR, name)

    # Create workspaces dir if needed
    os.makedirs(WORKSPACES_DIR, exist_ok=True)

    # Create jj workspace
    result = subprocess.run(
        ["jj", "workspace", "add", workspace_path, "--name", name],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"jj workspace add failed: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    # Print the workspace path — this is what EnterWorktree uses as the new cwd
    print(workspace_path)


def handle_remove(data):
    workspace_path = data.get("worktree_path")
    if not workspace_path:
        return

    # Derive workspace name from path
    name = os.path.basename(workspace_path)

    # Try to find the repo root by checking parent directories of the workspace
    # The workspace was created from a jj repo, so we need to forget it there
    # Try using jj from within the workspace itself
    subprocess.run(
        ["jj", "workspace", "forget", name],
        cwd=workspace_path,
        capture_output=True,
        text=True,
    )

    # Clean up the directory
    if os.path.isdir(workspace_path):
        import shutil

        shutil.rmtree(workspace_path, ignore_errors=True)


def main():
    if len(sys.argv) < 2:
        print(
            "Usage: worktree-hook.py <WorktreeCreate|WorktreeRemove|SubagentSto|Stop>",
            file=sys.stderr,
        )
        sys.exit(1)

    mode = sys.argv[1]
    data = json.load(sys.stdin)

    if mode == "WorktreeCreate":
        handle_create(data)
    elif mode == "WorktreeRemove":
        handle_remove(data)
    elif mode in ["Stop", "SubagentStop"]:
        block_stop_without_commit(data)


if __name__ == "__main__":
    main()
