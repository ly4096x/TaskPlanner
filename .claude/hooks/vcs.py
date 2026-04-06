#!/usr/bin/env python3
"""PreToolUse hook: block jj/git commit when there's nothing to commit."""

import json
import os
import subprocess
import sys


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


def is_jj_repo(path):
    while path != "/":
        if os.path.isdir(os.path.join(path, ".jj")):
            return True
        path = os.path.dirname(path)
    return False


def has_jj_changes(cwd):
    """Check if jj working copy has changes."""
    result = subprocess.run(
        ["jj", "diff"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return bool(result.stdout.strip())


def has_git_changes(cwd):
    """Check if git has staged or unstaged changes."""
    # Check staged
    staged = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        capture_output=True,
        cwd=cwd,
    )
    if staged.returncode != 0:
        return True
    # Check unstaged tracked files
    unstaged = subprocess.run(
        ["git", "diff", "--quiet"],
        capture_output=True,
        cwd=cwd,
    )
    if unstaged.returncode != 0:
        return True
    # Check untracked files
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return bool(untracked.stdout.strip())


def main():
    data = json.load(sys.stdin)
    tool_name = data.get("tool_name", "")
    if tool_name != "Bash":
        return

    command = data.get("tool_input", {}).get("command", "")

    # Detect jj commit or git commit commands
    is_jj_commit = any(
        tok in command for tok in ["jj commit", "jj ci "]
    ) or command.strip().endswith("jj ci")
    is_git_commit = "git commit" in command

    if not is_jj_commit and not is_git_commit:
        return

    cwd = os.getcwd()

    if is_jj_commit:
        if not has_jj_changes(cwd):
            deny("No changes to commit. jj working copy is clean.")
    elif is_git_commit:
        if not has_git_changes(cwd):
            deny("No changes to commit. Git working tree is clean.")


if __name__ == "__main__":
    main()
