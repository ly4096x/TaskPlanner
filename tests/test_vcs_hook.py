"""Tests for the vcs.py PreToolUse hook (client_cli/agent/hooks/vcs.py).

The hook must only gate actual jj/git commit invocations — the commit phrase
inside quoted arguments (commit messages, task reasons, heredoc payloads)
must never trigger it.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK_PATH = Path(__file__).parent.parent / "client_cli" / "agent" / "hooks" / "vcs.py"

_spec = importlib.util.spec_from_file_location("vcs_hook", HOOK_PATH)
assert _spec is not None and _spec.loader is not None
vcs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vcs)


class TestDetectCommitCommand:
    @pytest.mark.parametrize("command,expected", [
        # real invocations
        ("jj commit", "jj"),
        ("jj commit -m 'fix the thing'", "jj"),
        ("jj ci -m x", "jj"),
        ("jj ci", "jj"),
        ("cd sub && jj commit -m x", "jj"),
        ("jj st; jj commit -m x", "jj"),
        ("git commit -m x", "git"),
        ("git add -A && git commit -m 'msg'", "git"),
        ("yes | git commit", "git"),
        # phrase in quoted text must NOT match
        ('echo "jj commit"', None),
        ("echo 'git commit'", None),
        ('TaskPlanner edit 490 --status DONE --reason "fixed, see jj commit 208eb618"', None),
        ('TaskPlanner add-task --description "run jj commit -m ... && git commit"', None),
        ('grep "jj commit" file.txt', None),
        # quoted command-substitution payloads (heredoc style) must NOT match
        ('TaskPlanner add-comment 1 -m "$(cat <<EOF\nCommit with: jj commit -m msg\nEOF\n)"', None),
        # non-commit jj/git subcommands
        ("jj git push -b main", None),
        ("jj describe -m x", None),
        ("git status", None),
        ("jj cinema", None),
        # commit message itself mentioning the phrase
        ("jj commit -m 'mention git commit in message'", "jj"),
        ("echo done && jj commit -m 'jj commit inside quotes'", "jj"),
        # unparseable input fails open
        ("echo 'unbalanced", None),
    ])
    def test_detection(self, command, expected):
        assert vcs.detect_commit_command(command) == expected


class TestHookEndToEnd:
    def _run(self, command, cwd):
        data = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
        return subprocess.run(
            [sys.executable, str(HOOK_PATH)],
            input=data, capture_output=True, text=True, cwd=cwd,
        )

    def test_quoted_phrase_passes_through(self, tmp_path):
        result = self._run('echo "jj commit"', tmp_path)
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_real_commit_denied_when_nothing_to_commit(self, tmp_path):
        result = self._run("jj commit -m x", tmp_path)
        assert result.returncode == 0
        out = json.loads(result.stdout)
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
