#!/usr/bin/env python3
"""PreToolUse hook: block jj/git commit when there's nothing to commit."""

import json
import os
import shlex
import subprocess
import sys

_OPERATOR_CHARS = set("();<>|&")


def _is_operator(token):
    return bool(token) and all(c in _OPERATOR_CHARS for c in token)


def detect_commit_command(command):
    """Return 'jj' or 'git' if the command string actually invokes a commit.

    Tokenizes like a POSIX shell so the commit phrase inside quoted arguments
    (commit messages, task reasons, heredoc payloads) never matches — only a
    jj/git token in command position (start, or right after a shell operator)
    whose subcommand is commit/ci does. Anything unparseable or ambiguous
    fails open (returns None): this hook is a convenience guard, and a missed
    exotic invocation is harmless while a false positive blocks unrelated work.
    """
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        tokens = list(lex)
    except ValueError:
        return None

    command_pos = True
    for i, tok in enumerate(tokens):
        if _is_operator(tok):
            command_pos = True
            continue
        if not command_pos:
            continue
        name, sep, _ = tok.partition("=")
        if sep and name.isidentifier():
            continue  # VAR=value prefix keeps command position
        if tok in ("jj", "git"):
            sub = ""
            for nxt in tokens[i + 1:]:
                if _is_operator(nxt):
                    break
                if not nxt.startswith("-"):
                    sub = nxt
                    break
            if tok == "jj" and sub in ("commit", "ci"):
                return "jj"
            if tok == "git" and sub == "commit":
                return "git"
        command_pos = False
    return None


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

    vcs = detect_commit_command(command)
    if vcs is None:
        return

    cwd = os.getcwd()

    if vcs == "jj":
        if not has_jj_changes(cwd):
            deny("No changes to commit. jj working copy is clean.")
    elif vcs == "git":
        if not has_git_changes(cwd):
            deny("No changes to commit. Git working tree is clean.")


if __name__ == "__main__":
    main()
