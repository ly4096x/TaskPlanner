#!/usr/bin/env python3
"""
Claude Code Stop / SubagentStop hook: require a fresh "Current time" line.

The main agent's (Stop) or a subagent's (SubagentStop) FINAL message must
contain a line of the form:

    Current time: YYYY-MM-DD HH:MM:SS

and that stated time must match the real system clock within a tolerance
window. If the line is missing, malformed, or stale, the hook blocks the
stop and asks the agent to restate it with the correct current time.

Why one script covers both events:
  * Stop and SubagentStop both put the final response text in the
    `last_assistant_message` input field, so we never parse the transcript.
    (The transcript file is written asynchronously and lags the live turn;
    for SubagentStop `transcript_path` is the MAIN session, not the subagent.)

Communication protocol (both events):
  - exit 0 with no JSON            -> allow the agent to stop
  - exit 0 + {"decision":"block"}  -> keep the agent working (reason is fed back)
The hook fails OPEN (allows stopping) on any internal error so a broken
enforcement rule never bricks a session.
"""

import json
import re
import sys
from datetime import datetime
from typing import NoReturn

# --- Configuration -----------------------------------------------------------
# The stated time may be at most this many seconds BEHIND the real clock.
# Writing the reply takes a moment, so some lag is expected and allowed.
MAX_BEHIND_SECONDS = 10
# The stated time may be at most this many seconds AHEAD of the real clock
# (small grace for clock jitter / sub-second rounding).
MAX_AHEAD_SECONDS = 2
# Timestamp format the agent must use.
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
# Regex that pulls the timestamp out of the agent's message.
TIME_PATTERN = re.compile(
    r"Current time:\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"
)


def block(reason: str) -> NoReturn:
    """Tell Claude Code to keep going instead of stopping."""
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def allow() -> NoReturn:
    """Let Claude Code (or the subagent) stop normally."""
    sys.exit(0)


def last_assistant_text_from_transcript(path: str) -> str:
    """Fallback for older Claude Code builds without last_assistant_message.

    Reads a JSONL transcript and returns the text of the most recent
    assistant message.
    """
    last_text = ""
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("type") != "assistant":
                continue
            content = entry.get("message", {}).get("content", [])
            parts = []
            if isinstance(content, str):
                parts.append(content)
            else:
                for chunk in content:
                    if isinstance(chunk, dict) and chunk.get("type") == "text":
                        parts.append(chunk.get("text", ""))
            if parts:
                last_text = "\n".join(parts)
    return last_text


def final_message_text(event: dict) -> str:
    """Return the final assistant/subagent text for this Stop/SubagentStop event."""
    # Preferred: the event carries the final text directly.
    msg = event.get("last_assistant_message")
    if isinstance(msg, str) and msg.strip():
        return msg
    if isinstance(msg, list):  # be defensive if it ever arrives as content blocks
        parts = [b.get("text", "") for b in msg
                 if isinstance(b, dict) and b.get("type") == "text"]
        if parts:
            return "\n".join(parts)

    # Fallback: read a transcript. For SubagentStop the subagent's own
    # transcript is agent_transcript_path; transcript_path is the main session.
    path = event.get("agent_transcript_path") or event.get("transcript_path")
    if path:
        try:
            return last_assistant_text_from_transcript(path)
        except Exception:
            return ""
    return ""


def main() -> None:
    raw = sys.stdin.read()
    try:
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        allow()  # Unreadable event -> fail open.

    now = datetime.now()
    now_str = now.strftime(TIME_FORMAT)

    text = final_message_text(event)

    # Validate the LAST match: a reply may quote an older "Current time:" line
    # (e.g. echoing earlier hook feedback) before stating the fresh one at the
    # end; first-match semantics would validate the stale quote and block.
    matches = TIME_PATTERN.findall(text)
    if not matches:
        block(
            "Your reply must state the current time. Run `date '+%Y-%m-%d %H:%M:%S'` and end your response with a line exactly like:\n"
            f"  Current time: {now_str}\n\n"
        )

    stated_str = matches[-1]
    try:
        stated = datetime.strptime(stated_str, TIME_FORMAT)
    except ValueError:
        block(
            f"The time you stated ('{stated_str}') is not a valid '{TIME_FORMAT}' timestamp."
        )

    delta = (now - stated).total_seconds()  # positive => stated time is in the past
    if delta > MAX_BEHIND_SECONDS or delta < -MAX_AHEAD_SECONDS:
        block(f"The time you stated ('{stated_str}') is off by {delta:.0f}s from the real system time ('{now_str}').")

    # Timestamp is present and fresh -> allow stopping.
    allow()


if __name__ == "__main__":
    main()
