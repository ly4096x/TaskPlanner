#!/usr/bin/env python3
"""VCS hooks for jj/git workspaces.

WorktreeCreate: creates a jj workspace under ~/.vcs_workspaces/<name>
WorktreeRemove: removes the jj workspace and cleans up the directory
SubagentStop:   blocks subagent if cwd has uncommitted changes

If cwd is not a jj or git repo, worktree hooks exit with code 1.
"""

import json
import os
import subprocess
import sys

WORKSPACES_DIR = os.path.expanduser("~/.vcs_workspaces")


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
        print(
            json.dumps(
                {
                    "decision": "block",
                    "reason": (
                        f"{description}\n\n"
                        "You have uncommitted work. Before stopping:\n"
                        "1. Restart your task (TaskPlanner edit <id> --status STARTED)\n"
                        "2. Commit your changes (jj commit -m '...' or git add -A && git commit -m '...')\n"
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
