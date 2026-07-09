"""Unit tests for the worktree-hook Stop/SubagentStop dirty-tree gate.

The hook under test is the repo's own client_cli/agent/hooks/worktree-hook.py —
never a copy deployed on the developer's machine, which drifts and would make
this suite measure the wrong file. It must:

- allow stopping when the final message carries the escape line
  "I'm stopping with uncommitted changes because: <reason>" — read from the
  event's `last_assistant_message` field, NOT the (lagging, and on
  SubagentStop wrong-session) transcript file;
- fall back to `agent_transcript_path` when the field is absent;
- block when the tree is dirty and no escape line is present;
- stay quiet for clean trees and non-repo directories.

Each test drives the hook as a subprocess exactly like Claude Code does:
JSON event on stdin, block decision (if any) as JSON on stdout.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).parent / "client_cli" / "agent" / "hooks" / "worktree-hook.py"

ESCAPE = "I'm stopping with uncommitted changes because: dirty files are not mine."

# The TaskPlanner hook reads the escape line from the transcript file only; the
# `last_assistant_message` / `agent_transcript_path` handling these tests describe
# was never ported to it (the hook is kept as is, by ruling). strict=True: the
# day it is ported, these flip to XPASS and force the markers off.
NOT_PORTED = pytest.mark.xfail(
    strict=True,
    reason="TaskPlanner's hook reads the transcript only; last_assistant_message not ported",
)


def run_hook(mode, payload):
    proc = subprocess.run(
        [sys.executable, str(HOOK), mode],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def decision(stdout):
    return json.loads(stdout).get("decision") if stdout else None


@pytest.fixture
def dirty_git_repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "wip.txt").write_text("uncommitted\n")
    return tmp_path


@pytest.fixture
def clean_git_repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


class TestDirtyTreeGate:
    def test_dirty_without_escape_blocks(self, dirty_git_repo):
        out = run_hook("Stop", {
            "cwd": str(dirty_git_repo),
            "last_assistant_message": "All done, stopping now.",
        })
        assert decision(out) == "block"

    def test_clean_repo_allows(self, clean_git_repo):
        out = run_hook("Stop", {
            "cwd": str(clean_git_repo),
            "last_assistant_message": "done",
        })
        assert out == ""

    def test_non_repo_cwd_allows(self, tmp_path):
        out = run_hook("Stop", {
            "cwd": str(tmp_path),
            "last_assistant_message": "done",
        })
        assert out == ""


class TestEscapePhrase:
    """The escape line must be honored from `last_assistant_message` — the
    live final text of the agent that is stopping."""

    @NOT_PORTED
    def test_escape_first_line_allows(self, dirty_git_repo):
        out = run_hook("Stop", {
            "cwd": str(dirty_git_repo),
            "last_assistant_message": ESCAPE,
        })
        assert out == ""

    @NOT_PORTED
    def test_escape_mid_message_line_allows(self, dirty_git_repo):
        out = run_hook("Stop", {
            "cwd": str(dirty_git_repo),
            "last_assistant_message": f"Findings posted.\n{ESCAPE}",
        })
        assert out == ""

    @NOT_PORTED
    def test_curly_apostrophe_allows(self, dirty_git_repo):
        out = run_hook("Stop", {
            "cwd": str(dirty_git_repo),
            "last_assistant_message": (
                "I’m stopping with uncommitted changes because: read-only run."
            ),
        })
        assert out == ""

    def test_reason_required(self, dirty_git_repo):
        out = run_hook("Stop", {
            "cwd": str(dirty_git_repo),
            "last_assistant_message": "I'm stopping with uncommitted changes because:",
        })
        assert decision(out) == "block"

    def test_quoted_mid_line_phrase_still_blocks(self, dirty_git_repo):
        # Line-anchored: merely discussing the phrase must not bypass the gate.
        out = run_hook("Stop", {
            "cwd": str(dirty_git_repo),
            "last_assistant_message": (
                f'The hook offers "{ESCAPE}" as an opt-out.'
            ),
        })
        assert decision(out) == "block"


class TestSubagentStop:
    @NOT_PORTED
    def test_escape_via_last_assistant_message_allows(self, dirty_git_repo):
        # Regression: the subagent's escape line lives in its own
        # final message; transcript_path points at the MAIN session and must
        # not be consulted when the field is present.
        out = run_hook("SubagentStop", {
            "cwd": str(dirty_git_repo),
            "transcript_path": "/nonexistent/main-session.jsonl",
            "last_assistant_message": f"Review done.\n{ESCAPE}",
        })
        assert out == ""

    @NOT_PORTED
    def test_fallback_reads_agent_transcript(self, dirty_git_repo, tmp_path):
        transcript = tmp_path / "subagent.jsonl"
        transcript.write_text(json.dumps({
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": ESCAPE}]},
        }) + "\n")
        out = run_hook("SubagentStop", {
            "cwd": str(dirty_git_repo),
            "transcript_path": "/nonexistent/main-session.jsonl",
            "agent_transcript_path": str(transcript),
        })
        assert out == ""

    def test_dirty_without_escape_blocks(self, dirty_git_repo):
        out = run_hook("SubagentStop", {
            "cwd": str(dirty_git_repo),
            "last_assistant_message": "Review done.",
        })
        assert decision(out) == "block"
